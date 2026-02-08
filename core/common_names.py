"""Embedded list of common names for exclusion from word statistics."""

# Common names sourced from public domain data:
# - English: US Census data (public domain)
# - German: German name statistics (common names, public domain sources)

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


def add_name_with_genitive(names: set[str], name: str) -> None:
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


def load_and_generate_genitives(file_path: Path) -> set[str]:
    """Load names from file and generate genitive variations.

    Args:
        file_path: Path to names.txt file.

    Returns:
        Set of names including genitive variations.
    """
    names = set()
    if file_path.exists():
        with open(file_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    add_name_with_genitive(names, line)
    return names


def save_names_sorted(names: set[str], file_path: Path) -> None:
    """Save names to file (sorted, unique).

    Args:
        names: Set of names to save.
        file_path: Path to save to.
    """
    with open(file_path, 'w') as f:
        for name in sorted(names):
            f.write(f"{name}\n")


# Load all names with genitive variations
_ALL_NAMES_WITH_GENITIVES = load_and_generate_genitives(NAMES_FILE)

# Maintain backward compatibility with language-specific sets
# All names are available in both en and de for maximum coverage
COMMON_NAMES: dict[str, set[str]] = {
    "en": _ALL_NAMES_WITH_GENITIVES,
    "de": _ALL_NAMES_WITH_GENITIVES,
}

__all__ = ["COMMON_NAMES", "generate_genitive", "add_name_with_genitive", "load_and_generate_genitives", "save_names_sorted"]
