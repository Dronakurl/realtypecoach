"""Add sync_log table for tracking sync operations.

Creates sync_log table to track sync operations with per-table breakdown.
Revision ID: 002
Revises: 001
Create Date: 2026-02-22

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create sync_log table.

    Detects database dialect and creates appropriate schema:
    - SQLite: Standard schema without user_id
    - PostgreSQL: Includes user_id for multi-user support
    """
    # Get database dialect
    conn = op.get_bind()
    dialect_name = conn.dialect.name

    log_msg = f"Adding sync_log table for {dialect_name}"
    print(log_msg)

    if dialect_name == "sqlite":
        _create_sqlite_sync_log()
    elif dialect_name == "postgresql":
        _create_postgresql_sync_log()
    else:
        raise ValueError(f"Unsupported dialect: {dialect_name}")


def downgrade() -> None:
    """Drop sync_log table."""
    op.drop_table("sync_log")


def _create_sqlite_sync_log() -> None:
    """Create SQLite sync_log table without user support."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp INTEGER NOT NULL,
            machine_name TEXT NOT NULL,
            pushed INTEGER NOT NULL DEFAULT 0,
            pulled INTEGER NOT NULL DEFAULT 0,
            merged INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            table_breakdown TEXT
        )
    """.strip()
    )

    # Create index on timestamp for efficient querying
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_log_timestamp
        ON sync_log(timestamp DESC)
    """.strip()
    )


def _create_postgresql_sync_log() -> None:
    """Create PostgreSQL sync_log table with user support."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_log (
            id SERIAL PRIMARY KEY,
            user_id UUID NOT NULL,
            timestamp BIGINT NOT NULL,
            machine_name TEXT NOT NULL,
            pushed INTEGER NOT NULL DEFAULT 0,
            pulled INTEGER NOT NULL DEFAULT 0,
            merged INTEGER NOT NULL DEFAULT 0,
            duration_ms INTEGER NOT NULL DEFAULT 0,
            error TEXT,
            table_breakdown TEXT
        )
    """.strip()
    )

    # Create index on user_id and timestamp for efficient querying
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sync_log_user_timestamp
        ON sync_log(user_id, timestamp DESC)
    """.strip()
    )
