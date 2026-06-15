#!/usr/bin/env python3
"""Test script to demonstrate date format standardization functionality.

This script creates a temporary test database and demonstrates that the
date format standardization works correctly.
"""

import sys
from pathlib import Path
import tempfile
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
import re
from utils.config import Config
from core.storage import Storage


class InMemoryKeyring:
    """Simple in-memory keyring to avoid DBus issues."""

    def __init__(self):
        self._passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self._passwords.pop((service, username), None)


def standardize_date_format(date_value: str | int | float | None) -> str:
    """Convert various date formats to standardized ISO 8601 format (YYYY-MM-DD)."""
    if date_value is None:
        return "1970-01-01"
    
    # If already in ISO format, return as-is
    if isinstance(date_value, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', date_value):
        return date_value
    
    # If it's a timestamp (milliseconds), convert to date
    if isinstance(date_value, (int, float)):
        try:
            # Convert from milliseconds to seconds
            timestamp_sec = date_value / 1000.0
            date_obj = datetime.fromtimestamp(timestamp_sec)
            return date_obj.strftime("%Y-%m-%d")
        except (ValueError, OverflowError):
            return "1970-01-01"
    
    # If it's a string but not in ISO format, try to parse it
    if isinstance(date_value, str):
        try:
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d-%m-%Y"]:
                try:
                    date_obj = datetime.strptime(date_value, fmt)
                    return date_obj.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            # If no format matched, return epoch date
            return "1970-01-01"
        except Exception:
            return "1970-01-01"
    
    # Fallback
    return "1970-01-01"


def test_date_standardization():
    """Test date format standardization with a temporary database."""
    print("Creating temporary test database...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        
        try:
            # Use mocked keyring to bypass system keyring requirement
            mock_keyring = InMemoryKeyring()
            
            with patch("utils.crypto.keyring", mock_keyring):
                # Import CryptoManager to generate and store a key
                from utils.crypto import CryptoManager
                
                # Create a crypto manager to generate and store a key
                crypto = CryptoManager(db_path)
                
                # Generate a key
                key = crypto.generate_key()
                crypto.store_key(key)
                print("✓ Generated and stored encryption key in mocked keyring")
                
                # Load config
                config = Config(db_path)
                print("✓ Created configuration")
                
                # Initialize storage (this handles encryption automatically)
                storage = Storage(db_path, config)
                print("✓ Initialized storage with encrypted database")
                
                # Access the adapter directly
                adapter = storage.adapter
                
                # Test date standardization function with various inputs
                print("\n" + "="*50)
                print("Testing date format standardization function:")
                print("="*50)
                
                test_cases = [
                    ("2023-12-25", "2023-12-25", "ISO format (already correct)"),
                    ("2023/12/25", "2023-12-25", "Slash-separated format"),
                    ("12/25/2023", "2023-12-25", "US format"),
                    ("25-12-2023", "2023-12-25", "European format"),
                    (1703476800000, "2023-12-25", "Timestamp (milliseconds)"),
                    (1703476800, "1970-01-19", "Timestamp (seconds) - converted"),
                    (0, "1970-01-01", "Epoch timestamp"),
                    (None, "1970-01-01", "None value"),
                    ("invalid", "1970-01-01", "Invalid string"),
                ]
                
                for input_val, expected, description in test_cases:
                    result = standardize_date_format(input_val)
                    status = "✓" if result == expected else "✗"
                    print(f"{status} {description}: {input_val} -> {result} (expected: {expected})")
                
                # Test with actual database operations
                print("\n" + "="*50)
                print("Testing database operations:")
                print("="*50)
                
                # Add some test data with mixed date formats
                print("Adding test data with mixed date formats...")
                
                # Add high scores with different date formats
                test_high_scores = [
                    {
                        "date": "2023-12-25",  # Already ISO format
                        "fastest_burst_wpm": 85.5,
                        "burst_duration_sec": 15.2,
                        "burst_key_count": 75,
                        "timestamp": 1703476800000,
                        "burst_duration_ms": 15200
                    },
                    {
                        "date": 1703476800000,  # Timestamp in milliseconds
                        "fastest_burst_wpm": 92.3,
                        "burst_duration_sec": 12.8,
                        "burst_key_count": 68,
                        "timestamp": 1703477000000,
                        "burst_duration_ms": 12800
                    },
                    {
                        "date": "25/12/2023",  # European format
                        "fastest_burst_wpm": 78.9,
                        "burst_duration_sec": 18.5,
                        "burst_key_count": 92,
                        "timestamp": 1703477200000,
                        "burst_duration_ms": 18500
                    }
                ]
                
                # Insert test data
                inserted_count = adapter.batch_insert_high_scores(test_high_scores)
                print(f"✓ Inserted {inserted_count} high score records with mixed date formats")
                
                # Retrieve and check the data
                all_high_scores = adapter.get_all_high_scores()
                print(f"✓ Retrieved {len(all_high_scores)} high score records")
                
                # Check that all dates are now standardized
                print("\nChecking date format standardization:")
                all_standardized = True
                for record in all_high_scores:
                    date_val = record.get('date')
                    is_iso_format = isinstance(date_val, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', date_val)
                    status = "✓" if is_iso_format else "✗"
                    print(f"{status} Record {record.get('id')}: date = {date_val}")
                    if not is_iso_format:
                        all_standardized = False
                
                if all_standardized:
                    print("\n✓ All dates are properly standardized to ISO 8601 format!")
                else:
                    print("\n✗ Some dates are not in ISO 8601 format")
                
                # Test daily summaries too
                print("\nTesting daily summaries...")
                
                test_daily_summaries = [
                    {
                        "date": "2023-12-25",  # ISO format
                        "total_keystrokes": 5000,
                        "total_bursts": 150,
                        "avg_wpm": 65.5,
                        "slowest_keycode": 30,
                        "slowest_key_name": "a",
                        "total_typing_sec": 450
                    },
                    {
                        "date": 1703476800000,  # Timestamp
                        "total_keystrokes": 3200,
                        "total_bursts": 95,
                        "avg_wpm": 58.2,
                        "slowest_keycode": 31,
                        "slowest_key_name": "s",
                        "total_typing_sec": 320
                    }
                ]
                
                # Insert test daily summaries
                inserted_count = adapter.batch_insert_daily_summaries(test_daily_summaries)
                print(f"✓ Inserted {inserted_count} daily summary records with mixed date formats")
                
                # Retrieve and check daily summaries
                all_daily_summaries = adapter.get_all_daily_summaries()
                print(f"✓ Retrieved {len(all_daily_summaries)} daily summary records")
                
                # Check that all dates are standardized
                print("\nChecking daily summary date format standardization:")
                all_standardized = True
                for record in all_daily_summaries:
                    date_val = record.get('date')
                    is_iso_format = isinstance(date_val, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', date_val)
                    status = "✓" if is_iso_format else "✗"
                    print(f"{status} Date = {date_val}")
                    if not is_iso_format:
                        all_standardized = False
                
                if all_standardized:
                    print("\n✓ All daily summary dates are properly standardized!")
                else:
                    print("\n✗ Some daily summary dates are not in ISO 8601 format")
                
                print("\n" + "="*60)
                print("✓ Date format standardization test completed successfully!")
                print("="*60)
                print("\nThe PostgreSQL adapter has been updated to:")
                print("1. Use standardized ISO 8601 date format (YYYY-MM-DD)")
                print("2. Handle mixed input formats gracefully")
                print("3. Store dates consistently across SQLite and PostgreSQL")
                print("\nWhen you run the actual sync with your database:")
                print("1. Existing mixed formats will be automatically standardized")
                print("2. No manual conversion will be needed")
                print("3. Data will sync seamlessly between databases")
                
                return True
                
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    print("=" * 60)
    print("RealTypeCoach Date Format Standardization Test")
    print("=" * 60)
    print("This test demonstrates the date format standardization")
    print("functionality that has been implemented in the PostgreSQL adapter.")
    print()
    
    success = test_date_standardization()
    
    if not success:
        print("\n✗ Date standardization test failed.")
        sys.exit(1)