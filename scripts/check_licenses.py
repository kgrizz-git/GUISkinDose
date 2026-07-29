#!/usr/bin/env python3
"""License compliance checker for MyPySkinDose third-party dependencies.

Purpose:
    Inventory installed Python packages (core + optional extras), classify
    licenses against project policy, and optionally regenerate the tracked
    third-party notices file.

Inputs:
    Active Python environment with the full declared dependency set installed.
    For a reproducible inventory, sync from the lockfile so versions are pinned:
        uv sync --all-extras

Outputs:
    Exit code 0 when policy passes; 1 when forbidden or (with --strict)
    unknown licenses are found. With --write-notices, updates
    ``dev-docs/THIRD_PARTY_NOTICES.md``.

Usage:
    python scripts/check_licenses.py
    python scripts/check_licenses.py --strict
    python scripts/check_licenses.py --write-notices
    python scripts/check_licenses.py --check-notices
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date
from importlib import metadata
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

PROJECT_NAME = "mypyskindose"
NOTICES_PATH = Path("dev-docs/THIRD_PARTY_NOTICES.md")
APACHE_2_LICENSE = "Apache-2.0"
# Inventory the full declared dependency set so the notices file is reproducible
# regardless of which extras a given developer happened to install. Keep in sync
# with the [project.optional-dependencies] keys in pyproject.toml.
SELECTED_EXTRAS = frozenset({"dev", "gui", "gui-native", "docs", "notebooks"})
BOOTSTRAP_PACKAGES = frozenset(
    {
        "pip",
        "setuptools",
        "wheel",
        "build",
    }
)

# SPDX-style identifiers and normalized aliases permitted for runtime + dev tooling.
ALLOWED_LICENSES = frozenset(
    {
        "0BSD",
        APACHE_2_LICENSE,
        "BSD-2-Clause",
        "BSD-3-Clause",
        "CC0-1.0",
        "ISC",
        "MIT",
        "MPL-2.0",
        "PSF-2.0",
        "Python-2.0",
        "Unlicense",
        "Zlib",
    }
)

# Strong copyleft licenses that require explicit legal review before use.
FORBIDDEN_LICENSES = frozenset(
    {
        "AGPL-3.0",
        "AGPL-3.0-only",
        "AGPL-3.0-or-later",
        "GPL-2.0",
        "GPL-2.0-only",
        "GPL-2.0-or-later",
        "GPL-3.0",
        "GPL-3.0-only",
        "GPL-3.0-or-later",
    }
)

# Trove license classifiers look like "License :: OSI Approved :: MIT License".
# We split on "::" and compare stripped segments rather than using a regex, so
# non-canonical whitespace around the separators still parses and there is no
# backtracking risk (Sonar S8786).
LICENSE_CLASSIFIER_PREFIX = ("license", "osi approved")

# Map common PyPI classifier / metadata names to SPDX-style identifiers.
LICENSE_ALIASES = {
    "apache license 2.0": APACHE_2_LICENSE,
    "apache license, version 2.0": APACHE_2_LICENSE,
    "apache software license": APACHE_2_LICENSE,
    "bsd": "BSD-3-Clause",
    "bsd license": "BSD-3-Clause",
    "bsd-3-clause": "BSD-3-Clause",
    "bsd-2-clause": "BSD-2-Clause",
    "isc license (iscl)": "ISC",
    "isc license": "ISC",
    "mit license": "MIT",
    "mit": "MIT",
    "mozilla public license 2.0 (mpl 2.0)": "MPL-2.0",
    "python software foundation license": "PSF-2.0",
    "the unlicense (unlicense)": "Unlicense",
    "zlib/libpng license": "Zlib",
}


@dataclass(frozen=True)
class PackageLicense:
    name: str
    version: str
    license_ids: tuple[str, ...]
    raw_license: str
    home_page: str
    license_operator: str = "SINGLE"

    @property
    def primary_license(self) -> str:
        return self.license_ids[0] if self.license_ids else "UNKNOWN"

    @property
    def status(self) -> str:
        if not self.license_ids or self.license_ids == ("UNKNOWN",):
            return "unknown"

        if self.license_operator == "OR":
            if any(lic in ALLOWED_LICENSES for lic in self.license_ids):
                return "allowed"
            if all(lic in FORBIDDEN_LICENSES for lic in self.license_ids):
                return "forbidden"
            return "review"

        if any(lic in FORBIDDEN_LICENSES for lic in self.license_ids):
            return "forbidden"
        if all(lic in ALLOWED_LICENSES for lic in self.license_ids):
            return "allowed"
        return "review"


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parent.parent


def _normalize_token(value: str) -> str:
    token = value.strip()
    if not token:
        return "UNKNOWN"
    lowered = token.lower()
    if lowered in LICENSE_ALIASES:
        return LICENSE_ALIASES[lowered]
    if re.fullmatch(r"[A-Za-z0-9\-.+]+", token):
        return token
    for pattern, spdx in LICENSE_ALIASES.items():
        if pattern in lowered:
            return spdx
    if "mit" in lowered:
        return "MIT"
    if "apache" in lowered and "2" in lowered:
        return APACHE_2_LICENSE
    if "bsd" in lowered:
        return "BSD-3-Clause"
    if "gnu general public license" in lowered or re.search(r"\bgpl\b", lowered):
        if "3" in lowered:
            return "GPL-3.0-or-later"
        return "GPL-2.0-or-later"
    if "gnu affero" in lowered or "agpl" in lowered:
        return "AGPL-3.0-or-later"
    return "UNKNOWN"


def _license_from_classifiers(classifiers: list[str]) -> list[str]:
    licenses: list[str] = []
    for classifier in classifiers:
        segments = [segment.strip() for segment in classifier.split("::")]
        if len(segments) < 3:
            continue
        if tuple(segment.lower() for segment in segments[:2]) != LICENSE_CLASSIFIER_PREFIX:
            continue
        name = " :: ".join(segments[2:]).strip()
        if name:
            licenses.append(_normalize_token(name))
    return licenses


def _meta_get(meta: metadata.PackageMetadata, key: str, default: str = "") -> str:
    """Safely get a metadata field, working around basedpyright stub gaps."""
    return meta.get(key) or default  # type: ignore[return-value]


def _license_from_metadata(meta: metadata.PackageMetadata) -> tuple[str, tuple[str, ...]]:
    expression = _meta_get(meta, "License-Expression").strip()
    if expression:
        if re.search(r"\s+\bOR\b\s+", expression, flags=re.IGNORECASE):
            operator = "OR"
            parts = re.split(r"\s+\bOR\b\s+", expression, flags=re.IGNORECASE)
        elif re.search(r"\s+\bAND\b\s+", expression, flags=re.IGNORECASE):
            operator = "AND"
            parts = re.split(r"\s+\bAND\b\s+", expression, flags=re.IGNORECASE)
        else:
            operator = "SINGLE"
            parts = [expression]
        normalized = [_normalize_token(part) for part in parts if part.strip()]
        licenses = tuple(lic for lic in normalized if lic != "UNKNOWN") or ("UNKNOWN",)
        return operator, licenses

    classifiers = list(meta.get_all("Classifier") or [])
    from_classifiers = _license_from_classifiers(classifiers)
    if from_classifiers:
        operator = "OR" if len(from_classifiers) > 1 else "SINGLE"
        return operator, tuple(from_classifiers)

    raw = _meta_get(meta, "License").strip()
    if raw:
        if re.search(r"\s+\bor\b\s+", raw, flags=re.IGNORECASE):
            parts = re.split(r"\s+\bor\b\s+", raw, flags=re.IGNORECASE)
            licenses = tuple(_normalize_token(part) for part in parts if part.strip())
            return "OR", licenses or ("UNKNOWN",)
        return "SINGLE", (_normalize_token(raw),)
    return "SINGLE", ("UNKNOWN",)


def _requirement_applies(req_str: str, selected_extras: frozenset[str]) -> bool:
    req = Requirement(req_str)
    if req.marker is None:
        return True
    env: dict[str, str] = {k: str(v) for k, v in default_environment().items()}
    if req.marker.evaluate(env):
        return True
    for extra in selected_extras:
        if req.marker.evaluate({**env, "extra": extra}):
            return True
    return False


def _resolve_distribution(name: str) -> metadata.Distribution:
    canonical = canonicalize_name(name)
    try:
        return metadata.distribution(name)
    except metadata.PackageNotFoundError:
        for dist in metadata.distributions():
            dist_name = (_meta_get(dist.metadata, "Name") or dist.name or "").strip()
            if dist_name and canonicalize_name(dist_name) == canonical:
                return dist
        raise


def project_package_names(
    project: str = PROJECT_NAME,
    selected_extras: frozenset[str] = SELECTED_EXTRAS,
) -> set[str]:
    """Return canonical names of packages in the project dependency tree."""
    visited: set[str] = set()
    queue: list[str] = [project]

    while queue:
        pkg_name = queue.pop(0)
        try:
            dist = _resolve_distribution(pkg_name)
        except metadata.PackageNotFoundError:
            continue

        dist_name = (_meta_get(dist.metadata, "Name") or dist.name or pkg_name).strip()
        canonical = canonicalize_name(dist_name)
        if canonical in visited:
            continue
        visited.add(canonical)

        for req_str in dist.requires or []:
            if _requirement_applies(req_str, selected_extras):
                queue.append(Requirement(req_str).name)

    visited.discard(canonicalize_name(project))
    return visited


def collect_package_licenses(
    skip_project: bool = True,
    selected_extras: frozenset[str] = SELECTED_EXTRAS,
) -> list[PackageLicense]:
    try:
        in_tree = project_package_names(selected_extras=selected_extras)
    except metadata.PackageNotFoundError:
        in_tree = None

    packages: list[PackageLicense] = []
    for dist in metadata.distributions():
        meta = dist.metadata
        name = (_meta_get(meta, "Name") or dist.name or "").strip()
        if not name:
            continue
        canonical = canonicalize_name(name)
        if skip_project and canonical == canonicalize_name(PROJECT_NAME):
            continue
        if canonical in BOOTSTRAP_PACKAGES:
            continue
        if in_tree is not None and canonical not in in_tree:
            continue

        operator, license_ids = _license_from_metadata(meta)
        packages.append(
            PackageLicense(
                name=name,
                version=dist.version,
                license_ids=license_ids,
                raw_license=_meta_get(meta, "License"),
                home_page=_meta_get(meta, "Home-page") or _meta_get(meta, "Project-URL"),
                license_operator=operator,
            )
        )
    return sorted(packages, key=lambda pkg: pkg.name.casefold())


def render_notices(packages: list[PackageLicense], _root: Path) -> str:
    today = date.today().isoformat()
    lines = [
        "# Third-party notices",
        "",
        "Auto-generated inventory of Python packages resolved when installing the",
        "full declared dependency set (all extras), pinned by `uv.lock`:",
        "",
        "```bash",
        "uv sync --all-extras",
        "```",
        "",
        f"Regenerate with `python scripts/check_licenses.py --write-notices` (last updated: {today}).",
        "",
        "Project license: MIT — see [`LICENSE`](../LICENSE). Policy: [`LICENSE_COMPLIANCE.md`](LICENSE_COMPLIANCE.md).",
        "",
        "| Package | Version | License(s) | Notes |",
        "| --- | --- | --- | --- |",
    ]
    for pkg in packages:
        notes = pkg.home_page or pkg.raw_license.replace("\n", " ")[:120]
        licenses = ", ".join(pkg.license_ids)
        lines.append(f"| {pkg.name} | {pkg.version} | {licenses} | {notes} |")
    lines.append("")
    return "\n".join(lines)


def evaluate_packages(
    packages: list[PackageLicense],
    *,
    strict: bool,
) -> tuple[list[PackageLicense], list[PackageLicense], list[PackageLicense]]:
    forbidden = [pkg for pkg in packages if pkg.status == "forbidden"]
    unknown = [pkg for pkg in packages if pkg.status == "unknown"]
    review = [pkg for pkg in packages if pkg.status == "review"]
    if strict:
        return forbidden, unknown + review, []
    return forbidden, unknown, review


def check_licenses(
    root: Path,
    *,
    strict: bool = False,
    write_notices: bool = False,
    check_notices: bool = False,
) -> int:
    packages = collect_package_licenses()
    forbidden, unknown, review = evaluate_packages(packages, strict=strict)

    if write_notices:
        notices_path = root / NOTICES_PATH
        notices_path.parent.mkdir(parents=True, exist_ok=True)
        notices_path.write_text(render_notices(packages, root), encoding="utf-8")
        print(f"Wrote {NOTICES_PATH} ({len(packages)} packages)")

    if check_notices:
        notices_path = root / NOTICES_PATH
        if not notices_path.exists():
            print(f"Missing {NOTICES_PATH}. Run: python scripts/check_licenses.py --write-notices", file=sys.stderr)
            return 1
        expected = render_notices(packages, root)
        actual = notices_path.read_text(encoding="utf-8")
        if _normalize_notices_for_compare(actual) != _normalize_notices_for_compare(expected):
            print(
                f"{NOTICES_PATH} is out of date. Run: python scripts/check_licenses.py --write-notices",
                file=sys.stderr,
            )
            return 1

    for pkg in review:
        print(f"REVIEW  {pkg.name}=={pkg.version}  licenses={','.join(pkg.license_ids)}")

    for pkg in unknown:
        label = "ERROR" if strict else "UNKNOWN"
        print(f"{label}  {pkg.name}=={pkg.version}  raw={pkg.raw_license!r}")

    for pkg in forbidden:
        print(f"FORBIDDEN  {pkg.name}=={pkg.version}  licenses={','.join(pkg.license_ids)}")

    if forbidden:
        print(f"\nLicense check failed: {len(forbidden)} forbidden package(s).", file=sys.stderr)
        return 1
    if strict and unknown:
        print(f"\nLicense check failed: {len(unknown)} unknown package(s) in --strict mode.", file=sys.stderr)
        return 1

    print(f"License check passed ({len(packages)} packages inventoried).")
    return 0


def _normalize_notices_for_compare(text: str) -> str:
    """Ignore the 'last updated' line when comparing notice files."""
    return re.sub(
        r"\(last updated: [0-9]{4}-[0-9]{2}-[0-9]{2}\)",
        "(last updated: DATE)",
        text,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check third-party dependency licenses.")
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail on unknown or review-required licenses (not just forbidden copyleft)",
    )
    parser.add_argument(
        "--write-notices",
        action="store_true",
        help=f"Regenerate {NOTICES_PATH}",
    )
    parser.add_argument(
        "--check-notices",
        action="store_true",
        help=f"Fail if {NOTICES_PATH} does not match the current environment",
    )
    args = parser.parse_args(argv)
    root = args.repo_root or repo_root_from_script()
    return check_licenses(
        root,
        strict=args.strict,
        write_notices=args.write_notices,
        check_notices=args.check_notices,
    )


if __name__ == "__main__":
    sys.exit(main())
