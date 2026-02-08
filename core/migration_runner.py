"""Base migration runner for database migrations.

Provides common migration functionality for all database backends.
"""

import logging
from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import Self

from alembic.config import Config
from alembic.script import ScriptDirectory

log = logging.getLogger("realtypecoach.migration_runner")


class MigrationRunner(ABC):
    """Abstract base class for database migration runners.

    Handles Alembic migration execution for different database backends.
    """

    def __init__(self, migration_dir: Path):
        """Initialize migration runner.

        Args:
            migration_dir: Path to migrations directory
        """
        self.migration_dir = migration_dir
        self._config = None
        self._script_dir = None

    @abstractmethod
    def _create_alembic_config(self) -> Config:
        """Create Alembic configuration for this backend.

        Returns:
            Alembic Config object
        """
        pass

    @property
    def config(self) -> Config:
        """Get Alembic configuration (lazy initialization)."""
        if self._config is None:
            self._config = self._create_alembic_config()
        return self._config

    @property
    def script_dir(self) -> ScriptDirectory:
        """Get Alembic script directory (lazy initialization)."""
        if self._script_dir is None:
            self._script_dir = ScriptDirectory.from_config(self.config)
        return self._script_dir

    def get_current_version(self) -> str | None:
        """Get current database version.

        Returns:
            Current revision hex or None if database is not versioned
        """
        from alembic.runtime.migration import MigrationContext

        with self._get_connection() as conn:
            context = MigrationContext.configure(conn)
            return context.get_current_revision()

    def upgrade(self, revision: str = "head") -> None:
        """Run database migrations to target revision.

        Args:
            revision: Target revision ("head" for latest)
        """
        from alembic import command
        from alembic.runtime.migration import MigrationContext

        log.info(f"Running migrations to {revision}")
        current = self.get_current_version()
        log.info(f"Current version: {current or 'none'}")

        with self._get_connection() as conn:
            context = MigrationContext.configure(conn)
            with context.begin_transaction():
                with self.config.attributes["connection"] as conn:
                    command.upgrade(self.config, revision)
                    new_version = context.get_current_revision()
                    log.info(f"Migration complete. New version: {new_version}")

    def downgrade(self, revision: str) -> None:
        """Downgrade database to target revision.

        Args:
            revision: Target revision
        """
        from alembic import command
        from alembic.runtime.migration import MigrationContext

        log.info(f"Downgrading to {revision}")
        current = self.get_current_version()
        log.info(f"Current version: {current or 'none'}")

        with self._get_connection() as conn:
            context = MigrationContext.configure(conn)
            with context.begin_transaction():
                with self.config.attributes["connection"] as conn:
                    command.downgrade(self.config, revision)
                    new_version = context.get_current_revision()
                    log.info(f"Downgrade complete. New version: {new_version}")

    def check_needs_upgrade(self) -> bool:
        """Check if database needs to be upgraded.

        Returns:
            True if upgrades are available, False otherwise
        """
        from alembic.runtime.migration import MigrationContext

        current = self.get_current_version()
        if current is None:
            # Not versioned yet
            return True

        with self._get_connection() as conn:
            context = MigrationContext.configure(conn)
            return context.get_current_head() != current

    def stamp(self, revision: str) -> None:
        """Stamp database with revision without running migrations.

        Used for marking legacy databases.

        Args:
            revision: Revision to stamp
        """
        from alembic import command

        log.info(f"Stamping database as {revision}")
        with self._get_connection() as conn:
            with self.config.attributes["connection"] as conn:
                command.stamp(self.config, revision)
                log.info(f"Database stamped as {revision}")

    @abstractmethod
    @contextmanager
    def _get_connection(self):
        """Get a database connection for migration operations.

        Yields:
            Database connection
        """
        pass
