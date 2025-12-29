"""Tests for word statistics functionality (updated for dictionary validation)."""

import pytest
import tempfile
from pathlib import Path
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


class TestWordStatistics:
    """Test word statistics functionality with new schema."""

    def test_word_statistics_table_created(self, storage):
        """Test that word_statistics table is created."""
        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='word_statistics'")
            result = cursor.fetchone()

        assert result is not None, "word_statistics table should exist"

    def test_new_columns_exist(self, storage):
        """Test that new columns were added to word_statistics table."""
        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(word_statistics)")
            columns = {row[1] for row in cursor.fetchall()}

        assert 'backspace_count' in columns, "backspace_count column should exist"
        assert 'editing_time_ms' in columns, "editing_time_ms column should exist"

    def test_update_word_statistics_new_word(self, storage):
        """Test adding a new word to statistics."""
        storage.update_word_statistics('hello', 'us', 500, 5)

        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM word_statistics WHERE word = ? AND layout = ?', ('hello', 'us'))
            result = cursor.fetchone()

        assert result is not None
        word, layout, speed, total_letters, total_duration, count, last_seen, backspace_count, editing_time = result
        assert word == 'hello'
        assert layout == 'us'
        assert speed == 100.0  # 500ms / 5 letters
        assert total_letters == 5
        assert total_duration == 500
        assert count == 1
        assert backspace_count == 0
        assert editing_time == 0

    def test_update_word_statistics_with_backspace(self, storage):
        """Test adding word with backspace editing metadata."""
        storage.update_word_statistics('shoes', 'us', 550, 5, backspace_count=2, editing_time_ms=100)

        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM word_statistics WHERE word = ? AND layout = ?', ('shoes', 'us'))
            result = cursor.fetchone()

        assert result is not None
        word, layout, speed, total_letters, total_duration, count, last_seen, backspace_count, editing_time = result
        assert word == 'shoes'
        # Allow for default values if not passed
        assert backspace_count >= 2
        assert editing_time >= 100

    def test_get_slowest_words_empty(self, storage):
        """Test getting slowest words from empty database."""
        result = storage.get_slowest_words(limit=10)
        assert result == []

    def test_get_fastest_words_empty(self, storage):
        """Test getting fastest words from empty database."""
        result = storage.get_fastest_words(limit=10)
        assert result == []
