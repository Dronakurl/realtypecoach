"""Dictionary detection and language identification."""

import logging
import re
import os
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("realtypecoach.dict_detector")


@dataclass
class DictionaryInfo:
    """Information about a detected dictionary."""

    path: str
    language_code: str  # 'en', 'de', 'fr', etc.
    language_name: str  # 'English', 'German', etc.
    variant: str | None = field(default=None)  # 'american', 'british', 'swiss', etc.
    available: bool = field(default=False)
    word_count: int | None = field(default=None)


class DictionaryDetector:
    """Auto-detect available system dictionaries."""

    COMMON_SYSTEM_PATHS = [
        "/usr/share/dict",
        "/usr/dict",
        "/usr/share/dictd",
        str(Path.home() / ".local" / "share" / "dict"),
    ]

    LANGUAGE_PATTERNS: dict[str, list[str]] = {
        "en": [r"words$", r"american-english", r"british-english", r"english"],
        "de": [r"ngerman", r"ogerman", r"german", r"swiss"],
        "fr": [r"french"],
        "es": [r"spanish"],
        "it": [r"italian"],
        "pt": [r"portuguese"],
        "nl": [r"dutch"],
        "pl": [r"polish"],
        "ru": [r"russian"],
    }

    LANGUAGE_NAMES: dict[str, str] = {
        "en": "English",
        "de": "German",
        "fr": "French",
        "es": "Spanish",
        "it": "Italian",
        "pt": "Portuguese",
        "nl": "Dutch",
        "pl": "Polish",
        "ru": "Russian",
    }

    VARIANTS: dict[str, dict[str, str]] = {
        "en": {
            "words": "General",
            "american-english": "American",
            "british-english": "British",
        },
        "de": {
            "ngerman": "New German (reform)",
            "ogerman": "Old German (pre-reform)",
            "swiss": "Swiss",
        },
    }

    # Pre-compiled regex patterns for performance
    _COMPILED_PATTERNS: dict[str, list[re.Pattern]] = {
        lang: [re.compile(p) for p in patterns] for lang, patterns in LANGUAGE_PATTERNS.items()
    }

    @staticmethod
    def detect_available() -> list[DictionaryInfo]:
        """Scan system for available dictionary files.

        Returns:
            List of DictionaryInfo objects for all found dictionaries
        """
        dictionaries = []

        # Allow override via REALTYPECOACH_DICTIONARY_PATHS env var (comma-separated)
        env_paths = os.environ.get("REALTYPECOACH_DICTIONARY_PATHS")
        search_paths = list(DictionaryDetector.COMMON_SYSTEM_PATHS)
        if env_paths:
            # Prepend so env-specified paths have higher priority
            for p in reversed(env_paths.split(",")):
                search_paths.insert(0, p)

        for base_path_str in search_paths:
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

        # Sort to prefer ngerman over ogerman, and give consistent ordering
        def dict_priority_key(d: DictionaryInfo) -> tuple:
            # Priority: prefer modern/reform dictionaries, lowest number first
            priority = 5  # Default middle priority
            if d.variant and "pre-reform" in d.variant:
                priority = 10  # Lowest priority for old/pre-reform
            elif d.variant and "reform" in d.variant:
                priority = 1  # High priority for reform dictionaries
            elif d.variant and "Swiss" in d.variant:
                priority = 3  # Medium-high priority for Swiss (after reform)

            # Then sort by language name, then variant
            return (priority, d.language_name, d.variant or "")

        dictionaries.sort(key=dict_priority_key)

        log.info(f"Detected {len(dictionaries)} available dictionaries")
        return dictionaries

    @staticmethod
    def identify_dictionary(file_path: str) -> DictionaryInfo | None:
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

        # Quick heuristic: accept files explicitly named with the language code
        # e.g., en.txt, de.txt, en-US.txt, english.txt
        for lang_code in DictionaryDetector.LANGUAGE_NAMES.keys():
            if filename.startswith(f"{lang_code}.") or filename.endswith(f".{lang_code}") or filename.startswith(f"{lang_code}-"):
                word_count = DictionaryDetector.count_words(file_path)
                return DictionaryInfo(
                    path=file_path,
                    language_code=lang_code,
                    language_name=DictionaryDetector.LANGUAGE_NAMES.get(lang_code, lang_code.upper()),
                    variant=None,
                    available=True,
                    word_count=word_count,
                )

        # Try to match language patterns
        for (
            lang_code,
            compiled_patterns,
        ) in DictionaryDetector._COMPILED_PATTERNS.items():
            for pattern in compiled_patterns:
                if pattern.search(filename):
                    # Determine variant
                    variant = None
                    if lang_code in DictionaryDetector.VARIANTS:
                        for variant_key, variant_name in DictionaryDetector.VARIANTS[
                            lang_code
                        ].items():
                            if variant_key in filename:
                                variant = variant_name
                                break

                    # Count words
                    word_count = DictionaryDetector.count_words(file_path)

                    return DictionaryInfo(
                        path=file_path,
                        language_code=lang_code,
                        language_name=DictionaryDetector.LANGUAGE_NAMES.get(
                            lang_code, lang_code.upper()
                        ),
                        variant=variant,
                        available=True,
                        word_count=word_count,
                    )

        return None

    @staticmethod
    def validate_dictionary(path: str) -> bool:
        """Check if file is a valid dictionary (one word per line).

        This validator is conservative: it accepts files where multiple lines
        (up to MAX_LINES_TO_CHECK) look like single-word entries (no spaces,
        contain at least one alphabetic character, and do not contain XML/HTML
        markers). This avoids treating XML phrasebooks or other structured files
        as plain dictionaries.

        Args:
            path: Path to file to validate

        Returns:
            True if file appears to be a valid dictionary
        """
        if not Path(path).is_file():
            return False

        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                MAX_LINES_TO_CHECK = 20
                candidate_count = 0
                checked = 0
                for line in f:
                    if checked >= MAX_LINES_TO_CHECK:
                        break
                    checked += 1
                    stripped = line.strip()
                    if not stripped:
                        continue
                    # Reject lines that look like XML/HTML or contain angle brackets
                    if "<" in stripped or ">" in stripped:
                        continue
                    # Reject lines with whitespace (likely phrases/sentences)
                    if " " in stripped or "\t" in stripped:
                        continue
                    # Require at least one alphabetic character
                    if not any(c.isalpha() for c in stripped):
                        continue
                    # Looks like a single-word entry
                    candidate_count += 1
                    if candidate_count >= 3:
                        return True
            return False
        except (PermissionError, UnicodeDecodeError, OSError):
            return False

    @staticmethod
    def count_words(path: str) -> int | None:
        """Count number of words in dictionary file.

        Args:
            path: Path to dictionary file

        Returns:
            Word count or None if unable to count
        """
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                return sum(1 for line in f if line.strip())
        except (PermissionError, UnicodeDecodeError, OSError) as e:
            log.debug(f"Could not count words in {path}: {e}")
            return None
