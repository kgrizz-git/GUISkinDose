"""Tests for the SonarQube issue-dump helper (offline parts only)."""

from __future__ import annotations

import json
from http.client import HTTPMessage
from io import BytesIO
from pathlib import Path
from typing import Self
from urllib.error import HTTPError
from urllib.request import Request

import pytest

import scripts.dump_sonar_issues as dsi
from scripts.dump_sonar_issues import (
    check_host_loopback,
    clean_env_value,
    page_complete,
    project_key_from_properties,
    prune_dumps,
    refresh_state_counts,
    summarize_issues,
)


def test_loopback_hosts_allowed_and_remote_refused() -> None:
    assert check_host_loopback("http://localhost:9000", allow_remote=False)
    with pytest.raises(ValueError, match="non-loopback"):
        check_host_loopback("https://sonar.example.com", allow_remote=False)
    assert check_host_loopback("https://sonar.example.com", allow_remote=True)


def test_project_key_from_properties(tmp_path: Path) -> None:
    (tmp_path / "sonar-project.properties").write_text(
        "# comment\nsonar.projectKey=my-key\n", encoding="utf-8"
    )
    assert project_key_from_properties(tmp_path) == "my-key"
    assert project_key_from_properties(tmp_path / "missing") is None


def test_summarize_issues_formats_locations() -> None:
    summary = summarize_issues(
        [
            {
                "severity": "MAJOR",
                "rule": "python:S100",
                "component": "proj:src/mod.py",
                "line": 12,
                "message": "Rename this.",
            }
        ]
    )
    assert "Total: 1" in summary
    assert "src/mod.py:12" in summary


def test_refresh_state_counts_preserves_scan_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.dump_sonar_issues as dump

    monkeypatch.setattr(dump, "repo_root", lambda: tmp_path)
    state_file = tmp_path / "tmp" / "sonar-state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(
        json.dumps({"last_scan_commit": "abc", "last_scan_time": "t", "issues_count": None}),
        encoding="utf-8",
    )
    assert refresh_state_counts(tmp_path, issues_count=7, issues_path="tmp/sonar-issues/x.json") is True
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["last_scan_commit"] == "abc"
    assert state["issues_count"] == 7


def test_refresh_state_counts_missing_file_is_false(tmp_path: Path) -> None:
    assert refresh_state_counts(tmp_path, issues_count=1, issues_path="tmp/sonar-issues/x.json") is False


def test_prune_dumps_keeps_recent_minimum(tmp_path: Path) -> None:
    issues_dir = tmp_path / "dumps"
    issues_dir.mkdir()
    for stamp in ("2026-09-20T120000Z", "2026-09-24T120000Z"):
        (issues_dir / f"{stamp}.json").write_text("[]", encoding="utf-8")
        (issues_dir / f"{stamp}.md").write_text("#", encoding="utf-8")
    removed, kept = prune_dumps(issues_dir)
    assert removed == 0
    assert kept == 2


def test_prune_dumps_removes_beyond_minimum(tmp_path: Path) -> None:
    issues_dir = tmp_path / "dumps"
    issues_dir.mkdir()
    for day in range(1, 7):  # 6 stale stamps; minimum keeps 5
        stamp = f"2020-01-0{day}T120000Z"
        (issues_dir / f"{stamp}.json").write_text("[]", encoding="utf-8")
        (issues_dir / f"{stamp}.md").write_text("#", encoding="utf-8")
    removed, kept = prune_dumps(issues_dir)
    assert removed == 2
    assert kept == 5
    assert not (issues_dir / "2020-01-01T120000Z.json").exists()


def test_refresh_state_counts_rejects_corrupt_or_commitless_state(tmp_path: Path) -> None:
    state_file = tmp_path / "tmp" / "sonar-state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text("{not json\n", encoding="utf-8")
    assert refresh_state_counts(tmp_path, issues_count=1, issues_path="tmp/sonar-issues/x.json") is False
    state_file.write_text(json.dumps({"issues_count": 1}), encoding="utf-8")
    assert refresh_state_counts(tmp_path, issues_count=1, issues_path="tmp/sonar-issues/x.json") is False


@pytest.mark.parametrize(
    ("batch_empty", "collected", "total", "cap", "expected"),
    [
        (True, 0, 0, 2000, True),  # empty page always ends pagination
        (False, 500, 1200, 2000, False),  # more pages reported
        (False, 1200, 1200, 2000, True),  # server total reached
        (False, 500, 0, 2000, False),  # missing paging block: keep fetching
        (False, 2000, 0, 2000, True),  # cap reached without paging info
        (False, 2100, 5000, 2000, True),  # cap reached before server total
    ],
)
def test_page_complete(batch_empty: bool, collected: int, total: int, cap: int, expected: bool) -> None:
    assert page_complete(batch_empty=batch_empty, collected=collected, total=total, cap=cap) is expected


def test_summarize_issues_marks_truncation() -> None:
    summary = summarize_issues([{"severity": "x"}], truncated=True, cap=1)
    assert "Total: 1 (truncated to --cap 1)" in summary


@pytest.mark.parametrize(
    ("raw", "expected"),
    [('squ_abc123', "squ_abc123"), ('"squ_abc123"', "squ_abc123"), ("'squ_abc123'", "squ_abc123")],
)
def test_clean_env_value(raw: str, expected: str) -> None:
    assert clean_env_value(raw) == expected


# --- token resolution, HTTP fetch, and main() with a stubbed opener ---

class _FakeResponse:
    def __init__(self, body: bytes, status: int = 200) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _stub_pages(monkeypatch: pytest.MonkeyPatch, pages: list[object], seen: list[str] | None = None) -> None:
    """Serve each page in order; bytes/int entries simulate raw bodies or HTTP statuses."""
    queue = list(pages)

    def fake_open(request, timeout):
        if seen is not None:
            seen.append(request.get_header("Authorization"))
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, int):
            return _FakeResponse(b"{}", status=item)
        if isinstance(item, bytes):
            return _FakeResponse(item)
        return _FakeResponse(json.dumps(item).encode("utf-8"))

    monkeypatch.setattr(dsi._NO_REDIRECT_OPENER, "open", fake_open)


def _issue(n: int) -> dict:
    return {"severity": "MINOR", "rule": "python:S1", "component": f"k:src/f{n}.py", "line": n, "message": "m"}


def test_resolve_token_prefers_export_then_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text("# c\nOTHER=1\nSONAR_TOKEN=\nSONAR_TOKEN='from-file' # note\n", encoding="utf-8")
    monkeypatch.setenv("SONAR_TOKEN", "  exported  ")
    assert dsi.resolve_token(tmp_path) == "exported"
    monkeypatch.delenv("SONAR_TOKEN")
    assert dsi.resolve_token(tmp_path) == "from-file"
    assert dsi.resolve_token(tmp_path / "missing") is None


def test_check_host_rejects_malformed_urls() -> None:
    for url in ("ftp://localhost", "http://", "http://localhost\n:9000"):
        with pytest.raises(ValueError, match="invalid"):
            check_host_loopback(url, allow_remote=True)


def test_remote_host_requires_https_but_loopback_http_is_fine() -> None:
    with pytest.raises(ValueError, match="requires https"):
        check_host_loopback("http://sonar.example.com", allow_remote=True)
    assert check_host_loopback("http://127.0.0.1:9000", allow_remote=False)


def test_redirects_are_refused_for_credentialed_requests() -> None:
    request = Request("http://localhost:9000/api/issues/search", headers={"Authorization": "Bearer tok"})
    with pytest.raises(HTTPError, match="redirect refused"):
        dsi._RefuseRedirects().redirect_request(
            request, BytesIO(), 302, "Found", HTTPMessage(), "http://elsewhere/"
        )


def test_fetch_all_issues_paginates_and_truncates(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    _stub_pages(
        monkeypatch,
        [
            {"issues": [_issue(1), _issue(2)], "paging": {"total": 5}},
            {"issues": [_issue(3), _issue(4)], "paging": {"total": 5}},
        ],
        seen,
    )
    issues, truncated = dsi.fetch_all_issues("http://localhost:9000/", "tok", "k", page_size=2, cap=3)
    assert [i["line"] for i in issues] == [1, 2, 3]
    assert truncated is True
    assert seen == ["Bearer tok", "Bearer tok"]


@pytest.mark.parametrize(
    ("page", "match"),
    [
        (500, "HTTP 500"),
        (b"not json", "invalid JSON"),
        ({"errors": [{"msg": "x"}]}, "returned errors"),
        ({"paging": {}}, "no issues array"),
        (b"[1, 2]", "non-object"),
        (OSError("down"), "request failed"),
    ],
)
def test_fetch_issues_page_failures_raise(monkeypatch: pytest.MonkeyPatch, page: object, match: str) -> None:
    _stub_pages(monkeypatch, [page])
    with pytest.raises(RuntimeError, match=match):
        dsi.fetch_issues_page("http://localhost:9000", "tok", "k", 1, 10)


def _fake_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, key: bool = True) -> Path:
    if key:
        (tmp_path / "sonar-project.properties").write_text("sonar.projectKey=k\n", encoding="utf-8")
    monkeypatch.setattr(dsi, "repo_root", lambda: tmp_path)
    monkeypatch.setenv("SONAR_TOKEN", "tok")
    return tmp_path


def test_main_writes_dumps_and_refreshes_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    state = root / "tmp" / "sonar-state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"last_scan_commit": "a" * 40}), encoding="utf-8")
    _stub_pages(monkeypatch, [{"issues": [_issue(1)], "paging": {"total": 1}}])

    assert dsi.main(["--host-url", "http://localhost:9000"]) == 0

    out = capsys.readouterr().out
    assert "issues on record: 1" in out and "State counts refreshed" in out
    assert "tok" not in out
    assert json.loads((root / "tmp" / "sonar-latest-issues.json").read_text(encoding="utf-8"))[0]["line"] == 1
    refreshed = json.loads(state.read_text(encoding="utf-8"))
    assert refreshed["issues_count"] == 1 and refreshed["last_scan_commit"] == "a" * 40


@pytest.mark.parametrize(("state_text", "expected"), [(None, "No state file"), ("{bad", "present but invalid")])
def test_main_reports_missing_or_invalid_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    state_text: str | None,
    expected: str,
) -> None:
    root = _fake_repo(tmp_path, monkeypatch)
    if state_text is not None:
        (root / "tmp").mkdir()
        (root / "tmp" / "sonar-state.json").write_text(state_text, encoding="utf-8")
    _stub_pages(monkeypatch, [{"issues": []}])
    assert dsi.main(["--host-url", "http://localhost:9000"]) == 0
    assert expected in capsys.readouterr().out


def test_main_refusals_and_fetch_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _fake_repo(tmp_path, monkeypatch, key=False)
    assert dsi.main(["--host-url", "https://sonar.example.com"]) == 2
    assert dsi.main(["--host-url", "http://localhost:9000"]) == 2  # no project key
    assert dsi.main(["--host-url", "http://localhost:9000", "--project-key", "k", "--cap", "0"]) == 2
    monkeypatch.delenv("SONAR_TOKEN")
    assert dsi.main(["--host-url", "http://localhost:9000", "--project-key", "k"]) == 2
    monkeypatch.setenv("SONAR_TOKEN", "tok")
    _stub_pages(monkeypatch, [503])
    assert dsi.main(["--host-url", "http://localhost:9000", "--project-key", "k"]) == 1
    assert not (root / "tmp").exists()
    assert "tok" not in capsys.readouterr().err
