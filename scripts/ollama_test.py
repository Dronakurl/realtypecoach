#!/usr/bin/env python3
"""Test script for Ollama text generation."""

import sys

sys.path.insert(0, ".")

try:
    import ollama
except ImportError:
    print("❌ ollama package not installed. Installing...")
    import subprocess

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "ollama"],
        check=True,
    )
    import ollama

if len(sys.argv) < 2:
    print("Usage: ollama_test.py '<prompt>'")
    sys.exit(1)

prompt = " ".join(sys.argv[1:])

print("Testing Ollama text generation...")
print(f"Prompt: {prompt}")
print("=" * 50)

try:
    response = ollama.generate(
        model="gemma2:2b",
        prompt=prompt,
        stream=False,
    )
    print("\nGenerated text:")
    print(response.get("response", "").strip())
    print("\n✓ Test completed successfully")
except Exception as err:
    print(f"\n✗ Error: {err}")
    sys.exit(1)
