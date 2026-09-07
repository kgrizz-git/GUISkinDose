(install/installation)=
# Installation

Installing GUISkinDose (this independently maintained fork of PySkinDose) provides access to two interfaces.

* A python script that parses an RDSR DICOM file and creates output according to the settings used
* A scriptable interface for customizing calculations on already parsed dose reports

This fork is **not yet published to PyPI**. Install from GitHub (or a local clone), preferably in a virtual environment:

```bash
pip install "git+https://github.com/kgrizz-git/GUISkinDose.git"
```

For local development:

```bash
pip install -e ".[dev,gui]"
```

Optional extras match `pyproject.toml`: `gui`, `gui-native`, `dev`, `docs`, `notebooks`.
Installing with `[dev,gui]` matches the CI/dev toolchain (ruff, pytest, basedpyright, pre-commit hooks).
Using [uv](https://docs.astral.sh/uv/) is recommended for faster sync (`uv sync --all-extras`).

When a PyPI release exists:

```bash
pip install guiskindose
```

Installing also provides a `guiskindose` console command — equivalent to
`python -m guiskindose`:

```bash
guiskindose --mode gui    # launch the GUI; see `guiskindose --help` for all options
```
