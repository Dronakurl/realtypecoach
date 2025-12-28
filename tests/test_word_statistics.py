"""Tests for word statistics functionality."""

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
    """Test word statistics functionality."""

    def test_word_statistics_table_created(self, storage):
        """Test that word_statistics table is created."""
        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='word_statistics'")
            result = cursor.fetchone()
            assert result is not None, "word_statistics table should exist"

    def test_is_letter_key(self, storage):
        """Test letter key detection."""
        assert storage._is_letter_key('a') is True
        assert storage._is_letter_key('A') is True
        assert storage._is_letter_key('ä') is True  # German umlaut
        assert storage._is_letter_key('ö') is True
        assert storage._is_letter_key('ü') is True
        assert storage._is_letter_key('ß') is True
        assert storage._is_letter_key('SPACE') is False
        assert storage._is_letter_key('ENTER') is False
        assert storage._is_letter_key(';') is False
        assert storage._is_letter_key('1') is False

    def test_is_word_boundary(self, storage):
        """Test word boundary detection."""
        assert storage._is_word_boundary('SPACE') is True
        assert storage._is_word_boundary('ENTER') is True
        assert storage._is_word_boundary('TAB') is True
        assert storage._is_word_boundary('BACKSPACE') is True
        assert storage._is_word_boundary('.') is True
        assert storage._is_word_boundary(',') is True
        assert storage._is_word_boundary('a') is False
        assert storage._is_word_boundary('Z') is False

    def test_update_word_statistics_new_word(self, storage):
        """Test adding a new word to statistics."""
        storage.update_word_statistics('hello', 'us', 500, 5)

        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM word_statistics WHERE word = ? AND layout = ?', ('hello', 'us'))
            result = cursor.fetchone()

        assert result is not None
        word, layout, speed, total_letters, total_duration, count, last_seen = result
        assert word == 'hello'
        assert layout == 'us'
        assert speed == 100.0  # 500ms / 5 letters
        assert total_letters == 5
        assert total_duration == 500
        assert count == 1

    def test_update_word_statistics_running_average(self, storage):
        """Test that running average is calculated correctly."""
        # First observation: 500ms / 5 letters = 100 ms/letter
        storage.update_word_statistics('test', 'us', 500, 5)

        # Second observation: 600ms / 5 letters = 120 ms/letter
        storage.update_word_statistics('test', 'us', 600, 5)

        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT avg_speed_ms_per_letter, total_letters, total_duration_ms, observation_count FROM word_statistics WHERE word = ? AND layout = ?', ('test', 'us'))
            result = cursor.fetchone()

        avg_speed, total_letters, total_duration, count = result
        assert count == 2
        assert total_letters == 10  # 5 + 5
        assert total_duration == 1100  # 500 + 600
        assert avg_speed == 110.0  # (100 * 1 + 120 * 1) / 2 = 110

    def test_process_key_events_word_detection(self, storage):
        """Test word detection from key events."""
        import time
        base_time = int(time.time() * 1000)

        # Type "hello "
        events = [
            (35, 'h', base_time),
            (18, 'e', base_time + 50),
            (38, 'l', base_time + 100),
            (38, 'l', base_time + 150),
            (24, 'o', base_time + 200),
            (57, 'SPACE', base_time + 250),
        ]

        for keycode, key_name, timestamp in events:
            storage.store_key_event(keycode, key_name, timestamp, 'press', 'test_app', False)

        # Process events
        processed = storage._process_new_key_events(layout='us', max_events=100)
        assert processed == 6

        # Check that 'hello' was detected
        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT word FROM word_statistics WHERE word = ?', ('hello',))
            result = cursor.fetchone()

        assert result is not None
        assert result[0] == 'hello'

    def test_process_key_events_short_words_ignored(self, storage):
        """Test that words < 3 letters are ignored."""
        import time
        base_time = int(time.time() * 1000)

        # Type "hi " (2 letters, should be ignored)
        events = [
            (35, 'h', base_time),
            (23, 'i', base_time + 50),
            (57, 'SPACE', base_time + 100),
        ]

        for keycode, key_name, timestamp in events:
            storage.store_key_event(keycode, key_name, timestamp, 'press', 'test_app', False)

        storage._process_new_key_events(layout='us', max_events=100)

        # Check that 'hi' is NOT in word_statistics
        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM word_statistics WHERE word = ?', ('hi',))
            count = cursor.fetchone()[0]

        assert count == 0

    def test_get_slowest_words_empty(self, storage):
        """Test getting slowest words from empty database."""
        result = storage.get_slowest_words(limit=10)
        assert result == []

    def test_get_fastest_words_empty(self, storage):
        """Test getting fastest words from empty database."""
        result = storage.get_fastest_words(limit=10)
        assert result == []

    def test_get_slowest_words_with_data(self, storage):
        """Test getting slowest words."""
        # Add words with different speeds
        storage.update_word_statistics('quick', 'us', 600, 5)   # 120 ms/letter
        storage.update_word_statistics('the', 'us', 120, 3)     # 40 ms/letter
        storage.update_word_statistics('hello', 'us', 500, 5)    # 100 ms/letter
        storage.update_word_statistics('the', 'us', 130, 3)      # Second observation

        result = storage.get_slowest_words(limit=5)

        # Should return sorted by avg_speed_ms_per_letter DESC
        # Note: Need >= 2 observations for each word
        storage.update_word_statistics('quick', 'us', 620, 5)
        storage.update_word_statistics('hello', 'us', 510, 5)

        result = storage.get_slowest_words(limit=5)
        assert len(result) == 3

        word, speed, duration, letters = result[0]
        assert word == 'quick'  # Slowest
        assert speed > 100

        word, speed, duration, letters = result[2]
        assert word == 'the'  # Fastest among the three

    def test_get_fastest_words_with_data(self, storage):
        """Test getting fastest words."""
        # Add words with different speeds (need >= 2 observations)
        storage.update_word_statistics('the', 'us', 120, 3)
        storage.update_word_statistics('the', 'us', 125, 3)
        storage.update_word_statistics('cat', 'us', 150, 3)
        storage.update_word_statistics('cat', 'us', 155, 3)
        storage.update_word_statistics('dog', 'us', 200, 3)
        storage.update_word_statistics('dog', 'us', 205, 3)

        result = storage.get_fastest_words(limit=5)

        assert len(result) == 3

        # First result should be 'the' (fastest)
        word, speed, duration, letters = result[0]
        assert word == 'the'
        assert speed < 50

        # Last result should be 'dog' (slowest)
        word, speed, duration, letters = result[2]
        assert word == 'dog'
        assert speed > 60

    def test_case_sensitivity(self, storage):
        """Test that 'Hello' and 'hello' are treated separately."""
        storage.update_word_statistics('Hello', 'us', 500, 5)
        storage.update_word_statistics('hello', 'us', 400, 5)
        storage.update_word_statistics('Hello', 'us', 510, 5)

        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM word_statistics')
            count = cursor.fetchone()[0]

        assert count == 2  # Two separate entries

    def test_word_boundaries_with_punctuation(self, storage):
        """Test that punctuation marks word boundaries."""
        import time
        base_time = int(time.time() * 1000)

        # Type "hello," (comma should be a boundary)
        events = [
            (35, 'h', base_time),
            (18, 'e', base_time + 50),
            (38, 'l', base_time + 100),
            (38, 'l', base_time + 150),
            (24, 'o', base_time + 200),
            (51, ',', base_time + 250),  # Comma (punctuation boundary)
        ]

        for keycode, key_name, timestamp in events:
            storage.store_key_event(keycode, key_name, timestamp, 'press', 'test_app', False)

        storage._process_new_key_events(layout='us', max_events=100)

        import sqlite3
        with sqlite3.connect(storage.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT word FROM word_statistics WHERE word = ?', ('hello',))
            result = cursor.fetchone()

        assert result is not None

    def test_layout_filtering(self, storage):
        """Test filtering by layout."""
        storage.update_word_statistics('hallo', 'de', 500, 5)
        storage.update_word_statistics('hallo', 'de', 510, 5)
        storage.update_word_statistics('hello', 'us', 400, 5)
        storage.update_word_statistics('hello', 'us', 410, 5)

        us_words = storage.get_slowest_words(limit=10, layout='us')
        de_words = storage.get_slowest_words(limit=10, layout='de')

        assert len(us_words) == 1
        assert us_words[0][0] == 'hello'

        assert len(de_words) == 1
        assert de_words[0][0] == 'hallo'

    def test_get_last_processed_event_id(self, storage):
        """Test tracking of last processed event ID."""
        event_id = storage._get_last_processed_event_id('us')
        assert event_id == 0

        storage._set_last_processed_event_id('us', 100)
        event_id = storage._get_last_processed_event_id('us')
        assert event_id == 100

        # Different layouts are tracked separately
        event_id = storage._get_last_processed_event_id('de')
        assert event_id == 0
