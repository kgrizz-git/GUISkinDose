#!/usr/bin/env python3
"""Run dicom-phi-scan locally with raw reports confined to private temporary storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

try:
    from approved_asset_review import is_hash_pinned_approved
except ModuleNotFoundError:  # Imported as scripts.run_dicom_phi_advisory in tests.
    from scripts.approved_asset_review import is_hash_pinned_approved


def path_token(path: Path) -> str:
    return hashlib.sha256(path.as_posix().encode("utf-8")).hexdigest()[:12]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="Snapshot-relative DICOM paths.")
    parser.add_argument("--scan-root", type=Path, required=True, help="Private materialized snapshot root.")
    return parser.parse_args(argv)


def finding_count(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    count = 0
    for key in ("tag_findings", "ocr_findings", "findings"):
        value = payload.get(key)
        if isinstance(value, list):
            count += len(value)
    return count


class DicomScanError(RuntimeError):
    """A value-safe DICOM scanner failure suitable for user-visible reporting."""


def _scan_dicom_path(
    binary: str,
    root: Path,
    temporary_directory: Path,
    index: int,
    relative: Path,
) -> tuple[int, int]:
    """Scan one confined DICOM path and return unreviewed and reviewed counts."""
    normalized = Path(relative.as_posix())
    target = (root / normalized).resolve()
    if not target.is_relative_to(root):
        raise DicomScanError("ERROR: DICOM path escaped the private snapshot.")
    if not target.is_file():
        raise DicomScanError(f"ERROR: DICOM input unavailable path_token={path_token(normalized)}.")

    report = temporary_directory / f"report-{index}.json"
    completed = subprocess.run(
        [binary, str(target), "--cpu", "-o", str(report)],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    try:
        payload = json.loads(report.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DicomScanError(f"ERROR: invalid DICOM scan result path_token={path_token(normalized)}.") from exc

    count = finding_count(payload)
    if completed.returncode == 2:
        raise DicomScanError(f"ERROR: DICOM scan failed path_token={path_token(normalized)}.")
    if completed.returncode not in (0, 1):
        raise DicomScanError("ERROR: DICOM scanner returned an unsupported status.")
    if completed.returncode != 1 and not count:
        return 0, 0

    reported_count = count or 1
    if is_hash_pinned_approved(root, normalized, require_dicom_review=True):
        print(
            f"ADVISORY: DICOM scanner finding(s) explicitly triaged by exact-hash inventory review "
            f"path_token={path_token(normalized)}; values suppressed."
        )
        return 0, reported_count
    print(
        f"ADVISORY: DICOM scanner found {reported_count} potential finding(s) "
        f"path_token={path_token(normalized)}; values suppressed."
    )
    return reported_count, 0


def _print_summary(paths: Sequence[Path], total_findings: int, reviewed_findings: int) -> int:
    """Print the value-safe DICOM summary and return its advisory exit status."""
    if total_findings:
        print(f"DICOM privacy advisory complete: {total_findings} finding(s); triage required.")
        return 1
    if reviewed_findings:
        print(
            f"DICOM privacy advisory complete: {reviewed_findings} finding(s) explicitly triaged "
            "by exact-hash human review."
        )
    else:
        print(f"DICOM privacy advisory clean: {len(paths)} file(s).")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    binary = shutil.which("dicom-phi-scan")
    if binary is None:
        print("ERROR: dicom-phi-scan did not run (binary_missing).", file=sys.stderr)
        return 2
    root = args.scan_root.resolve()
    if not root.is_dir():
        print("ERROR: dicom-phi-scan did not run (scan_root_unavailable).", file=sys.stderr)
        return 2
    total_findings = 0
    reviewed_findings = 0
    with tempfile.TemporaryDirectory(prefix="dicom-phi-private-") as temp_dir:
        for index, relative in enumerate(args.paths):
            try:
                unreviewed, reviewed = _scan_dicom_path(binary, root, Path(temp_dir), index, relative)
            except DicomScanError as exc:
                print(str(exc), file=sys.stderr)
                return 2
            total_findings += unreviewed
            reviewed_findings += reviewed
    return _print_summary(args.paths, total_findings, reviewed_findings)


if __name__ == "__main__":
    raise SystemExit(main())
