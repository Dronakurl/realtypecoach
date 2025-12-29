"""Dictionary detection and language identification."""

from pathlib import Path
import re
from typing import List, Optional, Dict
from dataclasses import dataclass, field
import logging

log = logging.getLogger('realtypecoach.dict_detector')


@dataclass
class DictionaryInfo:
    """Information about a detected dictionary."""
    path: str
    language_code: str  # 'en', 'de', 'fr', etc.
    language_name: str  # 'English', 'German', etc.
    variant: Optional[str] = field(default=None)  # 'american', 'british', 'swiss', etc.
    available: bool = field(default=False)
    word_count: Optional[int] = field(default=None)


class DictionaryDetector:
    """Auto-detect available system dictionaries."""

    COMMON_SYSTEM_PATHS = [
        '/usr/share/dict',
        '/usr/dict',
        '/usr/share/dictd',
        str(Path.home() / '.local' / 'share' / 'dict'),
    ]

    LANGUAGE_PATTERNS: Dict[str, List[str]] = {
        'en': [r'words$', r'american-english', r'british-english', r'english'],
        'de': [r'ngerman', r'ogerman', r'german', r'swiss'],
        'fr': [r'french'],
        'es': [r'spanish'],
        'it': [r'italian'],
        'pt': [r'portuguese'],
        'nl': [r'dutch'],
        'pl': [r'polish'],
        'ru': [r'russian'],
    }

    LANGUAGE_NAMES: Dict[str, str] = {
        'en': 'English',
        'de': 'German',
        'fr': 'French',
        'es': 'Spanish',
        'it': 'Italian',
        'pt': 'Portuguese',
        'nl': 'Dutch',
        'pl': 'Polish',
        'ru': 'Russian',
    }

    VARIANTS: Dict[str, Dict[str, str]] = {
        'en': {
            'words': 'General',
            'american-english': 'American',
            'british-english': 'British',
        },
        'de': {
            'ngerman': 'New German (reform)',
            'ogerman': 'Old German (pre-reform)',
            'swiss': 'Swiss',
        },
    }

    # Pre-compiled regex patterns for performance
    _COMPILED_PATTERNS: Dict[str, List[re.Pattern]] = {
        lang: [re.compile(p) for p in patterns]
        for lang, patterns in LANGUAGE_PATTERNS.items()
    }

    @staticmethod
    def detect_available() -> List[DictionaryInfo]:
        """Scan system for available dictionary files.

        Returns:
            List of DictionaryInfo objects for all found dictionaries
        """
        dictionaries = []

        for base_path_str in DictionaryDetector.COMMON_SYSTEM_PATHS:
            base_path = Path(base_path_str)
            if not base_path.exists():
                continue

            try:
                for file_path in base_path.iterdir():
                    # Skip directories
                    if file_path.is_dir():
                        continue

                    # Try to identify language and variant
                    info = DictionaryDetector.identify_dictionary(str(file_path))
                    if info:
                        dictionaries.append(info)
            except PermissionError:
                log.debug(f"Permission denied scanning {base_path}")
                continue

        # Deduplicate by language code (keep first found)
        seen = set()
        unique_dictionaries = []
        for d in dictionaries:
            if d.language_code not in seen:
                seen.add(d.language_code)
                unique_dictionaries.append(d)

        log.info(f"Detected {len(unique_dictionaries)} available dictionaries")
        return unique_dictionaries

    @staticmethod
    def identify_dictionary(file_path: str) -> Optional[DictionaryInfo]:
        """Identify dictionary language and variant from filename.

        Args:
            file_path: Path to dictionary file

        Returns:
            DictionaryInfo if identified, None otherwise
        """
        filename = Path(file_path).name.lower()

        # Check if it's a valid dictionary file
        if not DictionaryDetector.validate_dictionary(file_path):
            return None

        # Try to match language patterns
        for lang_code, compiled_patterns in DictionaryDetector._COMPILED_PATTERNS.items():
            for pattern in compiled_patterns:
                if pattern.search(filename):
                    # Determine variant
                    variant = None
                    if lang_code in DictionaryDetector.VARIANTS:
                        for variant_key, variant_name in DictionaryDetector.VARIANTS[lang_code].items():
                            if variant_key in filename:
                                variant = variant_name
                                break

                    # Count words
                    word_count = DictionaryDetector.count_words(file_path)

                    return DictionaryInfo(
                        path=file_path,
                        language_code=lang_code,
                        language_name=DictionaryDetector.LANGUAGE_NAMES.get(lang_code, lang_code.upper()),
                        variant=variant,
                        available=True,
                        word_count=word_count
                    )

        return None

    @staticmethod
    def validate_dictionary(path: str) -> bool:
        """Check if file is a valid dictionary (one word per line).

        Args:
            path: Path to file to validate

        Returns:
            True if file appears to be a valid dictionary
        """
        if not Path(path).is_file():
            return False

        try:
            # Check if file is readable and has at least one line
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                line_count = 0
                MAX_LINES_TO_CHECK = 10  # Don't read entire file for validation
                for line in f:
                    stripped = line.strip()
                    if stripped:  # Found a non-empty line
                        return True
                    line_count += 1
                    if line_count >= MAX_LINES_TO_CHECK:
                        break
            return False  # No content found
        except (PermissionError, UnicodeDecodeError):
            return False

    @staticmethod
    def count_words(path: str) -> Optional[int]:
        """Count number of words in dictionary file.

        Args:
            path: Path to dictionary file

        Returns:
            Word count or None if unable to count
        """
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return sum(1 for line in f if line.strip())
        except (PermissionError, UnicodeDecodeError, OSError, IOError) as e:
            log.debug(f"Could not count words in {path}: {e}")
            return None
