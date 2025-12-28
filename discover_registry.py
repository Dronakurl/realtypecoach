#!/usr/bin/env python3
"""Simple test to discover AT-SPI Registry methods."""

import pyatspi
import pyatspi.registry as registry

print("=" * 60)
print("AT-SPI Registry Methods Discovery")
print("=" * 60)
print()

print(f"Registry class: {registry.Registry.__name__}")
print()

# List all methods (excluding _ methods)
methods = [m for m in dir(registry.Registry) if not m.startswith('_')]
print(f"Found {len(methods)} public methods:")
print()

for method in sorted(methods):
    try:
        # Get method signature
        import inspect
        sig = inspect.signature(registry.Registry.__dict__[method]) if method in registry.Registry.__dict__ else inspect.signature(getattr(registry.Registry, method))
        print(f"  {method}{sig}")
    except Exception as e:
        print(f"  {method} (error: {e})")

print()
print("=" * 60)
print("Looking for register-related methods:")
print("=" * 60)

register_methods = [m for m in dir(registry.Registry) if 'register' in m.lower()]
for method in sorted(register_methods):
    print(f"  {method}")

print()
print("=" * 60)
print("Done!")
print("=" * 60)
