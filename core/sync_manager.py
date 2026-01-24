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
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.data_encryption import DataEncryption
    from core.database_adapter import DatabaseAdapter

log = logging.getLogger("realtypecoach.sync_manager")


@dataclass
class SyncResult:
    """Result of a sync operation."""

    success: bool
    pushed: int = 0
    pulled: int = 0
    conflicts_resolved: int = 0
    error: str | None = None
    duration_ms: int = 0


class SyncManager:
    """Bidirectional smart merge between SQLite and PostgreSQL.

    Conflict resolution strategies:
    - bursts: Insert only (check by id + start_time to avoid duplicates)
    - statistics: Merge - recalculate weighted avg from both totals
    - word_statistics: Merge - weighted average by observation_count
    - high_scores: Keep higher WPM for same date
    - daily_summaries: Merge - sum keystrokes/bursts, recalculate avg
    """

    # Tables to sync in order
    SYNC_TABLES = [
        "bursts",
        "statistics",
        "word_statistics",
        "high_scores",
        "daily_summaries",
    ]

    def __init__(
        self,
        local_adapter: "DatabaseAdapter",
        remote_adapter: "DatabaseAdapter",
        encryption: "DataEncryption | None" = None,
        user_id: str = "",
    ):
        """Initialize sync manager.

        Args:
            local_adapter: Local SQLite database adapter
            remote_adapter: Remote PostgreSQL database adapter
            encryption: DataEncryption instance for client-side encryption
            user_id: User UUID for filtering data
        """
        self.local = local_adapter
        self.remote = remote_adapter
        self.encryption = encryption
        self.user_id = user_id

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
            # Sync each table
            for table in self.SYNC_TABLES:
                pushed, pulled, conflicts = self._sync_table(table)
                result.pushed += pushed
                result.pulled += pulled
                result.conflicts_resolved += conflicts
                log.info(f"Synced {table}: pushed={pushed}, pulled={pulled}, conflicts={conflicts}")

            result.success = True

        except Exception as e:
            log.error(f"Sync failed: {e}")
            result.success = False
            result.error = str(e)

        result.duration_ms = int((time.time() - start_time) * 1000)
        return result

    def _sync_table(self, table: str) -> tuple[int, int, int]:
        """Sync a single table bidirectionally.

        Args:
            table: Table name to sync

        Returns:
            Tuple of (pushed, pulled, conflicts_resolved)
        """
        pushed = 0
        pulled = 0
        conflicts = 0

        # Get local and remote data
        local_data = self._get_local_data(table)
        remote_data = self._get_remote_data(table)

        log.debug(f"Table {table}: local={len(local_data)}, remote={len(remote_data)} records")

        # Push local data to remote
        for record in local_data:
            if self._should_push_record(table, record, remote_data):
                if self._push_record(table, record):
                    pushed += 1

        # Pull remote data to local
        for record in remote_data:
            local_match = self._find_local_match(table, record, local_data)
            if local_match is None:
                # New record from remote
                if self._pull_record(table, record):
                    pulled += 1
            else:
                # Conflict resolution
                resolved = self._resolve_conflict(table, local_match, record)
                if resolved is not None and resolved != local_match:
                    if self._update_local_record(table, resolved):
                        conflicts += 1

        return pushed, pulled, conflicts

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
                        data.append({
                            "id": row[0],
                            "start_time": row[1],
                            "end_time": row[2],
                            "key_count": row[3],
                            "backspace_count": row[4],
                            "net_key_count": row[5],
                            "duration_ms": row[6],
                            "avg_wpm": row[7],
                            "qualifies_for_high_score": bool(row[8]),
                        })
            except Exception as e:
                log.warning(f"Failed to get local bursts: {e}")

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
                        data.append({
                            "keycode": row[0],
                            "key_name": row[1],
                            "layout": row[2],
                            "avg_press_time": row[3],
                            "total_presses": row[4],
                            "slowest_ms": row[5],
                            "fastest_ms": row[6],
                            "last_updated": row[7],
                        })
            except Exception as e:
                log.warning(f"Failed to get local statistics: {e}")

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
                        data.append({
                            "word": row[0],
                            "layout": row[1],
                            "avg_speed_ms_per_letter": row[2],
                            "total_letters": row[3],
                            "total_duration_ms": row[4],
                            "observation_count": row[5],
                            "last_seen": row[6],
                            "backspace_count": row[7] or 0,
                            "editing_time_ms": row[8] or 0,
                        })
            except Exception as e:
                log.warning(f"Failed to get local word statistics: {e}")

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
                        data.append({
                            "id": row[0],
                            "date": row[1],
                            "fastest_burst_wpm": row[2],
                            "burst_duration_sec": row[3],
                            "burst_key_count": row[4],
                            "timestamp": row[5],
                            "burst_duration_ms": row[6],
                        })
            except Exception as e:
                log.warning(f"Failed to get local high scores: {e}")

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
                        data.append({
                            "date": row[0],
                            "total_keystrokes": row[1],
                            "total_bursts": row[2],
                            "avg_wpm": row[3],
                            "slowest_keycode": row[4],
                            "slowest_key_name": row[5],
                            "total_typing_sec": row[6],
                            "summary_sent": bool(row[7] or 0),
                        })
            except Exception as e:
                log.warning(f"Failed to get local daily summaries: {e}")

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
                    cursor.execute("""
                        SELECT id, start_time, end_time, key_count, backspace_count,
                               net_key_count, duration_ms, avg_wpm, qualifies_for_high_score,
                               encrypted_data
                        FROM bursts
                        WHERE user_id = %s
                        ORDER BY start_time
                    """, (self.user_id,))
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
                                log.warning(f"Failed to decrypt burst: {e}")
                        data.append(record)

            elif table == "statistics":
                with self.remote.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT keycode, layout, avg_press_time, total_presses,
                               slowest_ms, fastest_ms, last_updated, encrypted_data
                        FROM statistics
                        WHERE user_id = %s
                    """, (self.user_id,))
                    for row in cursor.fetchall():
                        record = {
                            "keycode": row[0],
                            "layout": row[1],
                            "avg_press_time": row[2],
                            "total_presses": row[3],
                            "slowest_ms": row[4],
                            "fastest_ms": row[5],
                            "last_updated": row[6],
                        }
                        # Decrypt if encrypted
                        if row[7] and self.encryption:
                            try:
                                decrypted = self.encryption.decrypt_statistics(row[7])
                                record = {**record, **decrypted}
                            except Exception as e:
                                log.warning(f"Failed to decrypt statistics: {e}")
                        data.append(record)

            elif table == "word_statistics":
                with self.remote.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT word, layout, avg_speed_ms_per_letter, total_letters,
                               total_duration_ms, observation_count, last_seen,
                               backspace_count, editing_time_ms, encrypted_data
                        FROM word_statistics
                        WHERE user_id = %s
                    """, (self.user_id,))
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
                                log.warning(f"Failed to decrypt word statistics: {e}")
                        data.append(record)

            elif table == "high_scores":
                with self.remote.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id, date, fastest_burst_wpm, burst_duration_sec,
                               burst_key_count, timestamp, burst_duration_ms, encrypted_data
                        FROM high_scores
                        WHERE user_id = %s
                    """, (self.user_id,))
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
                                log.warning(f"Failed to decrypt high score: {e}")
                        data.append(record)

            elif table == "daily_summaries":
                with self.remote.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT date, total_keystrokes, total_bursts, avg_wpm,
                               slowest_keycode, slowest_key_name, total_typing_sec,
                               summary_sent, encrypted_data
                        FROM daily_summaries
                        WHERE user_id = %s
                    """, (self.user_id,))
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
                                log.warning(f"Failed to decrypt daily summary: {e}")
                        data.append(record)

        except Exception as e:
            log.error(f"Failed to get remote data for {table}: {e}")

        return data

    def _should_push_record(self, table: str, record: dict, remote_data: list[dict]) -> bool:
        """Check if record should be pushed to remote.

        Args:
            table: Table name
            record: Local record
            remote_data: All remote records

        Returns:
            True if record should be pushed
        """
        # Check for duplicates
        remote_match = self._find_remote_match(table, record, remote_data)
        return remote_match is None

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
                    cursor.execute("""
                        INSERT INTO statistics
                        (keycode, key_name, layout, avg_press_time, total_presses,
                         slowest_ms, fastest_ms, last_updated, user_id, encrypted_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, keycode, layout) DO NOTHING
                    """, (
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
                    ))

                elif table == "word_statistics":
                    cursor.execute("""
                        INSERT INTO word_statistics
                        (word, layout, avg_speed_ms_per_letter, total_letters,
                         total_duration_ms, observation_count, last_seen,
                         backspace_count, editing_time_ms, user_id, encrypted_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, word, layout) DO NOTHING
                    """, (
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
                    ))

                elif table == "high_scores":
                    cursor.execute("""
                        INSERT INTO high_scores
                        (id, date, fastest_burst_wpm, burst_duration_sec,
                         burst_key_count, timestamp, burst_duration_ms, user_id, encrypted_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, id) DO NOTHING
                    """, (
                        record.get("id"),
                        record.get("date"),
                        record.get("fastest_burst_wpm"),
                        record.get("burst_duration_sec"),
                        record.get("burst_key_count"),
                        record.get("timestamp"),
                        record.get("burst_duration_ms"),
                        self.user_id,
                        encrypted_data,
                    ))

                elif table == "daily_summaries":
                    cursor.execute("""
                        INSERT INTO daily_summaries
                        (date, total_keystrokes, total_bursts, avg_wpm,
                         slowest_keycode, slowest_key_name, total_typing_sec,
                         summary_sent, user_id, encrypted_data)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (user_id, date) DO NOTHING
                    """, (
                        record.get("date"),
                        record.get("total_keystrokes"),
                        record.get("total_bursts"),
                        record.get("avg_wpm"),
                        record.get("slowest_keycode"),
                        record.get("slowest_key_name"),
                        record.get("total_typing_sec"),
                        record.get("summary_sent"),
                        self.user_id,
                        encrypted_data,
                    ))

                conn.commit()
            return True
        except Exception as e:
            log.error(f"Failed to push record to {table}: {e}")
            return False

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
                    cursor.execute("""
                        INSERT OR IGNORE INTO statistics
                        (keycode, key_name, layout, avg_press_time, total_presses,
                         slowest_ms, fastest_ms, last_updated)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.get("keycode"),
                        record.get("key_name"),
                        record.get("layout"),
                        record.get("avg_press_time"),
                        record.get("total_presses"),
                        record.get("slowest_ms"),
                        record.get("fastest_ms"),
                        record.get("last_updated"),
                    ))

                elif table == "word_statistics":
                    cursor.execute("""
                        INSERT OR IGNORE INTO word_statistics
                        (word, layout, avg_speed_ms_per_letter, total_letters,
                         total_duration_ms, observation_count, last_seen,
                         backspace_count, editing_time_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.get("word"),
                        record.get("layout"),
                        record.get("avg_speed_ms_per_letter"),
                        record.get("total_letters"),
                        record.get("total_duration_ms"),
                        record.get("observation_count"),
                        record.get("last_seen"),
                        record.get("backspace_count"),
                        record.get("editing_time_ms"),
                    ))

                elif table == "high_scores":
                    cursor.execute("""
                        INSERT OR IGNORE INTO high_scores
                        (id, date, fastest_burst_wpm, burst_duration_sec,
                         burst_key_count, timestamp, burst_duration_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.get("id"),
                        record.get("date"),
                        record.get("fastest_burst_wpm"),
                        record.get("burst_duration_sec"),
                        record.get("burst_key_count"),
                        record.get("timestamp"),
                        record.get("burst_duration_ms"),
                    ))

                elif table == "daily_summaries":
                    cursor.execute("""
                        INSERT OR IGNORE INTO daily_summaries
                        (date, total_keystrokes, total_bursts, avg_wpm,
                         slowest_keycode, slowest_key_name, total_typing_sec, summary_sent)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record.get("date"),
                        record.get("total_keystrokes"),
                        record.get("total_bursts"),
                        record.get("avg_wpm"),
                        record.get("slowest_keycode"),
                        record.get("slowest_key_name"),
                        record.get("total_typing_sec"),
                        1 if record.get("summary_sent") else 0,
                    ))

                conn.commit()
            return True
        except Exception as e:
            log.error(f"Failed to pull record from {table}: {e}")
            return False

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
            # Merge: weighted average of press times
            local_presses = local.get("total_presses", 0)
            remote_presses = remote.get("total_presses", 0)
            total_presses = local_presses + remote_presses

            if total_presses == 0:
                return local

            local_avg = local.get("avg_press_time", 0)
            remote_avg = remote.get("avg_press_time", 0)

            merged_avg = (local_avg * local_presses + remote_avg * remote_presses) / total_presses

            return {
                **local,
                "avg_press_time": merged_avg,
                "total_presses": total_presses,
                "slowest_ms": min(local.get("slowest_ms", 0), remote.get("slowest_ms", 0)),
                "fastest_ms": max(local.get("fastest_ms", 0), remote.get("fastest_ms", 0)),
            }

        elif table == "word_statistics":
            # Merge: weighted average by observation_count
            local_count = local.get("observation_count", 0)
            remote_count = remote.get("observation_count", 0)
            total_count = local_count + remote_count

            if total_count == 0:
                return local

            local_speed = local.get("avg_speed_ms_per_letter", 0)
            remote_speed = remote.get("avg_speed_ms_per_letter", 0)

            merged_speed = (local_speed * local_count + remote_speed * remote_count) / total_count

            return {
                **local,
                "avg_speed_ms_per_letter": merged_speed,
                "total_letters": local.get("total_letters", 0) + remote.get("total_letters", 0),
                "total_duration_ms": local.get("total_duration_ms", 0) + remote.get("total_duration_ms", 0),
                "observation_count": total_count,
            }

        elif table == "high_scores":
            # Keep higher WPM
            local_wpm = local.get("fastest_burst_wpm", 0)
            remote_wpm = remote.get("fastest_burst_wpm", 0)
            return local if local_wpm >= remote_wpm else remote

        elif table == "daily_summaries":
            # Merge: sum keystrokes/bursts, recalculate avg
            total_keystrokes = local.get("total_keystrokes", 0) + remote.get("total_keystrokes", 0)
            total_bursts = local.get("total_bursts", 0) + remote.get("total_bursts", 0)

            # Recalculate weighted average WPM
            local_bursts = local.get("total_bursts", 0) or 1
            remote_bursts = remote.get("total_bursts", 0) or 1
            total_bursts_for_avg = local_bursts + remote_bursts

            local_wpm = local.get("avg_wpm", 0)
            remote_wpm = remote.get("avg_wpm", 0)
            merged_wpm = (local_wpm * local_bursts + remote_wpm * remote_bursts) / total_bursts_for_avg

            return {
                **local,
                "total_keystrokes": total_keystrokes,
                "total_bursts": total_bursts,
                "avg_wpm": merged_wpm,
            }

        return None

    def _find_local_match(self, table: str, record: dict, local_data: list[dict]) -> dict | None:
        """Find matching local record for remote record.

        Args:
            table: Table name
            record: Remote record
            local_data: All local records

        Returns:
            Matching local record or None
        """
        for local_record in local_data:
            if self._records_match(table, record, local_record):
                return local_record
        return None

    def _find_remote_match(self, table: str, record: dict, remote_data: list[dict]) -> dict | None:
        """Find matching remote record for local record.

        Args:
            table: Table name
            record: Local record
            remote_data: All remote records

        Returns:
            Matching remote record or None
        """
        for remote_record in remote_data:
            if self._records_match(table, record, remote_record):
                return remote_record
        return None

    def _records_match(self, table: str, record1: dict, record2: dict) -> bool:
        """Check if two records match (are duplicates).

        Args:
            table: Table name
            record1: First record
            record2: Second record

        Returns:
            True if records match
        """
        if table == "bursts":
            # Compare by start_time + user_id
            return record1.get("start_time") == record2.get("start_time")

        elif table == "statistics":
            # Compare by keycode + layout
            return (
                record1.get("keycode") == record2.get("keycode")
                and record1.get("layout") == record2.get("layout")
            )

        elif table == "word_statistics":
            # Compare by word + layout
            return (
                record1.get("word") == record2.get("word")
                and record1.get("layout") == record2.get("layout")
            )

        elif table == "high_scores":
            # Compare by date
            return record1.get("date") == record2.get("date")

        elif table == "daily_summaries":
            # Compare by date
            return record1.get("date") == record2.get("date")

        return False

    def _encrypt_record(self, table: str, record: dict) -> str:
        """Encrypt a record for storage.

        Args:
            table: Table name
            record: Record to encrypt

        Returns:
            Base64 encoded encrypted data
        """
        if not self.encryption:
            raise ValueError("Encryption not enabled")

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

        # Add other table types as needed
        return ""

    def _decrypt_record(self, table: str, record: dict) -> dict:
        """Decrypt a record from storage.

        Args:
            table: Table name
            record: Record with encrypted_data field

        Returns:
            Decrypted record dictionary
        """
        if not self.encryption:
            raise ValueError("Encryption not enabled")

        encrypted_data = record.get("encrypted_data")
        if not encrypted_data:
            return record

        if table == "bursts":
            return self.encryption.decrypt_burst(encrypted_data)

        # Add other table types as needed
        return record

    def _update_local_record(self, table: str, record: dict) -> bool:
        """Update a local record with merged data.

        Args:
            table: Table name
            record: Record to update

        Returns:
            True if successful
        """
        try:
            log.info(f"Updating local record in {table}, local adapter type: {type(self.local).__name__}")
            with self.local.get_connection() as conn:
                cursor = conn.cursor()
                log.info(f"Connection type: {type(conn).__name__}, cursor type: {type(cursor).__name__}")

                if table == "statistics":
                    cursor.execute("""
                        UPDATE statistics
                        SET avg_press_time = ?,
                            total_presses = ?,
                            slowest_ms = ?,
                            fastest_ms = ?,
                            last_updated = ?
                        WHERE keycode = ? AND layout = ?
                    """, (
                        record.get("avg_press_time"),
                        record.get("total_presses"),
                        record.get("slowest_ms"),
                        record.get("fastest_ms"),
                        record.get("last_updated"),
                        record.get("keycode"),
                        record.get("layout"),
                    ))

                elif table == "word_statistics":
                    cursor.execute("""
                        UPDATE word_statistics
                        SET avg_speed_ms_per_letter = ?,
                            total_letters = ?,
                            total_duration_ms = ?,
                            observation_count = ?,
                            last_seen = ?
                        WHERE word = ? AND layout = ?
                    """, (
                        record.get("avg_speed_ms_per_letter"),
                        record.get("total_letters"),
                        record.get("total_duration_ms"),
                        record.get("observation_count"),
                        record.get("last_seen"),
                        record.get("word"),
                        record.get("layout"),
                    ))

                elif table == "high_scores":
                    cursor.execute("""
                        UPDATE high_scores
                        SET fastest_burst_wpm = ?,
                            burst_duration_sec = ?,
                            burst_key_count = ?,
                            timestamp = ?,
                            burst_duration_ms = ?
                        WHERE id = ?
                    """, (
                        record.get("fastest_burst_wpm"),
                        record.get("burst_duration_sec"),
                        record.get("burst_key_count"),
                        record.get("timestamp"),
                        record.get("burst_duration_ms"),
                        record.get("id"),
                    ))

                elif table == "daily_summaries":
                    cursor.execute("""
                        UPDATE daily_summaries
                        SET total_keystrokes = ?,
                            total_bursts = ?,
                            avg_wpm = ?
                        WHERE date = ?
                    """, (
                        record.get("total_keystrokes"),
                        record.get("total_bursts"),
                        record.get("avg_wpm"),
                        record.get("date"),
                    ))

                conn.commit()
            return True
        except Exception as e:
            log.error(f"Failed to update local record in {table}: {e}")
            return False
