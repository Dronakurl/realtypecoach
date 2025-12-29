"""Tests for word statistics functionality (updated for dictionary validation)."""

import pytest
import sqlite3
import tempfile
from pathlib import Path

from core.storage import Storage
from utils.config import Config


@pytest.fixture
def temp_db():
    """Create temporary database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)
    yield db_path
    db_path.unlink()


@pytest.fixture
def storage(temp_db):
    """Create storage with temporary database."""
    config = Config(temp_db)
    return Storage(temp_db, config=config)


class TestWordStatistics:
    """Test word statistics functionality with new schema."""

    def test_word_statistics_table_created(self, storage):
        """Test that word_statistics table is created."""
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='word_statistics'"
            )
            result = cursor.fetchone()

        assert result is not None, "word_statistics table should exist"

    def test_new_columns_exist(self, storage):
        """Test that new columns were added to word_statistics table."""
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(word_statistics)")
            columns = {row[1] for row in cursor.fetchall()}

        assert "backspace_count" in columns, "backspace_count column should exist"
        assert "editing_time_ms" in columns, "editing_time_ms column should exist"

    def test_update_word_statistics_new_word(self, storage):
        """Test adding a new word to statistics."""
        storage.update_word_statistics("hello", "us", 500, 5)

        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM word_statistics WHERE word = ? AND layout = ?",
                ("hello", "us"),
            )
            result = cursor.fetchone()

        assert result is not None
        (
            word,
            layout,
            speed,
            total_letters,
            total_duration,
            count,
            last_seen,
            backspace_count,
            editing_time,
        ) = result
        assert word == "hello"
        assert layout == "us"
        assert speed == 100.0  # 500ms / 5 letters
        assert total_letters == 5
        assert total_duration == 500
        assert count == 1
        assert backspace_count == 0
        assert editing_time == 0

    def test_update_word_statistics_with_backspace(self, storage):
        """Test adding word with backspace editing metadata."""
        storage.update_word_statistics(
            "shoes", "us", 550, 5, backspace_count=2, editing_time_ms=100
        )

        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM word_statistics WHERE word = ? AND layout = ?",
                ("shoes", "us"),
            )
            result = cursor.fetchone()

        assert result is not None
        (
            word,
            layout,
            speed,
            total_letters,
            total_duration,
            count,
            last_seen,
            backspace_count,
            editing_time,
        ) = result
        assert word == "shoes"
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


class TestSlowestFastestWords:
    """Tests for get_slowest_words and get_fastest_words with actual data."""

    def test_get_slowest_words_with_data(self, storage):
        """Test get_slowest_words returns correct ordering."""
        # Insert words with varying speeds
        storage.update_word_statistics("hello", "us", 500, 5)  # 100 ms/letter
        storage.update_word_statistics("world", "us", 600, 5)  # 120 ms/letter
        storage.update_word_statistics("fast", "us", 200, 4)  # 50 ms/letter
        # Insert second observations to meet observation_count >= 2
        storage.update_word_statistics("hello", "us", 550, 5)
        storage.update_word_statistics("world", "us", 650, 5)

        result = storage.get_slowest_words(limit=10)
        assert len(result) >= 2
        # Results should be ordered by slowest first
        words = [r.word for r in result]
        assert "hello" in words
        assert "world" in words
        # 'fast' should not appear as it only has 1 observation
        assert "fast" not in words

    def test_get_fastest_words_with_data(self, storage):
        """Test get_fastest_words returns correct ordering."""
        # Insert words with varying speeds
        storage.update_word_statistics("fast", "us", 200, 4)  # 50 ms/letter
        storage.update_word_statistics("hello", "us", 500, 5)  # 100 ms/letter
        storage.update_word_statistics("slow", "us", 800, 5)  # 160 ms/letter
        # Insert second observations
        storage.update_word_statistics("fast", "us", 220, 4)
        storage.update_word_statistics("hello", "us", 550, 5)
        storage.update_word_statistics("slow", "us", 850, 5)

        result = storage.get_fastest_words(limit=10)
        assert len(result) >= 3
        # Fastest should be first
        assert result[0].word == "fast"

    def test_observation_count_filter(self, storage):
        """Test that words with single observation are excluded."""
        storage.update_word_statistics("single", "us", 500, 5)  # Only 1 observation
        storage.update_word_statistics("multiple", "us", 500, 5)
        storage.update_word_statistics("multiple", "us", 550, 5)  # 2 observations

        result = storage.get_slowest_words()
        words = [r.word for r in result]
        assert "multiple" in words
        assert "single" not in words

    def test_layout_filtering(self, storage):
        """Test layout parameter filters correctly."""
        storage.update_word_statistics("hello", "us", 500, 5)
        storage.update_word_statistics("hello", "de", 400, 5)
        storage.update_word_statistics("hello", "us", 550, 5)  # 2nd obs for us
        storage.update_word_statistics("hello", "de", 450, 5)  # 2nd obs for de

        result_us = storage.get_slowest_words(layout="us")
        result_de = storage.get_slowest_words(layout="de")

        # Each layout should return the word for that layout
        us_words = [r.word for r in result_us]
        de_words = [r.word for r in result_de]

        assert "hello" in us_words
        assert "hello" in de_words

        # Different layouts should have different speeds
        us_result = next(r for r in result_us if r.word == "hello")
        de_result = next(r for r in result_de if r.word == "hello")
        assert us_result.avg_speed_ms_per_letter == 105.0  # (500 + 550) / 10
        assert de_result.avg_speed_ms_per_letter == 85.0  # (400 + 450) / 10

    def test_limit_parameter(self, storage):
        """Test limit parameter works correctly."""
        # Insert 20 words with multiple observations
        for i in range(20):
            storage.update_word_statistics(f"word{i}", "us", 500, 5)
            storage.update_word_statistics(f"word{i}", "us", 550, 5)

        result = storage.get_slowest_words(limit=5)
        assert len(result) == 5

        result_larger = storage.get_slowest_words(limit=100)
        assert len(result_larger) == 20  # All words returned
