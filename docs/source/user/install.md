(install/installation)=
# Installation

Installing GUISkinDose (this independently maintained fork of PySkinDose) provides access to two interfaces.

* A python script that parses an RDSR DICOM file and creates output according to the settings used
* A scriptable interface for customizing calculations on already parsed dose reports

Install from PyPI, preferably in a virtual environment:

```bash
pip install "guiskindose[gui]"
```

Then run `guiskindose --mode gui` to open the GUI in your browser.
For a native window, install `guiskindose[gui-native]` and run `guiskindose --mode gui --native`.
Plain `guiskindose` installs the library and CLI only, without GUI mode.

To install it as a standalone command in its own isolated environment, use
[uv](https://docs.astral.sh/uv/) or [pipx](https://pipx.pypa.io/):

```bash
uv tool install "guiskindose[gui]"     # or: pipx install "guiskindose[gui]"
```

See [Running the GUI](running_the_gui.md) for launch options, local access, and logging.

For local development:

```bash
pip install -e ".[dev,gui]"
```

Optional extras match `pyproject.toml`: `gui`, `gui-native`, `dev`, `docs`, `notebooks`.
Installing with `[dev,gui]` matches the CI/dev toolchain (ruff, pytest, basedpyright, pre-commit hooks).
Using [uv](https://docs.astral.sh/uv/) is recommended for faster sync (`uv sync --all-extras`).

Installing also provides a `guiskindose` console command — equivalent to
`python -m guiskindose`:

```bash
guiskindose --mode gui    # launch the GUI; see `guiskindose --help` for all options
```
