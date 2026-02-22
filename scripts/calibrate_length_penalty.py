#!/usr/bin/env python3
"""Calibration script for length penalty factor.

Tests different penalty_factor values to validate that the default
produces target average word length of approximately 5.
"""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.dictionary_config import DictionaryConfig
from core.storage import Storage
from utils.config import Config


def main():
    import random

    print("=== Length Penalty Calibration ===\n")

    # Initialize storage
    test_db_path = Path.home() / ".local" / "share" / "realtypecoach" / "typing_data.db"

    if not test_db_path.exists():
        print(f"Error: Database not found at {test_db_path}")
        return

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

    # Test with common digraphs
    test_digraphs = [
        (['th'], 'th'),
        (['he'], 'he'),
        (['in'], 'in'),
        (['er'], 'er'),
    ]

    word_count = 50
    penalty_factor = 0.15  # Default value

    print(f"Testing penalty_factor={penalty_factor}, word_count={word_count}\n")

    for digraph_list, digraph_name in test_digraphs:
        words = storage.find_words_with_digraphs(digraph_list, language=None)

        if not words:
            continue

        # Calculate weights
        target_length = 5
        weights = [
            1.0 / (1.0 + penalty_factor * ((len(word) - target_length) ** 2))
            for word in words
        ]

        # Simulate selection
        avg_lengths = []
        for _ in range(100):
            selected = random.choices(words, weights=weights, k=min(word_count, len(words)))
            avg_lengths.append(sum(len(w) for w in selected) / len(selected))

        avg = sum(avg_lengths) / len(avg_lengths)
        print(f"  {digraph_name}: {len(words)} words, avg length = {avg:.2f}")

    print("\nTarget: Average length ~5.0")


if __name__ == "__main__":
    main()
