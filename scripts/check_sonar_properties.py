#!/usr/bin/env python3
"""Verify the Sonar analysis-scope settings agree across both configuration files."""

from pathlib import Path


SHARED_KEYS = (
    "sonar.exclusions",
    "sonar.test.exclusions",
    "sonar.coverage.exclusions",
)
CONFIGURATION_FILES = ("sonar-project.properties", ".sonarcloud.properties")


def read_properties(path: Path) -> dict[str, str]:
    """Read simple ``key=value`` Sonar properties, ignoring blank lines and comments."""
    properties: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip():
            raise ValueError(f"{path.name}:{line_number}: expected key=value")
        properties[key.strip()] = value.strip()
    return properties


def check_sonar_properties(repo_root: Path | None = None) -> bool:
    """Return whether each analysis-scope key is present and identical in both files."""
    root = repo_root or Path(__file__).resolve().parent.parent
    paths = [root / filename for filename in CONFIGURATION_FILES]
    try:
        configurations = {path.name: read_properties(path) for path in paths}
    except (OSError, ValueError) as exc:
        print(f"ERROR: could not read Sonar properties: {exc}")
        return False

    valid = True
    for key in SHARED_KEYS:
        values = {filename: configuration.get(key) for filename, configuration in configurations.items()}
        if None in values.values():
            missing = ", ".join(filename for filename, value in values.items() if value is None)
            print(f"ERROR: {key} is missing from {missing}")
            valid = False
        elif len(set(values.values())) != 1:
            print(f"ERROR: {key} differs between Sonar configuration files")
            valid = False

    if valid:
        print("SUCCESS: shared Sonar analysis-scope settings are in sync.")
    return valid


if __name__ == "__main__":
    raise SystemExit(0 if check_sonar_properties() else 1)
