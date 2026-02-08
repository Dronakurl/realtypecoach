#!/usr/bin/env python3
"""Add names to the common names list."""

import argparse
import sys
from pathlib import Path

NAMES_FILE = Path(__file__).parent / "names.txt"


def generate_genitive(name: str) -> str | None:
    """Generate genitive form if name doesn't end in 's'.

    Args:
        name: The name to generate genitive for (lowercase).

    Returns:
        The genitive form (name + 's') or None if name ends with 's'.
    """
    if not name.endswith('s'):
        return f"{name}s"
    return None


def add_name_to_set(names: set[str], name: str) -> None:
    """Add base name and genitive form to set.

    Args:
        names: Set to add names to.
        name: Name to add (will be lowercased).
    """
    name_lower = name.lower()
    names.add(name_lower)
    genitive = generate_genitive(name_lower)
    if genitive:
        names.add(genitive)


def load_existing_names() -> set[str]:
    """Load existing names from names.txt.

    Returns:
        Set of existing names (lowercase).
    """
    names = set()
    if NAMES_FILE.exists():
        with open(NAMES_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    names.add(line.lower())
    return names


def save_names(names: set[str]) -> None:
    """Save names to file (sorted, unique).

    Args:
        names: Set of names to save.
    """
    with open(NAMES_FILE, 'w') as f:
        for name in sorted(names):
            f.write(f"{name}\n")


def add_single_name(name: str) -> None:
    """Add a single name to names.txt.

    Args:
        name: Name to add.
    """
    names = load_existing_names()
    add_name_to_set(names, name)
    save_names(names)
    print(f"Added '{name}' (and genitive form if applicable) to {NAMES_FILE}")


def add_names_from_file(file_path: Path) -> None:
    """Add names from a file to names.txt.

    Args:
        file_path: Path to file containing names (one per line).
    """
    if not file_path.exists():
        print(f"Error: File '{file_path}' not found", file=sys.stderr)
        sys.exit(1)

    names = load_existing_names()
    added_count = 0

    with open(file_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                name_lower = line.lower()
                if name_lower not in names:
                    add_name_to_set(names, line)
                    added_count += 1

    save_names(names)
    print(f"Added {added_count} names from '{file_path}' to {NAMES_FILE}")


def sort_and_deduplicate() -> None:
    """Sort and deduplicate existing names.txt."""
    names = load_existing_names()
    original_count = len(names)
    save_names(names)
    print(f"Sorted and deduplicated {NAMES_FILE} ({len(names)} unique names)")


def main() -> None:
    """Main entry point for CLI."""
    parser = argparse.ArgumentParser(
        description="Add names to the common names list."
    )
    parser.add_argument(
        "name",
        nargs="?",
        help="Name to add (or omit to use --file/--sort-only)",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Add names from file (one per line)",
    )
    parser.add_argument(
        "--sort-only",
        action="store_true",
        help="Only sort and deduplicate existing names.txt",
    )

    args = parser.parse_args()

    if args.sort_only:
        sort_and_deduplicate()
    elif args.file:
        if args.name:
            parser.error("Cannot specify both NAME and --file")
        add_names_from_file(args.file)
    elif args.name:
        add_single_name(args.name)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
