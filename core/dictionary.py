"""Dictionary validation for multiple languages."""

import logging
from pathlib import Path

from core.dictionary_config import DictionaryConfig

log = logging.getLogger("realtypecoach.dictionary")


class Dictionary:
    """Dictionary validator for multiple languages with fallback support."""

    MIN_WORD_LENGTH: int = 3

    def __init__(
        self, config: DictionaryConfig, ignore_file_path: Path | None = None, storage=None
    ):
        """Initialize dictionary with configuration.

        Args:
            config: DictionaryConfig object with settings
            ignore_file_path: Optional path to ignorewords.txt file
            storage: Optional Storage instance for hash-based ignored words
        """
        self.words: dict[str, set[str]] = {}  # language_code -> word set
        self.loaded_paths: dict[str, str] = {}  # language_code -> file path
        self._capitalized_words: dict[
            str, dict[str, str]
        ] = {}  # language_code -> lowercase->capitalized mapping
        self._config: DictionaryConfig = config
        self._ignored_words: set[str] = set()
        self._storage = storage
        self._exclude_names = config.exclude_names_enabled
        self._names_set: set[str] = set()

        # Load ignore words from file
        self._load_ignore_words(ignore_file_path)

        # Load names exclusion list
        if self._exclude_names:
            self._load_names_list()

        # Resolve which languages to load and get their paths
        resolved_paths, self.accept_all_mode = self._determine_languages_to_load(config)

        # Load dictionaries using resolved paths
        for lang_code, path in resolved_paths.items():
            self._load_dictionary(lang_code, path)

        # Log final state
        if self.accept_all_mode:
            log.warning("Dictionary in accept-all mode - all words (3+ letters) will be valid")
        else:
            loaded = self.get_loaded_languages()
            if loaded:
                log.info(f"Dictionary loaded for languages: {', '.join(loaded)}")

    def _load_ignore_words(self, ignore_file_path: Path | None) -> None:
        """Load ignore words from file.

        Args:
            ignore_file_path: Path to ignorewords.txt file, or None
        """
        if ignore_file_path is None or not ignore_file_path.exists():
            return

        try:
            with open(ignore_file_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue
                    # Store lowercase for case-insensitive matching
                    self._ignored_words.add(line.lower())
            log.info(f"Loaded {len(self._ignored_words)} ignored words from {ignore_file_path}")
        except (OSError, UnicodeDecodeError) as e:
            log.warning(f"Failed to load ignore words from {ignore_file_path}: {e}")

    def _load_names_list(self) -> None:
        """Load common names from embedded list."""
        try:
            from core.common_names import COMMON_NAMES

            # Use enabled languages from config instead of loaded languages
            # (loaded_languages is empty during initialization)
            enabled_langs = self._config.enabled_languages

            for lang_code in enabled_langs:
                if lang_code in COMMON_NAMES:
                    self._names_set.update(COMMON_NAMES[lang_code])
            log.info(f"Loaded {len(self._names_set)} common names for exclusion")
        except ImportError:
            log.warning("Common names module not found")

    def update_exclude_names_setting(self, exclude_names: bool) -> None:
        """Update the exclude_names setting dynamically.

        Args:
            exclude_names: New value for exclude_names_enabled

        This allows the setting to take effect without requiring a full dictionary reload.
        """
        self._exclude_names = exclude_names

        if self._exclude_names:
            # Load names list if enabling
            if not self._names_set:
                self._load_names_list()
            log.info("Exclude names enabled: common names will be filtered from statistics")
        else:
            # Clear names list if disabling
            self._names_set.clear()
            log.info("Exclude names disabled: common names will not be filtered")

    @classmethod
    def _detect_dictionaries(cls) -> dict[str, str]:
        """Detect available dictionaries on the system.

        This method re-scans the filesystem on every call to detect
        newly installed dictionaries.

        Returns:
            Dict mapping dictionary identifiers to their file paths.
            The identifier is language_code (e.g., 'de', 'en') for the first
            dictionary found of each language to maintain backward compatibility.
        """
        try:
            from utils.dict_detector import DictionaryDetector

            detected = DictionaryDetector.detect_available()
            # Use language_code as key for backward compatibility
            # With sorted detection, this gives us ngerman before ogerman
            detected_dict = {}
            seen_languages = set()
            for d in detected:
                if d.available and d.language_code not in seen_languages:
                    detected_dict[d.language_code] = d.path
                    seen_languages.add(d.language_code)
            log.debug(f"Detected dictionaries: {list(detected_dict.keys())}")
            return detected_dict
        except (ImportError, AttributeError, OSError) as e:
            log.warning(f"Dictionary detection failed ({e})")
            return {}

    @classmethod
    def _resolve_paths(
        cls, requested_languages: list[str], custom_paths: dict[str, str]
    ) -> dict[str, str]:
        """Resolve dictionary paths for requested languages.

        Args:
            requested_languages: List of language codes
            custom_paths: Dict of custom paths per language

        Returns:
            Dict mapping language codes to resolved paths (empty if not found)
        """
        resolved = {}
        detected = cls._detect_dictionaries()

        for lang in requested_languages:
            # Custom path takes priority
            if lang in custom_paths:
                resolved[lang] = custom_paths[lang]
            # Fall back to detected dictionary
            elif lang in detected:
                resolved[lang] = detected[lang]

        return resolved

    def _determine_languages_to_load(self, config: DictionaryConfig) -> tuple[dict[str, str], bool]:
        """Determine which languages to load and whether to use accept_all mode.

        Args:
            config: Dictionary configuration

        Returns:
            Tuple of (dict mapping language codes to paths, should_use_accept_all_mode)
        """
        # If explicit accept_all_mode, don't load any dictionaries
        if config.accept_all_mode:
            return {}, True

        # If specific dictionary paths are provided, use them
        if config.enabled_dictionary_paths:
            resolved_paths = {}
            for path in config.enabled_dictionary_paths:
                # Detect language code from the dictionary file
                from utils.dict_detector import DictionaryDetector

                dict_info = DictionaryDetector.identify_dictionary(path)
                if dict_info:
                    resolved_paths[dict_info.language_code] = path
                else:
                    # Fallback: try to guess from filename
                    from pathlib import Path

                    filename = Path(path).name.lower()
                    if "ngerman" in filename or "german" in filename:
                        resolved_paths["de"] = path
                    elif "american" in filename or "english" in filename or "words" in filename:
                        resolved_paths["en"] = path
                    else:
                        log.warning(f"Could not detect language for {path}")

            if resolved_paths:
                log.info(f"Loading specific dictionaries: {list(resolved_paths.keys())}")
                return resolved_paths, False
            elif config.auto_fallback:
                log.warning("No valid specific dictionaries found, enabling accept-all mode")
                return {}, True
            else:
                log.error("No valid specific dictionaries found and auto_fallback is disabled")
                return {}, False

        # Legacy behavior: use enabled_languages
        requested = config.enabled_languages
        custom_paths = config.custom_paths

        # Resolve paths for requested languages
        resolved_paths = self._resolve_paths(requested, custom_paths)

        # Check if all requested languages are available
        if len(resolved_paths) >= len(requested):
            # All (or most) requested languages available
            return resolved_paths, False

        # Some requested languages not available
        missing = set(requested) - set(resolved_paths.keys())
        log.warning(f"Requested languages not available: {', '.join(missing)}")

        if resolved_paths:
            # Load what we can find
            log.info(f"Loading available languages: {', '.join(resolved_paths.keys())}")
            return resolved_paths, False

        # No dictionaries available
        if config.auto_fallback:
            log.warning("No dictionaries available, enabling accept-all mode")
            return {}, True
        else:
            log.error("No dictionaries available and auto_fallback is disabled")
            return {}, False

    def _load_dictionary(self, language_code: str, path: str) -> bool:
        """Load dictionary for a language.

        Args:
            language_code: Language code (e.g., 'en', 'de')
            path: Path to dictionary file

        Returns:
            True if loaded successfully, False otherwise
        """
        # Check if file exists
        if not Path(path).exists():
            log.warning(f"Dictionary file not found: {path}")
            return False

        # Load dictionary
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                # Store both lowercase for validation and original case for capitalization
                word_set = set()
                capitalized_mapping = {}
                for line in f:
                    original_word = line.strip()
                    if not original_word:
                        continue
                    lowercase_word = original_word.lower()
                    word_set.add(lowercase_word)
                    # Store the first (typically proper) capitalization for each lowercase form
                    # German dictionaries like ngerman have nouns capitalized (Haus, Aal, etc.)
                    if lowercase_word not in capitalized_mapping:
                        capitalized_mapping[lowercase_word] = original_word

                self.words[language_code] = word_set
                self._capitalized_words[language_code] = capitalized_mapping
            self.loaded_paths[language_code] = path
            log.info(f"Loaded {len(self.words[language_code])} {language_code} words from {path}")
            return True
        except (PermissionError, UnicodeDecodeError, OSError) as e:
            log.error(f"Error loading {language_code} dictionary from {path}: {e}")
            return False

    def _is_name(self, word: str) -> bool:
        """Check if word is in the common names list.

        Args:
            word: Word to check

        Returns:
            True if word is a common name
        """
        return word.lower() in self._names_set

    def is_valid_word(self, word: str, language: str | None = None) -> bool:
        """Check if word exists in loaded dictionaries.

        In accept_all_mode, always returns True for words with MIN_WORD_LENGTH+ letters.

        Args:
            word: Word to validate (case-insensitive)
            language: Specific language to check, or None to check all loaded

        Returns:
            True if word is valid
        """
        if not word:
            return False

        # Check ignore list first
        word_lower = word.lower()

        # NEW: Check hash-based ignored words from storage
        if (
            self._storage
            and self._storage.is_word_ignored(word_lower)
            or word_lower in self._ignored_words
        ):
            return False

        # Check names list if enabled
        if self._exclude_names and self._is_name(word_lower):
            return False

        # In accept-all mode, validate based on word length
        if self.accept_all_mode:
            return len(word) >= self.MIN_WORD_LENGTH

        # Check specific language if requested
        if language:
            if language in self.words:
                # Found in specific language dictionary
                if word_lower in self.words[language]:
                    return True
                # Not found in specific language, fall through to check all dictionaries
                # This allows validation when the word exists in other loaded dictionaries
            # Language not loaded or word not found, fall through to check all

        # Check all loaded dictionaries
        for word_set in self.words.values():
            if word_lower in word_set:
                return True

        return False

    def is_abbreviation_from_dictionary(self, word_lower: str) -> bool:
        """Check if word (lowercase) was originally an abbreviation in the dictionary.

        An abbreviation is defined as a word whose original form in the dictionary
        has 2+ uppercase letters AND the word isn't just a normally capitalized word
        (i.e., it's an acronym like "BTX", not a proper noun like "Haus").

        Args:
            word_lower: The lowercase word to check

        Returns:
            True if the word was originally an abbreviation/acronym
        """
        if not word_lower or self.accept_all_mode:
            return False

        # Check all loaded languages for the original capitalized form
        for lang_code, mapping in self._capitalized_words.items():
            if word_lower in mapping:
                original = mapping[word_lower]
                # Count ALL uppercase letters in the word
                # Then exclude the first character IF the word is normally capitalized
                # (i.e., if only first letter is cap, it's a noun like "Haus", not an acronym)
                uppercase_count = sum(1 for c in original if c.isupper())
                # It's an abbreviation if 2+ letters are uppercase total
                # This catches "PC" (2 caps), "USB" (3 caps) but not "Haus" (1 cap)
                return uppercase_count >= 2

        return False

    def get_loaded_languages(self) -> list[str]:
        """Get list of successfully loaded language codes.

        Returns:
            List of language codes
        """
        return list(self.words.keys())

    def is_loaded(self) -> bool:
        """Check if at least one dictionary is loaded.

        Returns:
            True if at least one dictionary is loaded (or in accept_all_mode)
        """
        return self.accept_all_mode or len(self.words) > 0

    def get_capitalized_form(self, word: str, language_code: str | None = None) -> str:
        """Get properly capitalized form of word from dictionary.

        For German nouns, returns the capitalized form (e.g., 'haus' -> 'Haus').
        For words not in dictionary or non-German languages, returns original word.

        Args:
            word: The word to look up (case-insensitive)
            language_code: Specific language to check ('de' for German), or None for all loaded

        Returns:
            Capitalized form if found in dictionary, original word otherwise
        """
        if not word:
            return word

        # In accept-all mode, we don't have capitalization info
        if self.accept_all_mode:
            return word

        word_lower = word.lower()

        # If specific language requested, only check that language
        if language_code:
            if language_code in self._capitalized_words:
                if word_lower in self._capitalized_words[language_code]:
                    return self._capitalized_words[language_code][word_lower]
            # Not found in specific language, return original
            return word

        # Otherwise check all loaded dictionaries
        for lang_code, mapping in self._capitalized_words.items():
            if word_lower in mapping:
                return mapping[word_lower]

        # Not found in any dictionary, return original
        return word

    def calculate_digraph_frequencies(self, language: str | None = None) -> dict[str, int]:
        """Calculate how many words contain each 2-character combination (digraph).

        Iterates through all dictionary words and counts how many words contain
        each 2-character combination. Used to determine "common" digraphs for
        practice filtering.

        Args:
            language: Specific language to calculate for (e.g., 'en', 'de'),
                     or None to calculate across all loaded languages

        Returns:
            Dict mapping digraph (2-char string) to word count.
            Example: {'th': 5423, 'he': 4891, 'uu': 12}
        """
        frequencies: dict[str, int] = {}

        # Get languages to process
        if language:
            languages_to_process = [language] if language in self.words else []
        else:
            languages_to_process = list(self.words.keys())

        # Count digraph occurrences
        for lang in languages_to_process:
            word_set = self.words[lang]
            for word in word_set:
                word_lower = word.lower()
                # Extract all 2-character combinations from this word
                for i in range(len(word_lower) - 1):
                    digraph = word_lower[i:i+2]
                    # Only count 2-letter combinations (no spaces, special chars)
                    if digraph.isalpha():
                        frequencies[digraph] = frequencies.get(digraph, 0) + 1

        log.info(f"Calculated digraph frequencies for {len(frequencies)} digraphs "
                 f"across {len(languages_to_process)} language(s)")
        return frequencies

    def reload_languages(self, config: DictionaryConfig) -> None:
        """Reload dictionaries with new configuration.

        Args:
            config: New Dictionary configuration
        """
        # Clear existing dictionaries
        self.words.clear()
        self.loaded_paths.clear()
        self._capitalized_words.clear()
        self._config = config
        self._exclude_names = config.exclude_names_enabled

        # Reload names list if enabled
        if self._exclude_names:
            self._names_set.clear()
            self._load_names_list()

        # Determine new state and get resolved paths
        resolved_paths, self.accept_all_mode = self._determine_languages_to_load(config)

        # Load dictionaries using resolved paths
        for lang_code, path in resolved_paths.items():
            self._load_dictionary(lang_code, path)

        # Log final state
        if self.accept_all_mode:
            log.warning("Dictionary reloaded in accept-all mode")
        else:
            loaded = self.get_loaded_languages()
            if loaded:
                log.info(f"Dictionary reloaded for languages: {', '.join(loaded)}")
