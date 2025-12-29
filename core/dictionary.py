"""Dictionary validation for English and German words."""

import os
from typing import Set, List, Optional
import logging

log = logging.getLogger('realtypecoach.dictionary')


class Dictionary:
    """Dictionary validator for English and German words."""

    def __init__(self, english_path: Optional[str] = None, german_path: Optional[str] = None):
        """Initialize dictionary with word lists.

        Args:
            english_path: Path to English dictionary file
            german_path: Path to German dictionary file
        """
        self.english_words: Set[str] = set()
        self.german_words: Set[str] = set()
        self.english_loaded = False
        self.german_loaded = False

        if english_path is None:
            english_path = '/usr/share/dict/words'

        if german_path is None:
            german_path = '/usr/share/dict/ngerman'

        self._load_english(english_path)
        self._load_german(german_path)

    def _load_english(self, path: str) -> None:
        """Load English dictionary from file.

        Args:
            path: Path to dictionary file
        """
        if not os.path.exists(path):
            log.warning(f"English dictionary not found: {path}")
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.english_words = set(line.strip().lower() for line in f if line.strip())
            self.english_loaded = True
            log.info(f"Loaded {len(self.english_words)} English words from {path}")
        except Exception as e:
            log.error(f"Error loading English dictionary: {e}")

    def _load_german(self, path: str) -> None:
        """Load German dictionary from file.

        Args:
            path: Path to dictionary file
        """
        if not os.path.exists(path):
            log.warning(f"German dictionary not found: {path}")
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.german_words = set(line.strip().lower() for line in f if line.strip())
            self.german_loaded = True
            log.info(f"Loaded {len(self.german_words)} German words from {path}")
        except Exception as e:
            log.error(f"Error loading German dictionary: {e}")

    def is_valid_word(self, word: str, language: Optional[str] = None) -> bool:
        """Check if word exists in dictionary.

        Args:
            word: Word to validate (case-insensitive)
            language: Language code ('en' or 'de'), or None to check both

        Returns:
            True if word exists in dictionary, False otherwise
        """
        if not word:
            return False

        word_lower = word.lower()

        if language == 'en':
            return self.english_loaded and word_lower in self.english_words
        elif language == 'de':
            return self.german_loaded and word_lower in self.german_words
        else:
            return (self.english_loaded and word_lower in self.english_words) or \
                   (self.german_loaded and word_lower in self.german_words)

    def get_available_languages(self) -> List[str]:
        """Get list of available languages.

        Returns:
            List of language codes ('en', 'de')
        """
        languages = []
        if self.english_loaded:
            languages.append('en')
        if self.german_loaded:
            languages.append('de')
        return languages

    def is_loaded(self) -> bool:
        """Check if at least one dictionary is loaded.

        Returns:
            True if at least one dictionary is loaded
        """
        return self.english_loaded or self.german_loaded
