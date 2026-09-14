"""Static regression tests for the GUI launchers (``run_gui.bat`` / ``run_gui.sh``).

The ``.bat`` launcher once shipped ``echo`` lines with unescaped parentheses
inside ``if (...)`` blocks, which made ``cmd.exe`` fail with
``. was unexpected at this time`` before reaching the mode prompt. Escaping
every text paren as ``^(`` / ``^)`` is harmless at top level (the caret is
consumed by the parser), so the convention -- and the test below -- is simple:
no ``echo`` text paren may appear unescaped, anywhere in the file.

These tests run on Linux CI (no ``cmd.exe`` needed); the ``test_bat_exec_*``
tests additionally execute the real launcher on Windows runners, where
``cmd.exe`` exists and the system python is a real executable.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BAT = REPO / "run_gui.bat"
SH = REPO / "run_gui.sh"


def _bat_echo_text_lines() -> list[tuple[int, str]]:
    """``(lineno, text-after-echo)`` for every real ``echo`` text line."""
    lines = BAT.read_text(encoding="utf-8").splitlines()
    found: list[tuple[int, str]] = []
    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped.lower().startswith("echo"):
            continue
        rest = stripped[4:]
        if rest == "" or rest[0] in (".", "(", ":", "/", "-", "+"):
            continue
        found.append((lineno, rest))
    return found


def test_bat_echo_parens_escaped() -> None:
    """Every ``echo`` text paren in ``run_gui.bat`` is escaped as ``^(`` / ``^)``."""
    violations = [
        f"line {lineno}: {text}"
        for lineno, text in _bat_echo_text_lines()
        if re.search(r"(?<!\^)\(", text) or re.search(r"(?<!\^)\)", text)
    ]
    assert not violations, "unescaped parens in echo text (breaks inside if-blocks):\n" + "\n".join(violations)


def test_bat_echo_bang_marker() -> None:
    """Notice markers render as ``[!]``: a literal bang is swallowed by delayed expansion."""
    for lineno, text in _bat_echo_text_lines():
        assert "[!]" not in text, f"line {lineno}: literal [!] renders as [] under delayed expansion"


def test_bat_block_comments_paren_free() -> None:
    """Indented ``::`` comments carry no parens: cmd counts comment parens as block delimiters."""
    lines = BAT.read_text(encoding="utf-8").splitlines()
    violations = [
        f"line {lineno}: {raw.strip()}"
        for lineno, raw in enumerate(lines, start=1)
        if raw != raw.lstrip() and raw.lstrip().startswith("::") and ("(" in raw or ")" in raw)
    ]
    assert not violations, "parens in in-block :: comment (breaks block parsing):\n" + "\n".join(violations)


def test_bat_version_guard_fail_closed() -> None:
    """Both version gates reject garbage output before any ``LSS``/``EQU`` comparison.

    The system-python gate (top of file) and the ``:validate_selected`` gate
    each carry a fail-closed numeric guard plus an empty-``MINOR`` backstop;
    all four rejection paths share the standard error message (exact count so
    a deleted guard is caught, not just a deleted message).
    """
    text = BAT.read_text(encoding="utf-8")
    assert text.count("Could not determine Python version") == 4
    assert "0.0.0" not in text
    for var in ("PYTHON_VERSION", "PYTHON_MAJOR", "PYTHON_MINOR"):
        assert text.count(f"set {var}=unreadable") == 3
    label = text.index("\n:validate_selected")
    for part in (text[:label], text[label:]):
        assert part.index("NUM_OK") < part.index("LSS 3")
        assert "EQU 3" in part
    # Guards stay pipeless: pipe children do not inherit delayed expansion, so
    # an echo-pipe guard cannot read !VAR! values (see PR95 review).
    assert "| findstr" not in text


def test_broken_venv_repair_hint() -> None:
    """A `.venv` without an interpreter errors with a delete-and-rerun hint, never silent fallback."""
    sh = SH.read_text(encoding="utf-8")
    bat = BAT.read_text(encoding="utf-8")
    assert "rm -rf .venv" in sh
    assert "rmdir /s /q .venv" in bat


def test_launch_failure_exit_code() -> None:
    """A failed app launch exits nonzero instead of falling off with success."""
    sh = SH.read_text(encoding="utf-8")
    bat = BAT.read_text(encoding="utf-8")
    assert 'exit "$launch_status"' in sh
    assert bat.rindex("exit /b 1") > bat.index("failed to start")


def test_sh_syntax_check() -> None:
    """``bash -n run_gui.sh`` parses cleanly (Windows has no functional bash; covered on Linux CI)."""
    if os.name == "nt":
        pytest.skip("no functional bash on Windows")  # pragma: no cover - Windows-only branch
    if shutil.which("bash") is None:
        pytest.skip("bash unavailable")  # pragma: no cover - bash always present on Linux CI
    result = subprocess.run(["bash", "-n", str(SH)], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr


def test_launcher_parity() -> None:
    """Both launchers agree on the 3.11 floor, native-by-default, and skip-install exit 0."""
    bat = BAT.read_text(encoding="utf-8")
    sh = SH.read_text(encoding="utf-8")
    assert "3.11" in bat and "3.11" in sh
    assert "default is 2" in bat.lower() and "default is 2" in sh.lower()
    assert "exit /b 0" in bat
    assert re.search(r"rerun.*exit 0", sh, re.DOTALL | re.IGNORECASE) is not None
    # Install menus allow-list: only empty input takes the native default;
    # garbage choices are rejected, never silently installed.
    assert "Invalid install option" in sh and "Invalid install option" in bat
    assert '"${install_choice:-2}"' in sh
    # Delayed expansion: tainted set /p input must never be %-expanded into
    # parsed command text (quote/& injection); compare the literal value.
    assert 'if "%install_choice%"=="" set install_choice=2' not in bat
    assert 'if "!install_choice!"=="" set "install_choice=2"' in bat
    assert bat.count('!install_choice!') == 5
    # Same tainted-input class for the mode choice and env-var echoes: delayed
    # form everywhere a value meets parsed command text inside a block.
    assert '%choice%' not in bat and bat.count('!choice!') == 3
    assert '%VIRTUAL_ENV%' not in bat


WINDOWS_ONLY = pytest.mark.skipif(os.name != "nt", reason="requires cmd.exe")


def _run_launcher(cwd: Path, stdin_text: str | None) -> subprocess.CompletedProcess[str]:  # pragma: no cover
    """Run a copy of ``run_gui.bat`` with ``cwd`` as its working directory."""
    bat = cwd / "run_gui.bat"
    shutil.copyfile(BAT, bat)
    # Strip VIRTUAL_ENV: CI invokes pytest via `uv run`, which sets it, and an
    # active venv changes launcher routing (broken-.venv repair is skipped,
    # the create-venv prompt disappears and shifts every later stdin answer).
    # Tests must observe the no-venv flow deterministically on any runner.
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    return subprocess.run(
        ["cmd", "/d", "/c", str(bat)],
        cwd=cwd,
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def _stdin_survives_version_gate() -> bool:  # pragma: no cover
    """Whether ``for /f`` version parsing preserves redirected stdin for later prompts.

    Some shims (e.g. pyenv-win) drain stdin while their output is captured,
    which makes prompt-driven rows untestable in that environment.
    """
    if shutil.which("cmd") is None or shutil.which("python") is None:
        return False
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        probe = Path(tmp) / "probe.bat"
        probe.write_text(
            "@echo off\n"
            "for /f \"tokens=2 delims= \" %%v in ('python --version 2>&1') do set PV=%%v\n"
            "set /p ANS=Q:\n"
            'if "%ANS%"=="n" (echo PROBE-OK) else (echo PROBE-DRAINED)\n',
            encoding="ascii",
        )
        result = subprocess.run(
            ["cmd", "/d", "/c", "probe.bat"],
            cwd=tmp,
            input="n\n",
            capture_output=True,
            text=True,
            timeout=60,
        )
    return "PROBE-OK" in result.stdout


@WINDOWS_ONLY
def test_bat_exec_broken_venv_exit_code(tmp_path: Path) -> None:  # pragma: no cover
    """A `.venv` directory without an interpreter exits 1 with the repair hint."""
    (tmp_path / ".venv").mkdir()
    result = _run_launcher(tmp_path, None)
    assert result.returncode == 1
    assert "rmdir /s /q .venv" in result.stdout


@WINDOWS_ONLY
def test_bat_exec_malformed_version_exit_code(tmp_path: Path) -> None:  # pragma: no cover
    """An interpreter whose `--version` probe fails routes to the repair hint, not version parsing."""
    system_root = os.environ.get("SYSTEMROOT", r"C:\Windows")
    where_exe = Path(system_root) / "System32" / "where.exe"
    if not where_exe.is_file():
        pytest.skip("no where.exe to stand in as a failing interpreter")
    scripts = tmp_path / ".venv" / "Scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(where_exe, scripts / "python.exe")
    result = _run_launcher(tmp_path, None)
    assert result.returncode == 1
    assert ".venv interpreter failed to start" in result.stdout
    assert "rmdir /s /q .venv" in result.stdout


@WINDOWS_ONLY
def test_bat_exec_skip_install_exit_code(tmp_path: Path) -> None:  # pragma: no cover
    """Declining the venv and skipping install exits 0 with the rerun hint."""
    if not _stdin_survives_version_gate():
        pytest.skip("system python drains redirected stdin (e.g. pyenv shim)")
    check = subprocess.run(
        ["python", "-c", "import guiskindose"],
        capture_output=True,
        timeout=60,
    )
    if check.returncode == 0:
        pytest.skip("system python already has guiskindose installed")
    result = _run_launcher(tmp_path, "n\n3\n")
    assert result.returncode == 0
    assert "Then rerun run_gui.bat." in result.stdout
