#!/usr/bin/env python3
"""Report SonarCloud quality-gate status and new-code issue counts (stdlib-only).

Reads ``sonar.projectKey`` from ``sonar-project.properties``, authenticates with
``SONAR_CLOUD_TOKEN`` or ``SONAR_TOKEN`` (see ``dump_sonar_issues.resolve_cloud_token``),
and queries the public SonarCloud API. Tokens are never printed.

Typical use before or after a ``main`` push when ``sonar-scan`` is enabled:

    python scripts/check_sonarcloud_gate.py
    python scripts/check_sonarcloud_gate.py --fail-on-error

Exits 0 when the gate is red unless ``--fail-on-error`` is set (report-only default).

Cloud **new code** reflects the last analysis SonarCloud recorded (usually ``main``
after CI ``sonar-scan``), not an unmerged PR branch until that analysis lands.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.dump_sonar_issues import (  # noqa: E402
    _NO_REDIRECT_OPENER,
    project_key_from_properties,
    repo_root,
    resolve_cloud_token,
)

DEFAULT_HOST = "https://sonarcloud.io"
REQUEST_TIMEOUT = 30


def _get_json(host_url: str, token: str, path: str, query: dict[str, str]) -> dict[str, Any]:
    url = f"{host_url.rstrip('/')}{path}?{urlencode(query)}"
    request = Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with _NO_REDIRECT_OPENER.open(request, timeout=REQUEST_TIMEOUT) as response:
            status = response.status
            body = response.read()
    except OSError as exc:
        raise RuntimeError(f"request failed ({type(exc).__name__})") from exc
    if status != 200:
        raise RuntimeError(f"HTTP {status}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except ValueError as exc:
        raise RuntimeError("invalid JSON response") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("non-object JSON response")
    if payload.get("errors"):
        raise RuntimeError("API returned errors")
    return payload


def fetch_project_status(host_url: str, token: str, project_key: str) -> dict[str, Any]:
    payload = _get_json(host_url, token, "/api/qualitygates/project_status", {"projectKey": project_key})
    if not isinstance(payload.get("projectStatus"), dict):
        raise RuntimeError("invalid project status response")
    return payload


def fetch_new_code_issues(
    host_url: str, token: str, project_key: str, *, page_size: int, issue_types: str | None
) -> dict[str, Any]:
    query: dict[str, str] = {
        "componentKeys": project_key,
        "resolved": "false",
        "inNewCodePeriod": "true",
        "ps": str(page_size),
        "p": "1",
    }
    if issue_types:
        query["types"] = issue_types
    return _get_json(host_url, token, "/api/issues/search", query)


def format_gate_report(
    status_payload: dict[str, Any],
    issues_payload: dict[str, Any],
    bugs_payload: dict[str, Any],
    *,
    sample_limit: int,
) -> str:
    project_status = status_payload.get("projectStatus", {})
    gate = project_status.get("status", "UNKNOWN")
    lines = [f"SonarCloud quality gate status={gate}", ""]
    lines.append("Gate conditions (non-OK):")
    conditions = project_status.get("conditions") or []
    failing = [c for c in conditions if isinstance(c, dict) and c.get("status") != "OK"]
    if not failing:
        lines.append("  (none)")
    else:
        for cond in failing:
            metric = cond.get("metricKey", "?")
            level = cond.get("status", "?")
            actual = cond.get("actualValue", "?")
            threshold = cond.get("errorThreshold", "?")
            lines.append(f"  - {metric}: {level} (actual={actual}, threshold={threshold})")
    lines.append("")
    total_new = issues_payload.get("total", 0)
    total_bugs = bugs_payload.get("total", 0)
    lines.append(f"Unresolved new-code issues (inNewCodePeriod): total={total_new}, bugs={total_bugs}")
    issues = issues_payload.get("issues") or []
    if isinstance(issues, list):
        by_type = Counter(str(i.get("type", "?")) for i in issues if isinstance(i, dict))
        if by_type:
            lines.append("Sample page by type: " + ", ".join(f"{k}={v}" for k, v in sorted(by_type.items())))
        lines.append("")
        lines.append(f"Sample issues (up to {sample_limit}):")
        for issue in issues[:sample_limit]:
            if not isinstance(issue, dict):
                continue
            lines.append(
                f"  - [{issue.get('type', '?')}] {issue.get('severity', '?')} {issue.get('rule', '?')}"
            )
    lines.append("")
    lines.append(
        "Note: SonarCloud new code updates after CI analysis on the analyzed branch (typically main). "
        "Compare with local Docker SonarQube for the working tree."
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-url", default=DEFAULT_HOST, help=f"SonarCloud base URL (default: {DEFAULT_HOST}).")
    parser.add_argument("--project-key", default=None, help="Override sonar.projectKey from sonar-project.properties.")
    parser.add_argument("--sample-limit", type=int, default=20, help="Max sample new-code issues to print.")
    parser.add_argument(
        "--fail-on-error",
        action="store_true",
        help="Exit 1 when the quality gate status is not OK.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root()
    project_key = args.project_key or project_key_from_properties(root)
    if not project_key:
        print("ERROR: SonarCloud project key is missing (sonar-project.properties).", file=sys.stderr)
        return 2
    token = resolve_cloud_token(root)
    if not token:
        print(
            "ERROR: SonarCloud token missing; set SONAR_CLOUD_TOKEN or SONAR_TOKEN in the environment or .env.",
            file=sys.stderr,
        )
        return 2
    if args.sample_limit < 1:
        print("ERROR: --sample-limit must be a positive integer.", file=sys.stderr)
        return 2
    host = args.host_url.rstrip("/")
    if not host.startswith("https://"):
        print("ERROR: SonarCloud host must use HTTPS.", file=sys.stderr)
        return 2
    try:
        status_payload = fetch_project_status(host, token, project_key)
        issues_payload = fetch_new_code_issues(
            host, token, project_key, page_size=min(max(args.sample_limit, 50), 500), issue_types=None
        )
        bugs_payload = fetch_new_code_issues(host, token, project_key, page_size=10, issue_types="BUG")
    except (RuntimeError, HTTPError, json.JSONDecodeError) as exc:
        print(f"ERROR: SonarCloud query failed ({exc}).", file=sys.stderr)
        return 1
    report = format_gate_report(
        status_payload,
        issues_payload,
        bugs_payload,
        sample_limit=args.sample_limit,
    )
    print(report)
    gate = (status_payload.get("projectStatus") or {}).get("status", "UNKNOWN")
    if args.fail_on_error and gate != "OK":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
