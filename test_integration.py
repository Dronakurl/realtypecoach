#!/usr/bin/env python3
"""Test script for wordfreq integration in RealTypeCoach."""

import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_dictionary_methods():
    """Test Dictionary wordfreq methods."""
    print("Testing Dictionary wordfreq methods...")

    try:
        from core.dictionary import Dictionary
        from core.dictionary_config import DictionaryConfig

        # Create a simple dictionary config (accept-all mode for testing)
        config = DictionaryConfig(
            enabled_languages=['en'],
            accept_all_mode=True
        )

        dictionary = Dictionary(config)

        # Test weighted digraph frequency calculation
        print("  Testing weighted digraph frequency calculation...")
        weighted = dictionary.calculate_digraph_frequencies_weighted('en')

        if weighted:
            print(f"  ✓ Calculated {len(weighted)} weighted digraph frequencies")
            # Show some examples
            examples = sorted(weighted.items(), key=lambda x: x[1], reverse=True)[:5]
            for digraph, freq in examples:
                print(f"    - '{digraph}': {freq:.6f}")
        else:
            print("  ⚠ No weighted frequencies (may be expected in accept-all mode)")

        # Test Zipf frequency lookup
        print("\n  Testing word Zipf frequency lookup...")
        test_cases = [
            ('the', 'en', 7.0),
            ('house', 'en', 5.0),
            ('xyz', 'en', 0.0),
        ]
        for word, lang, min_expected in test_cases:
            zipf = dictionary.get_word_zipf_frequency(word, lang)
            print(f"    - '{word}' ({lang}): {zipf:.2f}")
            assert zipf >= min_expected, f"Expected {word} to have Zipf >= {min_expected}"

        # Test top N words
        print("\n  Testing top N words retrieval...")
        top_words = dictionary.iter_top_n_words('en', 10, min_zipf=5.0)
        print(f"  ✓ Retrieved {len(top_words)} words with Zipf >= 5.0")
        for word, zipf in top_words[:5]:
            print(f"    - '{word}': {zipf:.2f}")

        print("\n✅ Dictionary method tests passed!\n")
        return True

    except Exception as e:
        import traceback
        print(f"\n❌ Dictionary method test failed: {e}")
        traceback.print_exc()
        return False


def test_frequency_utils():
    """Test frequency utility functions."""
    print("Testing frequency utility functions...")

    try:
        from core.frequency_utils import (
            filter_by_frequency_threshold,
            get_zipf_threshold_name
        )

        # Test filter_by_frequency_threshold
        print("  Testing filter_by_frequency_threshold...")
        items = [
            {'name': 'a', 'freq': 0.1},
            {'name': 'b', 'freq': 0.5},
            {'name': 'c', 'freq': 0.9},
            {'name': 'd', 'freq': 0.3}
        ]
        filtered = filter_by_frequency_threshold(items, lambda x: x['freq'], 0.4)
        print(f"  ✓ Filtered {len(items)} items to {len(filtered)} items (threshold >= 0.4)")
        assert len(filtered) == 2, "Expected 2 items to pass filter"
        assert all(item['freq'] >= 0.4 for item in filtered), "Expected all filtered items to meet threshold"

        # Test get_zipf_threshold_name
        print("\n  Testing get_zipf_threshold_name...")
        test_cases = [
            (7.5, "Very Common"),
            (5.5, "Common"),
            (4.5, "Moderate"),
            (3.5, "Uncommon"),
            (2.0, "Rare"),
        ]
        for zipf, expected in test_cases:
            result = get_zipf_threshold_name(zipf)
            print(f"    - Zipf {zipf}: '{result}'")
            assert result == expected, f"Expected '{expected}' for Zipf {zipf}"

        print("\n✅ Frequency utility tests passed!\n")
        return True

    except Exception as e:
        import traceback
        print(f"\n❌ Frequency utility test failed: {e}")
        traceback.print_exc()
        return False


def test_config_settings():
    """Test that new config settings have defaults."""
    print("Testing config settings...")

    try:
        from utils.config import AppSettings

        settings = AppSettings()

        # Check new settings exist with correct defaults
        print("  Checking new config settings...")
        assert hasattr(settings, 'digraph_frequency_use_wordfreq'), "Missing digraph_frequency_use_wordfreq"
        print(f"    ✓ digraph_frequency_use_wordfreq: {settings.digraph_frequency_use_wordfreq}")

        assert hasattr(settings, 'digraph_frequency_weighted'), "Missing digraph_frequency_weighted"
        print(f"    ✓ digraph_frequency_weighted: {settings.digraph_frequency_weighted}")

        assert hasattr(settings, 'word_frequency_use_common'), "Missing word_frequency_use_common"
        print(f"    ✓ word_frequency_use_common: {settings.word_frequency_use_common}")

        assert hasattr(settings, 'word_frequency_zipf_threshold'), "Missing word_frequency_zipf_threshold"
        print(f"    ✓ word_frequency_zipf_threshold: {settings.word_frequency_zipf_threshold}")

        print("\n✅ Config settings tests passed!\n")
        return True

    except Exception as e:
        import traceback
        print(f"\n❌ Config settings test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("Wordfreq Integration Test Suite")
    print("=" * 60)
    print()

    results = []
    results.append(("Dictionary methods", test_dictionary_methods()))
    results.append(("Frequency utilities", test_frequency_utils()))
    results.append(("Config settings", test_config_settings()))

    print("=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{name}: {status}")

    print()
    print(f"Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
