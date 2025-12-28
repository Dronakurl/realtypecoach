"""Tests for Storage class."""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
import sys
sys.path.insert(0, '.')

from core.storage import Storage


@pytest.fixture
def temp_db():
    """Create temporary database."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink()


@pytest.fixture
def storage(temp_db):
    """Create storage with temporary database."""
    return Storage(temp_db)


class TestStorage:
    """Test Storage class."""

    def test_init_database(self, storage):
        """Test database initialization."""
        # Check that tables exist
        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            assert 'key_events' in tables
            assert 'bursts' in tables
            assert 'statistics' in tables
            assert 'high_scores' in tables
            assert 'daily_summaries' in tables
            assert 'settings' in tables

    def test_store_key_event(self, storage):
        """Test storing key events."""
        storage.store_key_event(30, 'KEY_A', 1234567890, 'press', 'test_app', False)

        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM key_events")
            count = cursor.fetchone()[0]

            assert count == 1

    def test_store_burst(self, storage):
        """Test storing bursts."""
        storage.store_burst(1234567890, 1234568890, 50, 5000, 60.0, True)

        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM bursts")
            count = cursor.fetchone()[0]
            cursor.execute("SELECT duration_ms FROM bursts")
            duration = cursor.fetchone()[0]

            assert count == 1
            assert duration == 5000  # 5 seconds in milliseconds

    def test_update_daily_summary_typing_time(self, storage):
        """Test that typing time is stored correctly in daily summary."""
        date = '2025-01-01'
        keystrokes = 1000
        bursts = 10
        avg_wpm = 50.0
        slowest_keycode = 30
        slowest_key_name = 'KEY_A'
        total_typing_sec = 300  # 5 minutes

        storage.update_daily_summary(
            date, keystrokes, bursts, avg_wpm,
            slowest_keycode, slowest_key_name, total_typing_sec
        )

        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT total_typing_sec FROM daily_summaries WHERE date = ?", (date,))
            result = cursor.fetchone()

            assert result is not None
            assert result[0] == 300  # Should be 300 seconds, not 300000

    def test_get_slowest_keys_empty(self, storage):
        """Test getting slowest keys when database is empty."""
        result = storage.get_slowest_keys(limit=10)
        assert result == []

    def test_update_key_statistics(self, storage):
        """Test updating key statistics."""
        storage.update_key_statistics(30, 'KEY_A', 'us', 150.0, True, False)

        result = storage.get_slowest_keys(limit=10)

        # Check that statistics were created
        assert len(result) == 1
        keycode, key_name, avg_time = result[0]
        assert keycode == 30
        assert key_name == 'KEY_A'
        assert avg_time == 150.0

    def test_get_slowest_keys_ordering(self, storage):
        """Test that slowest keys are returned in correct order."""
        # Add keys with different average times
        storage.update_key_statistics(30, 'KEY_A', 'us', 100.0, False, False)
        storage.update_key_statistics(31, 'KEY_B', 'us', 200.0, False, False)
        storage.update_key_statistics(32, 'KEY_C', 'us', 150.0, False, False)

        result = storage.get_slowest_keys(limit=10)

        # Should be ordered by avg_press_time DESC
        assert len(result) == 3
        assert result[0][1] == 'KEY_B'  # 200ms - slowest
        assert result[1][1] == 'KEY_C'  # 150ms
        assert result[2][1] == 'KEY_A'  # 100ms - fastest
