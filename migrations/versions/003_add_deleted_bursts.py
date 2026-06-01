"""Add deleted_bursts table for tracking permanently deleted bursts.

This table prevents re-downloading of bursts that have been explicitly
deleted by the user from the remote database during sync operations.

Revision ID: 003
Revises: 002
Create Date: 2025-05-04

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create deleted_bursts table.

    Detects database dialect and creates appropriate schema:
    - SQLite: Standard schema
    - PostgreSQL: Includes user_id for multi-user support
    """
    # Get database dialect
    conn = op.get_bind()
    dialect_name = conn.dialect.name

    log_msg = f"Adding deleted_bursts table for {dialect_name}"
    print(log_msg)

    if dialect_name == "sqlite":
        _create_sqlite_deleted_bursts()
    elif dialect_name == "postgresql":
        _create_postgresql_deleted_bursts()
    else:
        raise ValueError(f"Unsupported dialect: {dialect_name}")


def downgrade() -> None:
    """Drop deleted_bursts table."""
    op.drop_table("deleted_bursts")


def _create_sqlite_deleted_bursts() -> None:
    """Create SQLite deleted_bursts table."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deleted_bursts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time INTEGER NOT NULL UNIQUE,
            deleted_at INTEGER NOT NULL DEFAULT (strftime('%s', 'now') * 1000)
        )
    """.strip()
    )

    # Create index on start_time for efficient lookup during sync
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_deleted_bursts_start_time
        ON deleted_bursts(start_time)
    """.strip()
    )


def _create_postgresql_deleted_bursts() -> None:
    """Create PostgreSQL deleted_bursts table with user support."""
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deleted_bursts (
            id SERIAL PRIMARY KEY,
            user_id UUID NOT NULL,
            start_time BIGINT NOT NULL,
            deleted_at BIGINT NOT NULL DEFAULT (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT
        )
    """.strip()
    )

    # Create unique constraint to prevent duplicate entries
    op.execute(
        """
        ALTER TABLE deleted_bursts ADD CONSTRAINT uq_deleted_bursts_user_start_time
        UNIQUE (user_id, start_time)
    """.strip()
    )

    # Create index on user_id and start_time for efficient lookup during sync
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_deleted_bursts_user_start_time
        ON deleted_bursts(user_id, start_time)
    """.strip()
    )
