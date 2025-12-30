# Distribution and Packaging

This document describes how RealTypeCoach is distributed and packaged for Linux systems.

## Current Distribution Method

RealTypeCoach uses a **user-space installation** approach following XDG Base Directory specifications:

### Installation Structure

```
~/.local/share/realtypecoach/     # XDG_DATA_HOME
  ├── main.py
  ├── core/
  ├── ui/
  ├── utils/
  ├── tests/
  ├── pyproject.toml
  ├── .venv/                       # Isolated production virtual environment
  ├── icon.svg
  ├── icon_paused.svg
  └── icon_stopping.svg

~/.local/bin/realtypecoach         # Wrapper script (XDG_BIN_HOME)

~/.local/share/applications/       # XDG_DATA_HOME/applications
  └── realtypecoach.desktop        # Desktop entry
```

### Installation Process

The `install.sh` script:

1. **Creates production venv**: Fresh virtual environment at install location (not copied from dev)
2. **Installs dependencies**: Uses `pyproject.toml` for dependency management
3. **Copies application files**: Python source code to install directory
4. **Generates icons**: Creates SVG icons dynamically
5. **Creates wrapper script**: Executable at `~/.local/bin/realtypecoach`
6. **Creates desktop entry**: For application launcher integration

### Development vs Production Environments

**Development** (source checkout):
- `.venv/` in project root
- Managed by `just run` via `sync-deps` command
- Uses standard pip: `.venv/bin/python3 -m pip install -e .`

**Production** (installed app):
- `~/.local/share/realtypecoach/.venv/`
- Created during installation
- Independent of source code
- Source can be deleted after install

## Why This Approach?

### Advantages

1. **No system dependencies**: Doesn't interfere with system Python or packages
2. **Easy to uninstall**: Single directory to remove
3. **User installation**: No sudo required
4. **Works on any distro**: Distribution-agnostic
5. **Standard locations**: Follows XDG specifications
6. **Isolated updates**: Won't affect other Python applications

### Limitations

1. **Not in package managers**: Not available via `apt`, `dnf`, etc.
2. **No automatic updates**: Manual reinstall required
3. **Larger footprint**: Each app has its own venv
4. **Not discoverable**: Users must find the project manually

## Alternative Distribution Methods

### 1. Flatpak (Recommended for Future)

**Pros:**
- Containerized dependencies (no system Python needed)
- Works on any Linux distro
- Available in Flathub (discoverable)
- Automatic updates
- Sandboxed security

**Cons:**
- Larger download size
- Requires Flatpak runtime
- Slower startup

**Resources:**
- [KDE Documentation: Publishing Python apps as Flatpak](https://develop.kde.org/docs/getting-started/python/python-flatpak/)
- [Flatpak Requirements & Conventions](https://docs.flatpak.org/en/latest/conventions.html)

**Implementation:**
- Create `flatpak/org.realtypecoach.RealTypeCoach.json` manifest
- Build with `flatpak-builder`
- Submit to Flathub

### 2. Native System Packages

**Debian/Ubuntu (.deb):**
- Use `dh_virtualenv` for Python apps
- Install to `/usr/lib/realtypecoach`
- Requires packaging for each Python version
- Available in official repos

**Fedora/openSUSE (.rpm):**
- Use `python3-setuptools` with `bdist_rpm`
- Similar to Debian approach

**Examples:**
- qutebrowser: Available in official repos of most distros
- Calibre: Provides both repo packages and standalone binaries

### 3. Standalone Binaries

**PyInstaller / Nuitka:**
- Single executable containing Python interpreter
- 70-100MB+ file size
- No dependencies required on target system

**Use case:** Commercial/closed-source applications

## Packaging Tools Comparison

| Tool | Best For | Size | Complexity | Updates |
|------|----------|------|------------|---------|
| **User venv** (current) | Simple distribution | Medium | Low | Manual |
| **Flatpak** | Wide distribution | Large | Medium | Auto |
| **Native packages** | System integration | Small | High | System |
| **PyInstaller** | Standalone apps | Large | Low | Manual |

## Virtual Environment Management

### Development Workflow

```bash
# Install dependencies automatically
just run

# Manually install dependencies
just sync-deps
```

The `sync-deps` command:
- Creates venv if missing: `python3 -m venv .venv`
- Installs dependencies: `.venv/bin/python3 -m pip install -e .`

### Production Installation

```bash
# Install to system
./install.sh

# Uninstall
./uninstall.sh

# Or manually remove
rm -rf ~/.local/share/realtypecoach
rm ~/.local/bin/realtypecoach
rm ~/.local/share/applications/realtypecoach.desktop
```

## Dependency Management

### pyproject.toml

```toml
[project]
name = "realtypecoach"
version = "1.0.0"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.0",
    "PySide6",           # Qt bindings
    "pandas",            # Data analysis
    "matplotlib",        # Graphing
    "evdev",             # Keyboard access (system package)
]
```

### System Dependencies

**evdev** must be installed via system package manager:
```bash
# Debian/Ubuntu
sudo apt install python3-evdev

# Fedora
sudo dnf install python3-evdev

# Arch Linux
sudo pacman -S python-evdev
```

## Future Improvements

### Roadmap

1. **Phase 1** (Current): User-space installation with venv
2. **Phase 2** (Next): Add Flatpak distribution for Flathub
3. **Phase 3** (Future): Submit to distro repositories (Debian/Ubuntu AUR)

### Flatpak Implementation Plan

See GitHub issue for Flatpak distribution task.

Key steps:
1. Create Flatpak manifest
2. Set up flatpak-builder
3. Test build in clean environment
4. Submit to Flathub
5. Add documentation for users

## Related Documentation

- [README.md](../README.md) - Installation instructions
- [pyproject.toml](../pyproject.toml) - Project dependencies
- [install.sh](../install.sh) - Installation script

## References

- [How to package and distribute your Python Desktop App](https://medium.com/@saschaschwarz_8182/how-to-package-and-distribute-your-python-desktop-app-f47f44855a37)
- [Publishing your Python app as a Flatpak (KDE)](https://develop.kde.org/docs/getting-started/python/python-flatpak/)
- [Distribute Python applications "with" a venv](https://stackoverflow.com/questions/30663433/distribute-python-applications-with-a-venv)
- [qutebrowser Installation](https://qutebrowser.org/doc/install.html)
- [Flatpak Requirements & Conventions](https://docs.flatpak.org/en/latest/conventions.html)
