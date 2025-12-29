"""Dictionary validation for multiple languages."""

from pathlib import Path
import logging

from core.dictionary_config import DictionaryConfig

log = logging.getLogger('realtypecoach.dictionary')


class Dictionary:
    """Dictionary validator for multiple languages with fallback support."""

    MIN_WORD_LENGTH: int = 3
    _detected_dictionaries: dict[str, str] | None = None  # Cache: language_code -> path

    @classmethod
    def _detect_dictionaries(cls) -> dict[str, str]:
        """Detect available dictionaries on the system.

        Returns:
            Dict mapping language codes to their file paths
        """
        if cls._detected_dictionaries is not None:
            return cls._detected_dictionaries

        try:
            from utils.dict_detector import DictionaryDetector
            detected = DictionaryDetector.detect_available()
            cls._detected_dictionaries = {
                d.language_code: d.path for d in detected if d.available
            }
            log.debug(f"Detected dictionaries: {list(cls._detected_dictionaries.keys())}")
            return cls._detected_dictionaries
        except (ImportError, AttributeError, OSError) as e:
            log.warning(f"Dictionary detection failed ({e})")
            cls._detected_dictionaries = {}
            return {}

    @staticmethod
    def _resolve_paths(
        requested_languages: list[str],
        custom_paths: dict[str, str]
    ) -> dict[str, str]:
        """Resolve dictionary paths for requested languages.

        Args:
            requested_languages: List of language codes
            custom_paths: Dict of custom paths per language

        Returns:
            Dict mapping language codes to resolved paths (empty if not found)
        """
        resolved = {}
        detected = Dictionary._detect_dictionaries()

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

        # Track explicit user intent for accept_all_mode
        self._explicit_accept_all_mode: bool = config.accept_all_mode

        # Resolve which languages to load
        final_languages, self.accept_all_mode = self._determine_languages_to_load(config)

        # Load dictionaries
        for lang_code in final_languages:
            path = config.custom_paths.get(lang_code)
            if path is None:
                detected = self._detect_dictionaries()
                path = detected.get(lang_code)
            if path:
                self._load_dictionary(lang_code, path)

        # Log final state
        if self.accept_all_mode:
            log.warning("Dictionary in accept-all mode - all words (3+ letters) will be valid")
        else:
            loaded = self.get_loaded_languages()
            if loaded:
                log.info(f"Dictionary loaded for languages: {', '.join(loaded)}")

    def _determine_languages_to_load(
        self,
        config: DictionaryConfig
    ) -> tuple[list[str], bool]:
        """Determine which languages to load and whether to use accept_all mode.

        Args:
            config: Dictionary configuration

        Returns:
            Tuple of (list of language codes to load, should_use_accept_all_mode)
        """
        requested = config.enabled_languages
        custom_paths = config.custom_paths

        # If explicit accept_all_mode, don't load any dictionaries
        if config.accept_all_mode:
            return [], True

        # Resolve paths for requested languages
        resolved_paths = self._resolve_paths(requested, custom_paths)

        # Check if all requested languages are available
        if len(resolved_paths) >= len(requested):
            # All (or most) requested languages available
            return list(resolved_paths.keys()), False

        # Some requested languages not available
        missing = set(requested) - set(resolved_paths.keys())
        log.warning(f"Requested languages not available: {', '.join(missing)}")

        if resolved_paths:
            # Load what we can find
            log.info(f"Loading available languages: {', '.join(resolved_paths.keys())}")
            return list(resolved_paths.keys()), False

        # No dictionaries available
        if config.auto_fallback:
            log.warning("No dictionaries available, enabling accept-all mode")
            return [], True
        else:
            log.error("No dictionaries available and auto_fallback is disabled")
            return [], False

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
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                self.words[language_code] = set(line.strip().lower() for line in f if line.strip())
            self.loaded_paths[language_code] = path
            log.info(f"Loaded {len(self.words[language_code])} {language_code} words from {path}")
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

        # Update explicit intent (preserve original choice unless explicitly changed)
        if config.accept_all_mode:
            self._explicit_accept_all_mode = True

        # Determine new state
        final_languages, self.accept_all_mode = self._determine_languages_to_load(config)

        # Load dictionaries
        for lang_code in final_languages:
            path = config.custom_paths.get(lang_code)
            if path is None:
                detected = self._detect_dictionaries()
                path = detected.get(lang_code)
            if path:
                self._load_dictionary(lang_code, path)

        # Log final state
        if self.accept_all_mode:
            log.warning("Dictionary reloaded in accept-all mode")
        else:
            loaded = self.get_loaded_languages()
            if loaded:
                log.info(f"Dictionary reloaded for languages: {', '.join(loaded)}")
