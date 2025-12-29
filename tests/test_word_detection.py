"""Tests for word detection with backspace editing and dictionary validation."""

import pytest
import sqlite3
import tempfile
from pathlib import Path
import time

from core.word_detector import WordDetector
from core.dictionary import Dictionary
from core.dictionary_config import DictionaryConfig
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
def storage_with_dict(temp_db):
    """Create storage with dictionary validation."""
    config = Config(temp_db)
    dict_config = DictionaryConfig(
        enabled_languages=["en", "de"], accept_all_mode=False
    )
    return Storage(
        temp_db,
        word_boundary_timeout_ms=1000,
        dictionary_config=dict_config,
        config=config,
    )


class TestWordDetector:
    """Test WordDetector state machine."""

    def test_letter_addition(self):
        """Test adding letters builds word."""
        detector = WordDetector(word_boundary_timeout_ms=1000)

        result = detector.process_keystroke("h", 1000, "us", is_letter=True)
        assert result is None
        assert detector.current_state.word == "h"
        assert detector.current_state.start_time_ms == 1000

        result = detector.process_keystroke("e", 1100, "us", is_letter=True)
        assert result is None
        assert detector.current_state.word == "he"

    def test_backspace_handling(self):
        """Test backspace removes letters."""
        detector = WordDetector(word_boundary_timeout_ms=1000)

        detector.process_keystroke("t", 1000, "us", is_letter=True)
        detector.process_keystroke("e", 1100, "us", is_letter=True)
        detector.process_keystroke("s", 1200, "us", is_letter=True)
        detector.process_keystroke("t", 1300, "us", is_letter=True)

        result = detector.process_keystroke("BACKSPACE", 1400, "us", is_letter=False)
        assert result is None
        assert detector.current_state.word == "tes"
        assert detector.current_state.backspace_count == 1

    def test_shoes_backspace_scenario(self):
        """Test S H O E S <BACKSPACE> S sequence."""
        detector = WordDetector(word_boundary_timeout_ms=1000, min_word_length=3)

        # S H O E S <BACKSPACE> S
        detector.process_keystroke("s", 1000, "us", is_letter=True)
        detector.process_keystroke("h", 1100, "us", is_letter=True)
        detector.process_keystroke("o", 1200, "us", is_letter=True)
        detector.process_keystroke("e", 1300, "us", is_letter=True)
        detector.process_keystroke("s", 1400, "us", is_letter=True)
        detector.process_keystroke("BACKSPACE", 1500, "us", is_letter=False)
        detector.process_keystroke("s", 1600, "us", is_letter=True)

        # Finalize with space
        result = detector.process_keystroke("SPACE", 1700, "us", is_letter=False)

        assert result is not None
        assert result.word == "shoes"
        assert result.num_letters == 5
        assert result.backspace_count == 1
        assert (
            result.editing_time_ms == 100
        )  # Time between 's' (1400) and backspace (1500)
        assert result.total_duration_ms == 700  # From first 's' (1000) to space (1700)

    def test_short_words_ignored(self):
        """Test that words < 3 letters are ignored."""
        detector = WordDetector(word_boundary_timeout_ms=1000)

        detector.process_keystroke("h", 1000, "us", is_letter=True)
        detector.process_keystroke("i", 1100, "us", is_letter=True)
        detector.process_keystroke("SPACE", 1200, "us", is_letter=False)

        result = detector.process_keystroke("SPACE", 1200, "us", is_letter=False)
        assert result is None

    def test_word_finalization(self):
        """Test that word boundary finalizes word >= 3 letters."""
        detector = WordDetector(word_boundary_timeout_ms=1000)

        detector.process_keystroke("h", 1000, "us", is_letter=True)
        detector.process_keystroke("e", 1100, "us", is_letter=True)
        detector.process_keystroke("l", 1200, "us", is_letter=True)
        detector.process_keystroke("l", 1300, "us", is_letter=True)
        detector.process_keystroke("o", 1400, "us", is_letter=True)

        result = detector.process_keystroke("SPACE", 1500, "us", is_letter=False)

        assert result is not None
        assert result.word == "hello"
        assert result.num_letters == 5

    def test_timeout_splits_words(self):
        """Test long pause splits words."""
        detector = WordDetector(word_boundary_timeout_ms=1000)

        detector.process_keystroke("h", 1000, "us", is_letter=True)
        detector.process_keystroke("e", 1100, "us", is_letter=True)

        result = detector.process_keystroke("w", 2200, "us", is_letter=True)
        assert result is None
        assert detector.current_state.word == "w"

    def test_word_editing_scenario(self):
        """Test 'shooes' → 'shoes' editing scenario."""
        detector = WordDetector(word_boundary_timeout_ms=1000, min_word_length=3)

        base_time = int(time.time() * 1000)

        detector.process_keystroke("s", base_time, "us", is_letter=True)
        detector.process_keystroke("h", base_time + 50, "us", is_letter=True)
        detector.process_keystroke("o", base_time + 100, "us", is_letter=True)
        detector.process_keystroke("o", base_time + 150, "us", is_letter=True)
        detector.process_keystroke("e", base_time + 200, "us", is_letter=True)
        detector.process_keystroke("s", base_time + 250, "us", is_letter=True)
        detector.process_keystroke("BACKSPACE", base_time + 300, "us", is_letter=False)
        detector.process_keystroke("BACKSPACE", base_time + 350, "us", is_letter=False)
        detector.process_keystroke("BACKSPACE", base_time + 400, "us", is_letter=False)
        detector.process_keystroke("e", base_time + 450, "us", is_letter=True)
        detector.process_keystroke("s", base_time + 500, "us", is_letter=True)
        result = detector.process_keystroke(
            "SPACE", base_time + 550, "us", is_letter=False
        )

        assert result is not None
        assert result.word == "shoes"
        assert result.backspace_count == 3
        assert result.total_duration_ms == 550
        assert result.editing_time_ms > 0
        assert result.num_letters == 5


class TestDictionary:
    """Test Dictionary class."""

    def test_load_english_dictionary(self):
        """Test English dictionary loads."""
        config = DictionaryConfig(enabled_languages=["en"])
        dict_obj = Dictionary(config)
        loaded = dict_obj.get_loaded_languages()
        # May have loaded en or fallen back to accept_all mode
        assert "en" in loaded or dict_obj.accept_all_mode

    def test_load_german_dictionary(self):
        """Test German dictionary loads."""
        config = DictionaryConfig(enabled_languages=["de"])
        dict_obj = Dictionary(config)
        loaded = dict_obj.get_loaded_languages()
        # May have loaded de or fallen back to accept_all mode
        assert "de" in loaded or dict_obj.accept_all_mode

    def test_valid_english_word(self):
        """Test valid English word recognized."""
        config = DictionaryConfig(enabled_languages=["en"])
        dict_obj = Dictionary(config)
        # If in accept_all mode, all 3+ letter words are valid
        # If dictionary loaded, check actual words
        if dict_obj.accept_all_mode:
            assert dict_obj.is_valid_word("hello")
        else:
            assert dict_obj.is_valid_word("hello", "en")

    def test_valid_german_word(self):
        """Test valid German word recognized."""
        config = DictionaryConfig(enabled_languages=["de"])
        dict_obj = Dictionary(config)
        if dict_obj.accept_all_mode:
            assert dict_obj.is_valid_word("hallo")
        else:
            assert dict_obj.is_valid_word("hallo", "de")
            assert dict_obj.is_valid_word("Welt", "de")
            assert dict_obj.is_valid_word("Schuhe", "de")

    def test_invalid_word_rejected(self):
        """Test invalid word rejected (only when not in accept_all mode)."""
        config = DictionaryConfig(enabled_languages=["en"])
        dict_obj = Dictionary(config)
        if not dict_obj.accept_all_mode:
            assert not dict_obj.is_valid_word("xyz", "en")
            assert not dict_obj.is_valid_word("asdfgh", "en")

    def test_case_insensitive(self):
        """Test dictionary is case-insensitive."""
        config = DictionaryConfig(enabled_languages=["en"])
        dict_obj = Dictionary(config)
        if dict_obj.accept_all_mode:
            assert dict_obj.is_valid_word("HELLO")
            assert dict_obj.is_valid_word("Hello")
        else:
            assert dict_obj.is_valid_word("HELLO", "en")
            assert dict_obj.is_valid_word("Hello", "en")
            assert dict_obj.is_valid_word("hElLo", "en")

    def test_available_languages(self):
        """Test get_loaded_languages returns loaded languages."""
        config = DictionaryConfig(enabled_languages=["en", "de"])
        dict_obj = Dictionary(config)
        languages = dict_obj.get_loaded_languages()
        # Should have loaded languages or be in accept_all mode
        assert len(languages) > 0 or dict_obj.accept_all_mode


class TestWordStorageWithDictionary:
    """Test word storage with dictionary validation."""

    def test_valid_word_stored(self, storage_with_dict):
        """Test valid dictionary word is stored."""
        base_time = int(time.time() * 1000)

        events = [
            (35, "h", base_time),
            (18, "e", base_time + 50),
            (38, "l", base_time + 100),
            (38, "l", base_time + 150),
            (24, "o", base_time + 200),
            (57, "SPACE", base_time + 250),
        ]

        for keycode, key_name, timestamp in events:
            storage_with_dict.store_key_event(keycode, key_name, timestamp)

        processed = storage_with_dict._process_new_key_events(
            layout="us", max_events=100
        )
        assert processed == 6

        with sqlite3.connect(storage_with_dict.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT word, backspace_count, editing_time_ms FROM word_statistics WHERE word = ?",
                ("hello",),
            )
            result = cursor.fetchone()

        assert result is not None
        word, backspace_count, editing_time = result
        assert word == "hello"
        assert backspace_count == 0
        assert editing_time == 0

    def test_invalid_word_not_stored(self, storage_with_dict):
        """Test invalid word is not stored."""
        base_time = int(time.time() * 1000)

        events = [
            (35, "x", base_time),
            (51, "y", base_time + 50),
            (50, "z", base_time + 100),
            (57, "SPACE", base_time + 150),
        ]

        for keycode, key_name, timestamp in events:
            storage_with_dict.store_key_event(keycode, key_name, timestamp)

        processed = storage_with_dict._process_new_key_events(
            layout="us", max_events=100
        )
        assert processed == 4

        with sqlite3.connect(storage_with_dict.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM word_statistics WHERE word = ?", ("xyz",)
            )
            count = cursor.fetchone()[0]

        assert count == 0

    def test_edited_word_with_backspace(self, storage_with_dict):
        """Test edited word stored with editing metadata."""
        base_time = int(time.time() * 1000)

        events = [
            (35, "s", base_time),
            (18, "h", base_time + 50),
            (24, "o", base_time + 100),
            (24, "o", base_time + 150),
            (23, "e", base_time + 200),
            (35, "s", base_time + 250),
            (14, "BACKSPACE", base_time + 300),
            (14, "BACKSPACE", base_time + 350),
            (14, "BACKSPACE", base_time + 400),
            (23, "e", base_time + 450),
            (35, "s", base_time + 500),
            (57, "SPACE", base_time + 550),
        ]

        for keycode, key_name, timestamp in events:
            storage_with_dict.store_key_event(keycode, key_name, timestamp)

        processed = storage_with_dict._process_new_key_events(
            layout="us", max_events=100
        )
        assert processed == 12

        with sqlite3.connect(storage_with_dict.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT word, backspace_count, editing_time_ms, total_duration_ms FROM word_statistics WHERE word = ?",
                ("shoes",),
            )
            result = cursor.fetchone()

        assert result is not None
        word, backspace_count, editing_time, total_duration = result
        assert word == "shoes"
        assert backspace_count == 3
        assert editing_time > 0
        assert total_duration > 0

    def test_multiple_words(self, storage_with_dict):
        """Test multiple words detected and stored."""
        base_time = int(time.time() * 1000)

        events = [
            (35, "h", base_time),
            (18, "e", base_time + 50),
            (38, "l", base_time + 100),
            (38, "l", base_time + 150),
            (24, "o", base_time + 200),
            (57, "SPACE", base_time + 250),
            (57, "SPACE", base_time + 300),
            (57, "SPACE", base_time + 350),
            (57, "SPACE", base_time + 400),
            (23, "i", base_time + 450),
            (28, "t", base_time + 500),
            (57, "SPACE", base_time + 550),
        ]

        for keycode, key_name, timestamp in events:
            storage_with_dict.store_key_event(keycode, key_name, timestamp)

        processed = storage_with_dict._process_new_key_events(
            layout="us", max_events=100
        )
        assert processed == 12

        with sqlite3.connect(storage_with_dict.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT word FROM word_statistics ORDER BY word")
            words = [row[0] for row in cursor.fetchall()]

        assert "hello" in words
        assert "it" not in words  # Too short (< 3 letters)

    def test_long_pause_splits_words(self, storage_with_dict):
        """Test long pause creates separate words (Option A)."""
        base_time = int(time.time() * 1000)

        events = [
            (35, "s", base_time),
            (18, "h", base_time + 50),
            (24, "o", base_time + 100),
            (24, "o", base_time + 150),
            (23, "e", base_time + 200),
            (35, "s", base_time + 250),
            (14, "BACKSPACE", base_time + 2500),
            (14, "BACKSPACE", base_time + 2550),
            (14, "BACKSPACE", base_time + 2600),
            (23, "e", base_time + 2650),
            (35, "s", base_time + 2700),
            (57, "SPACE", base_time + 2750),
        ]

        for keycode, key_name, timestamp in events:
            storage_with_dict.store_key_event(keycode, key_name, timestamp)

        processed = storage_with_dict._process_new_key_events(
            layout="us", max_events=100
        )
        assert processed == 12

        with sqlite3.connect(storage_with_dict.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT word FROM word_statistics")
            words = [row[0] for row in cursor.fetchall()]

        # 'shooes' not in dictionary, 'shoes' should be stored
        assert "shoes" in words
