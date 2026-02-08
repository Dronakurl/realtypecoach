"""Background sync handler for automatic PostgreSQL sync."""

import logging
import threading
import time
from typing import Any

from PySide6.QtCore import QObject, Signal

log = logging.getLogger("realtypecoach.sync")


class SyncHandler(QObject):
    """Handles automatic background sync to remote database."""

    signal_sync_completed = Signal(dict)  # Sync result
    signal_sync_failed = Signal(str)  # Error message

    def __init__(self, storage, config, enabled: bool = False, interval_sec: int = 300):
        """Initialize sync handler.

        Args:
            storage: Storage instance for sync operations
            config: Config instance for accessing settings
            enabled: Whether auto-sync is enabled
            interval_sec: Sync interval in seconds
        """
        super().__init__()
        self.storage = storage
        self.config = config
        self.enabled = enabled
        self.interval_sec = interval_sec

        self.running = False
        self._stop_event = threading.Event()
        self.sync_thread: threading.Thread | None = None
        self._sync_lock = threading.Lock()
        self._last_sync_time = 0

    def start(self) -> None:
        """Start background sync thread."""
        if self.running:
            return

        self.running = True
        self._stop_event.clear()

        self.sync_thread = threading.Thread(target=self._run_sync_loop, daemon=True)
        self.sync_thread.start()

        log.info(f"Sync handler started: enabled={self.enabled}, interval={self.interval_sec}s")

    def stop(self) -> None:
        """Stop background sync thread."""
        if not self.running:
            return

        self.running = False
        self._stop_event.set()

        if self.sync_thread:
            self.sync_thread.join(timeout=5)

        log.info("Sync handler stopped")

    def sync_now(self) -> dict[str, Any]:
        """Trigger immediate sync (can be called from UI).

        Returns:
            Sync result dictionary
        """
        log.info("Manual sync triggered")
        return self._perform_sync()

    def _run_sync_loop(self) -> None:
        """Background thread that syncs at configured interval."""
        while not self._stop_event.is_set():
            # Check if we should sync
            if self.enabled:
                self._perform_sync()

            # Wait for the interval or stop event
            self._stop_event.wait(self.interval_sec)

    def _perform_sync(self) -> dict[str, Any]:
        """Perform the actual sync operation.

        Returns:
            Sync result dictionary with success status
        """
        # Use lock to prevent concurrent syncs
        if not self._sync_lock.acquire(blocking=False):
            log.debug("Sync already in progress, skipping")
            return {"success": False, "error": "Sync already in progress"}

        try:
            # Check if postgres sync is enabled
            postgres_sync_enabled = self.config.get_bool("postgres_sync_enabled", False)
            if not postgres_sync_enabled:
                log.debug("Skipping sync: postgres_sync_enabled is False")
                return {"success": False, "error": "PostgreSQL sync not enabled"}

            # Check if postgres is configured
            host = self.config.get("postgres_host", "")
            user = self.config.get("postgres_user", "")
            if not host or not user:
                log.warning("Skipping sync: PostgreSQL not configured")
                return {"success": False, "error": "PostgreSQL not configured"}

            log.info("Starting automatic sync...")
            start_time = time.time()

            # Perform the sync
            result = self.storage.merge_with_remote()

            duration_ms = int((time.time() - start_time) * 1000)
            result["duration_ms"] = duration_ms

            if result["success"]:
                # Check if exclude_names_enabled setting changed during sync
                local_exclude_names = self.config.get_bool("exclude_names_enabled", False)
                remote_exclude_names_str = self.storage.adapter.get_setting("exclude_names_enabled")
                remote_exclude_names = False
                if remote_exclude_names_str is not None:
                    remote_exclude_names = remote_exclude_names_str.lower() in ("true", "1", "yes")

                # If remote has exclude_names_enabled=True and local was False, update config and delete names
                if remote_exclude_names and not local_exclude_names:
                    log.info(
                        "Remote exclude_names_enabled is True, deleting names from local database"
                    )
                    try:
                        deleted_count = self.storage.delete_all_names_from_database()
                        log.info(f"Deleted {deleted_count} name statistics after sync")
                        # Update local config
                        self.config.set("exclude_names_enabled", True)
                        # Update the running dictionary so the setting takes effect immediately
                        self.storage.update_exclude_names_setting(True)
                        log.info("Updated dictionary exclude_names setting to True after sync")
                    except Exception as e:
                        log.error(f"Failed to delete names after sync: {e}")
                # If remote has exclude_names_enabled=False and local was True, update config
                elif not remote_exclude_names and local_exclude_names:
                    log.info(
                        "Remote exclude_names_enabled is False, disabling exclude names locally"
                    )
                    try:
                        # Update local config
                        self.config.set("exclude_names_enabled", False)
                        # Update the running dictionary so the setting takes effect immediately
                        self.storage.update_exclude_names_setting(False)
                        log.info("Updated dictionary exclude_names setting to False after sync")
                    except Exception as e:
                        log.error(f"Failed to disable exclude names after sync: {e}")

                self._last_sync_time = time.time()
                log.info(
                    f"Sync completed: pushed={result['pushed']}, "
                    f"pulled={result['pulled']}, duration={duration_ms}ms"
                )
                self.signal_sync_completed.emit(result)
            else:
                error = result.get("error", "Unknown error")
                log.error(f"Sync failed: {error}")
                self.signal_sync_failed.emit(error)

            return result

        except Exception as e:
            error_msg = str(e)
            log.error(f"Sync error: {error_msg}")
            self.signal_sync_failed.emit(error_msg)
            return {"success": False, "error": error_msg}

        finally:
            self._sync_lock.release()

    def update_settings(self, enabled: bool, interval_sec: int) -> None:
        """Update sync settings and restart if necessary.

        Args:
            enabled: New enabled state
            interval_sec: New interval in seconds
        """
        settings_changed = self.enabled != enabled or self.interval_sec != interval_sec

        self.enabled = enabled
        self.interval_sec = interval_sec

        if settings_changed and self.running:
            log.info(f"Sync settings changed: enabled={enabled}, interval={interval_sec}s")
            # Stop and restart to apply new settings
            self.stop()
            if enabled:
                self.start()
        elif not self.running and enabled:
            # Start if previously disabled
            self.start()
