"""SQLite migration runner for Alembic migrations.

Handles SQLite-specific migration logic including batch mode support.
"""

import logging
from contextlib import contextmanager
from pathlib import Path

import sqlalchemy.pool
from alembic.config import Config
from sqlalchemy import create_engine

from core.migration_runner import MigrationRunner

log = logging.getLogger("realtypecoach.sqlite_migration_runner")


class SQLiteMigrationRunner(MigrationRunner):
    """Migration runner for SQLite databases.

    Uses SQLite batch mode for migrations that require table recreation.
    """

    def __init__(self, db_path: Path, migration_dir: Path):
        """Initialize SQLite migration runner.

        Args:
            db_path: Path to SQLite database file
            migration_dir: Path to migrations directory
        """
        super().__init__(migration_dir)
        self.db_path = db_path

    def _create_alembic_config(self) -> Config:
        """Create Alembic configuration for SQLite.

        Returns:
            Alembic Config object configured for SQLite
        """
        config = Config()
        config.set_main_option("script_location", str(self.migration_dir))
        config.set_main_option("sqlalchemy.url", f"sqlite:///{self.db_path}")

        # Set render_as_batch for SQLite (allows ALTER TABLE operations)
        config.attributes["connection"] = None  # Will be set per-operation
        config.set_main_option("render_as_batch", "true")

        return config

    @contextmanager
    def _get_connection(self):
        """Get a SQLite connection for migration operations.

        Yields:
            SQLAlchemy Connection with sqlcipher3 backend
        """
        import sqlcipher3 as sqlite3

        # Check if database file is empty (new database)
        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        log.debug(f"Migration runner: database file size check: {db_size} bytes")
        if not self.db_path.exists() or db_size == 0:
            log.info("Database file is empty or doesn't exist, skipping migrations")
            raise RuntimeError("Database file is empty, migrations not needed")

        # Import CryptoManager for key retrieval
        from utils.crypto import CryptoManager

        # Try to get encryption key with retry logic
        max_retries = 3
        encryption_key = None

        for attempt in range(max_retries):
            crypto = CryptoManager(self.db_path)
            encryption_key = crypto.get_key()
            if encryption_key:
                break
            if attempt < max_retries - 1:
                log.warning(
                    f"Encryption key not available (attempt {attempt + 1}/{max_retries}), retrying..."
                )
                import time

                time.sleep(0.5)

        if not encryption_key:
            raise RuntimeError(
                "Encryption key not available for database migration. "
                "This may indicate a keyring access issue. "
                "Ensure the keyring is accessible and the database path is correct."
            )

        # Create a raw SQLite connection with proper encryption setup
        # This avoids SQLAlchemy's pysqlcipher dialect initialization issues
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(f"PRAGMA key = \"x'{encryption_key.hex()}'\"")
        conn.execute("PRAGMA cipher_memory_security = ON")
        conn.execute("PRAGMA cipher_page_size = 4096")
        conn.execute("PRAGMA cipher_kdf_iter = 256000")
        conn.execute("PRAGMA foreign_keys = ON")

        try:
            yield conn
        finally:
            conn.close()

    def upgrade(self, revision: str = "head") -> None:
        """Run SQLite migrations with batch mode support.

        Args:
            revision: Target revision ("head" for latest)
        """
        from alembic import command
        from alembic.runtime.migration import MigrationContext

        log.info(f"Running SQLite migrations to {revision}")
        current = self.get_current_version()
        log.info(f"Current version: {current or 'none'}")

        with self._get_connection() as conn:
            context = MigrationContext.configure(conn)
            with context.begin_transaction():
                # Enable batch mode for SQLite
                context_opts = {"as_sql": False, "render_as_batch": True}
                # Set connection in config for Alembic to use
                self.config.attributes["connection"] = conn
                command.upgrade(self.config, revision)
                new_version = context.get_current_revision()
                log.info(f"Migration complete. New version: {new_version}")
