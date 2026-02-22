"""Bidirectional smart merge between SQLite and PostgreSQL.

Implements smart merge logic for syncing typing history between
local SQLite and remote PostgreSQL databases with support for:
- Push local changes to PostgreSQL (with encryption)
- Pull remote changes from PostgreSQL (with decryption)
- Smart merge for conflicts (no data loss)
- Duplicate detection and handling
"""

import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.data_encryption import DataEncryption
    from core.database_adapter import DatabaseAdapter

log = logging.getLogger("realtypecoach.sync_manager")


@dataclass
class TableSyncStats:
    """Per-table sync statistics."""

    pushed: int = 0
    pulled: int = 0
    merged: int = 0


@dataclass
class SyncResult:
    """Result of a sync operation."""

    success: bool
    pushed: int = 0
    pulled: int = 0
    merged: int = 0
    error: str | None = None
    duration_ms: int = 0
    table_breakdown: dict[str, TableSyncStats] = field(default_factory=dict)


class SyncManager:
    """Bidirectional smart merge between SQLite and PostgreSQL.

    Conflict resolution strategies:
    - bursts: Insert only (check by id + start_time to avoid duplicates)
    - statistics: Take record with more presses (max, not sum)
    - word_statistics: Take record with more observations (max, not sum)
    - high_scores: Keep higher WPM for same date
    - daily_summaries: Take more complete record (max keystrokes)
    """

    # Tables to sync in order
    SYNC_TABLES = [
        "bursts",
        "statistics",
        "digraph_statistics",
        "word_statistics",
        "high_scores",
        "daily_summaries",
        "ignored_words",
        "settings",
        "llm_prompts",
    ]

    def __init__(
        self,
        local_adapter: "DatabaseAdapter",
        remote_adapter: "DatabaseAdapter",
        encryption: "DataEncryption | None" = None,
        user_id: str = "",
        is_name_callback: "callable | None" = None,
    ):
        """Initialize sync manager.

        Args:
            local_adapter: Local SQLite database adapter
            remote_adapter: Remote PostgreSQL database adapter
            encryption: DataEncryption instance for client-side encryption
            user_id: User UUID for filtering data
            is_name_callback: Optional callback to check if a word is a name.
                              If provided, filters out names during remote data pull.
        """
        self.local = local_adapter
        self.remote = remote_adapter
        self.encryption = encryption
        self.user_id = user_id
        self.is_name_callback = is_name_callback

    def _validate_remote_connection(self) -> bool:
        """Validate remote PostgreSQL connection is healthy before sync.

        Returns:
            True if remote is reachable and schema-compatible, False otherwise

        Raises:
            AdapterError: If remote connection fails
        """
        try:
            # Test connection with simple query
            with self.remote.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()

            # Verify critical tables exist
            required_tables = ["bursts", "statistics", "word_statistics",
                              "digraph_statistics", "high_scores", "daily_summaries"]
            for table in required_tables:
                cursor.execute(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = %s)",
                    (table,)
                )
                if not cursor.fetchone()[0]:
                    raise AdapterError(f"Remote missing required table: {table}")

            log.info("Remote connection validated successfully")
            return True

        except Exception as e:
            log.error(f"Remote validation failed: {e}")
            raise AdapterError(f"Remote database unavailable: {e}") from e

    def _validate_schema_compatibility(self, table: str) -> None:
        """Verify local and remote schemas are compatible for sync.

        Args:
            table: Table name to validate

        Raises:
            AdapterError: If schemas are incompatible
        """
        # Check that column sets match
        local_columns = self._get_table_columns(self.local, table)
        remote_columns = self._get_table_columns(self.remote, table)

        local_set = set(local_columns)
        remote_set = set(remote_columns)

        # Remote should have all local columns (may have extras like user_id)
        missing = local_set - remote_set
        if missing:
            raise AdapterError(
                f"Schema mismatch for {table}: remote missing columns {missing}"
            )

        log.debug(f"Schema compatibility verified for {table}")

    def _get_table_columns(self, adapter: "DatabaseAdapter", table: str) -> list[str]:
        """Get column names for a table.

        Args:
            adapter: Database adapter to query
            table: Table name

        Returns:
            List of column names
        """
        with adapter.get_connection() as conn:
            cursor = conn.cursor()

            # Use PRAGMA for SQLite, information_schema for PostgreSQL
            from core.sqlite_adapter import SQLiteAdapter
            if isinstance(adapter, SQLiteAdapter):
                cursor.execute(f"PRAGMA table_info({table})")
                return [row[1] for row in cursor.fetchall()]
            else:
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = %s",
                    (table,)
                )
                return [row[0] for row in cursor.fetchall()]

    def bidirectional_merge(self) -> SyncResult:
        """Perform bidirectional merge between local and remote databases.

        Returns:
            SyncResult with sync statistics

        Raises:
            AdapterError: If sync operation fails
        """
        start_time = time.time()
        result = SyncResult(success=True)

        log.info(f"Starting bidirectional merge for user {self.user_id}")

        try:
            # Validate remote connection before starting sync
            self._validate_remote_connection()

            # Sync each table
            for table in self.SYNC_TABLES:
                # Validate schema compatibility for this table
                self._validate_schema_compatibility(table)

                pushed, pulled, conflicts = self._sync_table(table)
                result.pushed += pushed
                result.pulled += pulled
                result.merged += conflicts

                # Store per-table breakdown
                result.table_breakdown[table] = TableSyncStats(
                    pushed=pushed, pulled=pulled, merged=conflicts
                )
                log.info(f"Synced {table}: pushed={pushed}, pulled={pulled}, merged={conflicts}")

            result.success = True

        except Exception as e:
            log.error(f"Sync failed: {e}")
            result.success = False
            result.error = str(e)

            # Add helpful context for common failures
            error_str = str(e).lower()
            if "connection" in error_str or "timeout" in error_str:
                result.error += "\n\nHint: Check your internet connection and PostgreSQL server status."
            elif "schema" in error_str or "column" in error_str:
                result.error += "\n\nHint: Local and remote databases may be at different versions. Run migrations on both."
            elif "authentication" in error_str or "password" in error_str:
                result.error += "\n\nHint: Check your PostgreSQL credentials in settings."

        result.duration_ms = int((time.time() - start_time) * 1000)
        return result

    def _sync_table(self, table: str) -> tuple[int, int, int]:
        """Sync a single table bidirectionally.

        Args:
            table: Table name to sync

        Returns:
            Tuple of (pushed, pulled, merged)
        """
        # Get local and remote data
        local_data = self._get_local_data(table)
        remote_data = self._get_remote_data(table)

        log.debug(f"Table {table}: local={len(local_data)}, remote={len(remote_data)} records")

        # Build hash-based lookups for O(1) matching
        local_lookup = self._build_lookup_dict(table, local_data)
        remote_lookup = self._build_lookup_dict(table, remote_data)

        # Collect records to process
        to_push = []
        to_pull = []
        conflicts = []

        # Find records to push (local not in remote)
        for record in local_data:
            key = self._get_record_key(table, record)
            if key not in remote_lookup:
                to_push.append(record)

        # Find records to pull and conflicts
        for record in remote_data:
            key = self._get_record_key(table, record)
            if key in local_lookup:
                local_record = local_lookup[key]
                # Only resolve conflict if records actually differ
                if not self._records_equal(table, local_record, record):
                    resolved = self._resolve_conflict(table, local_record, record)
                    if resolved is not None:
                        conflicts.append(resolved)
            else:
                to_pull.append(record)

        # Phase 2: Commit with rollback on failure
        pushed = pulled = resolved = 0
        try:
            pushed = self._batch_push(table, to_push)
            pulled = self._batch_pull(table, to_pull)
            resolved = self._batch_update_local(table, conflicts)

            # Critical: ensure remote update succeeds
            # Also update remote with merged values so both sides are in sync
            remote_resolved = self._batch_update_remote(table, conflicts)
            if remote_resolved != resolved:
                raise RuntimeError(
                    f"Remote update count mismatch for {table}: expected {resolved}, got {remote_resolved}"
                )

            return pushed, pulled, resolved
        except Exception as e:
            log.error(f"Sync failed for {table}, partial changes may exist: {e}")
            raise

    def _build_lookup_dict(self, table: str, records: list[dict]) -> dict:
        """Build hash-based lookup dictionary for O(1) record matching.

        Args:
            table: Table name
            records: List of record dictionaries

        Returns:
            Dictionary mapping record keys to records
        """
        lookup = {}
        for record in records:
            key = self._get_record_key(table, record)
            lookup[key] = record
        return lookup

    def _get_record_key(self, table: str, record: dict) -> tuple | str | int:
        """Get unique key for record based on table type.

        Args:
            table: Table name
            record: Record dictionary

        Returns:
            Unique key for the record (can be tuple, string, or int)
        """
        if table == "bursts":
            return record.get("start_time")
        elif table == "statistics":
            return (record.get("keycode"), record.get("layout"))
        elif table == "digraph_statistics":
            return (record.get("first_keycode"), record.get("second_keycode"), record.get("layout"))
        elif table == "word_statistics":
            return (record.get("word"), record.get("layout"))
        elif table == "high_scores":
            # Use timestamp as key (unique per user due to UNIQUE constraint in migrations)
            # ID differs between local and remote due to auto-increment
            return record.get("timestamp")
        elif table == "daily_summaries":
            return record.get("date")
        elif table == "ignored_words":
            return record.get("word_hash")
        elif table == "settings":
            return record.get("key")
        elif table == "llm_prompts":
            return record.get("id")
        return None

    def _records_equal(self, table: str, local: dict, remote: dict) -> bool:
        """Check if local and remote records are effectively equal.

        Handles floating point precision and compares all relevant fields.

        Args:
            table: Table name
            local: Local record
            remote: Remote record

        Returns:
            True if records are effectively equal, False otherwise
        """
        if table == "bursts":
            # For bursts, we don't merge - compare key fields
            return (
                local.get("start_time") == remote.get("start_time")
                and local.get("key_count") == remote.get("key_count")
                and local.get("duration_ms") == remote.get("duration_ms")
            )

        elif table == "statistics":
            # Compare all numeric fields with tolerance for floats
            return (
                self._float_equal(local.get("avg_press_time"), remote.get("avg_press_time"))
                and local.get("total_presses") == remote.get("total_presses")
                and local.get("slowest_ms") == remote.get("slowest_ms")
                and local.get("fastest_ms") == remote.get("fastest_ms")
            )

        elif table == "digraph_statistics":
            # Compare all numeric fields with tolerance for floats
            return self._float_equal(
                local.get("avg_interval_ms"), remote.get("avg_interval_ms")
            ) and local.get("total_sequences") == remote.get("total_sequences")

        elif table == "word_statistics":
            # Compare all numeric fields
            return (
                self._float_equal(
                    local.get("avg_speed_ms_per_letter"), remote.get("avg_speed_ms_per_letter")
                )
                and local.get("total_letters") == remote.get("total_letters")
                and local.get("total_duration_ms") == remote.get("total_duration_ms")
                and local.get("observation_count") == remote.get("observation_count")
            )

        elif table == "high_scores":
            # Compare all numeric fields
            return (
                self._float_equal(local.get("fastest_burst_wpm"), remote.get("fastest_burst_wpm"))
                and local.get("burst_duration_sec") == remote.get("burst_duration_sec")
                and local.get("burst_key_count") == remote.get("burst_key_count")
                and local.get("timestamp") == remote.get("timestamp")
                and local.get("burst_duration_ms") == remote.get("burst_duration_ms")
            )

        elif table == "daily_summaries":
            # Compare all numeric fields
            return (
                local.get("total_keystrokes") == remote.get("total_keystrokes")
                and local.get("total_bursts") == remote.get("total_bursts")
                and self._float_equal(local.get("avg_wpm"), remote.get("avg_wpm"))
            )

        elif table == "settings":
            # Compare key, value, and timestamp
            return (
                local.get("key") == remote.get("key")
                and local.get("value") == remote.get("value")
                and local.get("updated_at") == remote.get("updated_at")
            )
        elif table == "llm_prompts":
            # Compare name, content, and timestamp
            return (
                local.get("id") == remote.get("id")
                and local.get("name") == remote.get("name")
                and local.get("content") == remote.get("content")
                and local.get("updated_at") == remote.get("updated_at")
            )

        return False

    def _float_equal(self, a: float | None, b: float | None, tolerance: float = 0.001) -> bool:
        """Compare two floats with tolerance for precision issues.

        Args:
            a: First value
            b: Second value
            tolerance: Maximum allowed difference

        Returns:
            True if values are equal within tolerance
        """
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        return abs(a - b) <= tolerance

    def _batch_push(self, table: str, records: list[dict]) -> int:
        """Push multiple records to remote database in a batch.

        Args:
            table: Table name
            records: List of records to push

        Returns:
            Number of records pushed
        """
        if not records:
            return 0

        try:
            if table == "bursts":
                # Use adapter's batch_insert_bursts method if available
                if hasattr(self.remote, "batch_insert_bursts"):
                    return self.remote.batch_insert_bursts(records)
                # Fall back to individual inserts
                for record in records:
                    self.remote.store_burst(
                        start_time=record.get("start_time", 0),
                        end_time=record.get("end_time", 0),
                        key_count=record.get("key_count", 0),
                        backspace_count=record.get("backspace_count", 0),
                        net_key_count=record.get("net_key_count", 0),
                        duration_ms=record.get("duration_ms", 0),
                        avg_wpm=record.get("avg_wpm", 0.0),
                        qualifies_for_high_score=record.get("qualifies_for_high_score", False),
                    )
                return len(records)

            # For other tables, use batch insert if available
            batch_method = f"batch_insert_{table}"
            if hasattr(self.remote, batch_method):
                return getattr(self.remote, batch_method)(records)

            # Fall back to individual inserts
            count = 0
            for record in records:
                if self._push_record(table, record):
                    count += 1
            return count

        except Exception as e:
            error_msg = f"Failed to batch push to {table}: {e}"
            log.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _batch_pull(self, table: str, records: list[dict]) -> int:
        """Pull multiple records to local database in a batch.

        Args:
            table: Table name
            records: List of records to pull

        Returns:
            Number of records pulled
        """
        if not records:
            return 0

        try:
            if table == "bursts":
                # Use adapter's batch_insert_bursts method if available
                if hasattr(self.local, "batch_insert_bursts"):
                    return self.local.batch_insert_bursts(records)
                # Fall back to individual inserts
                for record in records:
                    self.local.store_burst(
                        start_time=record.get("start_time", 0),
                        end_time=record.get("end_time", 0),
                        key_count=record.get("key_count", 0),
                        backspace_count=record.get("backspace_count", 0),
                        net_key_count=record.get("net_key_count", 0),
                        duration_ms=record.get("duration_ms", 0),
                        avg_wpm=record.get("avg_wpm", 0.0),
                        qualifies_for_high_score=record.get("qualifies_for_high_score", False),
                    )
                return len(records)

            # For other tables, use batch insert if available
            batch_method = f"batch_insert_{table}"
            if hasattr(self.local, batch_method):
                return getattr(self.local, batch_method)(records)

            # Fall back to individual inserts
            count = 0
            for record in records:
                if self._pull_record(table, record):
                    count += 1
            return count

        except Exception as e:
            error_msg = f"Failed to batch pull from {table}: {e}"
            log.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _batch_update_local(self, table: str, records: list[dict]) -> int:
        """Update multiple local records in a batch.

        Args:
            table: Table name
            records: List of records to update

        Returns:
            Number of records updated
        """
        if not records:
            return 0

        try:
            with self.local.get_connection() as conn:
                cursor = conn.cursor()
                updated_count = 0

                if table == "statistics":
                    for record in records:
                        cursor.execute(
                            """
                            UPDATE statistics
                            SET avg_press_time = ?,
                                total_presses = ?,
                                slowest_ms = ?,
                                fastest_ms = ?,
                                last_updated = ?
                            WHERE keycode = ? AND layout = ?
                        """,
                            (
                                record.get("avg_press_time"),
                                record.get("total_presses"),
                                record.get("slowest_ms"),
                                record.get("fastest_ms"),
                                record.get("last_updated"),
                                record.get("keycode"),
                                record.get("layout"),
                            ),
                        )
                        if cursor.rowcount > 0:
                            updated_count += 1
                        else:
                            log.warning(
                                f"Statistics update affected 0 rows: keycode={record.get('keycode')}, layout={record.get('layout')}"
                            )

                elif table == "digraph_statistics":
                    for record in records:
                        cursor.execute(
                            """
                            UPDATE digraph_statistics
                            SET avg_interval_ms = ?,
                                total_sequences = ?,
                                slowest_ms = ?,
                                fastest_ms = ?,
                                last_updated = ?
                            WHERE first_keycode = ? AND second_keycode = ? AND layout = ?
                        """,
                            (
                                record.get("avg_interval_ms"),
                                record.get("total_sequences"),
                                record.get("slowest_ms"),
                                record.get("fastest_ms"),
                                record.get("last_updated"),
                                record.get("first_keycode"),
                                record.get("second_keycode"),
                                record.get("layout"),
                            ),
                        )
                        if cursor.rowcount > 0:
                            updated_count += 1
                        else:
                            log.warning(
                                f"Digraph statistics update affected 0 rows: "
                                f"{record.get('first_key')}{record.get('second_key')} layout={record.get('layout')}"
                            )

                elif table == "word_statistics":
                    for record in records:
                        cursor.execute(
                            """
                            UPDATE word_statistics
                            SET avg_speed_ms_per_letter = ?,
                                total_letters = ?,
                                total_duration_ms = ?,
                                observation_count = ?,
                                last_seen = ?
                            WHERE word = ? AND layout = ?
                        """,
                            (
                                record.get("avg_speed_ms_per_letter"),
                                record.get("total_letters"),
                                record.get("total_duration_ms"),
                                record.get("observation_count"),
                                record.get("last_seen"),
                                record.get("word"),
                                record.get("layout"),
                            ),
                        )
                        if cursor.rowcount > 0:
                            updated_count += 1
                        else:
                            log.warning(
                                f"Word statistics update affected 0 rows: word={record.get('word')}, layout={record.get('layout')}"
                            )

                elif table == "high_scores":
                    for record in records:
                        cursor.execute(
                            """
                            UPDATE high_scores
                            SET fastest_burst_wpm = ?,
                                burst_duration_sec = ?,
                                burst_key_count = ?,
                                timestamp = ?,
                                burst_duration_ms = ?
                            WHERE id = ?
                        """,
                            (
                                record.get("fastest_burst_wpm"),
                                record.get("burst_duration_sec"),
                                record.get("burst_key_count"),
                                record.get("timestamp"),
                                record.get("burst_duration_ms"),
                                record.get("id"),
                            ),
                        )
                        if cursor.rowcount > 0:
                            updated_count += 1
                        else:
                            log.warning(
                                f"High scores update affected 0 rows: id={record.get('id')}"
                            )

                elif table == "daily_summaries":
                    for record in records:
                        cursor.execute(
                            """
                            UPDATE daily_summaries
                            SET total_keystrokes = ?,
                                total_bursts = ?,
                                avg_wpm = ?
                            WHERE date = ?
                        """,
                            (
                                record.get("total_keystrokes"),
                                record.get("total_bursts"),
                                record.get("avg_wpm"),
                                record.get("date"),
                            ),
                        )
                        if cursor.rowcount > 0:
                            updated_count += 1
                        else:
                            log.warning(
                                f"Daily summary update affected 0 rows: date={record.get('date')}"
                            )

                elif table == "settings":
                    for record in records:
                        cursor.execute(
                            """
                            UPDATE settings
                            SET value = ?,
                                updated_at = ?
                            WHERE key = ?
                        """,
                            (
                                record.get("value"),
                                record.get("updated_at"),
                                record.get("key"),
                            ),
                        )
                        if cursor.rowcount > 0:
                            updated_count += 1
                        else:
                            log.warning(f"Settings update affected 0 rows: key={record.get('key')}")

                conn.commit()

                if updated_count != len(records):
                    log.error(
                        f"Update count mismatch for {table}: expected {len(records)}, got {updated_count}"
                    )

                return updated_count

        except Exception as e:
            error_msg = f"Failed to batch update local {table}: {e}"
            log.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _batch_update_remote(self, table: str, records: list[dict]) -> int:
        """Update multiple remote records in a batch using adapter batch_update methods.

        Args:
            table: Table name
            records: List of records to update

        Returns:
            Number of records updated
        """
        if not records:
            return 0

        # Only update if remote is PostgreSQL (has user_id)
        if not hasattr(self.remote, "user_id"):
            return 0

        log.debug(f"Batch updating {len(records)} remote records in {table}")

        # Pre-encrypt all records for efficiency
        encrypted_data_list = []
        for record in records:
            encrypted_data = None
            if self.encryption:
                encrypted_data = self._encrypt_record(table, record)
            encrypted_data_list.append(encrypted_data)

        # Delegate to adapter's batch_update method
        if table == "statistics":
            return self.remote.batch_update_statistics(records, encrypted_data_list)
        elif table == "digraph_statistics":
            return self.remote.batch_update_digraph_statistics(records, encrypted_data_list)
        elif table == "word_statistics":
            return self.remote.batch_update_word_statistics(records, encrypted_data_list)
        elif table == "high_scores":
            return self.remote.batch_update_high_scores(records, encrypted_data_list)
        elif table == "daily_summaries":
            return self.remote.batch_update_daily_summaries(records, encrypted_data_list)
        elif table == "settings":
            return self.remote.batch_update_settings(records, encrypted_data_list)
        else:
            log.warning(f"No batch_update method for table: {table}")
            return 0

    def _get_local_data(self, table: str) -> list[dict]:
        """Get all data from local table.

        Args:
            table: Table name

        Returns:
            List of record dictionaries
        """
        data = []

        if table == "bursts":
            # Get all bursts from local SQLite
            try:
                with self.local.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id, start_time, end_time, key_count, backspace_count,
                               net_key_count, duration_ms, avg_wpm, qualifies_for_high_score
                        FROM bursts
                        ORDER BY start_time
                    """)
                    for row in cursor.fetchall():
                        data.append(
                            {
                                "id": row[0],
                                "start_time": row[1],
                                "end_time": row[2],
                                "key_count": row[3],
                                "backspace_count": row[4],
                                "net_key_count": row[5],
                                "duration_ms": row[6],
                                "avg_wpm": row[7],
                                "qualifies_for_high_score": bool(row[8]),
                            }
                        )
            except Exception as e:
                error_msg = f"Failed to get local bursts: {e}"
                log.error(error_msg)
                raise RuntimeError(error_msg) from e

        elif table == "statistics":
            try:
                with self.local.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT keycode, key_name, layout, avg_press_time,
                               total_presses, slowest_ms, fastest_ms, last_updated
                        FROM statistics
                    """)
                    for row in cursor.fetchall():
                        data.append(
                            {
                                "keycode": row[0],
                                "key_name": row[1],
                                "layout": row[2],
                                "avg_press_time": row[3],
                                "total_presses": row[4],
                                "slowest_ms": row[5],
                                "fastest_ms": row[6],
                                "last_updated": row[7],
                            }
                        )
            except Exception as e:
                error_msg = f"Failed to get local statistics: {e}"
                log.error(error_msg)
                raise RuntimeError(error_msg) from e

        elif table == "digraph_statistics":
            try:
                with self.local.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT first_keycode, second_keycode, first_key, second_key, layout,
                               avg_interval_ms, total_sequences, slowest_ms, fastest_ms, last_updated
                        FROM digraph_statistics
                    """)
                    for row in cursor.fetchall():
                        data.append(
                            {
                                "first_keycode": row[0],
                                "second_keycode": row[1],
                                "first_key": row[2],
                                "second_key": row[3],
                                "layout": row[4],
                                "avg_interval_ms": row[5],
                                "total_sequences": row[6],
                                "slowest_ms": row[7],
                                "fastest_ms": row[8],
                                "last_updated": row[9],
                            }
                        )
            except Exception as e:
                error_msg = f"Failed to get local digraph statistics: {e}"
                log.error(error_msg)
                raise RuntimeError(error_msg) from e

        elif table == "word_statistics":
            try:
                with self.local.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT word, layout, avg_speed_ms_per_letter, total_letters,
                               total_duration_ms, observation_count, last_seen,
                               backspace_count, editing_time_ms
                        FROM word_statistics
                    """)
                    for row in cursor.fetchall():
                        data.append(
                            {
                                "word": row[0],
                                "layout": row[1],
                                "avg_speed_ms_per_letter": row[2],
                                "total_letters": row[3],
                                "total_duration_ms": row[4],
                                "observation_count": row[5],
                                "last_seen": row[6],
                                "backspace_count": row[7] or 0,
                                "editing_time_ms": row[8] or 0,
                            }
                        )
            except Exception as e:
                error_msg = f"Failed to get local word statistics: {e}"
                log.error(error_msg)
                raise RuntimeError(error_msg) from e

        elif table == "high_scores":
            try:
                with self.local.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id, date, fastest_burst_wpm, burst_duration_sec,
                               burst_key_count, timestamp, burst_duration_ms
                        FROM high_scores
                    """)
                    for row in cursor.fetchall():
                        data.append(
                            {
                                "id": row[0],
                                "date": row[1],
                                "fastest_burst_wpm": row[2],
                                "burst_duration_sec": row[3],
                                "burst_key_count": row[4],
                                "timestamp": row[5],
                                "burst_duration_ms": row[6],
                            }
                        )
            except Exception as e:
                error_msg = f"Failed to get local high scores: {e}"
                log.error(error_msg)
                raise RuntimeError(error_msg) from e

        elif table == "daily_summaries":
            try:
                with self.local.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT date, total_keystrokes, total_bursts, avg_wpm,
                               slowest_keycode, slowest_key_name, total_typing_sec, summary_sent
                        FROM daily_summaries
                    """)
                    for row in cursor.fetchall():
                        data.append(
                            {
                                "date": row[0],
                                "total_keystrokes": row[1],
                                "total_bursts": row[2],
                                "avg_wpm": row[3],
                                "slowest_keycode": row[4],
                                "slowest_key_name": row[5],
                                "total_typing_sec": row[6],
                                "summary_sent": bool(row[7] or 0),
                            }
                        )
            except Exception as e:
                error_msg = f"Failed to get local daily summaries: {e}"
                log.error(error_msg)
                raise RuntimeError(error_msg) from e

        elif table == "ignored_words":
            # Use adapter's get_all_ignored_word_hashes method
            return self.local.get_all_ignored_word_hashes()

        elif table == "settings":
            # Use adapter's get_all_settings method
            # Filter out last_sync_timestamp as it's sync metadata, not user data
            all_settings = self.local.get_all_settings()
            return [s for s in all_settings if s.get("key") != "last_sync_timestamp"]
        elif table == "llm_prompts":
            # Use adapter's get_all_llm_prompts_for_sync method
            return self.local.get_all_llm_prompts_for_sync()

        return data

    def _get_remote_data(self, table: str) -> list[dict]:
        """Get all data from remote table.

        Args:
            table: Table name

        Returns:
            List of record dictionaries
        """
        data = []

        # Only fetch if remote is PostgreSQL
        if not hasattr(self.remote, "user_id"):
            return data

        try:
            if table == "bursts":
                with self.remote.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT id, start_time, end_time, key_count, backspace_count,
                               net_key_count, duration_ms, avg_wpm, qualifies_for_high_score,
                               encrypted_data
                        FROM bursts
                        WHERE user_id = %s
                        ORDER BY start_time
                    """,
                        (self.user_id,),
                    )
                    for row in cursor.fetchall():
                        record = {
                            "id": row[0],
                            "start_time": row[1],
                            "end_time": row[2],
                            "key_count": row[3],
                            "backspace_count": row[4],
                            "net_key_count": row[5],
                            "duration_ms": row[6],
                            "avg_wpm": row[7],
                            "qualifies_for_high_score": bool(row[8]),
                        }
                        # Decrypt if encrypted
                        if row[9] and self.encryption:
                            try:
                                decrypted = self.encryption.decrypt_burst(row[9])
                                record = {**record, **decrypted}
                            except Exception as e:
                                error_msg = f"Failed to decrypt burst ID {row[0]}: {e}"
                                log.error(error_msg)
                                raise RuntimeError(error_msg) from e
                        data.append(record)

            elif table == "statistics":
                with self.remote.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT keycode, layout, key_name, avg_press_time, total_presses,
                               slowest_ms, fastest_ms, last_updated, encrypted_data
                        FROM statistics
                        WHERE user_id = %s
                    """,
                        (self.user_id,),
                    )
                    for row in cursor.fetchall():
                        record = {
                            "keycode": row[0],
                            "layout": row[1],
                            "key_name": row[2],
                            "avg_press_time": row[3],
                            "total_presses": row[4],
                            "slowest_ms": row[5],
                            "fastest_ms": row[6],
                            "last_updated": row[7],
                        }
                        # Decrypt if encrypted
                        if row[8] and self.encryption:
                            try:
                                decrypted = self.encryption.decrypt_statistics(row[8])
                                record = {**record, **decrypted}
                            except Exception as e:
                                error_msg = f"Failed to decrypt statistics for keycode={row[0]}, layout={row[1]}: {e}"
                                log.error(error_msg)
                                raise RuntimeError(error_msg) from e
                        data.append(record)

            elif table == "digraph_statistics":
                with self.remote.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT first_keycode, second_keycode, first_key, second_key, layout,
                               avg_interval_ms, total_sequences, slowest_ms, fastest_ms, last_updated, encrypted_data
                        FROM digraph_statistics
                        WHERE user_id = %s
                    """,
                        (self.user_id,),
                    )
                    for row in cursor.fetchall():
                        record = {
                            "first_keycode": row[0],
                            "second_keycode": row[1],
                            "first_key": row[2],
                            "second_key": row[3],
                            "layout": row[4],
                            "avg_interval_ms": row[5],
                            "total_sequences": row[6],
                            "slowest_ms": row[7],
                            "fastest_ms": row[8],
                            "last_updated": row[9],
                        }
                        # Decrypt if encrypted
                        if row[10] and self.encryption:
                            try:
                                decrypted = self.encryption.decrypt_digraph_statistics(row[10])
                                record = {**record, **decrypted}
                            except Exception as e:
                                error_msg = f"Failed to decrypt digraph statistics for {row[2]}{row[3]} layout={row[4]}: {e}"
                                log.error(error_msg)
                                raise RuntimeError(error_msg) from e
                        data.append(record)

            elif table == "word_statistics":
                with self.remote.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT word, layout, avg_speed_ms_per_letter, total_letters,
                               total_duration_ms, observation_count, last_seen,
                               backspace_count, editing_time_ms, encrypted_data
                        FROM word_statistics
                        WHERE user_id = %s
                    """,
                        (self.user_id,),
                    )
                    for row in cursor.fetchall():
                        record = {
                            "word": row[0],
                            "layout": row[1],
                            "avg_speed_ms_per_letter": row[2],
                            "total_letters": row[3],
                            "total_duration_ms": row[4],
                            "observation_count": row[5],
                            "last_seen": row[6],
                            "backspace_count": row[7] or 0,
                            "editing_time_ms": row[8] or 0,
                        }
                        # Decrypt if encrypted
                        if row[9] and self.encryption:
                            try:
                                decrypted = self.encryption.decrypt_word_statistics(row[9])
                                record = {**record, **decrypted}
                            except Exception as e:
                                error_msg = f"Failed to decrypt word statistics for word={row[0]}, layout={row[1]}: {e}"
                                log.error(error_msg)
                                raise RuntimeError(error_msg) from e

                        # Filter out names if callback is provided
                        if self.is_name_callback:
                            word = record.get("word", "")
                            if self.is_name_callback(word):
                                log.debug(
                                    f"Filtering out name '{word}' from remote word_statistics"
                                )
                                continue

                        data.append(record)

            elif table == "high_scores":
                with self.remote.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT id, date, fastest_burst_wpm, burst_duration_sec,
                               burst_key_count, timestamp, burst_duration_ms, encrypted_data
                        FROM high_scores
                        WHERE user_id = %s
                    """,
                        (self.user_id,),
                    )
                    for row in cursor.fetchall():
                        record = {
                            "id": row[0],
                            "date": row[1],
                            "fastest_burst_wpm": row[2],
                            "burst_duration_sec": row[3],
                            "burst_key_count": row[4],
                            "timestamp": row[5],
                            "burst_duration_ms": row[6],
                        }
                        # Decrypt if encrypted
                        if row[7] and self.encryption:
                            try:
                                decrypted = self.encryption.decrypt_high_score(row[7])
                                record = {**record, **decrypted}
                            except Exception as e:
                                error_msg = f"Failed to decrypt high score ID {row[0]}: {e}"
                                log.error(error_msg)
                                raise RuntimeError(error_msg) from e
                        data.append(record)

            elif table == "daily_summaries":
                with self.remote.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT date, total_keystrokes, total_bursts, avg_wpm,
                               slowest_keycode, slowest_key_name, total_typing_sec,
                               summary_sent, encrypted_data
                        FROM daily_summaries
                        WHERE user_id = %s
                    """,
                        (self.user_id,),
                    )
                    for row in cursor.fetchall():
                        record = {
                            "date": row[0],
                            "total_keystrokes": row[1],
                            "total_bursts": row[2],
                            "avg_wpm": row[3],
                            "slowest_keycode": row[4],
                            "slowest_key_name": row[5],
                            "total_typing_sec": row[6],
                            "summary_sent": bool(row[7] or 0),
                        }
                        # Decrypt if encrypted
                        if row[8] and self.encryption:
                            try:
                                decrypted = self.encryption.decrypt_daily_summary(row[8])
                                record = {**record, **decrypted}
                            except Exception as e:
                                error_msg = (
                                    f"Failed to decrypt daily summary for date={row[0]}: {e}"
                                )
                                log.error(error_msg)
                                raise RuntimeError(error_msg) from e
                        data.append(record)

            elif table == "ignored_words":
                # Use adapter's get_all_ignored_word_hashes method
                return self.remote.get_all_ignored_word_hashes()

            elif table == "settings":
                # Use adapter's get_all_settings method
                # Filter out last_sync_timestamp as it's sync metadata, not user data
                all_settings = self.remote.get_all_settings()
                return [s for s in all_settings if s.get("key") != "last_sync_timestamp"]
            elif table == "llm_prompts":
                # Use adapter's get_all_llm_prompts_for_sync method
                return self.remote.get_all_llm_prompts_for_sync()

        except Exception as e:
            error_msg = f"Failed to get remote data for {table}: {e}"
            log.error(error_msg)
            raise RuntimeError(error_msg) from e

        return data

    def _push_record(self, table: str, record: dict) -> bool:
        """Push a local record to remote database.

        Args:
            table: Table name
            record: Record to push

        Returns:
            True if successful
        """
        try:
            if table == "bursts":
                # Use adapter's store_burst method
                self.remote.store_burst(
                    start_time=record.get("start_time", 0),
                    end_time=record.get("end_time", 0),
                    key_count=record.get("key_count", 0),
                    backspace_count=record.get("backspace_count", 0),
                    net_key_count=record.get("net_key_count", 0),
                    duration_ms=record.get("duration_ms", 0),
                    avg_wpm=record.get("avg_wpm", 0.0),
                    qualifies_for_high_score=record.get("qualifies_for_high_score", False),
                )
                return True

            # Encrypt data if encryption is enabled
            encrypted_data = None
            if self.encryption:
                encrypted_data = self._encrypt_record(table, record)

            # Insert other tables using raw SQL
            with self.remote.get_connection() as conn:
                cursor = conn.cursor()

                if table == "statistics":
                    cursor.execute(
                        """
                        INSERT INTO statistics
                        (keycode, key_name, layout, avg_press_time, total_presses,
                         slowest_ms, fastest_ms, last_updated, user_id, encrypted_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, keycode, layout) DO NOTHING
                    """,
                        (
                            record.get("keycode"),
                            record.get("key_name"),
                            record.get("layout"),
                            record.get("avg_press_time"),
                            record.get("total_presses"),
                            record.get("slowest_ms"),
                            record.get("fastest_ms"),
                            record.get("last_updated"),
                            self.user_id,
                            encrypted_data,
                        ),
                    )

                elif table == "digraph_statistics":
                    cursor.execute(
                        """
                        INSERT INTO digraph_statistics
                        (first_keycode, second_keycode, first_key, second_key, layout,
                         avg_interval_ms, total_sequences, slowest_ms, fastest_ms, last_updated, user_id, encrypted_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, first_keycode, second_keycode, layout) DO NOTHING
                    """,
                        (
                            record.get("first_keycode"),
                            record.get("second_keycode"),
                            record.get("first_key"),
                            record.get("second_key"),
                            record.get("layout"),
                            record.get("avg_interval_ms"),
                            record.get("total_sequences"),
                            record.get("slowest_ms"),
                            record.get("fastest_ms"),
                            record.get("last_updated"),
                            self.user_id,
                            encrypted_data,
                        ),
                    )

                elif table == "word_statistics":
                    cursor.execute(
                        """
                        INSERT INTO word_statistics
                        (word, layout, avg_speed_ms_per_letter, total_letters,
                         total_duration_ms, observation_count, last_seen,
                         backspace_count, editing_time_ms, user_id, encrypted_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, word, layout) DO NOTHING
                    """,
                        (
                            record.get("word"),
                            record.get("layout"),
                            record.get("avg_speed_ms_per_letter"),
                            record.get("total_letters"),
                            record.get("total_duration_ms"),
                            record.get("observation_count"),
                            record.get("last_seen"),
                            record.get("backspace_count"),
                            record.get("editing_time_ms"),
                            self.user_id,
                            encrypted_data,
                        ),
                    )

                elif table == "high_scores":
                    cursor.execute(
                        """
                        INSERT INTO high_scores
                        (id, date, fastest_burst_wpm, burst_duration_sec,
                         burst_key_count, timestamp, burst_duration_ms, user_id, encrypted_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, id) DO NOTHING
                    """,
                        (
                            record.get("id"),
                            record.get("date"),
                            record.get("fastest_burst_wpm"),
                            record.get("burst_duration_sec"),
                            record.get("burst_key_count"),
                            record.get("timestamp"),
                            record.get("burst_duration_ms"),
                            self.user_id,
                            encrypted_data,
                        ),
                    )

                elif table == "daily_summaries":
                    cursor.execute(
                        """
                        INSERT INTO daily_summaries
                        (date, total_keystrokes, total_bursts, avg_wpm,
                         slowest_keycode, slowest_key_name, total_typing_sec,
                         summary_sent, user_id, encrypted_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, date) DO NOTHING
                    """,
                        (
                            record.get("date"),
                            record.get("total_keystrokes"),
                            record.get("total_bursts"),
                            record.get("avg_wpm"),
                            record.get("slowest_keycode"),
                            record.get("slowest_key_name"),
                            record.get("total_typing_sec"),
                            1 if record.get("summary_sent") else 0,
                            self.user_id,
                            encrypted_data,
                        ),
                    )

                elif table == "ignored_words":
                    # Use adapter's add_ignored_word method
                    self.remote.add_ignored_word(
                        word_hash=record.get("word_hash"), timestamp_ms=record.get("added_at")
                    )

                elif table == "settings":
                    # Use adapter's upsert_setting method
                    self.remote.upsert_setting(key=record.get("key"), value=record.get("value"))
                elif table == "llm_prompts":
                    # Use batch insert for prompts
                    self.remote.batch_insert_llm_prompts([record])

                conn.commit()
            return True
        except Exception as e:
            error_msg = f"Failed to push record to {table}: {e}"
            log.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _pull_record(self, table: str, record: dict) -> bool:
        """Pull a remote record to local database.

        Args:
            table: Table name
            record: Record to pull

        Returns:
            True if successful
        """
        try:
            if table == "bursts":
                # Use adapter's store_burst method
                self.local.store_burst(
                    start_time=record.get("start_time", 0),
                    end_time=record.get("end_time", 0),
                    key_count=record.get("key_count", 0),
                    backspace_count=record.get("backspace_count", 0),
                    net_key_count=record.get("net_key_count", 0),
                    duration_ms=record.get("duration_ms", 0),
                    avg_wpm=record.get("avg_wpm", 0.0),
                    qualifies_for_high_score=record.get("qualifies_for_high_score", False),
                )
                return True

            # Insert other tables using raw SQL
            with self.local.get_connection() as conn:
                cursor = conn.cursor()

                if table == "statistics":
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO statistics
                        (keycode, key_name, layout, avg_press_time, total_presses,
                         slowest_ms, fastest_ms, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            record.get("keycode"),
                            record.get("key_name"),
                            record.get("layout"),
                            record.get("avg_press_time"),
                            record.get("total_presses"),
                            record.get("slowest_ms"),
                            record.get("fastest_ms"),
                            record.get("last_updated"),
                        ),
                    )

                elif table == "digraph_statistics":
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO digraph_statistics
                        (first_keycode, second_keycode, first_key, second_key, layout,
                         avg_interval_ms, total_sequences, slowest_ms, fastest_ms, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            record.get("first_keycode"),
                            record.get("second_keycode"),
                            record.get("first_key"),
                            record.get("second_key"),
                            record.get("layout"),
                            record.get("avg_interval_ms"),
                            record.get("total_sequences"),
                            record.get("slowest_ms"),
                            record.get("fastest_ms"),
                            record.get("last_updated"),
                        ),
                    )

                elif table == "word_statistics":
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO word_statistics
                        (word, layout, avg_speed_ms_per_letter, total_letters,
                         total_duration_ms, observation_count, last_seen,
                         backspace_count, editing_time_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            record.get("word"),
                            record.get("layout"),
                            record.get("avg_speed_ms_per_letter"),
                            record.get("total_letters"),
                            record.get("total_duration_ms"),
                            record.get("observation_count"),
                            record.get("last_seen"),
                            record.get("backspace_count"),
                            record.get("editing_time_ms"),
                        ),
                    )

                elif table == "high_scores":
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO high_scores
                        (id, date, fastest_burst_wpm, burst_duration_sec,
                         burst_key_count, timestamp, burst_duration_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            record.get("id"),
                            record.get("date"),
                            record.get("fastest_burst_wpm"),
                            record.get("burst_duration_sec"),
                            record.get("burst_key_count"),
                            record.get("timestamp"),
                            record.get("burst_duration_ms"),
                        ),
                    )

                elif table == "daily_summaries":
                    cursor.execute(
                        """
                        INSERT OR IGNORE INTO daily_summaries
                        (date, total_keystrokes, total_bursts, avg_wpm,
                         slowest_keycode, slowest_key_name, total_typing_sec, summary_sent)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            record.get("date"),
                            record.get("total_keystrokes"),
                            record.get("total_bursts"),
                            record.get("avg_wpm"),
                            record.get("slowest_keycode"),
                            record.get("slowest_key_name"),
                            record.get("total_typing_sec"),
                            1 if record.get("summary_sent") else 0,
                        ),
                    )

                elif table == "ignored_words":
                    # Use adapter's add_ignored_word method
                    self.local.add_ignored_word(
                        word_hash=record.get("word_hash"), timestamp_ms=record.get("added_at")
                    )

                elif table == "settings":
                    # Use adapter's upsert_setting method
                    self.local.upsert_setting(key=record.get("key"), value=record.get("value"))
                elif table == "llm_prompts":
                    # Use batch insert for prompts
                    self.local.batch_insert_llm_prompts([record])

                conn.commit()
            return True
        except Exception as e:
            error_msg = f"Failed to pull record from {table}: {e}"
            log.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _resolve_conflict(self, table: str, local: dict, remote: dict) -> dict | None:
        """Resolve conflict between local and remote records.

        Args:
            table: Table name
            local: Local record
            remote: Remote record

        Returns:
            Merged record or None if no merge needed
        """
        if table == "bursts":
            # Bursts: Check by start_time, don't merge
            return None

        elif table == "statistics":
            # Take the record with more presses (more complete data)
            # Both sides track the same keys, so don't sum them
            local_presses = local.get("total_presses", 0)
            remote_presses = remote.get("total_presses", 0)

            if local_presses >= remote_presses:
                return local
            else:
                return remote

        elif table == "digraph_statistics":
            # Take the record with more sequences (more complete data)
            # Both sides track the same digraphs, so don't sum them
            local_sequences = local.get("total_sequences", 0)
            remote_sequences = remote.get("total_sequences", 0)

            if local_sequences >= remote_sequences:
                return local
            else:
                return remote

        elif table == "word_statistics":
            # Take the record with more observations (more complete data)
            # Both sides track the same words, so don't sum them
            local_count = local.get("observation_count", 0)
            remote_count = remote.get("observation_count", 0)

            if local_count >= remote_count:
                return local
            else:
                return remote

        elif table == "high_scores":
            # Keep higher WPM
            local_wpm = local.get("fastest_burst_wpm", 0)
            remote_wpm = remote.get("fastest_burst_wpm", 0)
            return local if local_wpm >= remote_wpm else remote

        elif table == "daily_summaries":
            # Merge: take the more complete record (max keystrokes)
            # Daily summaries represent a single day - don't sum them!
            local_keystrokes = local.get("total_keystrokes", 0)
            remote_keystrokes = remote.get("total_keystrokes", 0)
            local_bursts = local.get("total_bursts", 0)
            remote_bursts = remote.get("total_bursts", 0)

            # Take the record with more keystrokes (more complete data)
            if local_keystrokes >= remote_keystrokes:
                return local
            else:
                return remote

        elif table == "settings" or table == "llm_prompts":
            # Last write wins based on updated_at timestamp
            local_updated = local.get("updated_at", 0)
            remote_updated = remote.get("updated_at", 0)
            if local_updated >= remote_updated:
                return local
            else:
                return remote

        return None

    def _encrypt_record(self, table: str, record: dict) -> str:
        """Encrypt a record for storage.

        Args:
            table: Table name
            record: Record to encrypt

        Returns:
            Base64 encoded encrypted data
        """
        if not self.encryption:
            return ""

        if table == "bursts":
            return self.encryption.encrypt_burst(
                start_time=record.get("start_time", 0),
                end_time=record.get("end_time", 0),
                key_count=record.get("key_count", 0),
                backspace_count=record.get("backspace_count", 0),
                net_key_count=record.get("net_key_count", 0),
                duration_ms=record.get("duration_ms", 0),
                avg_wpm=record.get("avg_wpm", 0),
                qualifies_for_high_score=record.get("qualifies_for_high_score", False),
            )

        elif table == "statistics":
            return self.encryption.encrypt_statistics(
                keycode=record.get("keycode", 0),
                key_name=record.get("key_name", ""),
                layout=record.get("layout", ""),
                avg_press_time=record.get("avg_press_time", 0),
                total_presses=record.get("total_presses", 0),
                slowest_ms=record.get("slowest_ms", 0),
                fastest_ms=record.get("fastest_ms", 0),
                last_updated=record.get("last_updated", 0),
            )

        elif table == "digraph_statistics":
            return self.encryption.encrypt_digraph_statistics(
                first_keycode=record.get("first_keycode", 0),
                second_keycode=record.get("second_keycode", 0),
                first_key=record.get("first_key", ""),
                second_key=record.get("second_key", ""),
                layout=record.get("layout", ""),
                avg_interval_ms=record.get("avg_interval_ms", 0),
                total_sequences=record.get("total_sequences", 0),
                slowest_ms=record.get("slowest_ms", 0),
                fastest_ms=record.get("fastest_ms", 0),
                last_updated=record.get("last_updated", 0),
            )

        elif table == "word_statistics":
            return self.encryption.encrypt_word_statistics(
                word=record.get("word", ""),
                layout=record.get("layout", ""),
                avg_speed_ms_per_letter=record.get("avg_speed_ms_per_letter", 0),
                total_letters=record.get("total_letters", 0),
                total_duration_ms=record.get("total_duration_ms", 0),
                observation_count=record.get("observation_count", 0),
                last_seen=record.get("last_seen", 0),
                backspace_count=record.get("backspace_count", 0),
                editing_time_ms=record.get("editing_time_ms", 0),
            )

        elif table == "high_scores":
            return self.encryption.encrypt_high_score(
                date=record.get("date", ""),
                fastest_burst_wpm=record.get("fastest_burst_wpm", 0),
                burst_duration_sec=record.get("burst_duration_sec", 0),
                burst_key_count=record.get("burst_key_count", 0),
                timestamp=record.get("timestamp", 0),
                burst_duration_ms=record.get("burst_duration_ms", 0),
            )

        elif table == "daily_summaries":
            return self.encryption.encrypt_daily_summary(
                date=record.get("date", ""),
                total_keystrokes=record.get("total_keystrokes", 0),
                total_bursts=record.get("total_bursts", 0),
                avg_wpm=record.get("avg_wpm", 0),
                slowest_keycode=record.get("slowest_keycode", 0),
                slowest_key_name=record.get("slowest_key_name", ""),
                total_typing_sec=record.get("total_typing_sec", 0),
                summary_sent=record.get("summary_sent", False),
            )

        return ""
