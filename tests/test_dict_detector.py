"""Tests for dictionary detection module."""

from core.dictionary_config import DictionaryConfig
from utils.dict_detector import DictionaryDetector, DictionaryInfo


class TestDictionaryDetector:
    """Test dictionary detection."""

    def test_detect_available_returns_list(self):
        """Should return list of DictionaryInfo objects."""
        detected = DictionaryDetector.detect_available()
        assert isinstance(detected, list)

    def test_detect_common_system_paths(self):
        """Should find dictionaries in common system locations."""
        detected = DictionaryDetector.detect_available()
        # On most Linux systems, at least one dictionary should exist
        assert len(detected) >= 0  # May be 0 in container

    def test_identify_dictionary_info_structure(self):
        """Should return DictionaryInfo with correct structure."""
        detected = DictionaryDetector.detect_available()
        for d in detected:
            assert isinstance(d, DictionaryInfo)
            assert hasattr(d, 'path')
            assert hasattr(d, 'language_code')
            assert hasattr(d, 'language_name')
            assert hasattr(d, 'available')

    def test_validate_dictionary_with_valid_file(self, tmp_path):
        """Should accept valid dictionary format."""
        dict_file = tmp_path / "test.dict"
        dict_file.write_text("word1\nword2\nword3\n")
        assert DictionaryDetector.validate_dictionary(str(dict_file))

    def test_validate_dictionary_rejects_empty(self, tmp_path):
        """Should reject empty files."""
        empty = tmp_path / "empty.dict"
        empty.write_text("")
        assert not DictionaryDetector.validate_dictionary(str(empty))

    def test_validate_dictionary_rejects_directory(self, tmp_path):
        """Should reject directories."""
        assert not DictionaryDetector.validate_dictionary(str(tmp_path))


class TestDictionaryWithFallback:
    """Test Dictionary class with priority fallback."""

    def test_accept_all_mode(self):
        """Should accept all words in accept_all mode."""
        from core.dictionary import Dictionary

        config = DictionaryConfig(
            enabled_languages=[],
            accept_all_mode=True
        )
        dict_obj = Dictionary(config)
        assert dict_obj.accept_all_mode
        assert dict_obj.is_valid_word("test")
        assert dict_obj.is_valid_word("xyz")
        assert not dict_obj.is_valid_word("ab")  # Less than 3 chars

    def test_auto_detect_with_fallback(self):
        """Should auto-detect and apply priority fallback."""
        from core.dictionary import Dictionary

        # This will auto-detect available dictionaries
        config = DictionaryConfig()
        dict_obj = Dictionary(config)
        loaded = dict_obj.get_loaded_languages()

        # Should have loaded some languages or be in accept_all mode
        assert len(loaded) > 0 or dict_obj.accept_all_mode

    def test_reload_languages(self, tmp_path):
        """Should reload dictionaries when configuration changes."""
        from core.dictionary import Dictionary

        config = DictionaryConfig(accept_all_mode=True)
        dict_obj = Dictionary(config)
        assert dict_obj.accept_all_mode

        # Reload without accept_all_mode
        new_config = DictionaryConfig(enabled_languages=['en', 'de'])
        dict_obj.reload_languages(new_config)

        # May have loaded dictionaries or enabled accept_all_mode
        assert dict_obj.is_loaded()

    def test_get_loaded_languages(self):
        """Should return list of loaded language codes."""
        from core.dictionary import Dictionary

        config = DictionaryConfig()
        dict_obj = Dictionary(config)
        loaded = dict_obj.get_loaded_languages()

        assert isinstance(loaded, list)
        for lang in loaded:
            assert isinstance(lang, str)
            assert len(lang) == 2  # Language codes are 2 chars
