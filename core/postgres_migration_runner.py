"""PostgreSQL migration runner for Alembic migrations.

Handles PostgreSQL-specific migration logic.
"""

import logging
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config

from core.migration_runner import MigrationRunner

log = logging.getLogger("realtypecoach.postgres_migration_runner")


class PostgreSQLMigrationRunner(MigrationRunner):
    """Migration runner for PostgreSQL databases.

    Standard PostgreSQL migrations without special batch mode requirements.
    """

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        sslmode: str = "require",
        migration_dir: Path | None = None,
    ):
        """Initialize PostgreSQL migration runner.

        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            database: Database name
            user: Database user
            password: Database password
            sslmode: SSL mode (require, prefer, disable)
            migration_dir: Path to migrations directory
        """
        if migration_dir is None:
            # Default to migrations/ directory relative to project root
            import os

            project_root = Path(os.path.dirname(os.path.dirname(__file__)))
            migration_dir = project_root / "migrations"

        super().__init__(migration_dir)
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.sslmode = sslmode

    def _create_alembic_config(self) -> Config:
        """Create Alembic configuration for PostgreSQL.

        Returns:
            Alembic Config object configured for PostgreSQL
        """
        config = Config()
        config.set_main_option("script_location", str(self.migration_dir))

        # Build PostgreSQL connection URL
        url = (
            f"postgresql://{self.user}:{self.password}@"
            f"{self.host}:{self.port}/{self.database}"
            f"?sslmode={self.sslmode}"
        )
        config.set_main_option("sqlalchemy.url", url)

        config.attributes["connection"] = None  # Will be set per-operation

        return config

    @contextmanager
    def _get_connection(self):
        """Get a PostgreSQL connection for migration operations.

        Yields:
            psycopg2 connection
        """
        import psycopg2

        conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
            sslmode=self.sslmode,
        )
        conn.autocommit = False

        try:
            yield conn
        finally:
            conn.close()

    def upgrade(self, revision: str = "head") -> None:
        """Run PostgreSQL migrations.

        Args:
            revision: Target revision ("head" for latest)
        """
        from alembic import command
        from alembic.runtime.migration import MigrationContext

        log.info(f"Running PostgreSQL migrations to {revision}")
        current = self.get_current_version()
        log.info(f"Current version: {current or 'none'}")

        with self._get_connection() as conn:
            context = MigrationContext.configure(conn)
            with context.begin_transaction():
                with self.config.attributes["connection"] as conn:
                    command.upgrade(self.config, revision)
                    new_version = context.get_current_revision()
                    log.info(f"Migration complete. New version: {new_version}")
