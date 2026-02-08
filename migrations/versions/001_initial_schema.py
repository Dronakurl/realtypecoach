"""Initial schema migration.

Creates all database tables with support for both SQLite and PostgreSQL.
PostgreSQL includes additional columns for multi-user support and encryption.

Revision ID: 001
Revises:
Create Date: 2025-02-08

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create initial database schema.

    Detects database dialect and creates appropriate schema:
    - SQLite: Standard schema without user_id and encrypted_data
    - PostgreSQL: Includes user_id and encrypted_data columns for multi-user support
    """
    # Get database dialect
    conn = op.get_bind()
    dialect_name = conn.dialect.name

    log_msg = f"Creating initial schema for {dialect_name}"
    print(log_msg)

    if dialect_name == 'sqlite':
        _create_sqlite_schema()
    elif dialect_name == 'postgresql':
        _create_postgresql_schema()
    else:
        raise ValueError(f"Unsupported dialect: {dialect_name}")


def downgrade() -> None:
    """Drop all tables."""
    # Get database dialect
    conn = op.get_bind()
    dialect_name = conn.dialect.name

    # Drop tables in reverse order of creation
    op.drop_table('llm_prompts')
    op.drop_table('settings')
    op.drop_table('ignored_words')
    op.drop_table('word_statistics')
    op.drop_table('daily_summaries')
    op.drop_table('high_scores')
    op.drop_table('digraph_statistics')
    op.drop_table('statistics')
    op.drop_table('bursts')


def _create_sqlite_schema() -> None:
    """Create SQLite schema without user support."""

    # Bursts table
    op.execute("""
        CREATE TABLE IF NOT EXISTS bursts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time INTEGER NOT NULL UNIQUE,
            end_time INTEGER NOT NULL,
            key_count INTEGER NOT NULL,
            backspace_count INTEGER DEFAULT 0,
            net_key_count INTEGER DEFAULT 0,
            duration_ms INTEGER NOT NULL,
            avg_wpm REAL,
            qualifies_for_high_score INTEGER DEFAULT 0
        )
    """.strip())

    # Statistics table
    op.execute("""
        CREATE TABLE IF NOT EXISTS statistics (
            keycode INTEGER NOT NULL,
            key_name TEXT NOT NULL,
            layout TEXT NOT NULL,
            avg_press_time REAL,
            total_presses INTEGER,
            slowest_ms REAL,
            fastest_ms REAL,
            last_updated INTEGER,
            PRIMARY KEY (keycode, layout)
        )
    """.strip())

    # Digraph statistics table
    op.execute("""
        CREATE TABLE IF NOT EXISTS digraph_statistics (
            first_keycode INTEGER NOT NULL,
            second_keycode INTEGER NOT NULL,
            first_key TEXT NOT NULL,
            second_key TEXT NOT NULL,
            layout TEXT NOT NULL,
            avg_interval_ms REAL NOT NULL,
            total_sequences INTEGER NOT NULL DEFAULT 1,
            slowest_ms REAL,
            fastest_ms REAL,
            last_updated INTEGER,
            PRIMARY KEY (first_keycode, second_keycode, layout)
        )
    """.strip())

    # High scores table
    op.execute("""
        CREATE TABLE IF NOT EXISTS high_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            fastest_burst_wpm REAL,
            burst_duration_sec REAL,
            burst_key_count INTEGER,
            timestamp INTEGER NOT NULL UNIQUE,
            burst_duration_ms INTEGER
        )
    """.strip())

    # Daily summaries table
    op.execute("""
        CREATE TABLE IF NOT EXISTS daily_summaries (
            date TEXT PRIMARY KEY,
            total_keystrokes INTEGER,
            total_bursts INTEGER,
            avg_wpm REAL,
            slowest_keycode INTEGER,
            slowest_key_name TEXT,
            total_typing_sec INTEGER,
            summary_sent INTEGER DEFAULT 0
        )
    """.strip())

    # Word statistics table
    op.execute("""
        CREATE TABLE IF NOT EXISTS word_statistics (
            word TEXT NOT NULL,
            layout TEXT NOT NULL,
            avg_speed_ms_per_letter REAL NOT NULL,
            total_letters INTEGER NOT NULL,
            total_duration_ms INTEGER NOT NULL,
            observation_count INTEGER NOT NULL,
            last_seen INTEGER NOT NULL,
            backspace_count INTEGER DEFAULT 0,
            editing_time_ms INTEGER DEFAULT 0,
            PRIMARY KEY (word, layout)
        )
    """.strip())

    # Ignored words table (hash-based)
    op.execute("""
        CREATE TABLE IF NOT EXISTS ignored_words (
            word_hash TEXT PRIMARY KEY,
            added_at INTEGER NOT NULL
        )
    """.strip())

    # Settings table
    op.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at INTEGER NOT NULL
        )
    """.strip())

    # LLM prompts table
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            content TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            is_default BOOLEAN DEFAULT 0
        )
    """.strip())


def _create_postgresql_schema() -> None:
    """Create PostgreSQL schema with user support and encryption."""

    # Bursts table
    op.execute("""
        CREATE TABLE IF NOT EXISTS bursts (
            id SERIAL PRIMARY KEY,
            user_id UUID NOT NULL,
            start_time BIGINT NOT NULL,
            end_time BIGINT NOT NULL,
            key_count INTEGER NOT NULL,
            backspace_count INTEGER DEFAULT 0,
            net_key_count INTEGER DEFAULT 0,
            duration_ms INTEGER NOT NULL,
            avg_wpm DOUBLE PRECISION,
            qualifies_for_high_score INTEGER DEFAULT 0,
            UNIQUE(user_id, start_time)
        )
    """.strip())

    # Statistics table
    op.execute("""
        CREATE TABLE IF NOT EXISTS statistics (
            user_id UUID NOT NULL,
            keycode INTEGER NOT NULL,
            key_name TEXT NOT NULL,
            layout TEXT NOT NULL,
            avg_press_time DOUBLE PRECISION,
            total_presses INTEGER,
            slowest_ms DOUBLE PRECISION,
            fastest_ms DOUBLE PRECISION,
            last_updated BIGINT,
            PRIMARY KEY (user_id, keycode, layout)
        )
    """.strip())

    # Digraph statistics table
    op.execute("""
        CREATE TABLE IF NOT EXISTS digraph_statistics (
            user_id UUID NOT NULL,
            first_keycode INTEGER NOT NULL,
            second_keycode INTEGER NOT NULL,
            first_key TEXT NOT NULL,
            second_key TEXT NOT NULL,
            layout TEXT NOT NULL,
            avg_interval_ms DOUBLE PRECISION NOT NULL,
            total_sequences INTEGER NOT NULL DEFAULT 1,
            slowest_ms DOUBLE PRECISION,
            fastest_ms DOUBLE PRECISION,
            last_updated BIGINT,
            PRIMARY KEY (user_id, first_keycode, second_keycode, layout)
        )
    """.strip())

    # High scores table
    op.execute("""
        CREATE TABLE IF NOT EXISTS high_scores (
            id SERIAL PRIMARY KEY,
            user_id UUID NOT NULL,
            date TEXT NOT NULL,
            fastest_burst_wpm DOUBLE PRECISION,
            burst_duration_sec DOUBLE PRECISION,
            burst_key_count INTEGER,
            timestamp BIGINT NOT NULL,
            burst_duration_ms INTEGER,
            UNIQUE(user_id, timestamp)
        )
    """.strip())

    # Daily summaries table
    op.execute("""
        CREATE TABLE IF NOT EXISTS daily_summaries (
            user_id UUID NOT NULL,
            date TEXT NOT NULL,
            total_keystrokes INTEGER,
            total_bursts INTEGER,
            avg_wpm DOUBLE PRECISION,
            slowest_keycode INTEGER,
            slowest_key_name TEXT,
            total_typing_sec INTEGER,
            summary_sent INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, date)
        )
    """.strip())

    # Word statistics table
    op.execute("""
        CREATE TABLE IF NOT EXISTS word_statistics (
            user_id UUID NOT NULL,
            word TEXT NOT NULL,
            layout TEXT NOT NULL,
            avg_speed_ms_per_letter DOUBLE PRECISION NOT NULL,
            total_letters INTEGER NOT NULL,
            total_duration_ms INTEGER NOT NULL,
            observation_count INTEGER NOT NULL,
            last_seen BIGINT NOT NULL,
            backspace_count INTEGER DEFAULT 0,
            editing_time_ms INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, word, layout)
        )
    """.strip())

    # Ignored words table (hash-based)
    op.execute("""
        CREATE TABLE IF NOT EXISTS ignored_words (
            user_id UUID NOT NULL,
            word_hash TEXT NOT NULL,
            added_at BIGINT NOT NULL,
            PRIMARY KEY (user_id, word_hash)
        )
    """.strip())

    # Settings table
    op.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            user_id UUID NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at BIGINT NOT NULL,
            PRIMARY KEY (user_id, key)
        )
    """.strip())

    # LLM prompts table
    op.execute("""
        CREATE TABLE IF NOT EXISTS llm_prompts (
            id SERIAL PRIMARY KEY,
            user_id UUID NOT NULL,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at BIGINT NOT NULL,
            updated_at BIGINT NOT NULL,
            is_default INTEGER DEFAULT 0,
            UNIQUE(user_id, name)
        )
    """.strip())
