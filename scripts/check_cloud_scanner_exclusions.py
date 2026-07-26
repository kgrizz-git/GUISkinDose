#!/usr/bin/env python3
"""Verify cloud scanners retain the repository's sensitive-file exclusions.

This deliberately uses a small, strict parser for the only CodeRabbit YAML shape
we support, so the CI check does not need a YAML dependency.
"""

from __future__ import annotations

import re
from pathlib import Path


SONAR_CONFIGURATION_FILES = ("sonar-project.properties", ".sonarcloud.properties")
CODERABBIT_CONFIGURATION_FILE = ".coderabbit.yaml"
CLOUD_SENSITIVE_EXCLUSIONS = frozenset(
    {
        "**/*.avif",
        "**/*.bmp",
        "**/*.csv",
        "**/*.dcm",
        "**/*.dicom",
        "**/*.db",
        "**/*.doc",
        "**/*.docx",
        "**/*.eps",
        "**/*.gif",
        "**/*.heic",
        "**/*.ico",
        "**/*.ipynb",
        "**/*.jpeg",
        "**/*.jpg",
        "**/*.json",
        "**/*.log",
        "**/*.npy",
        "**/*.npz",
        "**/*.parquet",
        "**/*.pdf",
        "**/*.png",
        "**/*.ps",
        "**/*.pptx",
        "**/*.sqlite",
        "**/*.stl",
        "**/*.svg",
        "**/*.tif",
        "**/*.tiff",
        "**/*.tsv",
        "**/*.ttf",
        "**/*.txt",
        "**/*.webp",
        "**/*.woff",
        "**/*.woff2",
        "**/*.xls",
        "**/*.xlsb",
        "**/*.xlsm",
        "**/*.xlsx",
    }
)
PATH_FILTER_PATTERN = re.compile(r'^\s*-\s+"!(?P<pattern>[^"]+)"\s*$')


def sonar_exclusions(path: Path) -> set[str]:
    """Return the comma-separated ``sonar.exclusions`` patterns from one file."""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = raw_line.partition("=")
        if separator and key.strip() == "sonar.exclusions":
            return {pattern.strip() for pattern in value.split(",") if pattern.strip()}
    raise ValueError("missing sonar.exclusions")


def coderabbit_exclusions(path: Path) -> set[str]:
    """Return quoted negated ``path_filters`` from the supported CodeRabbit config shape."""
    return {
        match.group("pattern")
        for line in path.read_text(encoding="utf-8").splitlines()
        if (match := PATH_FILTER_PATTERN.match(line))
    }


def has_required_exclusions(exclusions: set[str]) -> bool:
    """Return whether every sensitive file pattern is excluded."""
    return CLOUD_SENSITIVE_EXCLUSIONS.issubset(exclusions)


def check_cloud_scanner_exclusions(repo_root: Path | None = None) -> bool:
    """Return whether Sonar and CodeRabbit retain required sensitive-file exclusions."""
    root = repo_root or Path(__file__).resolve().parent.parent
    valid = True

    for filename in SONAR_CONFIGURATION_FILES:
        try:
            excluded = sonar_exclusions(root / filename)
        except (OSError, ValueError):
            print("ERROR: could not read a required Sonar exclusion configuration.")
            valid = False
            continue
        if not has_required_exclusions(excluded):
            print("ERROR: a required Sonar sensitive-file exclusion is missing.")
            valid = False

    try:
        coderabbit = coderabbit_exclusions(root / CODERABBIT_CONFIGURATION_FILE)
    except OSError:
        print("ERROR: could not read the required CodeRabbit exclusion configuration.")
        valid = False
    else:
        if not has_required_exclusions(coderabbit):
            print("ERROR: a required CodeRabbit sensitive-file exclusion is missing.")
            valid = False

    if valid:
        print("SUCCESS: cloud scanner sensitive-file exclusions are present.")
    return valid


if __name__ == "__main__":
    raise SystemExit(0 if check_cloud_scanner_exclusions() else 1)
