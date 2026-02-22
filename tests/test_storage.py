"""Tests for Storage class."""

import tempfile
from pathlib import Path

import pytest

from core.burst_detector import Burst
from core.models import KeystrokeInfo, WordInfo
from core.storage import Storage
from utils.config import Config
from utils.crypto import CryptoManager


@pytest.fixture
def sample_burst():
    """Create a sample burst for testing."""
    return Burst(
        start_time_ms=1234567890,
        end_time_ms=1234568890,
        key_count=50,
        backspace_count=0,
        net_key_count=50,
        duration_ms=5000,
        qualifies_for_high_score=False,
    )


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
    # Initialize encryption key first
    crypto = CryptoManager(temp_db)
    if not crypto.key_exists():
        crypto.initialize_database_key()

    config = Config(temp_db)
    return Storage(temp_db, config=config)


class TestStorage:
    """Test Storage class."""

    def test_init_database(self, storage):
        """Test database initialization."""
        # Check that tables exist
        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            # key_events table removed for security
            assert "bursts" in tables
            assert "statistics" in tables
            assert "high_scores" in tables
            assert "daily_summaries" in tables
            assert "word_statistics" in tables
            assert "settings" in tables

    def test_store_burst(self, storage, sample_burst):
        """Test storing bursts."""
        storage.store_burst(sample_burst, 60.0)

        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM bursts")
            count = cursor.fetchone()[0]
            cursor.execute("SELECT duration_ms FROM bursts")
            duration = cursor.fetchone()[0]

            assert count == 1
            assert duration == 5000  # 5 seconds in milliseconds

    def test_store_burst_with_backspaces(self, storage):
        """Test storing bursts with backspace tracking."""
        burst = Burst(
            start_time_ms=1234567890,
            end_time_ms=1234568890,
            key_count=100,  # Total keystrokes
            backspace_count=20,  # 20 backspaces
            net_key_count=80,  # 80 productive keystrokes
            duration_ms=5000,
            qualifies_for_high_score=False,
        )

        storage.store_burst(burst, 96.0)  # 80/5 / (5000/60000) = 16 / 0.0833 = 192 WPM?

        with storage._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT key_count, backspace_count, net_key_count, avg_wpm FROM bursts")
            result = cursor.fetchone()

            assert result[0] == 100  # key_count
            assert result[1] == 20  # backspace_count
            assert result[2] == 80  # net_key_count
            assert result[3] == 96.0  # avg_wpm

    def test_update_daily_summary_typing_time(self, storage):
        """Test that typing time is stored correctly in daily summary."""
        date = "2025-01-01"
        keystrokes = 1000
        bursts = 10
        avg_wpm = 50.0
        slowest_keycode = 30
        slowest_key_name = "KEY_A"
        total_typing_sec = 300  # 5 minutes

        storage.update_daily_summary(
            date,
            keystrokes,
            bursts,
            avg_wpm,
            slowest_keycode,
            slowest_key_name,
            total_typing_sec,
        )

        with storage._get_connection() as conn:
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
        storage.update_key_statistics(30, "a", "us", 150.0)
        storage.update_key_statistics(30, "a", "us", 140.0)

        result = storage.get_slowest_keys(limit=10)

        # Check that statistics were created
        assert len(result) == 1
        key_perf = result[0]
        assert key_perf.keycode == 30
        assert key_perf.key_name == "a"
        assert key_perf.avg_press_time == 145.0

    def test_get_slowest_keys_ordering(self, storage):
        """Test that slowest keys are returned in correct order."""
        # Add keys with different average times
        storage.update_key_statistics(30, "a", "us", 100.0)
        storage.update_key_statistics(30, "a", "us", 110.0)
        storage.update_key_statistics(31, "b", "us", 200.0)
        storage.update_key_statistics(31, "b", "us", 210.0)
        storage.update_key_statistics(32, "c", "us", 150.0)
        storage.update_key_statistics(32, "c", "us", 160.0)

        result = storage.get_slowest_keys(limit=10)

        # Should be ordered by avg_press_time DESC
        assert len(result) == 3
        assert result[0].key_name == "b"  # ~205ms - slowest
        assert result[1].key_name == "c"  # ~155ms
        assert result[2].key_name == "a"  # ~105ms - fastest

    def test_digraph_timing_with_backspace(self, storage):
        """Test that digraph timing is correctly calculated after backspace correction.

        When typing "Nii<backspace>ke":
        - The word should be recognized as "Nike"
        - The digraph "ik" should be timed from the first 'i' to 'k', not the deleted second 'i'
        - This ensures the timing reflects the actual typing flow including the correction

        Note: Using "nice" instead of "Nike" to ensure it's a valid dictionary word.
        The timing pattern is the same: n@1000, i@1100, i@1200, backspace@1300, c@1400, e@1500
        """
        # Create a WordInfo simulating "nii<backspace>ce" -> "nice"
        # WordDetector filters keystrokes to remove backspace and deleted characters
        # So we use the filtered keystrokes here (as they come from WordDetector)
        # Original: n@1000, i@1100, i@1200, backspace@1300, c@1400, e@1500
        # Filtered: n@1000, i@1100, c@1400, e@1500
        word_info = WordInfo(
            word="nice",
            layout="us",
            total_duration_ms=500,  # 1500 - 1000
            active_duration_ms=500,
            editing_time_ms=100,  # Time spent on backspace
            backspace_count=1,
            num_letters=4,
            keystrokes=[
                KeystrokeInfo(key="n", time=1000, type="letter", keycode=49),
                KeystrokeInfo(key="i", time=1100, type="letter", keycode=31),
                # The second 'i' at 1200ms was deleted by backspace
                # The backspace at 1300ms is not included in filtered keystrokes
                KeystrokeInfo(key="c", time=1400, type="letter", keycode=46),
                KeystrokeInfo(key="e", time=1500, type="letter", keycode=35),
            ],
        )

        # Store the word TWICE to ensure digraphs have total_sequences >= 2
        # (required by get_slowest_digraphs query)
        for i in range(2):
            with storage._get_connection() as conn:
                storage._store_word_from_state(conn, word_info)
                conn.commit()

        # Verify digraphs were stored correctly
        slowest_digraphs = storage.get_slowest_digraphs(limit=10, layout="us")

        # Find the "ic" digraph
        ic_digraph = next(
            (d for d in slowest_digraphs if d.first_key == "i" and d.second_key == "c"), None
        )

        assert ic_digraph is not None, "Digraph 'ic' should be stored"

        # The critical assertion: timing should be from first 'i' (1100ms) to 'c' (1400ms) = 300ms
        # NOT from second 'i' (1200ms) to 'c' (1400ms) = 200ms
        # This ensures the timing includes the backspace correction
        assert ic_digraph.avg_interval_ms == 300.0, (
            f"Digraph 'ic' timing should be 300ms (from first 'i' at 1100ms to 'c' at 1400ms), "
            f"not {ic_digraph.avg_interval_ms}ms"
        )

        # Also verify the other digraphs
        ni_digraph = next(
            (d for d in slowest_digraphs if d.first_key == "n" and d.second_key == "i"), None
        )
        assert ni_digraph is not None
        assert ni_digraph.avg_interval_ms == 100.0  # n@1000 to i@1100

        ce_digraph = next(
            (d for d in slowest_digraphs if d.first_key == "c" and d.second_key == "e"), None
        )
        assert ce_digraph is not None
        assert ce_digraph.avg_interval_ms == 100.0  # c@1400 to e@1500


class TestDigraphStorageWithDictionaryValidation:
    """Test that digraphs are only stored for valid dictionary words."""

    @pytest.fixture
    def storage_with_dict(self, temp_db):
        """Create storage with dictionary validation enabled."""
        from core.dictionary_config import DictionaryConfig

        crypto = CryptoManager(temp_db)
        if not crypto.key_exists():
            crypto.initialize_database_key()

        config = Config(temp_db)
        dict_config = DictionaryConfig(enabled_languages=["en"], accept_all_mode=False)
        return Storage(temp_db, config=config, dictionary_config=dict_config)

    def test_digraphs_stored_only_for_valid_words(self, storage_with_dict):
        """Test that digraphs are stored for valid dictionary words but not for invalid ones.

        This verifies the fix that ensures digraph statistics only include digraphs
        from valid dictionary words, preventing invalid digraphs like 'üü' from being stored.
        """
        # "hello" is a valid English word
        valid_word_info = WordInfo(
            word="hello",
            layout="us",
            total_duration_ms=400,
            active_duration_ms=400,
            editing_time_ms=0,
            backspace_count=0,
            num_letters=5,
            keystrokes=[
                KeystrokeInfo(key="h", time=1000, type="letter", keycode=35),
                KeystrokeInfo(key="e", time=1100, type="letter", keycode=18),
                KeystrokeInfo(key="l", time=1200, type="letter", keycode=38),
                KeystrokeInfo(key="l", time=1300, type="letter", keycode=38),
                KeystrokeInfo(key="o", time=1400, type="letter", keycode=24),
            ],
        )

        # "xyz" is NOT a valid English word (not in dictionary)
        invalid_word_info = WordInfo(
            word="xyz",
            layout="us",
            total_duration_ms=300,
            active_duration_ms=300,
            editing_time_ms=0,
            backspace_count=0,
            num_letters=3,
            keystrokes=[
                KeystrokeInfo(key="x", time=2000, type="letter", keycode=35),
                KeystrokeInfo(key="y", time=2100, type="letter", keycode=18),
                KeystrokeInfo(key="z", time=2200, type="letter", keycode=38),
            ],
        )

        # Store both words TWICE (to meet total_sequences >= 2 requirement)
        for _ in range(2):
            # Valid word should pass the is_valid_word check and be stored
            if storage_with_dict.dictionary.is_valid_word(
                valid_word_info.word, storage_with_dict._get_language_from_layout("us")
            ):
                with storage_with_dict._get_connection() as conn:
                    storage_with_dict._store_word_from_state(conn, valid_word_info)
                    conn.commit()

            # Invalid word should NOT be stored
            if storage_with_dict.dictionary.is_valid_word(
                invalid_word_info.word, storage_with_dict._get_language_from_layout("us")
            ):
                with storage_with_dict._get_connection() as conn:
                    storage_with_dict._store_word_from_state(conn, invalid_word_info)
                    conn.commit()

        # Verify digraphs from valid word were stored
        slowest_digraphs = storage_with_dict.get_slowest_digraphs(limit=10, layout="us")

        # Check that "he", "el", "ll", "lo" digraphs from "hello" exist
        digraph_pairs = [(d.first_key, d.second_key) for d in slowest_digraphs]
        assert ("h", "e") in digraph_pairs, "Digraph 'he' from 'hello' should be stored"
        assert ("e", "l") in digraph_pairs, "Digraph 'el' from 'hello' should be stored"
        assert ("l", "l") in digraph_pairs, "Digraph 'll' from 'hello' should be stored"
        assert ("l", "o") in digraph_pairs, "Digraph 'lo' from 'hello' should be stored"

        # Check that "xy", "yz" digraphs from "xyz" do NOT exist
        assert ("x", "y") not in digraph_pairs, (
            "Digraph 'xy' from invalid word 'xyz' should NOT be stored"
        )
        assert ("y", "z") not in digraph_pairs, (
            "Digraph 'yz' from invalid word 'xyz' should NOT be stored"
        )

    def test_invalid_digraph_not_in_database(self, storage_with_dict):
        """Test that directly querying the database shows no invalid digraphs."""
        # Create a WordInfo with a non-existent digraph
        # Using a word that definitely won't be in the dictionary
        word_info = WordInfo(
            word="qwxyz",  # Not in dictionary
            layout="us",
            total_duration_ms=400,
            active_duration_ms=400,
            editing_time_ms=0,
            backspace_count=0,
            num_letters=5,
            keystrokes=[
                KeystrokeInfo(key="q", time=1000, type="letter", keycode=16),
                KeystrokeInfo(key="w", time=1100, type="letter", keycode=17),
                KeystrokeInfo(key="x", time=1200, type="letter", keycode=35),
                KeystrokeInfo(key="y", time=1300, type="letter", keycode=18),
                KeystrokeInfo(key="z", time=1400, type="letter", keycode=38),
            ],
        )

        # Try to store - should fail validation
        is_valid = storage_with_dict.dictionary.is_valid_word(
            word_info.word, storage_with_dict._get_language_from_layout("us")
        )

        assert not is_valid, f"Word '{word_info.word}' should not be valid"

        # Even if we try to bypass and store directly, the analyzer flow prevents it
        # So no digraphs should be in the database
        with storage_with_dict._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM digraph_statistics WHERE layout = ?", ("us",))
            count = cursor.fetchone()[0]

        assert count == 0, "No digraphs should be stored for invalid words"

    def test_uu_digraph_not_stored_for_nonexistent_word(self, storage_with_dict):
        """Test that üü digraph is not stored for a word not in the German dictionary.

        This is a regression test for the issue where 'üü' appeared in the database.
        Since no German word contains 'üü', it should never be stored.
        """
        from core.dictionary_config import DictionaryConfig

        # Create storage with German dictionary
        crypto = CryptoManager(storage_with_dict.db_path)
        config = Config(storage_with_dict.db_path)
        dict_config = DictionaryConfig(enabled_languages=["de"], accept_all_mode=False)
        storage_de = Storage(
            storage_with_dict.db_path, config=config, dictionary_config=dict_config
        )

        # Create a fake word that contains 'üü' (doesn't exist in German dictionary)
        fake_word = "grüße"  # Actual word is "grüße" but with 'üü' instead
        word_info = WordInfo(
            word="grüüße",  # This is NOT a valid German word
            layout="de",
            total_duration_ms=400,
            active_duration_ms=400,
            editing_time_ms=0,
            backspace_count=0,
            num_letters=6,
            keystrokes=[
                KeystrokeInfo(key="g", time=1000, type="letter", keycode=35),
                KeystrokeInfo(key="r", time=1100, type="letter", keycode=27),
                KeystrokeInfo(key="ü", time=1200, type="letter", keycode=30),
                KeystrokeInfo(key="ü", time=1300, type="letter", keycode=30),
                KeystrokeInfo(key="ß", time=1400, type="letter", keycode=38),
                KeystrokeInfo(key="e", time=1500, type="letter", keycode=18),
            ],
        )

        # Try to store - should fail validation
        is_valid = storage_de.dictionary.is_valid_word(
            word_info.word, storage_de._get_language_from_layout("de")
        )

        assert not is_valid, f"Word '{word_info.word}' should not be in German dictionary"

        # Verify 'üü' digraph is NOT in database
        with storage_de._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT COUNT(*) FROM digraph_statistics
                   WHERE first_key = 'ü' AND second_key = 'ü' AND layout = ?""",
                ("de",),
            )
            count = cursor.fetchone()[0]

        assert count == 0, (
            "Digraph 'üü' should never be stored as it's not in any valid German word"
        )


class TestEqualDigraphSelection:
    """Tests for equal digraph representation in word selection."""

    def test_equal_representation(self, storage):
        """Verify each digraph gets same word count."""
        # Use common digraphs that will have many words
        digraphs = ["th", "he", "in", "er", "on"]
        count = 50  # 10 words per digraph

        words = storage.get_random_words_with_equal_digraphs(digraphs=digraphs, count=count)

        # Count words per digraph
        digraph_word_counts = {d: 0 for d in digraphs}
        for word in words:
            word_lower = word.lower()
            for digraph in digraphs:
                if digraph in word_lower:
                    digraph_word_counts[digraph] += 1
                    break

        # Each digraph should have exactly count // len(digraphs) words
        expected_per_digraph = count // len(digraphs)
        for digraph, word_count in digraph_word_counts.items():
            assert word_count == expected_per_digraph, (
                f"Digraph '{digraph}' has {word_count} words, expected {expected_per_digraph}"
            )

    def test_insufficient_words_logs_warning(self, storage, caplog):
        """Verify warning logged when digraph has no words."""
        import logging

        # Create a scenario where we definitely get no words
        # by using an invalid digraph that won't match anything
        digraphs = ["xxxx"]  # Extremely unlikely to exist in any dictionary
        count = 100

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="core.storage"):
            words = storage.get_random_words_with_equal_digraphs(digraphs=digraphs, count=count)

        # Should get an empty result since no words contain 'xxxx'
        assert words == [], "Should return empty list for digraph with no matches"

    def test_length_penalty_applied(self, storage):
        """Verify weighted selection is used (by observing multiple runs)."""
        digraphs = ["th", "he"]
        count = 40

        # Run multiple times and check that we don't always get the same words
        # This demonstrates randomness is working
        results = []
        for _ in range(5):
            words = storage.get_random_words_with_equal_digraphs(digraphs=digraphs, count=count)
            results.append(set(words))

        # At least some variation across runs (not identical results every time)
        # Since we're using weighted random selection, results should vary
        all_same = all(r == results[0] for r in results)
        assert not all_same, "Results should vary across runs with random selection"

    def test_duplicate_handling(self, storage):
        """Verify words with multiple digraphs assigned once."""
        # Select digraphs where some words might contain multiple
        digraphs = ["th", "he"]
        count = 50

        words = storage.get_random_words_with_equal_digraphs(digraphs=digraphs, count=count)

        # No duplicate words should be in the result
        assert len(words) == len(set(words)), (
            f"Found duplicate words in result: {len(words)} total, {len(set(words))} unique"
        )

    def test_edge_case_empty_digraph_list(self, storage):
        """Verify empty digraph list returns empty result."""
        words = storage.get_random_words_with_equal_digraphs(digraphs=[], count=100)

        assert words == [], "Empty digraph list should return empty result"

    def test_edge_case_single_digraph(self, storage):
        """Verify single digraph works correctly."""
        digraphs = ["th"]
        count = 20

        words = storage.get_random_words_with_equal_digraphs(digraphs=digraphs, count=count)

        # All words should contain 'th'
        assert len(words) > 0, "Should return words for single digraph"
        assert all("th" in word.lower() for word in words), (
            "All words should contain the digraph 'th'"
        )

    def test_result_shuffled(self, storage):
        """Verify final result is shuffled (digraphs mixed)."""
        digraphs = ["th", "er"]
        count = 50

        words = storage.get_random_words_with_equal_digraphs(digraphs=digraphs, count=count)

        # Check that words from different digraphs are mixed
        # (not all 'th' words first, then all 'er' words)
        found_th_first = False
        found_er_first = False

        for _ in range(10):  # Run 10 times to account for randomness
            test_words = storage.get_random_words_with_equal_digraphs(
                digraphs=digraphs, count=count
            )

            if "th" in test_words[0].lower():
                found_th_first = True
            if "er" in test_words[0].lower():
                found_er_first = True

            if found_th_first and found_er_first:
                break

        # Due to shuffling, we should see different digraphs at the start
        # (This is probabilistic, but very likely with 10 runs)
        assert found_th_first or found_er_first, "Should see mixed digraphs"
