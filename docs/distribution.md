# Distribution and Packaging

RealTypeCoach uses a **user-space installation** approach following XDG specifications.

## Installation Structure

```
~/.local/share/realtypecoach/     # XDG_DATA_HOME
  ├── main.py
  ├── core/
  ├── ui/
  ├── utils/
  ├── tests/
  ├── pyproject.toml
  ├── .venv/                       # Production virtual environment
  ├── icon.svg
  ├── icon_paused.svg
  └── icon_stopping.svg

~/.local/bin/realtypecoach         # Wrapper script (XDG_BIN_HOME)
~/.local/share/applications/       # Desktop entry
  └── realtypecoach.desktop
```

## Installation Process

The `install.sh` script:
1. Checks prerequisites (Linux, Python 3.10+, input group)
2. Creates virtual environment with **uv** (Python 3.14.2)
3. Installs dependencies from `pyproject.toml`
4. Copies source files to `~/.local/share/realtypecoach/`
5. Generates SVG icons dynamically
6. Creates wrapper script at `~/.local/bin/realtypecoach`
7. Creates desktop entry for app launcher

## Dependencies

From `pyproject.toml`:
```
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "PySide6",           # Qt bindings
    "pandas",            # Data analysis
    "pyqtgraph",         # Graphing
    "evdev",             # Keyboard access (system package)
    "sqlcipher3-binary", # Encrypted database
    "keyring",           # System keyring access
    "cryptography>=41.0.0",
    "psycopg2-binary>=2.9.0",  # PostgreSQL (optional)
]
```

**System dependency**: `python3-evdev` via package manager.

## Development vs Production

| Aspect | Development | Production (Installed) |
|--------|-------------|----------------------|
| venv location | `.venv/` in project | `~/.local/share/realtypecoach/.venv/` |
| Dependency tool | `uv` / `just run` | `uv` in install script |
| Source | Live from checkout | Copied to install dir |
| Managed by | `just` commands | `install.sh` / `uninstall.sh` |

## Why This Approach?

**Pros**: No system dependencies, easy uninstall, works on any distro, follows XDG standards
**Cons**: Not in package managers, manual updates, larger footprint

## Uninstall

```bash
./uninstall.sh
# Or manually:
rm -rf ~/.local/share/realtypecoach
rm ~/.local/bin/realtypecoach
rm ~/.local/share/applications/realtypecoach.desktop
```
