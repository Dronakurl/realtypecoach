#!/usr/bin/env python3
"""Calibration script for length penalty factor.

Tests different penalty_factor values to find the optimal value
that produces target average word length of approximately 6.5.
"""
import argparse
import re
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.dictionary_config import DictionaryConfig
from core.storage import Storage
from utils.config import Config


def _is_abbreviation(word: str) -> bool:
    """Check if word is an abbreviation (>1 capital letter)."""
    return sum(1 for c in word if c.isupper()) > 1


def _is_roman_numeral(word: str) -> bool:
    """Check if word is a Roman numeral (e.g., iii, vii, xii, xvii)."""
    # Skip very short words that might be regular words
    if len(word) <= 2:
        return False

    # Check if word only contains Roman numeral letters
    roman_pattern = re.compile(r'^[ivxlcdm]+$', re.IGNORECASE)
    if not roman_pattern.match(word):
        return False

    # Common words that match roman numeral pattern but aren't
    common_words = {'civic', 'mid', 'did', 'lid', 'mix'}
    if word.lower() in common_words:
        return False

    return True


def _calculate_length_penalty(word: str, target_length: float, penalty_factor: float) -> float:
    """Calculate length penalty for weighted word selection."""
    length = len(word)

    # Extremely heavily penalize abbreviations and Roman numerals
    if _is_abbreviation(word) or _is_roman_numeral(word):
        effective_length = 100
    elif length == 3:
        effective_length = 10
    elif length == 4:
        effective_length = 8
    else:
        effective_length = length

    # Calculate penalty based on effective length
    excess = max(0, effective_length - target_length)
    return max(0.0, 1.0 - penalty_factor * excess / target_length)


def test_penalty_factor(storage, penalty_factor: float, word_count: int = 50, simulations: int = 100):
    """Test a penalty factor and return average word lengths per digraph."""
    import random

    test_digraphs = [
        (['th'], 'th'),
        (['he'], 'he'),
        (['in'], 'in'),
        (['er'], 'er'),
    ]

    target_length = 6.5
    results = {}

    for digraph_list, digraph_name in test_digraphs:
        words = storage.find_words_with_digraphs(digraph_list, language=None)

        if not words:
            continue

        # Calculate weights using new penalty formula
        weights = [
            _calculate_length_penalty(word, target_length, penalty_factor)
            for word in words
        ]

        # Simulate selection
        avg_lengths = []
        for _ in range(simulations):
            selected = random.choices(words, weights=weights, k=min(word_count, len(words)))
            avg_lengths.append(sum(len(w) for w in selected) / len(selected))

        avg = sum(avg_lengths) / len(avg_lengths)
        results[digraph_name] = avg

    return results


def main():
    parser = argparse.ArgumentParser(description="Calibrate length penalty factor")
    parser.add_argument(
        "--test-values",
        type=float,
        nargs="+",
        default=[0.10, 0.15, 0.20, 0.25, 0.30],
        help="Penalty factor values to test",
    )
    parser.add_argument(
        "--set",
        type=float,
        dest="set_value",
        help="Set the penalty factor to this value in config",
    )
    args = parser.parse_args()

    print("=== Length Penalty Calibration ===\n")

    # Initialize storage
    test_db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"

    if not test_db_path.exists():
        print(f"Error: Database not found at {test_db_path}")
        return 1

    config = Config(test_db_path)
    enabled_languages = config.get_list("enabled_languages")
    dictionary_config = DictionaryConfig(enabled_languages=enabled_languages)

    storage = Storage(
        test_db_path,
        word_boundary_timeout_ms=1000,
        dictionary_config=dictionary_config,
        config=config,
        ignore_file_path=None,
    )

    current_value = config.get_float("length_penalty_factor")
    print(f"Current penalty_factor: {current_value:.2f}\n")

    # Show current value performance
    print("=== Current Setting ===")
    current_results = test_penalty_factor(storage, current_value)
    if current_results:
        avg_length = sum(current_results.values()) / len(current_results)
        deviation = abs(avg_length - 6.5)
        print(f"penalty_factor={current_value:.2f}: avg_length={avg_length:.2f} (deviation: {deviation:.2f})")

    # Test other values
    test_values = [v for v in args.test_values if v != current_value]
    if test_values:
        print("\n=== Test Values ===")
        for value in test_values:
            results = test_penalty_factor(storage, value)
            if results:
                avg_length = sum(results.values()) / len(results)
                deviation = abs(avg_length - 6.5)
                print(f"penalty_factor={value:.2f}: avg_length={avg_length:.2f} (deviation: {deviation:.2f})")

    # Set new value if requested
    if args.set_value is not None:
        print(f"\nSetting penalty_factor to {args.set_value:.2f}")
        config.set("length_penalty_factor", args.set_value)

        # Verify it was set
        new_value = config.get_float("length_penalty_factor")
        print(f"Verification: penalty_factor is now {new_value:.2f}")

        if new_value == args.set_value:
            print("Done. Run without --set to test the new value.")
        else:
            print(f"Warning: Value not updated correctly (expected {args.set_value:.2f}, got {new_value:.2f})")

    print("\nTarget: Average length ~6.5")
    return 0


if __name__ == "__main__":
    sys.exit(main())
