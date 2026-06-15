#!/usr/bin/env python3
"""Simple script to clean up mixed date formats using the existing sync infrastructure.

This script uses the Storage class which handles encryption automatically.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime
import re
from utils.config import Config
from core.storage import Storage


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


def fix_date_formats():
    """Clean up mixed date formats in the local SQLite database."""
    # Get database path
    db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"
    
    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return False
    
    print(f"Opening database: {db_path}")
    
    try:
        # Load config
        config = Config(db_path)
        
        # Initialize storage (this handles encryption automatically)
        storage = Storage(db_path, config)
        
        print("Database opened successfully with encryption")
        
        # Access the adapter directly
        adapter = storage.adapter
        
        # Fix high_scores table
        print("\nProcessing high_scores table...")
        high_scores = adapter.get_all_high_scores()
        
        updated_count = 0
        for record in high_scores:
            date_value = record.get('date')
            standardized_date = standardize_date_format(date_value)
            if standardized_date != date_value:
                print(f"  Updating high_score {record.get('id')}: {date_value} -> {standardized_date}")
                # Update the record using the adapter
                adapter.update_high_score_date(record.get('id'), standardized_date)
                updated_count += 1
        
        print(f"  Updated {updated_count} records in high_scores")
        
        # Fix daily_summaries table
        print("\nProcessing daily_summaries table...")
        daily_summaries = adapter.get_all_daily_summaries()
        
        updated_count = 0
        for record in daily_summaries:
            date_value = record.get('date')
            standardized_date = standardize_date_format(date_value)
            if standardized_date != date_value:
                print(f"  Updating daily_summary: {date_value} -> {standardized_date}")
                # Update the record using the adapter
                adapter.update_daily_summary_date(date_value, standardized_date)
                updated_count += 1
        
        print(f"  Updated {updated_count} records in daily_summaries")
        
        print("\nAll date formats standardized successfully!")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("RealTypeCoach Date Format Cleanup (Simple)")
    print("=" * 60)
    
    success = fix_date_formats()
    
    if success:
        print("\n✓ Date format cleanup completed successfully!")
        print("You can now run the sync script to synchronize with PostgreSQL.")
    else:
        print("\n✗ Date format cleanup failed.")
        sys.exit(1)