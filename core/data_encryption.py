"""Client-side AES-256-GCM encryption for PostgreSQL data."""

import base64
import json
import logging
import os
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

log = logging.getLogger("realtypecoach.data_encryption")

# GCM standard IV size (12 bytes recommended for GCM)
IV_SIZE = 12


class DataEncryption:
    """Client-side AES-256-GCM encryption for PostgreSQL data.

    Encrypts entire records to JSON before storing in PostgreSQL.
    Uses random IV per encryption (12 bytes for GCM).

    What gets encrypted:
    - All typing statistics (WPM, press times, durations)
    - Burst timing data
    - Word statistics
    - High scores

    What stays plaintext:
    - user_id (for filtering)
    - Timestamps (for date range queries)
    - Primary key fields (for joins/lookups)
    """

    def __init__(self, encryption_key: bytes):
        """Initialize encryption with a 256-bit key.

        Args:
            encryption_key: 32-byte encryption key for AES-256

        Raises:
            ValueError: If key is not 32 bytes
        """
        if len(encryption_key) != 32:
            raise ValueError(f"Encryption key must be 32 bytes, got {len(encryption_key)}")

        self.key = encryption_key
        self.backend = default_backend()

    def encrypt_record(self, record: dict[str, Any]) -> str:
        """Encrypt a record dictionary to base64 encoded string.

        Args:
            record: Dictionary containing record data to encrypt

        Returns:
            Base64 encoded encrypted data (IV + ciphertext + tag)

        Raises:
            ValueError: If record is not a dictionary
        """
        if not isinstance(record, dict):
            raise ValueError("Record must be a dictionary")

        # Convert record to JSON
        json_data = json.dumps(record, separators=(",", ":")).encode("utf-8")

        # Generate random IV for each encryption
        iv = os.urandom(IV_SIZE)

        # Encrypt with AES-256-GCM
        aesgcm = AESGCM(self.key)
        ciphertext = aesgcm.encrypt(iv, json_data, None)

        # Return base64 encoded (IV + ciphertext)
        # GCM mode appends the 16-byte auth tag to ciphertext automatically
        result = iv + ciphertext
        return base64.b64encode(result).decode("utf-8")

    def decrypt_record(self, encrypted_b64: str) -> dict[str, Any]:
        """Decrypt a base64 encoded encrypted string.

        Args:
            encrypted_b64: Base64 encoded encrypted data (IV + ciphertext + tag)

        Returns:
            Decrypted record dictionary

        Raises:
            ValueError: If decryption fails
        """
        try:
            # Decode base64
            encrypted_data = base64.b64decode(encrypted_b64)

            # Extract IV and ciphertext
            iv = encrypted_data[:IV_SIZE]
            ciphertext = encrypted_data[IV_SIZE:]

            # Decrypt with AES-256-GCM
            aesgcm = AESGCM(self.key)
            plaintext = aesgcm.decrypt(iv, ciphertext, None)

            # Parse JSON
            return json.loads(plaintext.decode("utf-8"))
        except Exception as e:
            raise ValueError(f"Decryption failed: {e}")

    def encrypt_burst(
        self,
        start_time: int,
        end_time: int,
        key_count: int,
        backspace_count: int,
        net_key_count: int,
        duration_ms: int,
        avg_wpm: float,
        qualifies_for_high_score: bool,
    ) -> str:
        """Encrypt burst data.

        Args:
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
            key_count: Total key count
            backspace_count: Backspace count
            net_key_count: Net key count
            duration_ms: Duration in milliseconds
            avg_wpm: Average WPM
            qualifies_for_high_score: Whether burst qualifies for high score

        Returns:
            Base64 encoded encrypted data
        """
        record = {
            "start_time": start_time,
            "end_time": end_time,
            "key_count": key_count,
            "backspace_count": backspace_count,
            "net_key_count": net_key_count,
            "duration_ms": duration_ms,
            "avg_wpm": avg_wpm,
            "qualifies_for_high_score": qualifies_for_high_score,
        }
        return self.encrypt_record(record)

    def decrypt_burst(self, encrypted_b64: str) -> dict[str, Any]:
        """Decrypt burst data.

        Args:
            encrypted_b64: Base64 encoded encrypted data

        Returns:
            Dictionary with burst fields
        """
        return self.decrypt_record(encrypted_b64)

    def encrypt_statistics(
        self,
        keycode: int,
        key_name: str,
        layout: str,
        avg_press_time: float,
        total_presses: int,
        slowest_ms: float,
        fastest_ms: float,
        last_updated: int,
    ) -> str:
        """Encrypt key statistics data.

        Args:
            keycode: Key code
            key_name: Key name
            layout: Keyboard layout
            avg_press_time: Average press time
            total_presses: Total press count
            slowest_ms: Slowest press time
            fastest_ms: Fastest press time
            last_updated: Last updated timestamp

        Returns:
            Base64 encoded encrypted data
        """
        record = {
            "keycode": keycode,
            "key_name": key_name,
            "layout": layout,
            "avg_press_time": avg_press_time,
            "total_presses": total_presses,
            "slowest_ms": slowest_ms,
            "fastest_ms": fastest_ms,
            "last_updated": last_updated,
        }
        return self.encrypt_record(record)

    def decrypt_statistics(self, encrypted_b64: str) -> dict[str, Any]:
        """Decrypt key statistics data.

        Args:
            encrypted_b64: Base64 encoded encrypted data

        Returns:
            Dictionary with statistics fields
        """
        return self.decrypt_record(encrypted_b64)

    def encrypt_word_statistics(
        self,
        word: str,
        layout: str,
        avg_speed_ms_per_letter: float,
        total_letters: int,
        total_duration_ms: int,
        observation_count: int,
        last_seen: int,
        backspace_count: int = 0,
        editing_time_ms: int = 0,
    ) -> str:
        """Encrypt word statistics data.

        Args:
            word: The word
            layout: Keyboard layout
            avg_speed_ms_per_letter: Average speed per letter
            total_letters: Total letter count
            total_duration_ms: Total duration
            observation_count: Observation count
            last_seen: Last seen timestamp
            backspace_count: Backspace count
            editing_time_ms: Editing time

        Returns:
            Base64 encoded encrypted data
        """
        record = {
            "word": word,
            "layout": layout,
            "avg_speed_ms_per_letter": avg_speed_ms_per_letter,
            "total_letters": total_letters,
            "total_duration_ms": total_duration_ms,
            "observation_count": observation_count,
            "last_seen": last_seen,
            "backspace_count": backspace_count,
            "editing_time_ms": editing_time_ms,
        }
        return self.encrypt_record(record)

    def decrypt_word_statistics(self, encrypted_b64: str) -> dict[str, Any]:
        """Decrypt word statistics data.

        Args:
            encrypted_b64: Base64 encoded encrypted data

        Returns:
            Dictionary with word statistics fields
        """
        return self.decrypt_record(encrypted_b64)

    def encrypt_digraph_statistics(
        self,
        first_keycode: int,
        second_keycode: int,
        first_key: str,
        second_key: str,
        layout: str,
        avg_interval_ms: float,
        total_sequences: int,
        slowest_ms: float,
        fastest_ms: float,
        last_updated: int,
    ) -> str:
        """Encrypt digraph statistics data.

        Args:
            first_keycode: First key keycode
            second_keycode: Second key keycode
            first_key: First key name
            second_key: Second key name
            layout: Keyboard layout
            avg_interval_ms: Average interval between keys
            total_sequences: Total number of sequences observed
            slowest_ms: Slowest interval
            fastest_ms: Fastest interval
            last_updated: Last updated timestamp

        Returns:
            Base64 encoded encrypted data
        """
        record = {
            "first_keycode": first_keycode,
            "second_keycode": second_keycode,
            "first_key": first_key,
            "second_key": second_key,
            "layout": layout,
            "avg_interval_ms": avg_interval_ms,
            "total_sequences": total_sequences,
            "slowest_ms": slowest_ms,
            "fastest_ms": fastest_ms,
            "last_updated": last_updated,
        }
        return self.encrypt_record(record)

    def decrypt_digraph_statistics(self, encrypted_b64: str) -> dict[str, Any]:
        """Decrypt digraph statistics data.

        Args:
            encrypted_b64: Base64 encoded encrypted data

        Returns:
            Dictionary with digraph statistics fields
        """
        return self.decrypt_record(encrypted_b64)

    def encrypt_high_score(
        self,
        date: str,
        fastest_burst_wpm: float,
        burst_duration_sec: float,
        burst_key_count: int,
        timestamp: int,
        burst_duration_ms: int,
    ) -> str:
        """Encrypt high score data.

        Args:
            date: Date string
            fastest_burst_wpm: Fastest burst WPM
            burst_duration_sec: Burst duration in seconds
            burst_key_count: Key count
            timestamp: Timestamp
            burst_duration_ms: Burst duration in milliseconds

        Returns:
            Base64 encoded encrypted data
        """
        record = {
            "date": date,
            "fastest_burst_wpm": fastest_burst_wpm,
            "burst_duration_sec": burst_duration_sec,
            "burst_key_count": burst_key_count,
            "timestamp": timestamp,
            "burst_duration_ms": burst_duration_ms,
        }
        return self.encrypt_record(record)

    def decrypt_high_score(self, encrypted_b64: str) -> dict[str, Any]:
        """Decrypt high score data.

        Args:
            encrypted_b64: Base64 encoded encrypted data

        Returns:
            Dictionary with high score fields
        """
        return self.decrypt_record(encrypted_b64)

    def encrypt_daily_summary(
        self,
        date: str,
        total_keystrokes: int,
        total_bursts: int,
        avg_wpm: float,
        slowest_keycode: int,
        slowest_key_name: str,
        total_typing_sec: int,
        summary_sent: bool = False,
    ) -> str:
        """Encrypt daily summary data.

        Args:
            date: Date string
            total_keystrokes: Total keystrokes
            total_bursts: Total bursts
            avg_wpm: Average WPM
            slowest_keycode: Slowest keycode
            slowest_key_name: Slowest key name
            total_typing_sec: Total typing time in seconds
            summary_sent: Whether summary was sent

        Returns:
            Base64 encoded encrypted data
        """
        record = {
            "date": date,
            "total_keystrokes": total_keystrokes,
            "total_bursts": total_bursts,
            "avg_wpm": avg_wpm,
            "slowest_keycode": slowest_keycode,
            "slowest_key_name": slowest_key_name,
            "total_typing_sec": total_typing_sec,
            "summary_sent": summary_sent,
        }
        return self.encrypt_record(record)

    def decrypt_daily_summary(self, encrypted_b64: str) -> dict[str, Any]:
        """Decrypt daily summary data.

        Args:
            encrypted_b64: Base64 encoded encrypted data

        Returns:
            Dictionary with daily summary fields
        """
        return self.decrypt_record(encrypted_b64)
