#!/usr/bin/env python3
"""Dump unresolved local SonarQube issues to timestamped, gitignored files.

Queries ``api/issues/search`` on the self-hosted server for the project key in
``sonar-project.properties`` and writes:

* ``tmp/sonar-issues/<UTC>.json`` — raw unresolved issue objects
* ``tmp/sonar-issues/<UTC>.md`` — compact human-readable summary
* ``tmp/sonar-latest-issues.json`` / ``tmp/sonar-latest-issues.md`` — stable
  pointers the freshness gate references in its hint text

When ``tmp/sonar-state.json`` already exists (written by
``scripts/run_sonarqube_local.py`` after a successful analysis), the issue
count and summary paths are refreshed in place without touching
``last_scan_commit``. Dumps older than 30 days are pruned, always keeping the
5 most recent timestamps.

Stdlib-only. The token is read from ``SONAR_TOKEN`` (an exported value wins;
otherwise the repo-root ``.env`` is parsed, never sourced) and is never
printed or written anywhere. Non-200 responses abort without touching state.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ALLOWED_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
ISSUES_DIRNAME = Path("tmp/sonar-issues")
LATEST_JSON = Path("tmp/sonar-latest-issues.json")
LATEST_SUMMARY = Path("tmp/sonar-latest-issues.md")
STATE_PATH = Path("tmp/sonar-state.json")
DEFAULT_PAGE_SIZE = 500
DEFAULT_CAP = 2000
REQUEST_TIMEOUT = 30


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_token_from_dotenv(root: Path) -> str | None:
    """Parse SONAR_TOKEN out of the repo-local .env without sourcing it."""
    env_file = root / ".env"
    if not env_file.is_file():
        return None
    try:
        text = env_file.read_text(encoding="utf-8")
    except OSError:
        return None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "SONAR_TOKEN":
            cleaned = clean_env_value(value)
            if cleaned:
                return cleaned
    return None


def resolve_token(root: Path) -> str | None:
    exported = os.environ.get("SONAR_TOKEN")
    if exported and exported.strip():
        return exported.strip()
    return load_token_from_dotenv(root)


def clean_env_value(raw: str) -> str:
    """Tolerate quoted values and trailing ` #` comments in .env files."""
    value = raw.strip().split(" #", 1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return value


def check_host_loopback(host_url: str, *, allow_remote: bool) -> str:
    """Accept loopback hosts; refuse anything else without --allow-remote."""
    from urllib.parse import urlparse

    if any(ch in host_url for ch in "\r\n\x00"):
        raise ValueError("invalid SonarQube host URL")
    parsed = urlparse(host_url)
    hostname = (parsed.hostname or "").lower()
    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"} or not hostname:
        raise ValueError("invalid SonarQube host URL")
    if hostname not in ALLOWED_LOCAL_HOSTS and not allow_remote:
        raise ValueError("non-loopback SonarQube host requires --allow-remote")
    return host_url


def project_key_from_properties(root: Path) -> str | None:
    try:
        text = (root / "sonar-project.properties").read_text(encoding="utf-8")
    except OSError:
        return None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "sonar.projectKey" and value.strip():
            return value.strip()
    return None


def fetch_issues_page(host_url: str, token: str, component: str, page: int, page_size: int) -> dict:
    query = urlencode(
        {"componentKeys": component, "resolved": "false", "ps": page_size, "p": page}
    )
    request = Request(
        f"{host_url.rstrip('/')}/api/issues/search?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        # URL is built from a validated loopback host plus a fixed SonarQube
        # API path; the scheme/host are allowlisted in check_host_loopback.
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:  # nosec B310
            status = response.status
            body = response.read()
    except OSError as exc:
        raise RuntimeError(f"issue search request failed ({type(exc).__name__})") from exc
    if status != 200:
        raise RuntimeError(f"issue search returned HTTP {status}; state untouched")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("issue search returned invalid JSON; state untouched") from exc
    if payload.get("errors"):
        raise RuntimeError(f"issue search returned errors: {payload['errors']}")
    if not isinstance(payload.get("issues"), list):
        raise RuntimeError("issue search response has no issues array; state untouched")
    return payload


def page_complete(*, batch_empty: bool, collected: int, total: int, cap: int) -> bool:
    """Decide whether issue pagination is done (pure; unit-tested)."""
    if batch_empty:
        return True
    # A missing `paging` block reports total 0: keep fetching rather than
    # silently truncating after the first page.
    if total > 0 and collected >= total:
        return True
    return collected >= cap


def summarize_issues(issues: list[dict], *, truncated: bool = False, cap: int = 0) -> str:
    lines = ["# SonarQube unresolved issues", ""]
    total_line = f"Total: {len(issues)}"
    if truncated:
        total_line += f" (truncated to --cap {cap})"
    lines += [total_line, ""]
    for issue in issues:
        severity = issue.get("severity", "?")
        rule = issue.get("rule", "?")
        component = issue.get("component", "") or ""
        short_component = component.rsplit(":", 1)[-1] if component else "?"
        line_number = issue.get("line", "")
        message = (issue.get("message") or "").replace("\n", " ")
        location = f"{short_component}:{line_number}" if line_number else short_component
        lines.append(f"- [{severity}] {rule} — {location} — {message}")
    return "\n".join(lines) + "\n"


def collect_dump_stamps(issues_dir: Path) -> dict[str, list[Path]]:
    """Group timestamped dump files by UTC stamp; ignore anything else."""
    stamps: dict[str, list[Path]] = {}
    for path in issues_dir.glob("*"):
        if not path.is_file():
            continue
        match = re.fullmatch(r"(\d{4}-\d{2}-\d{2}T\d{6}Z)\.(?:json|md)", path.name)
        if match:
            stamps.setdefault(match.group(1), []).append(path)
    return stamps


def stamp_datetime(stamp: str) -> datetime:
    return datetime.strptime(stamp, "%Y-%m-%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def stamps_to_keep(
    stamps: Mapping[str, list[Path]], *, keep_days: int, keep_minimum: int
) -> set[str]:
    """All in-cutoff stamps, always retaining at least keep_minimum timestamps."""
    ordered = sorted(stamps, key=stamp_datetime, reverse=True)
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    recent = [stamp for stamp in ordered if stamp_datetime(stamp) >= cutoff]
    return set(ordered[: max(len(recent), keep_minimum, 1)])


def remove_stale_stamps(stamps: Mapping[str, list[Path]], keep: set[str]) -> tuple[int, int]:
    """Delete non-kept stamps; return (removed, failed) without aborting."""
    removed = 0
    failed = 0
    for stamp in stamps:
        if stamp in keep:
            continue
        for path in stamps[stamp]:
            try:
                path.unlink()
            except OSError:
                failed += 1
                continue
            removed += 1
    return removed, failed


def prune_dumps(issues_dir: Path, *, keep_days: int = 30, keep_minimum: int = 5) -> tuple[int, int]:
    stamps = collect_dump_stamps(issues_dir)
    keep = stamps_to_keep(stamps, keep_days=keep_days, keep_minimum=keep_minimum)
    removed, failed = remove_stale_stamps(stamps, keep)
    if failed:
        print(f"warning: could not remove {failed} stale dump file(s).", file=sys.stderr)
    return removed, len(keep)


def refresh_state_counts(root: Path, *, issues_count: int, issues_path: str) -> bool:
    """Update counts in an existing state file; never create one from a dump."""
    state_file = root / STATE_PATH
    if not state_file.is_file():
        return False
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not isinstance(state, dict) or not state.get("last_scan_commit"):
        return False
    state["issues_count"] = issues_count
    state["issues_path"] = issues_path
    state["issues_summary_path"] = LATEST_SUMMARY.as_posix()
    try:
        state_file.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True


def fetch_all_issues(host_url: str, token: str, component: str, *, page_size: int, cap: int) -> tuple[list[dict], bool]:
    """Fetch every unresolved issue page; trim hard to cap. Returns (issues, truncated)."""
    collected: list[dict] = []
    page = 1
    while True:
        payload = fetch_issues_page(host_url, token, component, page, page_size)
        batch = payload["issues"]
        collected.extend(batch)
        total = 0
        paging = payload.get("paging")
        if isinstance(paging, dict):
            raw_total = paging.get("total", 0)
            if isinstance(raw_total, int):
                total = raw_total
        if page_complete(
            batch_empty=not batch,
            collected=len(collected),
            total=total,
            cap=cap,
        ):
            break
        page += 1
    if len(collected) > cap:
        return collected[:cap], True
    return collected, False


def write_issue_dumps(root: Path, collected: list[dict], timestamp: str, *, truncated: bool, cap: int) -> Path:
    """Write timestamped + stable-pointer dumps; return the issues directory."""
    issues_dir = root / ISSUES_DIRNAME
    issues_dir.mkdir(parents=True, exist_ok=True)
    issues_json = issues_dir / f"{timestamp}.json"
    issues_summary = issues_dir / f"{timestamp}.md"
    issues_json.write_text(json.dumps(collected, indent=2) + "\n", encoding="utf-8")
    issues_summary.write_text(summarize_issues(collected, truncated=truncated, cap=cap), encoding="utf-8")
    shutil.copyfile(issues_summary, root / LATEST_SUMMARY)
    shutil.copyfile(issues_json, root / LATEST_JSON)
    return issues_dir


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host-url",
        default=os.environ.get("SONAR_HOST_URL", "http://localhost:9000"),
        help="Self-hosted SonarQube URL; defaults to http://localhost:9000.",
    )
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Allow a non-loopback SonarQube host after a separate data-processing review.",
    )
    parser.add_argument(
        "--project-key",
        default=None,
        help="Override the sonar.projectKey from sonar-project.properties.",
    )
    parser.add_argument("--page-size", type=int, default=DEFAULT_PAGE_SIZE)
    parser.add_argument("--cap", type=int, default=DEFAULT_CAP)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root()
    try:
        host_url = check_host_loopback(args.host_url, allow_remote=args.allow_remote)
    except ValueError as exc:
        print(f"ERROR: SonarQube issue dump refused ({exc}).", file=sys.stderr)
        return 2
    component = args.project_key or project_key_from_properties(root)
    if not component:
        print("ERROR: SonarQube project key is missing (sonar-project.properties).", file=sys.stderr)
        return 2
    token = resolve_token(root)
    if not token:
        print("ERROR: SONAR_TOKEN is not set; export it or add it to repo-root .env.", file=sys.stderr)
        return 2
    if args.page_size < 1 or args.cap < 1:
        print("ERROR: --page-size and --cap must be positive integers.", file=sys.stderr)
        return 2

    collected: list[dict] = []
    try:
        collected, truncated = fetch_all_issues(
            host_url, token, component, page_size=args.page_size, cap=args.cap
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}.", file=sys.stderr)
        return 1

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    try:
        issues_dir = write_issue_dumps(root, collected, timestamp, truncated=truncated, cap=args.cap)
    except OSError as exc:
        print(f"ERROR: could not write issue dumps ({type(exc).__name__}).", file=sys.stderr)
        return 1

    state_file = root / STATE_PATH
    refreshed = refresh_state_counts(
        root, issues_count=len(collected), issues_path=f"{ISSUES_DIRNAME.as_posix()}/{timestamp}.json"
    )
    removed, kept = prune_dumps(issues_dir)

    print(f"SonarQube issues on record: {len(collected)}")
    print(f"Summary: {LATEST_SUMMARY.as_posix()}")
    if refreshed:
        print("State counts refreshed in tmp/sonar-state.json.")
    elif not state_file.is_file():
        print("No state file to refresh; run scripts/run_sonarqube_local.py to create one.")
    else:
        print("State file is present but invalid; run scripts/run_sonarqube_local.py to regenerate it.")
    print(f"Pruned {removed} stale dump file(s); keeping {kept} timestamp(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
