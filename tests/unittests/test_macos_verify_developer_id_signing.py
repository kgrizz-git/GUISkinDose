"""Unit tests for macos_verify_developer_id_signing.py with stub codesign/file."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
VERIFY = REPO / "packaging/portable/macos_verify_developer_id_signing.py"

TEAM = "EXPECTEDTEAM"
FORBIDDEN = "B9A88FL5XJ"


def _write_stub_codesign(bin_dir: Path) -> None:
    script = bin_dir / "codesign"
    script.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env bash
            set -euo pipefail
            if [[ "${1:-}" == "--verify" ]]; then
              target="${!#}"
              if [[ -f "${target}.fail_verify" ]]; then
                exit 1
              fi
              exit 0
            fi
            if [[ "${1:-}" == "-dv" ]]; then
              target="${!#}"
              if [[ -f "${target}.wrong_team" ]]; then
                echo "TeamIdentifier=WRONGTEAM99" >&2
              elif [[ -f "${target}.forbidden_team" ]]; then
                echo "TeamIdentifier=B9A88FL5XJ" >&2
              else
                echo "TeamIdentifier=EXPECTEDTEAM" >&2
              fi
              exit 0
            fi
            if [[ "${1:-}" == "-d" && "${2:-}" == "--entitlements" ]]; then
              if ! [[ " $* " == *" --xml "* ]]; then
                echo "stub codesign requires --xml for entitlements dump" >&2
                exit 2
              fi
              target="${!#}"
              if [[ -f "${target}.abstract_ent" ]]; then
                printf '[Dict]\n'
                exit 0
              fi
              if [[ -f "${target}.empty_ent" ]]; then
                exit 0
              fi
              if [[ -f "${target}.no_jit" ]]; then
                python3 -c 'import plistlib; print(plistlib.dumps({}).decode())'
                exit 0
              fi
              if [[ -f "${target}.outer_bad" ]]; then
                python3 -c 'import plistlib; print(plistlib.dumps({"com.apple.security.get-task-allow": True}).decode())'
                exit 0
              fi
              case "$target" in
                *GUISkinDose)
                  python3 -c 'import plistlib; print(plistlib.dumps({}).decode())'
                  exit 0
                  ;;
                *)
                  python3 -c 'import plistlib; print(plistlib.dumps({"com.apple.security.cs.allow-jit": True}).decode())'
                  exit 0
                  ;;
              esac
            fi
            echo "unsupported codesign invocation: $*" >&2
            exit 2
            """
        ).lstrip(),
        encoding="utf-8",
    )
    script.chmod(stat.S_IRWXU)


def _write_stub_file(bin_dir: Path, *, macho: bool = True) -> None:
    script = bin_dir / "file"
    line = "Mach-O 64-bit executable arm64" if macho else "ASCII text"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            echo "{line}"
            """
        ).lstrip(),
        encoding="utf-8",
    )
    script.chmod(stat.S_IRWXU)


def _bundle_root(tmp_path: Path, *, chromium: bool = True) -> Path:
    app = tmp_path / "GUISkinDose.app"
    main = app / "Contents/MacOS/GUISkinDose"
    main.parent.mkdir(parents=True)
    main.write_bytes(b"\xcf\xfa\xed\xfe")
    if chromium:
        chrom = app / "Contents/Helpers/Chromium.app/Contents/MacOS"
        chrom_main = chrom / "Chromium"
        chrom_main.parent.mkdir(parents=True)
        chrom_main.write_bytes(b"\xcf\xfa\xed\xfe")
        helper = chrom.parent.parent / "Helpers/Chromium Helper.app/Contents/MacOS/Chromium Helper"
        helper.parent.mkdir(parents=True)
        helper.write_bytes(b"\xcf\xfa\xed\xfe")
    return app


def _run_verify(
    app: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
  *,
    edition: str = "full",
    chromium_main_jit: str = "1",
    macho: bool = True,
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_stub_codesign(bin_dir)
    _write_stub_file(bin_dir, macho=macho)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    env["GUISKINDOSE_EXPECTED_TEAM_ID"] = TEAM
    env["GUISKINDOSE_FORBIDDEN_TEAM_IDS"] = FORBIDDEN
    env["GUISKINDOSE_CHROMIUM_MAIN_NEEDS_JIT"] = chromium_main_jit
    env["GUISKINDOSE_PORTABLE_EDITION"] = edition
    monkeypatch.chdir(tmp_path)
    return subprocess.run(
        [sys.executable, str(VERIFY), str(app)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _counter(stdout: str, name: str) -> int:
    prefix = f"{name}="
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return int(line.split("=", 1)[1])
    raise AssertionError(f"missing counter {name} in:\n{stdout}")


def test_verify_pass_full_edition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _bundle_root(tmp_path)
    proc = _run_verify(app, tmp_path, monkeypatch, edition="full", chromium_main_jit="1")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert _counter(proc.stdout, "verify_macho_count") >= 2
    assert _counter(proc.stdout, "macho_empty_count") == 0
    assert _counter(proc.stdout, "chromium_missing_count") == 0


def test_macho_empty_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = tmp_path / "empty.app"
    (app / "Contents/Resources").mkdir(parents=True)
    (app / "Contents/Resources/nomacho.txt").write_text("no binaries", encoding="utf-8")
    proc = _run_verify(app, tmp_path, monkeypatch, edition="light", macho=False)
    assert proc.returncode != 0
    assert _counter(proc.stdout, "verify_macho_count") == 0
    assert _counter(proc.stdout, "macho_empty_count") == 1


def test_chromium_missing_full_edition(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _bundle_root(tmp_path, chromium=False)
    proc = _run_verify(app, tmp_path, monkeypatch, edition="full")
    assert proc.returncode != 0
    assert _counter(proc.stdout, "chromium_missing_count") == 1


def test_entitlements_abstract_format_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _bundle_root(tmp_path)
    chrom = app / "Contents/Helpers/Chromium.app/Contents/MacOS/Chromium"
    Path(f"{chrom}.abstract_ent").write_text("1", encoding="utf-8")
    proc = _run_verify(app, tmp_path, monkeypatch)
    assert proc.returncode != 0
    assert _counter(proc.stdout, "entitlements_parse_fail_count") >= 1


def test_entitlements_empty_stdout_ok_for_light(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _bundle_root(tmp_path, chromium=False)
    main = app / "Contents/MacOS/GUISkinDose"
    Path(f"{main}.empty_ent").write_text("1", encoding="utf-8")
    proc = _run_verify(app, tmp_path, monkeypatch, edition="light", chromium_main_jit="0")
    assert _counter(proc.stdout, "entitlements_parse_fail_count") == 0
    assert proc.returncode == 0


def test_helper_jit_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _bundle_root(tmp_path)
    chrom_macos = app / "Contents/Helpers/Chromium.app/Contents/MacOS"
    helper = chrom_macos.parent.parent / "Helpers/Chromium Helper.app/Contents/MacOS/Chromium Helper"
    Path(f"{helper}.no_jit").write_text("1", encoding="utf-8")
    proc = _run_verify(app, tmp_path, monkeypatch, chromium_main_jit="1")
    assert proc.returncode != 0
    assert _counter(proc.stdout, "helper_jit_missing_count") >= 1


def test_team_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _bundle_root(tmp_path)
    extra = app / "Contents/MacOS/extra_macho"
    extra.write_bytes(b"\xcf\xfa\xed\xfe")
    Path(f"{extra}.wrong_team").write_text("1", encoding="utf-8")
    proc = _run_verify(app, tmp_path, monkeypatch)
    assert proc.returncode != 0
    assert _counter(proc.stdout, "team_mismatch_count") >= 1


def test_forbidden_team(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _bundle_root(tmp_path)
    extra = app / "Contents/MacOS/forbidden_macho"
    extra.write_bytes(b"\xcf\xfa\xed\xfe")
    Path(f"{extra}.forbidden_team").write_text("1", encoding="utf-8")
    proc = _run_verify(app, tmp_path, monkeypatch)
    assert proc.returncode != 0
    assert _counter(proc.stdout, "forbidden_team_count") >= 1


def test_verify_failure_counter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _bundle_root(tmp_path)
    bad = app / "Contents/MacOS/bad_verify_macho"
    bad.write_bytes(b"\xcf\xfa\xed\xfe")
    Path(f"{bad}.fail_verify").write_text("1", encoding="utf-8")
    proc = _run_verify(app, tmp_path, monkeypatch)
    assert proc.returncode != 0
    assert _counter(proc.stdout, "verify_failures") >= 1


def test_outer_bad_entitlements(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = _bundle_root(tmp_path, chromium=False)
    main = app / "Contents/MacOS/GUISkinDose"
    Path(f"{main}.outer_bad").write_text("1", encoding="utf-8")
    proc = _run_verify(app, tmp_path, monkeypatch, edition="light", chromium_main_jit="0")
    assert proc.returncode != 0
    assert _counter(proc.stdout, "outer_bad_entitlements_count") >= 1
