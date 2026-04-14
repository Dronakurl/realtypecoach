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
        "/usr/share/hunspell",
        "/usr/share/myspell",
        "/usr/share/myspell/dicts",
        str(Path.home() / ".local" / "share" / "dict"),
        str(Path.home() / ".local" / "share" / "hunspell"),
    ]

    LANGUAGE_PATTERNS: dict[str, list[str]] = {
        "en": [r"words$", r"american-english", r"british-english", r"english", r"en_[A-Z]{2}", r"en_GB", r"en_US"],
        "de": [r"ngerman", r"ogerman", r"german", r"swiss", r"de_[A-Z]{2}", r"de_DE", r"de_AT", r"de_CH"],
        "fr": [r"french", r"fr_[A-Z]{2}", r"fr_FR"],
        "es": [r"spanish", r"es_[A-Z]{2}", r"es_ES"],
        "it": [r"italian", r"it_[A-Z]{2}", r"it_IT"],
        "pt": [r"portuguese", r"pt_[A-Z]{2}", r"pt_PT", r"pt_BR"],
        "nl": [r"dutch", r"nl_[A-Z]{2}", r"nl_NL"],
        "pl": [r"polish", r"pl_[A-Z]{2}", r"pl_PL"],
        "ru": [r"russian", r"ru_[A-Z]{2}", r"ru_RU"],
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
            "en_us": "American (US)",
            "en_gb": "British (GB)",
            "en_ca": "Canadian",
            "en_au": "Australian",
        },
        "de": {
            "ngerman": "New German (reform)",
            "ogerman": "Old German (pre-reform)",
            "swiss": "Swiss",
            "de_de": "German (Germany)",
            "de_at": "German (Austria)",
            "de_ch": "German (Switzerland)",
            "de_li": "German (Liechtenstein)",
            "de_lu": "German (Luxembourg)",
            "de_be": "German (Belgium)",
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
            path_priority = 5  # Default path priority
            # Prefer /usr/share/hunspell over /usr/share/myspell/dicts
            if "/usr/share/hunspell/" in d.path:
                path_priority = 1  # High priority for hunspell
            elif "/usr/share/myspell/dicts/" in d.path:
                path_priority = 10  # Low priority for myspell/dicts (duplicates)

            priority = path_priority
            if d.variant and "pre-reform" in d.variant:
                priority += 5  # Lowest priority for old/pre-reform
            elif d.variant and "reform" in d.variant:
                priority -= 1  # High priority for reform dictionaries
            elif d.variant and "Swiss" in d.variant:
                priority += 0  # Medium-high priority for Swiss (after reform)

            # Then sort by language name, then variant
            return (priority, d.language_name, d.variant or "")

        dictionaries.sort(key=dict_priority_key)

        # Deduplicate: keep first occurrence of each (language_code, variant) combination
        seen = set()
        deduplicated = []
        for d in dictionaries:
            key = (d.language_code, d.variant or "General")
            if key not in seen:
                seen.add(key)
                deduplicated.append(d)
            else:
                log.debug(f"Skipping duplicate dictionary: {d.path} (duplicate of {key})")

        log.info(f"Detected {len(deduplicated)} available dictionaries (deduplicated from {len(dictionaries)})")
        return deduplicated

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
        # e.g., en.txt, de.txt, en-US.txt, en_US.txt, english.txt
        for lang_code in DictionaryDetector.LANGUAGE_NAMES.keys():
            if filename.startswith(f"{lang_code}.") or filename.endswith(f".{lang_code}") or filename.startswith(f"{lang_code}-") or filename.startswith(f"{lang_code}_"):
                # Extract variant from locale code (e.g., de_DE.dic -> "German (Germany)")
                variant = None
                if lang_code in DictionaryDetector.VARIANTS:
                    # Extract locale part from filename (e.g., "de_DE" from "de_DE.dic")
                    import re
                    locale_match = re.match(rf'^{lang_code}[_-]([a-zA-Z]{{2}})', filename)
                    if locale_match:
                        locale_code = f"{lang_code}_{locale_match.group(1).lower()}"
                        variant = DictionaryDetector.VARIANTS[lang_code].get(locale_code)

                word_count = DictionaryDetector.count_words(file_path)
                return DictionaryInfo(
                    path=file_path,
                    language_code=lang_code,
                    language_name=DictionaryDetector.LANGUAGE_NAMES.get(lang_code, lang_code.upper()),
                    variant=variant,
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
                            # Check both underscore and hyphen separators
                            if f"{variant_key}" in filename.lower().replace("-", "_"):
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

        # Check for .dic extension (hunspell dictionaries)
        is_hunspell = path.endswith('.dic')

        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                MAX_LINES_TO_CHECK = 20
                candidate_count = 0
                checked = 0
                line_num = 0
                for line in f:
                    line_num += 1
                    if checked >= MAX_LINES_TO_CHECK:
                        break
                    stripped = line.strip()

                    # Skip first line for .dic files (contains word count)
                    if is_hunspell and line_num == 1:
                        continue

                    # Skip empty lines and metadata for .dic files
                    if not stripped:
                        continue
                    if is_hunspell and (stripped.startswith('\t') or stripped.startswith(' ')):
                        continue

                    # Reject lines that look like XML/HTML or contain angle brackets
                    if "<" in stripped or ">" in stripped:
                        continue

                    # For .dic files, strip the suffix information (e.g., "word/abc" -> "word")
                    if is_hunspell:
                        stripped = stripped.split('/')[0]

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
        is_hunspell = path.endswith('.dic')
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                if is_hunspell:
                    # For .dic files, skip first line (count) and metadata lines
                    # Count only actual word entries
                    count = 0
                    line_num = 0
                    for line in f:
                        line_num += 1
                        stripped = line.strip()
                        # Skip first line (count)
                        if line_num == 1:
                            continue
                        # Skip metadata and empty lines
                        if not stripped or stripped.startswith('\t') or stripped.startswith(' '):
                            continue
                        # Count the word (ignore suffix information after /)
                        if '/' in stripped:
                            word = stripped.split('/')[0]
                        else:
                            word = stripped
                        if word and any(c.isalpha() for c in word):
                            count += 1
                    return count
                else:
                    # For plain text dictionaries, count all non-empty lines
                    return sum(1 for line in f if line.strip())
        except (PermissionError, UnicodeDecodeError, OSError) as e:
            log.debug(f"Could not count words in {path}: {e}")
            return None
