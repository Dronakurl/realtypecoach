"""Storage management for RealTypeCoach - Database adapter facade.

This module provides the main Storage class which acts as a facade over
different database backends (SQLite, PostgreSQL) using the adapter pattern.
"""

import logging
import os
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from core.database_adapter import AdapterError, DatabaseAdapter
from core.dictionary import Dictionary
from core.dictionary_config import DictionaryConfig
from core.models import (
    BurstTimeSeries,
    DailySummaryDB,
    KeyPerformance,
    TypingTimeDataPoint,
    WordInfo,
    WordStatisticsLite,
)
from core.word_detector import WordDetector
from utils.config import Config
from utils.crypto import CryptoManager

if TYPE_CHECKING:
    from core.analyzer import Analyzer

log = logging.getLogger("realtypecoach.storage")


class Storage:
    """Database storage facade for typing data.

    This class delegates all database operations to a database adapter,
    allowing for pluggable backends (SQLite, PostgreSQL, etc.).
    """

    def __init__(
        self,
        db_path: Path,
        config: Config,
        word_boundary_timeout_ms: int = 1000,
        dictionary_config: DictionaryConfig | None = None,
        ignore_file_path: Path | None = None,
    ):
        """Initialize storage with database adapter.

        Args:
            db_path: Path to SQLite database file (for SQLite adapter)
            config: Config instance for accessing settings (required)
            word_boundary_timeout_ms: Max pause between letters before word splits (ms)
            dictionary_config: Dictionary configuration object
            ignore_file_path: Optional path to ignorewords.txt file

        Raises:
            ValueError: If word_boundary_timeout_ms is not positive or config is None
        """
        if word_boundary_timeout_ms <= 0:
            raise ValueError("word_boundary_timeout_ms must be positive")
        if config is None:
            raise ValueError("config parameter is required")
        self.db_path = db_path
        self.word_boundary_timeout_ms = word_boundary_timeout_ms
        self.config = config

        # Initialize crypto manager
        self.crypto = CryptoManager(db_path)

        # Initialize database adapter based on configuration
        self.adapter = self._create_adapter()

        # Initialize hash manager after encryption is available
        self.hash_manager = None
        try:
            from core.hash_manager import HashManager

            encryption_key = self.crypto.get_key()
            if encryption_key:
                self.hash_manager = HashManager(encryption_key)
                log.info("HashManager initialized for ignored words")
            else:
                log.warning("No encryption key available, ignored words feature disabled")
        except Exception as e:
            log.warning(f"Failed to initialize HashManager: {e}")

        # Migrate legacy ignorewords.txt if it exists
        if self.hash_manager:
            self._migrate_ignorewords_file()

        # Initialize non-database components
        dict_config = dictionary_config or DictionaryConfig()
        self.dictionary = Dictionary(dict_config, ignore_file_path, storage=self)
        self.word_detector = WordDetector(
            word_boundary_timeout_ms=word_boundary_timeout_ms, min_word_length=3
        )

        # Reference to analyzer (set later)
        self._analyzer: Analyzer | None = None

    def _create_adapter(self) -> DatabaseAdapter:
        """Create and initialize SQLite database adapter.

        Local SQLite is always used as the primary storage.
        PostgreSQL is only used for optional remote sync.

        Returns:
            Initialized SQLite adapter

        Raises:
            AdapterError: If adapter creation or initialization fails
        """
        from core.sqlite_adapter import SQLiteAdapter

        log.info("Using SQLite database adapter as primary storage")
        adapter = SQLiteAdapter(db_path=self.db_path, crypto=self.crypto)
        adapter.initialize()
        return adapter

    def _get_postgres_password(self) -> str:
        """Get PostgreSQL password from keyring or secret file.

        Returns:
            Password from keyring or secret file

        Raises:
            AdapterError: If password not found in either location
        """
        # Try keyring first
        password = self.crypto.get_postgres_password()
        if password:
            return password

        # Fallback to secret file (for non-interactive environments)
        # Look in project directory (where this file is located)
        from importlib.util import find_spec

        core_spec = find_spec("core.storage")
        if core_spec and core_spec.origin:
            project_dir = Path(core_spec.origin).parent.parent
        else:
            # Fallback to current directory
            project_dir = Path.cwd()
        secret_file = project_dir / "dronakurl.postgres.secret"
        if secret_file.exists():
            try:
                with open(secret_file) as f:
                    password = f.read().strip()
                if password:
                    log.info("Using PostgreSQL password from secret file")
                    return password
            except Exception as e:
                log.warning(f"Failed to read secret file: {e}")

        raise AdapterError(
            "PostgreSQL password not found in keyring or secret file. "
            "Please set it in the database settings."
        )

    def set_analyzer(self, analyzer: "Analyzer") -> None:
        """Set reference to analyzer (needed for word processing).

        Args:
            analyzer: Analyzer instance
        """
        self._analyzer = analyzer

    @contextmanager
    def _get_connection(self):
        """Get a database connection from the adapter.

        This method provides compatibility with existing code that uses
        direct database connections for word processing.

        Yields:
            Database connection
        """
        with self.adapter.get_connection() as conn:
            yield conn

    # ========== Language/Word Detection Methods (Non-Database) ==========

    def _get_language_from_layout(self, layout: str) -> str | None:
        """Get language code from layout identifier.

        Also checks loaded dictionaries to ensure language is available.
        If mapped language is not loaded, returns None to allow
        validation against all loaded dictionaries.

        Args:
            layout: Keyboard layout (e.g., 'us', 'de', 'gb')

        Returns:
            Language code ('en', 'de') or None
        """
        layout_map = {
            # English layouts
            "us": "en",
            "usa": "en",
            "gb": "en",
            "uk": "en",
            "ca": "en",
            "au": "en",
            "nz": "en",
            # German layouts
            "de": "de",
            "at": "de",
            "ch": "de",
            # French layouts
            "fr": "fr",
            "be": "fr",
            # Spanish layouts
            "es": "es",
            "latam": "es",
            # Italian layouts
            "it": "it",
            # Portuguese layouts
            "pt": "pt",
            "br": "pt",
            # Dutch layouts
            "nl": "nl",
            # Polish layouts
            "pl": "pl",
            # Russian layouts
            "ru": "ru",
        }

        layout_lower = layout.lower()
        language = layout_map.get(layout_lower)

        # Get loaded languages
        loaded_languages = self.dictionary.get_loaded_languages()

        # If no dictionaries are loaded, return None to validate against all
        if language and not loaded_languages:
            return None

        # If the mapped language is not loaded, return None to validate against all
        if language and language not in loaded_languages:
            return None

        # If multiple dictionaries are loaded, check all of them
        if loaded_languages and len(loaded_languages) > 1:
            return None

        return language

    def _store_word_from_state(self, conn, word_info: WordInfo) -> None:
        """Store word from WordDetector state with editing metadata.

        Args:
            conn: Database connection
            word_info: Word info from WordDetector
        """
        word = word_info.word
        layout = word_info.layout
        total_duration_ms = word_info.total_duration_ms
        editing_time_ms = word_info.editing_time_ms
        backspace_count = word_info.backspace_count
        num_letters = word_info.num_letters

        # Use adapter to store word statistics
        self.adapter.update_word_statistics(
            word=word,
            layout=layout,
            duration_ms=total_duration_ms,
            num_letters=num_letters,
            backspace_count=backspace_count,
            editing_time_ms=editing_time_ms,
        )

        # Update key statistics for keystrokes in this valid dictionary word
        self._process_keystroke_timings(conn, word_info)

    def _process_keystroke_timings(self, conn, word_info: WordInfo) -> None:
        """Update key statistics from keystrokes in a valid dictionary word.

        Only processes letter keystrokes that are part of valid dictionary words.
        Only includes keystrokes that are within bursts (gaps <= BURST_TIMEOUT_MS).

        Args:
            conn: Database connection to use
            word_info: Word info from WordDetector with keystroke list
        """
        from core.analyzer import BURST_TIMEOUT_MS

        letter_keystrokes = [
            ks for ks in word_info.keystrokes if ks.type == "letter" and ks.keycode is not None
        ]

        for i in range(len(letter_keystrokes)):
            current = letter_keystrokes[i]

            if i > 0:
                prev = letter_keystrokes[i - 1]
                time_between = current.time - prev.time

                # Only count if within burst timeout
                if time_between <= BURST_TIMEOUT_MS:
                    # Update key statistics inline
                    self._update_key_statistics_inline(
                        conn,
                        int(current.keycode),
                        current.key,
                        word_info.layout,
                        time_between,
                    )

    def _update_key_statistics_inline(
        self,
        conn,
        keycode: int,
        key_name: str,
        layout: str,
        press_time_ms: float,
    ) -> None:
        """Update statistics for a key using an existing connection.

        Args:
            conn: Database connection to use
            keycode: Linux evdev keycode
            key_name: Human-readable key name
            layout: Keyboard layout identifier
            press_time_ms: Time since last press
        """
        # Delegate to adapter
        self.adapter.update_key_statistics(keycode, key_name, layout, press_time_ms)

    # ========== Database Operation Delegation ==========

    # Burst Operations

    def store_burst(self, burst, avg_wpm: float) -> None:
        """Store a burst.

        Args:
            burst: Burst object with timing and keystroke data
            avg_wpm: Average WPM during burst (calculated from net keystrokes)
        """
        self.adapter.store_burst(
            start_time=burst.start_time_ms,
            end_time=burst.end_time_ms,
            key_count=burst.key_count,
            backspace_count=burst.backspace_count,
            net_key_count=burst.net_key_count,
            duration_ms=burst.duration_ms,
            avg_wpm=avg_wpm,
            qualifies_for_high_score=burst.qualifies_for_high_score,
        )

    def get_bursts_for_timeseries(self, start_ms: int, end_ms: int) -> list[BurstTimeSeries]:
        """Get burst data for time-series graph.

        Args:
            start_ms: Start timestamp (milliseconds since epoch)
            end_ms: End timestamp (milliseconds since epoch)

        Returns:
            List of BurstTimeSeries models
        """
        return self.adapter.get_bursts_for_timeseries(start_ms, end_ms)

    def get_burst_wpm_histogram(self, bin_count: int = 50) -> list[tuple]:
        """Get burst WPM distribution as histogram data.

        Args:
            bin_count: Number of histogram bins (10-200)

        Returns:
            List of (bin_center_wpm, count) tuples ordered by bin_center_wpm
        """
        return self.adapter.get_burst_wpm_histogram(bin_count)

    def get_recent_bursts(self, limit: int = 3) -> list[tuple]:
        """Get the most recent bursts.

        Args:
            limit: Maximum number of bursts to return

        Returns:
            List of tuples: (id, wpm, net_chars, duration_ms, backspaces, start_time_ms, time_str)
        """
        return self.adapter.get_recent_bursts(limit)

    def get_burst_duration_stats_ms(self) -> tuple[int, int, int]:
        """Get burst duration statistics across all bursts.

        Returns:
            Tuple of (average_ms, min_ms, max_ms)
        """
        return self.adapter.get_burst_duration_stats_ms()

    def get_burst_stats_for_date_range(self, start_ms: int, end_ms: int) -> tuple[int, int]:
        """Get burst statistics for a date range.

        Args:
            start_ms: Start timestamp (milliseconds since epoch)
            end_ms: End timestamp (milliseconds since epoch)

        Returns:
            Tuple of (total_keystrokes, total_bursts)
        """
        return self.adapter.get_burst_stats_for_date_range(start_ms, end_ms)

    def get_burst_wpms_for_threshold(self, start_ms: int, min_duration_ms: int) -> list[float]:
        """Get burst WPMS for threshold calculation.

        Args:
            start_ms: Start timestamp (milliseconds since epoch)
            min_duration_ms: Minimum burst duration in milliseconds

        Returns:
            List of WPM values (sorted ascending)
        """
        return self.adapter.get_burst_wpms_for_threshold(start_ms, min_duration_ms)

    def get_total_burst_duration(self, start_ms: int, end_ms: int) -> int:
        """Get total burst duration for a date range.

        Args:
            start_ms: Start timestamp (milliseconds since epoch)
            end_ms: End timestamp (milliseconds since epoch)

        Returns:
            Total duration in milliseconds
        """
        return self.adapter.get_total_burst_duration(start_ms, end_ms)

    def get_typing_time_by_granularity(
        self,
        granularity: str,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 90,
    ) -> list[TypingTimeDataPoint]:
        """Get typing time aggregated by time granularity.

        Args:
            granularity: Time period granularity ("day", "week", "month", "quarter")
            start_date: Optional start date (defaults to limit periods ago)
            end_date: Optional end date (defaults to now)
            limit: Maximum number of periods to return

        Returns:
            List of TypingTimeDataPoint models ordered by period_start
        """
        return self.adapter.get_typing_time_by_granularity(granularity, start_date, end_date, limit)

    # Key Statistics Operations

    def update_key_statistics(
        self, keycode: int, key_name: str, layout: str, press_time_ms: float
    ) -> None:
        """Update statistics for a key.

        Args:
            keycode: Linux evdev keycode
            key_name: Human-readable key name
            layout: Keyboard layout identifier
            press_time_ms: Time since last press
        """
        self.adapter.update_key_statistics(keycode, key_name, layout, press_time_ms)

    def get_slowest_keys(self, limit: int = 10, layout: str | None = None) -> list[KeyPerformance]:
        """Get slowest keys (highest average press time).

        Args:
            limit: Maximum number of keys to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of KeyPerformance models
        """
        return self.adapter.get_slowest_keys(limit, layout)

    def get_fastest_keys(self, limit: int = 10, layout: str | None = None) -> list[KeyPerformance]:
        """Get fastest keys (lowest average press time).

        Args:
            limit: Maximum number of keys to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of KeyPerformance models
        """
        return self.adapter.get_fastest_keys(limit, layout)

    # Word Statistics Operations

    def update_word_statistics(
        self,
        word: str,
        layout: str,
        duration_ms: int,
        num_letters: int,
        backspace_count: int = 0,
        editing_time_ms: int = 0,
    ) -> None:
        """Update statistics for a word with running average.

        Args:
            word: The word that was typed
            layout: Keyboard layout identifier
            duration_ms: Time taken to type the word (ms)
            num_letters: Number of letters in the word
            backspace_count: Number of backspaces used for this word
            editing_time_ms: Time spent editing with backspace (ms)
        """
        self.adapter.update_word_statistics(
            word, layout, duration_ms, num_letters, backspace_count, editing_time_ms
        )

    def get_slowest_words(
        self, limit: int = 10, layout: str | None = None
    ) -> list[WordStatisticsLite]:
        """Get slowest words (highest average time per letter).

        Args:
            limit: Maximum number of words to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of WordStatisticsLite models
        """
        return self.adapter.get_slowest_words(limit, layout)

    def get_fastest_words(
        self, limit: int = 10, layout: str | None = None
    ) -> list[WordStatisticsLite]:
        """Get fastest words (lowest average time per letter).

        Args:
            limit: Maximum number of words to return
            layout: Filter by layout (None for all layouts)

        Returns:
            List of WordStatisticsLite models
        """
        return self.adapter.get_fastest_words(limit, layout)

    # High Score Operations

    def store_high_score(self, date: str, wpm: float, duration_ms: int, key_count: int) -> None:
        """Store a high score for a date.

        Args:
            date: Date string (YYYY-MM-DD)
            wpm: Words per minute achieved
            duration_ms: Burst duration in milliseconds
            key_count: Number of keystrokes
        """
        self.adapter.store_high_score(date, wpm, duration_ms, key_count)

    def get_today_high_score(self, date: str) -> float | None:
        """Get today's highest WPM.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            WPM or None if no bursts today
        """
        return self.adapter.get_today_high_score(date)

    def get_all_time_high_score(self) -> float | None:
        """Get all-time highest WPM.

        Returns:
            WPM or None if no bursts recorded
        """
        return self.adapter.get_all_time_high_score()

    # Daily Summary Operations

    def update_daily_summary(
        self,
        date: str,
        total_keystrokes: int,
        total_bursts: int,
        avg_wpm: float,
        slowest_keycode: int,
        slowest_key_name: str,
        total_typing_sec: int,
    ) -> None:
        """Update daily summary.

        Args:
            date: Date string (YYYY-MM-DD)
            total_keystrokes: Total keystrokes today
            total_bursts: Total bursts today
            avg_wpm: Average WPM today
            slowest_keycode: Slowest keycode today
            slowest_key_name: Slowest key name today
            total_typing_sec: Total typing time today (seconds)
        """
        self.adapter.update_daily_summary(
            date,
            total_keystrokes,
            total_bursts,
            avg_wpm,
            slowest_keycode,
            slowest_key_name,
            total_typing_sec,
        )

    def get_daily_summary(self, date: str) -> DailySummaryDB | None:
        """Get daily summary for a date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            DailySummaryDB model or None if not found
        """
        return self.adapter.get_daily_summary(date)

    def mark_summary_sent(self, date: str) -> None:
        """Mark daily summary as sent.

        Args:
            date: Date string (YYYY-MM-DD)
        """
        self.adapter.mark_summary_sent(date)

    # All-Time Statistics

    def get_all_time_typing_time(self, exclude_today: str = None) -> int:
        """Get all-time total typing time from adapter.

        Args:
            exclude_today: Optional date string (YYYY-MM-DD) to exclude from sum.

        Returns:
            Total typing time in seconds
        """
        return self.adapter.get_all_time_typing_time(exclude_today)

    def get_today_typing_time(self, date: str) -> int:
        """Get typing time for a specific date.

        Args:
            date: Date string (YYYY-MM-DD)

        Returns:
            Typing time in milliseconds for the given date
        """
        return self.adapter.get_today_typing_time(date)

    def get_all_time_keystrokes_and_bursts(self, exclude_today: str = None) -> tuple[int, int]:
        """Get all-time total keystrokes and bursts from adapter.

        Args:
            exclude_today: Optional date string (YYYY-MM-DD) to exclude from sum.

        Returns:
            Tuple of (total_keystrokes, total_bursts)
        """
        return self.adapter.get_all_time_keystrokes_and_bursts(exclude_today)

    def get_average_burst_wpm(self) -> float | None:
        """Get long-term average WPM across all recorded bursts.

        Returns:
            Average WPM or None if no bursts recorded
        """
        return self.adapter.get_average_burst_wpm()

    def get_all_burst_wpms_ordered(self) -> list[float]:
        """Get all burst WPM values ordered by time.

        Returns:
            List of WPM values ordered by start_time
        """
        return self.adapter.get_all_burst_wpms_ordered()

    # Data Management

    def delete_old_data(self, retention_days: int) -> None:
        """Delete data older than retention period.

        Args:
            retention_days: Number of days to keep, or -1 to keep forever
        """
        self.adapter.delete_old_data(retention_days)

    def clear_database(self) -> None:
        """Clear all data from database."""
        self.adapter.clear_database()

    def export_to_csv(self, file_path, start_date: str) -> int:
        """Export data to CSV file.

        Args:
            file_path: Path to output CSV file
            start_date: Start date for export (YYYY-MM-DD)

        Returns:
            Number of rows exported
        """
        return self.adapter.export_to_csv(file_path, start_date)

    def clean_ignored_words(self) -> int:
        """Delete word statistics for words in the ignore list.

        Returns:
            Number of rows deleted
        """
        ignored_words = list(self.dictionary._ignored_words)
        return self.adapter.delete_words_by_list(ignored_words)

    # ========== Ignored Words Operations ==========

    def add_ignored_word(self, word: str) -> tuple[bool, int]:
        """Add word to ignored list, delete statistics, return (success, deleted_count).

        Args:
            word: The word to ignore (case-insensitive)

        Returns:
            Tuple of (success: bool, deleted_count: int)
            - success: True if word was added, False if already ignored or hash_manager unavailable
            - deleted_count: Number of statistics records deleted for this word

        Example:
            >>> success, deleted = storage.add_ignored_word("example")
            >>> if success:
            ...     print(f"Added 'example' to ignored list, deleted {deleted} statistics")
        """
        import time

        if self.hash_manager is None:
            log.warning("Cannot add ignored word: hash_manager not available")
            return (False, 0)

        # Hash the word
        word_hash = self.hash_manager.hash_word(word)

        # Check if already ignored
        if self.adapter.is_word_ignored(word_hash):
            return (False, 0)

        # Add to ignored list
        timestamp_ms = int(time.time() * 1000)
        added = self.adapter.add_ignored_word(word_hash, timestamp_ms)

        if not added:
            return (False, 0)

        # Delete statistics for this word (local)
        deleted_count = self.adapter.delete_words_by_list([word.lower()])

        log.info(
            f"Added word to ignored list (hash: {word_hash[:16]}...), deleted {deleted_count} statistics"
        )
        return (True, deleted_count)

    def is_word_ignored(self, word: str) -> bool:
        """Check if word is in ignored list.

        Args:
            word: The word to check (case-insensitive)

        Returns:
            True if word is ignored, False otherwise
        """
        if self.hash_manager is None:
            return False
        word_hash = self.hash_manager.hash_word(word)
        return self.adapter.is_word_ignored(word_hash)

    def _migrate_ignorewords_file(self) -> None:
        """Migrate legacy ignorewords.txt to new system and remove file.

        Reads words from the legacy ignorewords.txt file and adds them to the
        new hash-based ignored words system. The file is then renamed to
        prevent re-migration.
        """
        config_dir = (
            Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "realtypecoach"
        )
        ignore_file = config_dir / "ignorewords.txt"
        if not ignore_file.exists():
            return

        # Read words from file
        with open(ignore_file) as f:
            words = [
                line.strip().lower() for line in f if line.strip() and not line.startswith("#")
            ]

        if not words:
            return

        # Migrate to new system
        migrated_count = 0
        for word in words:
            if self.add_ignored_word(word)[0]:
                migrated_count += 1

        log.info(f"Migrated {migrated_count} words from ignorewords.txt")

        # Rename file to prevent re-migration and indicate migration completed
        backup_file = ignore_file.with_suffix(".txt.migrated")
        ignore_file.rename(backup_file)
        log.info(f"Renamed ignorewords.txt to {backup_file.name}")

    def merge_with_remote(self) -> dict:
        """Manually sync/merge local SQLite with remote PostgreSQL.

        Performs bidirectional smart merge between local and remote databases:
        - Pushes local changes to PostgreSQL (with encryption)
        - Pulls remote changes from PostgreSQL (with decryption)
        - Merges conflicts intelligently without data loss

        Returns:
            Sync result dict with:
                - success: True if sync succeeded
                - pushed: Number of records pushed to remote
                - pulled: Number of records pulled from remote
                - conflicts_resolved: Number of conflicts merged
                - error: Error message if failed
                - duration_ms: Sync duration in milliseconds

        Example:
            >>> result = storage.merge_with_remote()
            >>> if result["success"]:
            ...     print(f"Synced: {result['pushed']} pushed, {result['pulled']} pulled")
        """
        # Check if PostgreSQL sync is enabled
        postgres_sync_enabled = self.config.get_bool("postgres_sync_enabled", False)
        if not postgres_sync_enabled:
            return {
                "success": False,
                "error": "Remote sync not enabled. Please enable PostgreSQL sync in settings.",
            }

        # Import SyncManager
        from core.sync_manager import SyncManager
        from core.user_manager import UserManager

        try:
            # Get current user and encryption key
            user_manager = UserManager(self.db_path, self.config)
            user = user_manager.get_or_create_current_user()
            encryption_key = user_manager.get_encryption_key()

            # Initialize PostgreSQL adapter for sync
            from core.postgres_adapter import PostgreSQLAdapter

            host = self.config.get("postgres_host", "")
            port = self.config.get_int("postgres_port", 5432)
            database = self.config.get("postgres_database", "realtypecoach")
            postgres_user = self.config.get("postgres_user", "")
            sslmode = self.config.get("postgres_sslmode", "require")

            password = self._get_postgres_password()

            if not all([host, database, postgres_user, password]):
                return {
                    "success": False,
                    "error": "PostgreSQL configuration incomplete. Please set host, database, user, and password in settings.",
                }

            # Initialize encryption
            from core.data_encryption import DataEncryption

            encryption = DataEncryption(encryption_key)

            # Create remote adapter
            remote_adapter = PostgreSQLAdapter(
                host=host,
                port=port,
                database=database,
                user=postgres_user,
                password=password,
                sslmode=sslmode,
                user_id=user.user_id,
                encryption_key=encryption_key,
            )
            remote_adapter.initialize()
            log.info(
                f"Created PostgreSQL remote adapter for sync, type: {type(remote_adapter).__name__}"
            )

            # Initialize sync manager
            # Always use SQLite as local adapter for sync, regardless of main storage backend
            from core.sqlite_adapter import SQLiteAdapter

            # Ensure SQLite database exists for sync
            if not self.db_path.exists():
                return {
                    "success": False,
                    "error": "Local SQLite database not found.",
                }

            local_adapter = SQLiteAdapter(db_path=self.db_path, crypto=self.crypto)
            local_adapter.initialize()
            log.info(f"Created SQLite local adapter for sync, type: {type(local_adapter).__name__}")

            sync_mgr = SyncManager(
                local_adapter=local_adapter,
                remote_adapter=remote_adapter,
                encryption=encryption,
                user_id=user.user_id,
            )
            log.info(f"SyncManager local adapter type: {type(sync_mgr.local).__name__}")

            # Perform sync
            result = sync_mgr.bidirectional_merge()

            # Update last sync timestamp
            user_manager.update_last_sync()

            # Close adapters
            local_adapter.close()
            remote_adapter.close()

            return {
                "success": result.success,
                "pushed": result.pushed,
                "pulled": result.pulled,
                "conflicts_resolved": result.conflicts_resolved,
                "error": result.error,
                "duration_ms": result.duration_ms,
            }

        except Exception as e:
            log.error(f"Sync failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "pushed": 0,
                "pulled": 0,
                "conflicts_resolved": 0,
                "duration_ms": 0,
            }

    def close(self) -> None:
        """Close the database adapter and cleanup resources."""
        log.info("Closing storage adapter...")
        self.adapter.close()
        log.info("Storage closed successfully")
