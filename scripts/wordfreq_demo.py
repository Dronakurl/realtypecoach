#!/usr/bin/env python3
"""Test wordfreq package functionality."""

from wordfreq import word_frequency, zipf_frequency, top_n_list, available_languages

# Test basic functionality
print('=== English word frequencies ===')
print(f"'the' frequency: {word_frequency('the', 'en'):.6f}")
print(f"'house' frequency: {word_frequency('house', 'en'):.6f}")
print(f"'frequency' frequency: {word_frequency('frequency', 'en'):.6f}")
print()

print('=== German word frequencies ===')
print(f"'das' frequency: {word_frequency('das', 'de'):.6f}")
print(f"'Haus' frequency: {word_frequency('Haus', 'de'):.6f}")
print(f"'haus' frequency: {word_frequency('haus', 'de'):.6f}")
print()

print('=== Zipf frequency (logarithmic scale) ===')
print(f"'the' Zipf: {zipf_frequency('the', 'en'):.2f}")
print(f"'house' Zipf: {zipf_frequency('house', 'en'):.2f}")
print()

print('=== Top 10 English words ===')
print(top_n_list('en', 10))
print()

print('=== Available languages ===')
langs = available_languages()
print(f'Total languages: {len(langs)}')
print(f'Languages with data: {list(langs.keys())[:10]}...')
print()

print('=== Case sensitivity test ===')
print(f"'Haus' (capitalized): {word_frequency('Haus', 'de'):.6f}")
print(f"'haus' (lowercase): {word_frequency('haus', 'de'):.6f}")
print()

print('=== Unknown word test ===')
print(f"'xyz123' frequency: {word_frequency('xyz123', 'en'):.6f}")
print()

print('=== Offline capability test ===')
print('All data loaded from installed package - no internet required!')
