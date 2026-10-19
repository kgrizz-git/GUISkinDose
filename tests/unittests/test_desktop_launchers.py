"""Unit tests for scripts/desktop_launchers.py. No real OS calls; roots live under tmp_path."""

from __future__ import annotations

import base64
import os
import subprocess
from pathlib import Path

import pytest

from scripts import desktop_launchers as dl

REPO = Path(__file__).resolve().parents[2]


class FakeRunner:
    """Record subprocess calls and return scripted results."""

    def __init__(self, returncode: int = 0, stdout: bytes = b"", on_call=None) -> None:
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.returncode = returncode
        self.stdout = stdout
        self.on_call = on_call

    def __call__(self, argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((argv, kwargs))
        if self.on_call is not None:
            self.on_call(argv, kwargs)
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, b"")


def _root(tmp_path: Path, name: str = "checkout") -> Path:
    root = tmp_path / name
    root.mkdir()
    (root / dl.COMMAND_NAME).write_text("#!/bin/bash\n", encoding="utf-8")
    return root


def test_unknown_platform_is_a_no_op(tmp_path: Path) -> None:
    runner = FakeRunner()
    assert dl.ensure(_root(tmp_path), "Plan9", {}, runner) == ""
    assert runner.calls == []


@pytest.mark.parametrize("system", ["Darwin", "Windows", "Linux"])
def test_opt_out_skips_everything(tmp_path: Path, system: str) -> None:
    runner = FakeRunner()
    root = _root(tmp_path)
    assert dl.ensure(root, system, {dl.OPT_OUT: "1"}, runner) == ""
    assert runner.calls == []
    assert not (root / dl.DESKTOP_NAME).exists()


# --- macOS -----------------------------------------------------------------


def test_macos_existing_icon_is_left_alone(tmp_path: Path) -> None:
    runner = FakeRunner(returncode=0)
    assert dl.ensure(_root(tmp_path), "Darwin", {}, runner) == ""
    assert [argv[0] for argv, _ in runner.calls] == ["xattr"]


def test_macos_sets_icon_with_paths_only_in_argv(tmp_path: Path) -> None:
    root = _root(tmp_path)

    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        if argv[0] == "xattr":
            return subprocess.CompletedProcess(argv, 1, b"", b"")
        return subprocess.CompletedProcess(argv, 0, b"ok\n", b"")

    calls: list[list[str]] = []
    status = dl.ensure(root, "Darwin", {}, lambda argv, **kw: calls.append(argv) or run(argv, **kw))
    assert status == "Launcher icon set."
    osascript = calls[1]
    assert osascript[:5] == ["osascript", "-l", "JavaScript", "-e", dl._MACOS_SET_ICON]
    assert str(root) not in dl._MACOS_SET_ICON
    assert osascript[5:] == [str(dl.icon_path(root, ".ico")), str(root / dl.COMMAND_NAME)]


@pytest.mark.parametrize("stdout", [b"no-image\n", b"failed\n"])
def test_macos_failure_reports_not_applied(tmp_path: Path, stdout: bytes) -> None:
    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(argv, 1 if argv[0] == "xattr" else 0, stdout, b"")

    assert dl.ensure(_root(tmp_path), "Darwin", {}, run) == "Launcher icon not applied."


def test_macos_script_guards_nil_image() -> None:
    script = dl._MACOS_SET_ICON
    assert script.index("isNil()") < script.index("setIconForFileOptions")


# --- Windows ---------------------------------------------------------------


def _writes_lnk(argv: list[str], kwargs: dict[str, object]) -> None:
    env = kwargs["env"]
    assert isinstance(env, dict)
    Path(env["GSD_LNK"]).write_bytes(env["GSD_ROOT"].encode("utf-16-le"))


def test_windows_argv_is_constant_and_paths_are_env_only(tmp_path: Path) -> None:
    # Quotes are not valid in Windows file names; $, ' and spaces are.
    roots = [_root(tmp_path, "a"), _root(tmp_path, "b c$'")]
    argvs = []
    for root in roots:
        runner = FakeRunner(on_call=_writes_lnk)
        status = dl.ensure(root, "Windows", {"SystemRoot": r"C:\Windows", "PATH": "x"}, runner)
        assert status == "Launcher shortcut created: GUISkinDose.lnk"
        argv, kwargs = runner.calls[0]
        argvs.append(argv)
        env = kwargs["env"]
        assert isinstance(env, dict)
        assert env["SystemRoot"] == r"C:\Windows"
        assert env["GSD_TARGET"] == str(root / "run_gui.bat")
        assert env["GSD_ICON"] == str(dl.icon_path(root, ".ico"))
        assert kwargs["cwd"] == str(root)
        assert all(str(root) not in part for part in argv)
    assert argvs[0] == argvs[1]
    assert "-ExecutionPolicy" not in argvs[0]
    script = base64.b64decode(argvs[0][-1]).decode("utf-16-le")
    assert "$env:GSD_LNK" in script


def test_windows_current_shortcut_skips_powershell(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / dl.LNK_NAME).write_bytes(b"\x00" + str(root).encode("utf-16-le") + b"\x00")
    runner = FakeRunner()
    assert dl.ensure(root, "Windows", {}, runner) == ""
    assert runner.calls == []


def test_windows_shortcut_from_moved_checkout_is_rewritten(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / dl.LNK_NAME).write_bytes("C:\\old\\checkout".encode("utf-16-le"))
    runner = FakeRunner(on_call=_writes_lnk)
    assert dl.ensure(root, "Windows", {}, runner) == "Launcher shortcut updated."
    assert len(runner.calls) == 1
    assert dl.shortcut_names_root(root / dl.LNK_NAME, root)


def test_windows_blocked_com_reports_not_created(tmp_path: Path) -> None:
    assert dl.ensure(_root(tmp_path), "Windows", {}, FakeRunner(returncode=1)) == "Launcher shortcut not created."


# --- Linux (POSIX paths, modes, and symlinks) --------------------------------

POSIX_ONLY = pytest.mark.skipif(os.name == "nt", reason="Linux .desktop entries use POSIX paths and modes")


@POSIX_ONLY
def test_linux_renders_exact_entry_for_space_and_non_ascii(tmp_path: Path) -> None:
    root = _root(tmp_path, "My Dose Ångström")
    runner = FakeRunner()
    assert dl.ensure(root, "Linux", {}, runner) == "Launcher shortcut created: GUISkinDose.desktop"
    text = (root / dl.DESKTOP_NAME).read_text(encoding="utf-8")
    assert f'Exec="{root}/run_gui.sh"\n' in text
    assert f"Path={root}\n" in text
    assert f"Icon={root}/src/guiskindose/gui/static/guiskindose_icon.svg\n" in text
    assert (root / dl.DESKTOP_NAME).stat().st_mode & 0o777 == 0o755
    assert runner.calls[0][0][:2] == ["gio", "set"]
    assert not (root / f".{dl.DESKTOP_NAME}.tmp").exists()


@POSIX_ONLY
def test_linux_second_run_writes_nothing(tmp_path: Path) -> None:
    root = _root(tmp_path)
    dl.ensure(root, "Linux", {}, FakeRunner())
    runner = FakeRunner()
    assert dl.ensure(root, "Linux", {}, runner) == ""
    assert runner.calls == []


@POSIX_ONLY
def test_linux_lost_executable_bit_is_repaired_quietly(tmp_path: Path) -> None:
    root = _root(tmp_path)
    dl.ensure(root, "Linux", {}, FakeRunner())
    (root / dl.DESKTOP_NAME).chmod(0o644)
    runner = FakeRunner()
    assert dl.ensure(root, "Linux", {}, runner) == ""
    assert (root / dl.DESKTOP_NAME).stat().st_mode & 0o777 == 0o755
    assert runner.calls[0][0][:2] == ["gio", "set"]


@POSIX_ONLY
def test_linux_moved_checkout_rewrites_entry(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / dl.DESKTOP_NAME).write_text("[Desktop Entry]\nExec=/old/run_gui.sh\n", encoding="utf-8")
    assert dl.ensure(root, "Linux", {}, FakeRunner()).startswith("Launcher shortcut created")
    assert str(root) in (root / dl.DESKTOP_NAME).read_text(encoding="utf-8")


@POSIX_ONLY
@pytest.mark.parametrize("name", ["a%b", 'a"b', "a$b", "a\\b", "a`b", "a\nb", "a;b"])
def test_linux_unsafe_root_is_rejected(name: str) -> None:
    assert not dl.desktop_path_is_safe(Path("/srv") / name)


@POSIX_ONLY
def test_linux_unsafe_root_is_skipped_without_writing(tmp_path: Path) -> None:
    root = _root(tmp_path, "a%b")
    status = dl.ensure(root, "Linux", {}, FakeRunner())
    assert status.startswith("Launcher shortcut skipped")
    assert str(root) not in status
    assert not (root / dl.DESKTOP_NAME).exists()


@POSIX_ONLY
def test_linux_symlink_target_is_not_followed(tmp_path: Path) -> None:
    root = _root(tmp_path)
    elsewhere = tmp_path / "elsewhere.txt"
    elsewhere.write_text("keep", encoding="utf-8")
    (root / dl.DESKTOP_NAME).symlink_to(elsewhere)
    assert dl.ensure(root, "Linux", {}, FakeRunner()) == "Launcher shortcut skipped."
    assert elsewhere.read_text(encoding="utf-8") == "keep"


def test_linux_wsl_is_skipped(tmp_path: Path) -> None:
    root = _root(tmp_path)
    assert dl.ensure(root, "Linux", {"WSL_DISTRO_NAME": "Ubuntu"}, FakeRunner()) == ""
    assert not (root / dl.DESKTOP_NAME).exists()


# --- Failure handling ------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        OSError("synthetic error text"),
        UnicodeEncodeError("utf-8", "x", 0, 1, "bad"),
        subprocess.TimeoutExpired("x", 10),
    ],
)
def test_errors_never_raise_or_leak_paths(tmp_path: Path, error: Exception) -> None:
    def run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise error

    status = dl.ensure(_root(tmp_path), "Darwin", {}, run)
    assert status == "Launcher setup skipped."


def test_main_always_exits_zero(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(dl, "ensure", lambda: "Launcher icon set.")
    assert dl.main(["ensure"]) == 0
    assert capsys.readouterr().out == "Launcher icon set.\n"


def test_command_launcher_is_executable_in_git() -> None:
    result = subprocess.run(
        ["git", "ls-files", "-s", dl.COMMAND_NAME], cwd=REPO, capture_output=True, text=True, timeout=30, check=False
    )
    if not result.stdout:
        pytest.skip("not a git checkout")
    assert result.stdout.startswith("100755 ")
