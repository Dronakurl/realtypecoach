"""
Monkeytype URL generator for custom text practice.

This module generates Monkeytype-compatible URLs with custom text using
LZ-string compression, allowing direct links to start typing sessions.

Monkeytype Reference:
- URL format: https://monkeytype.com/?testSettings=<COMPRESSED_JSON>
- JSON structure: [Mode, Mode2, CustomTextSettings, Punctuation, Numbers, Language, Difficulty, Funbox]
"""

import json
from lzstring import LZString

# Monkeytype URL
MONKEYTYPE_URL = "https://monkeytype.com/"


def generate_custom_text_url(text: str, mode: str = "repeat") -> str:
    """
    Generate a Monkeytype URL with custom text.

    Args:
        text: The practice text to type
        mode: Custom text mode - "repeat" (default), "max", or "zip"

    Returns:
        A complete Monkeytype URL that opens with the custom text loaded

    Example:
        >>> url = generate_custom_text_url("Hello World!")
        >>> print(url)
        https://monkeytype.com/?testSettings=NoIgxgrgzgLg9gWx...
    """
    # Split text into words (Monkeytype stores text as word array)
    words = text.split()

    # Monkeytype's test settings structure is an 8-element tuple:
    # [0] Mode | null
    # [1] Mode2 | null
    # [2] CustomTextSettings | null
    # [3] boolean | null (punctuation)
    # [4] boolean | null (numbers)
    # [5] string | null (language)
    # [6] Difficulty | null
    # [7] FunboxName[] | null

    custom_text_settings = {
        "text": words,
        "mode": mode,
        "limit": {
            "mode": "word",
            "value": len(words)
        },
        "pipeDelimiter": False
    }

    # Build the settings array
    settings = [
        "custom",      # [0] Mode
        None,          # [1] Mode2 (not applicable for custom)
        custom_text_settings,  # [2] CustomTextSettings
        None,          # [3] Punctuation (use default)
        None,          # [4] Numbers (use default)
        None,          # [5] Language (use default)
        None,          # [6] Difficulty (use default)
        None           # [7] Funbox (use default)
    ]

    # Convert to JSON and compress using LZ-string
    json_str = json.dumps(settings, separators=(',', ':'))
    lz = LZString()

    # Monkeytype uses compressToEncodedURIComponent (same as compressToURI in lz-ts)
    compressed = lz.compressToEncodedURIComponent(json_str)

    # Build and return the final URL
    return f"{MONKEYTYPE_URL}?testSettings={compressed}"


def get_url_info(url: str) -> dict:
    """
    Extract information about a Monkeytype URL.

    Args:
        url: A Monkeytype URL with testSettings parameter

    Returns:
        Dict with 'word_count', 'url_length', and 'compressed_size' info
    """
    if "?testSettings=" not in url:
        return {"error": "Not a valid Monkeytype URL"}

    compressed_part = url.split("?testSettings=")[1]

    return {
        "url_length": len(url),
        "compressed_size": len(compressed_part),
    }
