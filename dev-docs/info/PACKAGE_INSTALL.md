# Why Install as a Package?

This document explains the benefits of installing GUISkinDose as a Python package rather than running it directly from source.

## What "Installing as a Package" Means

When you run `pip install -e .`, pip reads `pyproject.toml` and registers the `guiskindose` package with your Python environment. The `-e` flag means "editable mode" — instead of copying code into your site-packages, it creates a link to your source directory. Edits to the code take effect immediately without reinstalling.

## Benefits

### 1. Import Paths Work Anywhere

Without the package installed, Python doesn't know where `guiskindose` lives. You'd need to manually manipulate `sys.path`:

```python
# Without package install
import sys
from pathlib import Path

sys.path.insert(0, str(Path("src").resolve()))
from guiskindose.main import main
```

This is fragile — the path is hardcoded, and it breaks if you move the project or share the script.

With the package installed:

```python
# With package install
from guiskindose.main import main  # works anywhere
```

The import works from any directory, any script, any virtual environment that has the package installed.

### 2. CLI Entry Points

The `python -m guiskindose` command works because the package structure defines `__main__.py`. Without installation:

```bash
# Without package install
python src/guiskindose/__main__.py --mode gui
```

With installation:

```bash
# With package install
python -m guiskindose --mode gui
```

This is how the GUI launcher script (`run_gui.sh`) works — it just calls `python -m guiskindose --mode gui`.

### 3. Automatic Dependency Resolution

The package declares its dependencies in `pyproject.toml`:

```toml
dependencies = [
    "pandas >= 2.2.3",
    "numpy >= 2.2.4",
    "pydicom >= 2.0",
    "numpy-stl >= 3.2.0",
    "plotly >= 4.13.3",
    "scipy >= 1.15.2",
    ...
]
```

When you install the package, pip automatically installs everything it needs. Without this, you'd have to manually install each dependency and keep them in sync with the requirements.

### 4. Optional Extras

The package defines optional dependency groups:

```toml
[project.optional-dependencies]
gui = ["nicegui>=2.0.0"]
gui-native = ["nicegui>=2.0.0", "pywebview"]
```

Users can choose what they need:

```bash
pip install -e .                 # core only
pip install -e ".[gui]"          # core + browser GUI
pip install -e ".[gui-native]"   # core + native window GUI
```

### 5. Version Tracking

The package version is defined in one place (`pyproject.toml`) and can be queried:

```python
import importlib.metadata
print(importlib.metadata.version("guiskindose"))  # 25.1.1
```

This is useful for logging, reproducibility, and debugging.

### 6. Distribution and Sharing

Installing as a package enables several distribution methods:

**GitHub install (current):**
```bash
pip install git+https://github.com/kgrizz-git/MyPySkinDose.git
```

**PyPI (if published):**
```bash
pip install guiskindose
```

**Local wheel/sdist:**
```bash
pip install build
python -m build  # creates dist/guiskindose-25.1.1-py3-none-any.whl
pip install dist/guiskindose-25.1.1-py3-none-any.whl
```

Without the package structure, users would need to clone the repo, understand the directory layout, and manually configure their environment.

## Publishing to PyPI

If you want to make the package installable via `pip install guiskindose`, you can publish it to PyPI.

### Prerequisites

1. A PyPI account (create at https://pypi.org/account/register/)
2. An API token from PyPI settings
3. A unique package name (check that `guiskindose` isn't taken)

### Build and Upload

```bash
# Install build tools
pip install build twine

# Build the package
python -m build

# Check the package
twine check dist/*

# Upload to TestPyPI (optional, for testing)
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*
```

### Version Bumping

Before uploading a new version, update the version in `pyproject.toml`:

```toml
version = "1.0.0"  # first GUISkinDose identity; was MyPySkinDose 25.2.0
```

PyPI does not allow re-uploading the same version number.

### GitHub Releases

You can also automate PyPI uploads via GitHub Actions. The project already has a `release.yml` workflow that could be extended to publish to PyPI when you create a GitHub release.

## Summary

| Aspect | Without Package | With Package |
|--------|-----------------|--------------|
| Imports | Manual `sys.path` manipulation | Just works |
| CLI | Full path to `__main__.py` | `guiskindose` or `python -m guiskindose` |
| Dependencies | Install manually | Automatic |
| Distribution | Clone repo + manual setup | `pip install ...` |
| Versioning | Ad-hoc | Built-in metadata |

For local development, `pip install -e .` gives you all the benefits while keeping your code editable.
