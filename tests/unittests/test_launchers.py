"""Static regression tests for the GUI launchers (``run_gui.bat`` / ``run_gui.sh``).

The ``.bat`` launcher once shipped ``echo`` lines with unescaped parentheses
inside ``if (...)`` blocks, which made ``cmd.exe`` fail with
``. was unexpected at this time`` before reaching the mode prompt. Escaping
every text paren as ``^(`` / ``^)`` is harmless at top level (the caret is
consumed by the parser), so the convention -- and the test below -- is simple:
no ``echo`` text paren may appear unescaped, anywhere in the file.

These tests run on Linux CI (no ``cmd.exe`` needed); Windows manual smoke
remains the execution check per the launcher robustness plan.
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


def test_bat_version_guard_fail_closed() -> None:
    """Non-numeric ``--version`` output is rejected before any ``LSS``/``EQU`` comparison."""
    text = BAT.read_text(encoding="utf-8")
    assert text.count("Could not determine Python version") >= 2
    first_guard = text.index("NUM_OK")
    assert first_guard < text.index("LSS 3")


def test_sh_syntax_check() -> None:
    """``bash -n run_gui.sh`` parses cleanly (Windows has no functional bash; covered on Linux CI)."""
    if os.name == "nt":
        pytest.skip("no functional bash on Windows")
    if shutil.which("bash") is None:
        pytest.skip("bash unavailable")
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
