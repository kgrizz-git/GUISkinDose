#!/usr/bin/env python3
"""Run a local, non-blocking Presidio text scan over tracked repository files.

Install with ``uv sync --extra privacy-scan``. The optional dependency group
includes Presidio's compact English model. This script never uploads source
material or writes a report. It prints only the path, line, entity type, and
score--never the matching value--and returns zero after scan findings because
it is deliberately advisory.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# Presidio's NLP pass is not suitable for large generated tables/lockfiles.
# The deterministic gate still examines those files; this local advisory pass
# favors predictable resource use.
MAX_TEXT_BYTES = 64 * 1024
PII_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "US_BANK_NUMBER",
    "US_DRIVER_LICENSE",
    "US_ITIN",
    "US_PASSPORT",
    "US_SSN",
]


@dataclass(frozen=True)
class Finding:
    """A safe-to-log Presidio finding."""

    path: Path
    line: int
    entity_type: str
    score: float


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def tracked_paths(root: Path) -> list[Path]:
    """Return tracked files only, so ignored local data can never be scanned by default."""
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    return [root / Path(value.decode("utf-8")) for value in result.stdout.split(b"\0") if value]


def read_text(path: Path) -> str | None:
    """Return a small UTF-8 text file; skip opaque/binary and oversized content."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) > MAX_TEXT_BYTES or b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def make_engine() -> Any:
    """Build a Presidio engine using the small local English spaCy model."""
    try:
        from presidio_analyzer import AnalyzerEngine  # type: ignore[reportMissingImports]
        from presidio_analyzer.nlp_engine import NlpEngineProvider  # type: ignore[reportMissingImports]
    except ImportError as exc:
        raise RuntimeError(
            "Presidio is not installed. Run: uv sync --extra privacy-scan; "
            "uv run --extra privacy-scan python scripts/run_presidio_advisory.py"
        ) from exc

    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=configuration).create_engine()
    return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])


def scan_paths(engine: Any, root: Path, paths: Iterable[Path]) -> list[Finding]:
    """Scan readable text and retain location/type metadata without source values."""
    findings: list[Finding] = []
    for path in paths:
        text = read_text(path)
        if text is None:
            continue
        try:
            results = engine.analyze(
                text=text,
                language="en",
                entities=PII_ENTITIES,
                score_threshold=0.5,
            )
        except Exception as exc:  # Presidio recognizers must never stop an advisory scan.
            print(f"WARNING: Presidio could not scan {path.relative_to(root)}: {type(exc).__name__}", file=sys.stderr)
            continue
        relative_path = path.relative_to(root)
        for result in results:
            start = max(0, int(result.start))
            findings.append(
                Finding(
                    path=relative_path,
                    line=text.count("\n", 0, start) + 1,
                    entity_type=str(result.entity_type),
                    score=float(result.score),
                )
            )
    return findings


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Optional repository-relative tracked paths; defaults to all tracked files.",
    )
    parser.add_argument(
        "--max-displayed-findings",
        type=int,
        default=100,
        help="Maximum safe finding summaries to print (default: 100).",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_displayed_findings < 0:
        print("ERROR: --max-displayed-findings must be zero or greater", file=sys.stderr)
        return 2
    root = repo_root().resolve()
    all_tracked_paths = tracked_paths(root)
    tracked_by_resolved_path = {path.resolve(): path for path in all_tracked_paths}
    requested_paths = [root / path for path in args.paths] if args.paths else all_tracked_paths
    paths: list[Path] = []
    for path in requested_paths:
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(root)
        except ValueError:
            print(f"ERROR: path is outside the repository: {path}", file=sys.stderr)
            return 2
        if resolved_path not in tracked_by_resolved_path:
            print(f"ERROR: not a tracked regular file: {resolved_path.relative_to(root)}", file=sys.stderr)
            return 2
        paths.append(tracked_by_resolved_path[resolved_path])

    try:
        engine = make_engine()
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"Presidio advisory scan: evaluating {len(paths)} tracked file(s).", flush=True)
    findings = scan_paths(engine, root, paths)
    for finding in findings[: args.max_displayed_findings]:
        print(
            f"ADVISORY: {finding.path}:{finding.line}: Presidio {finding.entity_type} "
            f"(score {finding.score:.2f}); value suppressed"
        )
    suppressed_count = len(findings) - min(len(findings), args.max_displayed_findings)
    if suppressed_count:
        print(f"ADVISORY: suppressed {suppressed_count} additional finding summary/summaries.")
    print(f"Presidio advisory scan complete: {len(findings)} finding(s) across {len(paths)} tracked file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
