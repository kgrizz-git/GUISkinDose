#!/usr/bin/env python3
"""Validate and render the privacy-tool inventory and scanner references."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

INVENTORY_PATH = Path("dev-docs/privacy_tool_inventory.json")
MARKDOWN_PATH = Path("dev-docs/privacy_tool_inventory.md")
POLICY_PATH = Path("dev-docs/privacy_admission_policy.json")
REQUIRED_FIELDS = {
    "id",
    "name",
    "status",
    "version",
    "version_source",
    "execution",
    "role",
    "output_policy",
    "source",
}
ALLOWED_STATUSES = {"active", "optional", "candidate", "retired"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected_object")
    return payload


def validate(inventory: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if inventory.get("version") != 1:
        errors.append("unsupported inventory version")
    tools = inventory.get("tools")
    if not isinstance(tools, list):
        return [*errors, "tools must be a list"]
    ids: list[str] = []
    for index, item in enumerate(tools):
        if not isinstance(item, dict):
            errors.append(f"tool entry {index} is not an object")
            continue
        missing = sorted(REQUIRED_FIELDS - set(item))
        if missing:
            errors.append(f"tool entry {index} missing fields: {','.join(missing)}")
        tool_id = item.get("id")
        if not isinstance(tool_id, str) or not tool_id:
            errors.append(f"tool entry {index} has invalid id")
        else:
            ids.append(tool_id)
        if item.get("status") not in ALLOWED_STATUSES:
            errors.append(f"tool entry {index} has invalid status")
        source = item.get("source")
        if not isinstance(source, str) or not source.startswith("https://"):
            errors.append(f"tool entry {index} must use an HTTPS source")
    if len(ids) != len(set(ids)):
        errors.append("tool ids must be unique")
    known_ids = set(ids)
    scanners = policy.get("scanners")
    if not isinstance(scanners, list):
        return [*errors, "policy scanners must be a list"]
    for scanner in scanners:
        if not isinstance(scanner, dict):
            continue
        scanner_id = str(scanner.get("id", "unknown"))
        tool_ids = scanner.get("tool_ids")
        if not isinstance(tool_ids, list) or not tool_ids:
            errors.append(f"scanner {scanner_id} has no tool_ids")
            continue
        for tool_id in tool_ids:
            if tool_id not in known_ids:
                errors.append(f"scanner {scanner_id} references unknown tool {tool_id}")
    return errors


def escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def render(inventory: dict[str, Any]) -> str:
    rows = [
        "# Privacy tool inventory",
        "",
        "This file is generated from [`privacy_tool_inventory.json`](privacy_tool_inventory.json).",
        "It inventories direct external privacy tools and runtimes; it is not an approval for raw report output.",
        "",
        f"Last reviewed: {escape(inventory.get('reviewed_on', 'unknown'))}",
        "",
        "| Tool | Status | Version | Execution | Role | Output boundary |",
        "|---|---|---:|---|---|---|",
    ]
    tools = inventory.get("tools", [])
    for item in tools:
        if not isinstance(item, dict):
            continue
        name = escape(item["name"])
        source = escape(item["source"])
        rows.append(
            f"| [{name}]({source}) | {escape(item['status'])} | {escape(item['version'])} | "
            f"{escape(item['execution'])} | {escape(item['role'])} | {escape(item['output_policy'])} |"
        )
    rows.extend(
        [
            "",
            "Version provenance and installation details remain authoritative in the JSON inventory. Active tools",
            "must also be referenced by the privacy admission policy when they participate in conditional receipts.",
            "Candidate tools are not authorized for automated use until a value-safe wrapper and synthetic tests exist.",
            "",
        ]
    )
    return "\n".join(rows)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--write", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root()
    try:
        inventory = load_json(root / INVENTORY_PATH)
        policy = load_json(root / POLICY_PATH)
        errors = validate(inventory, policy)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: privacy tool inventory unavailable ({type(exc).__name__}).", file=sys.stderr)
        return 2
    if errors:
        for error in errors:
            print(f"ERROR: {error}.", file=sys.stderr)
        return 1
    expected = render(inventory)
    target = root / MARKDOWN_PATH
    if args.write:
        target.write_text(expected, encoding="utf-8")
        return 0
    try:
        current = target.read_text(encoding="utf-8")
    except OSError:
        current = ""
    if current != expected:
        print("ERROR: privacy tool inventory Markdown is stale; run with --write.", file=sys.stderr)
        return 1
    print("Privacy tool inventory OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
