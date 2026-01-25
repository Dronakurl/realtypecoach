"""Hash manager for privacy-preserving ignored words storage.

This module provides cryptographic hashing of words using BLAKE2b-256
with a double-salt approach (user_salt + pepper) to ensure:

1. Same word produces same hash across all devices (enables sync)
2. Hash cannot be reversed to retrieve original word (privacy)
3. Server cannot see which words are ignored (only stores hashes)
4. Frontend can add words but cannot retrieve the list of original words
"""

import hashlib
import logging

log = logging.getLogger("realtypecoach.hash_manager")

# Application-wide pepper (32 bytes, embedded in code)
# TODO: Generate with secrets.token_hex(32) before first release
# This is a placeholder - generate a real pepper before production
PEPPER = bytes.fromhex("1a2b3c4d5e6f1a2b3c4d5e6f1a2b3c4d5e6f1a2b3c4d5e6f1a2b3c4d5e6f1a2b")


class HashManager:
    """Manages cryptographic hashing for ignored words.

    Uses BLAKE2b-256 with double salt (user_salt + pepper) to hash words.
    The user_salt is derived from the encryption key, ensuring consistent
    hashing across all devices with the same encryption key.
    """

    def __init__(self, encryption_key: bytes):
        """Initialize hash manager with encryption key.

        Args:
            encryption_key: 32-byte encryption key (same key used for data encryption)

        Raises:
            ValueError: If encryption_key is not 32 bytes
        """
        if len(encryption_key) != 32:
            raise ValueError(f"encryption_key must be 32 bytes, got {len(encryption_key)}")

        self.encryption_key = encryption_key
        self._user_salt = self._derive_user_salt()
        log.info("HashManager initialized with derived user_salt")

    def _derive_user_salt(self) -> bytes:
        """Derive user_salt from encryption key using BLAKE2b-256.

        All devices with the same encryption key will derive the same user_salt,
        enabling consistent hashing across devices.

        Returns:
            32-byte user_salt derived from encryption_key
        """
        h = hashlib.blake2b(digest_size=32)
        h.update(self.encryption_key)
        h.update(b"ignored_words_user_salt_derivation")
        return h.digest()

    def hash_word(self, word: str) -> str:
        """Hash a word with derived user_salt + pepper.

        Args:
            word: The word to hash (case-insensitive, will be lowercased)

        Returns:
            64-character hex string representing the hash

        Example:
            >>> hm = HashManager(encryption_key)
            >>> hash1 = hm.hash_word("example")
            >>> hash2 = hm.hash_word("Example")
            >>> hash1 == hash2  # True (case-insensitive)
            True
        """
        # Normalize word to lowercase for case-insensitive hashing
        word_normalized = word.lower().encode("utf-8")

        # Hash with BLAKE2b-256 using pepper as key
        h = hashlib.blake2b(key=PEPPER, digest_size=32)
        h.update(self._user_salt)
        h.update(word_normalized)

        return h.hexdigest()  # 64 hex chars
