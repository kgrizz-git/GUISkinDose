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
            normalized = Path(relative.as_posix())
            target = (root / normalized).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                print("ERROR: DICOM path escaped the private snapshot.", file=sys.stderr)
                return 2
            if not target.is_file():
                print(f"ERROR: DICOM input unavailable path_token={path_token(normalized)}.", file=sys.stderr)
                return 2
            report = Path(temp_dir) / f"report-{index}.json"
            completed = subprocess.run(
                [binary, str(target), "--cpu", "-o", str(report)],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                print(f"ERROR: invalid DICOM scan result path_token={path_token(normalized)}.", file=sys.stderr)
                return 2
            count = finding_count(payload)
            total_findings += count
            if completed.returncode == 2:
                print(f"ERROR: DICOM scan failed path_token={path_token(normalized)}.", file=sys.stderr)
                return 2
            if completed.returncode not in (0, 1):
                print("ERROR: DICOM scanner returned an unsupported status.", file=sys.stderr)
                return 2
            if completed.returncode == 1 or count:
                reported_count = count or 1
                if is_hash_pinned_approved(root, normalized, require_dicom_review=True):
                    reviewed_findings += reported_count
                    print(
                        f"ADVISORY: DICOM scanner finding(s) explicitly triaged by exact-hash inventory review "
                        f"path_token={path_token(normalized)}; values suppressed."
                    )
                    total_findings -= count
                    continue
                print(
                    f"ADVISORY: DICOM scanner found {reported_count} potential finding(s) "
                    f"path_token={path_token(normalized)}; values suppressed."
                )
    if total_findings:
        print(f"DICOM privacy advisory complete: {total_findings} finding(s); triage required.")
        return 1
    if reviewed_findings:
        print(
            f"DICOM privacy advisory complete: {reviewed_findings} finding(s) explicitly triaged "
            "by exact-hash human review."
        )
    else:
        print(f"DICOM privacy advisory clean: {len(args.paths)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
