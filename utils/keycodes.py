"""Keyboard keycode to name mappings for different layouts."""

US_KEYCODE_TO_NAME = {
    30: 'a', 31: 's', 32: 'd', 33: 'f', 34: 'g',
    35: 'h', 36: 'j', 37: 'k', 38: 'l', 39: ';', 40: "'",
    41: '`', 42: 'LEFT_SHIFT', 43: '\\', 44: 'z', 45: 'x',
    46: 'c', 47: 'v', 48: 'b', 49: 'n', 50: 'm', 51: ',',
    52: '.', 53: '/', 54: 'RIGHT_SHIFT', 55: '*', 56: 'LEFT_ALT',
    57: 'SPACE', 58: 'CAPS_LOCK',
    2: '1', 3: '2', 4: '3', 5: '4', 6: '5',
    7: '6', 8: '7', 9: '8', 10: '9', 11: '0',
    12: '-', 13: '=', 14: 'BACKSPACE',
    15: 'TAB', 16: 'q', 17: 'w', 18: 'e', 19: 'r',
    20: 't', 21: 'y', 22: 'u', 23: 'i', 24: 'o',
    25: 'p', 26: '[', 27: ']', 28: 'ENTER',
    29: 'LEFT_CTRL',
    1: 'ESC',
    58: 'CAPS_LOCK',
    59: 'F1', 60: 'F2', 61: 'F3', 62: 'F4', 63: 'F5',
    64: 'F6', 65: 'F7', 66: 'F8', 67: 'F9', 68: 'F10',
    69: 'NUM_LOCK', 70: 'SCROLL_LOCK',
    71: 'KP_7', 72: 'KP_8', 73: 'KP_9', 74: 'KP_-',
    75: 'KP_4', 76: 'KP_5', 77: 'KP_6', 78: 'KP_+',
    79: 'KP_1', 80: 'KP_2', 81: 'KP_3', 82: 'KP_0',
    83: 'KP_.',
    87: 'F11', 88: 'F12',
    97: 'RIGHT_CTRL',
    98: 'KP_DIV', 99: 'KP_ENTER', 100: 'RIGHT_ALT',
    102: 'HOME', 103: 'UP', 104: 'PAGE_UP', 105: 'LEFT',
    106: 'RIGHT', 107: 'END', 108: 'DOWN', 109: 'PAGE_DOWN',
    110: 'INSERT', 111: 'DELETE',
    127: 'PAUSE'
}

DE_KEYCODE_TO_NAME = {
    30: 'a', 31: 's', 32: 'd', 33: 'f', 34: 'g',
    35: 'h', 36: 'j', 37: 'k', 38: 'l', 39: 'ö',
    40: 'ä',
    41: '^', 42: 'LEFT_SHIFT', 43: '#', 44: 'y', 45: 'x',
    46: 'c', 47: 'v', 48: 'b', 49: 'n', 50: 'm',
    51: ',', 52: '.', 53: '-', 54: 'RIGHT_SHIFT', 55: '*',
    56: 'LEFT_ALT', 57: 'SPACE', 58: 'CAPS_LOCK',
    2: '1', 3: '2', 4: '3', 5: '4', 6: '5',
    7: '6', 8: '7', 9: '8', 10: '9', 11: '0',
    12: 'ß', 13: "'",
    14: 'BACKSPACE',
    15: 'TAB', 16: 'q', 17: 'w', 18: 'e', 19: 'r',
    20: 't', 21: 'z', 22: 'u', 23: 'i', 24: 'o',
    25: 'p', 26: 'ü', 27: '+',
    28: 'ENTER',
    29: 'LEFT_CTRL',
    1: 'ESC',
    58: 'CAPS_LOCK',
    59: 'F1', 60: 'F2', 61: 'F3', 62: 'F4', 63: 'F5',
    64: 'F6', 65: 'F7', 66: 'F8', 67: 'F9', 68: 'F10',
    69: 'NUM_LOCK', 70: 'SCROLL_LOCK',
    71: 'KP_7', 72: 'KP_8', 73: 'KP_9', 74: 'KP_-',
    75: 'KP_4', 76: 'KP_5', 77: 'KP_6', 78: 'KP_+',
    79: 'KP_1', 80: 'KP_2', 81: 'KP_3', 82: 'KP_0',
    83: 'KP_.',
    87: 'F11', 88: 'F12',
    97: 'RIGHT_CTRL',
    98: 'KP_DIV', 99: 'KP_ENTER', 100: 'RIGHT_ALT',
    102: 'HOME', 103: 'UP', 104: 'PAGE_UP', 105: 'LEFT',
    106: 'RIGHT', 107: 'END', 108: 'DOWN', 109: 'PAGE_DOWN',
    110: 'INSERT', 111: 'DELETE',
    127: 'PAUSE'
}

LAYOUT_KEYCODE_MAPPINGS = {
    'us': US_KEYCODE_TO_NAME,
    'de': DE_KEYCODE_TO_NAME,
}


def get_key_name(keycode: int, layout: str = 'us') -> str:
    """Get key name for keycode in given layout.

    Args:
        keycode: Linux evdev keycode
        layout: Keyboard layout identifier ('us', 'de', etc.)

    Returns:
        Human-readable key name or 'UNKNOWN' if not found
    """
    mapping = LAYOUT_KEYCODE_MAPPINGS.get(layout, US_KEYCODE_TO_NAME)
    return mapping.get(keycode, f'KEY_{keycode}')


def is_supported_layout(layout: str) -> bool:
    """Check if layout has keycode mapping."""
    return layout in LAYOUT_KEYCODE_MAPPINGS


def is_letter_key(key_name: str) -> bool:
    """Check if a key name is a letter key (a-z, ä, ö, ü).

    Args:
        key_name: The key name to check

    Returns:
        True if the key is a letter, False otherwise
    """
    # Single letter a-z
    if len(key_name) == 1 and key_name.isalpha():
        return True
    # German umlauts
    if key_name in ('ä', 'ö', 'ü', 'ß'):
        return True
    return False
