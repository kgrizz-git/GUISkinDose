#!/usr/bin/env python3
"""Run local Presidio over bounded, tracked repository text.

Install with ``uv sync --extra privacy-scan``. The optional dependency group
includes Presidio's compact English model. This script never uploads source
material or writes a report. It prints only a path token, line, entity type,
and score--never the matching value. Scheduled review can fail on findings or
scan errors; noisy person-name detection requires a targeted local opt-in.
"""

from __future__ import annotations

import argparse
import hashlib
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
PRESIDIO_TEXT_SUFFIXES = {
    ".cfg",
    ".csv",
    ".html",
    ".ini",
    ".json",
    ".md",
    ".rst",
    ".svg",
    ".toml",
    ".tsv",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
# Public package-author contacts are already line-pinned in the deterministic
# allowlist; repeating them weekly adds no signal.
PRESIDIO_EXCLUDED_PATHS = {Path("pyproject.toml")}
PII_ENTITIES = [
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


def path_token(path: Path) -> str:
    """Return a stable, non-reversible display token for a repository path."""
    return hashlib.sha256(path.as_posix().encode("utf-8")).hexdigest()[:12]


def tracked_paths(root: Path, *, require_git: bool = True) -> list[Path]:
    """Return tracked files, or regular files from a private materialized snapshot."""
    if not require_git:
        return sorted(
            path
            for path in root.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and path.suffix.lower() in PRESIDIO_TEXT_SUFFIXES
            and path.relative_to(root) not in PRESIDIO_EXCLUDED_PATHS
        )
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    paths: list[Path] = []
    for value in result.stdout.split(b"\0"):
        if not value:
            continue
        path = Path(value.decode("utf-8"))
        if path.suffix.lower() in PRESIDIO_TEXT_SUFFIXES and path not in PRESIDIO_EXCLUDED_PATHS:
            paths.append(root / path)
    return paths


def read_text(path: Path) -> str | None:
    """Return a small UTF-8 text file; skip opaque/binary and oversized content."""
    if path.is_symlink():
        return None
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
        import en_core_web_sm  # type: ignore[import-not-found]  # noqa: F401
        import tldextract
        from presidio_analyzer import AnalyzerEngine  # type: ignore[reportMissingImports]
        from presidio_analyzer.nlp_engine import NlpEngineProvider  # type: ignore[reportMissingImports]
    except ImportError as exc:
        raise RuntimeError(
            "Presidio or its pinned local language model is not installed."
        ) from exc

    # Presidio's email recognizer otherwise lets tldextract fetch the public
    # suffix list on first use. Use its bundled snapshot with no cache/network.
    tldextract.extract = tldextract.TLDExtract(suffix_list_urls=(), cache_dir=None)

    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
    }
    nlp_engine = NlpEngineProvider(nlp_configuration=configuration).create_engine()
    return AnalyzerEngine(nlp_engine=nlp_engine, supported_languages=["en"])


def scan_paths(
    engine: Any,
    root: Path,
    paths: Iterable[Path],
    *,
    include_person: bool = False,
    fail_on_scan_error: bool = False,
) -> list[Finding]:
    """Scan readable text and retain location/type metadata without source values."""
    findings: list[Finding] = []
    for path in paths:
        text = read_text(path)
        if text is None:
            continue
        try:
            entities = [*PII_ENTITIES, "PERSON"] if include_person else PII_ENTITIES
            results = engine.analyze(
                text=text,
                language="en",
                entities=entities,
                score_threshold=0.85,
            )
        except Exception as exc:  # Presidio recognizers must never stop an advisory scan.
            token = path_token(path.relative_to(root))
            print(f"WARNING: Presidio could not scan path_token={token}: {type(exc).__name__}", file=sys.stderr)
            if fail_on_scan_error:
                raise RuntimeError("presidio_file_scan_failed") from None
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
        "--scan-root",
        type=Path,
        help="Private materialized snapshot to scan instead of the repository checkout.",
    )
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
    parser.add_argument(
        "--verbose-paths",
        action="store_true",
        help="Show repository paths locally; default output uses non-reversible path tokens.",
    )
    parser.add_argument(
        "--fail-on-findings",
        action="store_true",
        help="Exit 1 after reporting findings; useful for scheduled secondary review jobs.",
    )
    parser.add_argument(
        "--include-person",
        action="store_true",
        help=(
            "Enable noisy NLP person-name detection for targeted free-text review. "
            "Do not use this untriaged mode as an automated gate."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.max_displayed_findings < 0:
        print("ERROR: --max-displayed-findings must be zero or greater", file=sys.stderr)
        return 2
    root = (args.scan_root or repo_root()).resolve()
    if not root.is_dir():
        print("ERROR: scan root is unavailable", file=sys.stderr)
        return 2
    all_tracked_paths = tracked_paths(root, require_git=args.scan_root is None)
    tracked_by_resolved_path = {path.resolve(): path for path in all_tracked_paths}
    requested_paths = [root / path for path in args.paths] if args.paths else all_tracked_paths
    paths: list[Path] = []
    for path in requested_paths:
        resolved_path = path.resolve()
        try:
            resolved_path.relative_to(root)
        except ValueError:
            print("ERROR: requested path is outside the repository", file=sys.stderr)
            return 2
        if resolved_path not in tracked_by_resolved_path:
            print("ERROR: requested path is not a tracked regular file", file=sys.stderr)
            return 2
        paths.append(tracked_by_resolved_path[resolved_path])

    try:
        engine = make_engine()
    except Exception as exc:
        print(f"ERROR: Presidio did not start ({type(exc).__name__})", file=sys.stderr)
        return 2

    print(f"Presidio advisory scan: evaluating {len(paths)} tracked file(s).", flush=True)
    try:
        findings = scan_paths(
            engine,
            root,
            paths,
            include_person=args.include_person,
            fail_on_scan_error=args.fail_on_findings,
        )
    except RuntimeError as exc:
        print(f"ERROR: Presidio scan did not complete ({type(exc).__name__})", file=sys.stderr)
        return 2
    for finding in findings[: args.max_displayed_findings]:
        path_label = str(finding.path) if args.verbose_paths else f"path_token={path_token(finding.path)}"
        print(
            f"ADVISORY: {path_label}:{finding.line}: Presidio {finding.entity_type} "
            f"(score {finding.score:.2f}); value suppressed"
        )
    suppressed_count = len(findings) - min(len(findings), args.max_displayed_findings)
    if suppressed_count:
        print(f"ADVISORY: suppressed {suppressed_count} additional finding summary/summaries.")
    print(f"Presidio advisory scan complete: {len(findings)} finding(s) across {len(paths)} tracked file(s).")
    return 1 if findings and args.fail_on_findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
