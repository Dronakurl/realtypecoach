"""Tests for utils.keycodes module."""


from utils.keycodes import (
    get_key_name,
    is_supported_layout,
    is_letter_key,
    US_KEYCODE_TO_NAME,
    DE_KEYCODE_TO_NAME,
    LAYOUT_KEYCODE_MAPPINGS,
)


class TestGetKeyName:
    """Tests for get_key_name function."""

    def test_get_key_name_us_layout_lowercase_letters(self):
        """Test US layout returns correct lowercase letters."""
        assert get_key_name(30, 'us') == 'a'
        assert get_key_name(31, 'us') == 's'
        assert get_key_name(32, 'us') == 'd'
        assert get_key_name(48, 'b') == 'b'
        assert get_key_name(50, 'm') == 'm'

    def test_get_key_name_us_layout_numbers(self):
        """Test US layout returns correct numbers."""
        assert get_key_name(2, 'us') == '1'
        assert get_key_name(5, 'us') == '4'
        assert get_key_name(11, 'us') == '0'

    def test_get_key_name_us_layout_modifiers(self):
        """Test US layout returns correct modifier keys."""
        assert get_key_name(42, 'us') == 'LEFT_SHIFT'
        assert get_key_name(54, 'us') == 'RIGHT_SHIFT'
        assert get_key_name(29, 'us') == 'LEFT_CTRL'
        assert get_key_name(97, 'us') == 'RIGHT_CTRL'
        assert get_key_name(56, 'us') == 'LEFT_ALT'
        assert get_key_name(100, 'us') == 'RIGHT_ALT'

    def test_get_key_name_us_layout_special_keys(self):
        """Test US layout returns correct special keys."""
        assert get_key_name(57, 'us') == 'SPACE'
        assert get_key_name(14, 'us') == 'BACKSPACE'
        assert get_key_name(28, 'us') == 'ENTER'
        assert get_key_name(15, 'us') == 'TAB'
        assert get_key_name(1, 'us') == 'ESC'

    def test_get_key_name_de_layout_umlauts(self):
        """Test German layout returns correct umlauts."""
        assert get_key_name(39, 'de') == 'ö'  # Different from US ';'
        assert get_key_name(40, 'de') == 'ä'
        assert get_key_name(26, 'de') == 'ü'
        assert get_key_name(12, 'de') == 'ß'  # Different from US '-'

    def test_get_key_name_de_layout_y_z_swapped(self):
        """Test German layout has Y and Z swapped vs US."""
        assert get_key_name(21, 'de') == 'z'  # US has 'y' here
        assert get_key_name(44, 'de') == 'y'  # US has 'z' here

    def test_get_key_name_default_layout(self):
        """Test default layout is 'us'."""
        assert get_key_name(30) == 'a'
        assert get_key_name(42) == 'LEFT_SHIFT'

    def test_get_key_name_unknown_layout_fallback_to_us(self):
        """Test unknown layout falls back to US mapping."""
        assert get_key_name(30, 'fr') == 'a'  # Falls back to US
        assert get_key_name(30, 'unknown') == 'a'

    def test_get_key_name_unknown_keycode(self):
        """Test unknown keycode returns KEY_XXX format."""
        assert get_key_name(999, 'us') == 'KEY_999'
        assert get_key_name(1234, 'de') == 'KEY_1234'

    def test_get_key_name_function_keys(self):
        """Test function keys mapping."""
        assert get_key_name(59, 'us') == 'F1'
        assert get_key_name(68, 'us') == 'F10'
        assert get_key_name(87, 'us') == 'F11'
        assert get_key_name(88, 'us') == 'F12'

    def test_get_key_name_numpad_keys(self):
        """Test numpad keys mapping."""
        assert get_key_name(69, 'us') == 'NUM_LOCK'
        assert get_key_name(71, 'us') == 'KP_7'
        assert get_key_name(75, 'us') == 'KP_4'
        assert get_key_name(79, 'us') == 'KP_1'
        assert get_key_name(82, 'us') == 'KP_0'


class TestIsSupportedLayout:
    """Tests for is_supported_layout function."""

    def test_is_supported_layout_us(self):
        """Test 'us' layout is supported."""
        assert is_supported_layout('us') is True

    def test_is_supported_layout_de(self):
        """Test 'de' layout is supported."""
        assert is_supported_layout('de') is True

    def test_is_supported_layout_unsupported(self):
        """Test unsupported layouts return False."""
        assert is_supported_layout('fr') is False
        assert is_supported_layout('gb') is False
        assert is_supported_layout('dvorak') is False

    def test_is_supported_layout_empty_string(self):
        """Test empty string returns False."""
        assert is_supported_layout('') is False

    def test_is_supported_layout_case_sensitive(self):
        """Test layout matching is case-sensitive."""
        assert is_supported_layout('US') is False
        assert is_supported_layout('DE') is False
        assert is_supported_layout('Us') is False


class TestIsLetterKey:
    """Tests for is_letter_key function."""

    def test_is_letter_key_single_lowercase(self):
        """Test all lowercase a-z letters return True."""
        for letter in 'abcdefghijklmnopqrstuvwxyz':
            assert is_letter_key(letter) is True

    def test_is_letter_key_single_uppercase(self):
        """Test all uppercase A-Z letters return True."""
        for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            assert is_letter_key(letter) is True

    def test_is_letter_key_german_umlauts(self):
        """Test German umlauts return True."""
        assert is_letter_key('ä') is True
        assert is_letter_key('ö') is True
        assert is_letter_key('ü') is True
        assert is_letter_key('Ä') is True
        assert is_letter_key('Ö') is True
        assert is_letter_key('Ü') is True

    def test_is_letter_key_german_eszett(self):
        """Test German eszett returns True."""
        assert is_letter_key('ß') is True
        assert is_letter_key('SS') is False  # Uppercase version is two chars
        assert is_letter_key('ẞ') is True  # Capital eszett

    def test_is_letter_key_space(self):
        """Test SPACE returns False."""
        assert is_letter_key('SPACE') is False

    def test_is_letter_key_modifiers(self):
        """Test modifier keys return False."""
        assert is_letter_key('LEFT_SHIFT') is False
        assert is_letter_key('RIGHT_SHIFT') is False
        assert is_letter_key('LEFT_CTRL') is False
        assert is_letter_key('LEFT_ALT') is False

    def test_is_letter_key_special_keys(self):
        """Test special keys return False."""
        assert is_letter_key('ENTER') is False
        assert is_letter_key('TAB') is False
        assert is_letter_key('BACKSPACE') is False
        assert is_letter_key('ESC') is False
        assert is_letter_key('CAPS_LOCK') is False

    def test_is_letter_key_numbers(self):
        """Test number strings return False."""
        assert is_letter_key('1') is False
        assert is_letter_key('0') is False
        assert is_letter_key('123') is False

    def test_is_letter_key_punctuation(self):
        """Test punctuation returns False."""
        assert is_letter_key(',') is False
        assert is_letter_key('.') is False
        assert is_letter_key('-') is False
        assert is_letter_key(';') is False

    def test_is_letter_key_empty_string(self):
        """Test empty string returns False."""
        assert is_letter_key('') is False

    def test_is_letter_key_multi_character(self):
        """Test multi-character non-letter strings return False."""
        assert is_letter_key('abc') is False
        assert is_letter_key('ab') is False
        assert is_letter_key('SHIFT') is False

    def test_is_letter_key_numpad(self):
        """Test numpad keys return False."""
        assert is_letter_key('KP_1') is False
        assert is_letter_key('KP_ENTER') is False


class TestLayoutMappings:
    """Tests for layout mapping constants."""

    def test_us_mapping_is_complete(self):
        """Test US mapping has expected entries."""
        assert 30 in US_KEYCODE_TO_NAME
        assert 42 in US_KEYCODE_TO_NAME
        assert US_KEYCODE_TO_NAME[30] == 'a'

    def test_de_mapping_is_complete(self):
        """Test DE mapping has expected entries."""
        assert 30 in DE_KEYCODE_TO_NAME
        assert 39 in DE_KEYCODE_TO_NAME
        assert DE_KEYCODE_TO_NAME[30] == 'a'
        assert DE_KEYCODE_TO_NAME[39] == 'ö'

    def test_layout_mappings_dict(self):
        """Test LAYOUT_KEYCODE_MAPPINGS contains both layouts."""
        assert 'us' in LAYOUT_KEYCODE_MAPPINGS
        assert 'de' in LAYOUT_KEYCODE_MAPPINGS
        assert LAYOUT_KEYCODE_MAPPINGS['us'] is US_KEYCODE_TO_NAME
        assert LAYOUT_KEYCODE_MAPPINGS['de'] is DE_KEYCODE_TO_NAME
