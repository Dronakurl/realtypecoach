"""Dictionary validation for multiple languages."""

from pathlib import Path
import logging

from core.dictionary_config import DictionaryConfig

log = logging.getLogger("realtypecoach.dictionary")


class Dictionary:
    """Dictionary validator for multiple languages with fallback support."""

    MIN_WORD_LENGTH: int = 3

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

    def __init__(self, config: DictionaryConfig):
        """Initialize dictionary with configuration.

        Args:
            config: DictionaryConfig object with settings
        """
        self.words: dict[str, set[str]] = {}  # language_code -> word set
        self.loaded_paths: dict[str, str] = {}  # language_code -> file path
        self._config: DictionaryConfig = config

        # Resolve which languages to load and get their paths
        resolved_paths, self.accept_all_mode = self._determine_languages_to_load(config)

        # Load dictionaries using resolved paths
        for lang_code, path in resolved_paths.items():
            self._load_dictionary(lang_code, path)

        # Log final state
        if self.accept_all_mode:
            log.warning(
                "Dictionary in accept-all mode - all words (3+ letters) will be valid"
            )
        else:
            loaded = self.get_loaded_languages()
            if loaded:
                log.info(f"Dictionary loaded for languages: {', '.join(loaded)}")

    def _determine_languages_to_load(
        self, config: DictionaryConfig
    ) -> tuple[dict[str, str], bool]:
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
                    import re
                    from pathlib import Path
                    filename = Path(path).name.lower()
                    if 'ngerman' in filename or 'german' in filename:
                        resolved_paths['de'] = path
                    elif 'american' in filename or 'english' in filename or 'words' in filename:
                        resolved_paths['en'] = path
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
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                self.words[language_code] = set(
                    line.strip().lower() for line in f if line.strip()
                )
            self.loaded_paths[language_code] = path
            log.info(
                f"Loaded {len(self.words[language_code])} {language_code} words from {path}"
            )
            return True
        except (PermissionError, UnicodeDecodeError, OSError, IOError) as e:
            log.error(f"Error loading {language_code} dictionary from {path}: {e}")
            return False

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

        # In accept-all mode, validate based on word length
        if self.accept_all_mode:
            return len(word) >= self.MIN_WORD_LENGTH

        word_lower = word.lower()

        # Check specific language if requested
        if language:
            if language in self.words:
                return word_lower in self.words[language]
            return False

        # Check all loaded dictionaries
        for word_set in self.words.values():
            if word_lower in word_set:
                return True

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

    def reload_languages(self, config: DictionaryConfig) -> None:
        """Reload dictionaries with new configuration.

        Args:
            config: New Dictionary configuration
        """
        # Clear existing dictionaries
        self.words.clear()
        self.loaded_paths.clear()
        self._config = config

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
