"""Tests for the write-containment guard's value-safe path hints.

The guard's whole point is that its message is safe to appear in a public CI
log, so the assertions here are mostly about what must *not* be disclosed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from containment_hint import (
    CONTAINMENT_HINT_ENV,
    HINT_FULL,
    HINT_MASKED,
    HINT_TOKEN,
    MAX_REPORTED_CHANGES,
    change_report,
    collect_changes,
    describe_change,
    hint_footer,
    hint_mode,
    mask_name,
    masked_path,
    path_shape,
    path_token,
    running_in_ci,
    safe_suffix,
)


def _root_conftest(pytestconfig: pytest.Config) -> Any:
    """The repo-root ``tests/conftest.py`` module, via pytest's plugin manager.

    A bare ``import conftest`` resolves to ``tests/unittests/conftest.py``, and
    ``sys.modules`` keeps only one ``conftest`` key, so the root module is found
    among the registered conftest plugins instead.
    """
    target = Path(__file__).resolve().parents[1] / "conftest.py"
    for plugin in pytestconfig.pluginmanager.get_plugins():
        candidate = getattr(plugin, "__file__", None)
        if candidate and Path(candidate).resolve() == target:
            return plugin
    raise AssertionError("repo-root tests/conftest.py is not a registered plugin")


_SENSITIVE = Path("tmp/exports/Lastname_Firstname_19700101.xlsx")


class TestHintMode:
    """Mode selection fails closed: only exact known values change behaviour."""

    def test_unset_is_token(self) -> None:
        assert hint_mode({}) == HINT_TOKEN

    @pytest.mark.parametrize("raw", ["masked", "MASKED", "  masked  "])
    def test_masked_is_recognized_case_and_space_insensitively(self, raw: str) -> None:
        assert hint_mode({CONTAINMENT_HINT_ENV: raw}) == HINT_MASKED

    def test_full_is_recognized(self) -> None:
        assert hint_mode({CONTAINMENT_HINT_ENV: "full"}) == HINT_FULL

    @pytest.mark.parametrize("raw", ["fulll", "1", "true", "yes", "verbose", ""])
    def test_unrecognized_values_fail_closed_to_token(self, raw: str) -> None:
        """A typo must never escalate disclosure beyond what was asked for."""
        assert hint_mode({CONTAINMENT_HINT_ENV: raw}) == HINT_TOKEN


class TestPathToken:
    def test_is_stable_and_twelve_hex_characters(self) -> None:
        token = path_token(Path("tmp/nongui.log"))
        assert token == path_token(Path("tmp/nongui.log"))
        assert len(token) == 12
        assert all(char in "0123456789abcdef" for char in token)

    def test_differs_between_paths(self) -> None:
        assert path_token(Path("tmp/a.log")) != path_token(Path("tmp/b.log"))

    def test_matches_the_historical_token_for_a_known_path(self) -> None:
        """Pinned so tokens stay comparable across releases."""
        assert path_token(Path("tmp/nongui.log")) == "d9fe0e33a3f6"


class TestMaskName:
    @pytest.mark.parametrize(("name", "expected"), [("tmp", "t…p"), ("nongui", "n…i")])
    def test_keeps_only_first_and_last_character(self, name: str, expected: str) -> None:
        assert mask_name(name) == expected

    @pytest.mark.parametrize("name", ["a", "ab", "王", "JD"])
    def test_short_names_are_withheld_entirely(self, name: str) -> None:
        """An initial or a CJK surname is short *and* identifying.

        Echoing these (an earlier revision did) made masking the identity
        function for a path like ``tmp/J/D.dcm``.
        """
        assert mask_name(name) == "…"
        assert name not in mask_name(name)

    def test_empty_name_stays_empty(self) -> None:
        assert mask_name("") == ""


class TestMaskedPath:
    def test_masks_every_segment_and_keeps_the_suffix(self) -> None:
        assert masked_path(Path("tmp/nongui.log")) == "t…p/n…i.log"

    def test_withholds_the_middle_of_a_sensitive_stem(self) -> None:
        masked = masked_path(_SENSITIVE)
        assert masked == "t…p/e…s/L…1.xlsx"
        assert "Lastname" not in masked
        assert "Firstname" not in masked
        assert "19700101" not in masked

    def test_empty_path_is_empty(self) -> None:
        assert masked_path(Path()) == ""


class TestPathShape:
    def test_names_a_public_top_level_directory(self) -> None:
        shape = path_shape(Path("tmp/nongui.log"), tracked=False)
        assert shape == "new file in tmp/, depth 2, suffix .log"

    def test_distinguishes_a_modified_tracked_file(self) -> None:
        assert path_shape(Path("src/guiskindose/main.py"), tracked=True).startswith("modified tracked file in src/")

    def test_withholds_an_unlisted_top_level_directory(self) -> None:
        """A directory a test invented could have been named from data."""
        shape = path_shape(Path("Lastname_Firstname/report.pdf"), tracked=False)
        assert "<unlisted-top-level>" in shape
        assert "Lastname" not in shape

    def test_reports_repo_root_for_a_bare_filename(self) -> None:
        assert "<repo-root>" in path_shape(Path("stray.txt"), tracked=False)

    def test_reports_absent_suffix_explicitly(self) -> None:
        assert path_shape(Path("tmp/Makefile"), tracked=False).endswith("suffix <no-suffix>")


class TestDescribeChange:
    def test_token_mode_discloses_neither_names_nor_masked_names(self) -> None:
        line = describe_change(_SENSITIVE, tracked=False, mode=HINT_TOKEN)
        assert path_token(_SENSITIVE) in line
        assert "new file in tmp/" in line
        for leak in ("Lastname", "Firstname", "19700101", "masked=", "path="):
            assert leak not in line

    def test_masked_mode_adds_the_masked_path_only(self) -> None:
        line = describe_change(_SENSITIVE, tracked=False, mode=HINT_MASKED)
        assert "masked=t…p/e…s/L…1.xlsx" in line
        assert "Lastname" not in line
        assert "path=" not in line

    def test_full_mode_discloses_the_exact_relative_path(self) -> None:
        line = describe_change(_SENSITIVE, tracked=False, mode=HINT_FULL)
        assert f"path={_SENSITIVE.as_posix()}" in line

    def test_every_mode_keeps_the_token_for_cross_referencing(self) -> None:
        for mode in (HINT_TOKEN, HINT_MASKED, HINT_FULL):
            assert path_token(_SENSITIVE) in describe_change(_SENSITIVE, tracked=False, mode=mode)


class TestHintFooter:
    def test_token_mode_names_both_escalation_levels(self) -> None:
        footer = hint_footer(HINT_TOKEN)
        assert "masked" in footer
        assert "full" in footer

    @pytest.mark.parametrize("mode", [HINT_MASKED, HINT_FULL])
    def test_escalated_modes_warn_against_shared_logs(self, mode: str) -> None:
        assert CONTAINMENT_HINT_ENV in hint_footer(mode)


_ROOT = Path("/repo")


class TestCollectChanges:
    """Group index must survive: tracked-modified and new-file differ in cause."""

    def test_clean_snapshots_yield_nothing(self) -> None:
        snapshot = ({_ROOT / "src/a.py": "aaa"}, {})
        assert collect_changes(snapshot, snapshot) == []

    def test_new_untracked_file_is_reported_as_untracked(self) -> None:
        changed = collect_changes(({}, {}), ({}, {_ROOT / "tmp/stray.log": "d"}))
        assert changed == [(_ROOT / "tmp/stray.log", False)]

    def test_modified_tracked_file_is_reported_as_tracked(self) -> None:
        target = _ROOT / "src/a.py"
        changed = collect_changes(({target: "before"}, {}), ({target: "after"}, {}))
        assert changed == [(target, True)]

    def test_deleted_tracked_file_is_reported(self) -> None:
        target = _ROOT / "src/a.py"
        assert collect_changes(({target: "before"}, {}), ({}, {})) == [(target, True)]

    def test_unchanged_digest_is_not_reported(self) -> None:
        target = _ROOT / "src/a.py"
        assert collect_changes(({target: "same"}, {}), ({target: "same"}, {})) == []


class TestChangeReport:
    def test_clean_run_produces_no_report(self) -> None:
        assert change_report([], repo_root=_ROOT, mode=HINT_TOKEN) == []

    def test_reports_header_detail_and_footer(self) -> None:
        report = change_report([(_ROOT / "tmp/stray.log", False)], repo_root=_ROOT, mode=HINT_TOKEN)
        assert report[0].startswith("ERROR: tests changed the checkout")
        assert "new file in tmp/" in report[1]
        assert path_token(Path("tmp/stray.log")) in report[1]
        assert CONTAINMENT_HINT_ENV in report[-1]

    def test_labels_a_modified_tracked_file(self) -> None:
        report = change_report([(_ROOT / "src/guiskindose/main.py", True)], repo_root=_ROOT, mode=HINT_TOKEN)
        assert "modified tracked file in src/" in report[1]

    def test_caps_the_listing_and_states_the_remainder(self) -> None:
        changed = [(_ROOT / f"tmp/stray{index}.log", False) for index in range(MAX_REPORTED_CHANGES + 3)]
        report = change_report(changed, repo_root=_ROOT, mode=HINT_TOKEN)
        assert sum(1 for line in report if line.startswith("  - ")) == MAX_REPORTED_CHANGES
        assert "  ... and 3 more" in report

    def test_default_report_leaks_no_names(self) -> None:
        """The whole contract: safe to paste into a public CI log."""
        report = change_report([(_ROOT / _SENSITIVE, False)], repo_root=_ROOT, mode=HINT_TOKEN)
        body = "\n".join(report)
        for leak in ("Lastname", "Firstname", "19700101"):
            assert leak not in body

    def test_full_mode_reveals_the_path(self) -> None:
        report = change_report([(_ROOT / _SENSITIVE, False)], repo_root=_ROOT, mode=HINT_FULL)
        assert f"path={_SENSITIVE.as_posix()}" in "\n".join(report)

    def test_path_outside_the_repo_is_marked_not_fabricated(self) -> None:
        """A reporting helper must not raise, nor invent a repo-root location."""
        report = change_report([(Path("/elsewhere/odd.log"), False)], repo_root=_ROOT, mode=HINT_TOKEN)
        assert "<outside-repo>" in report[1]
        assert "<repo-root>" not in report[1]
        assert path_token(Path("odd.log")) in report[1]


class TestSuffixIsNotATrustedField:
    """``Path.suffix`` is "text after the last dot", not a vetted extension.

    A filename like ``x.Lastname_Firstname_19700101`` has a *suffix* carrying
    the whole identifier. Echoing it verbatim — which an earlier revision did,
    at the default disclosure level — defeated the entire guard.
    """

    _IDENTIFIER_SUFFIX = Path("tmp/x.Lastname_Firstname_19700101")
    _DOTTED_STEM = Path("tmp/..Lastname_Firstname")

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("tmp/nongui.log", ".log"),
            ("tmp/archive.tar.gz", ".gz"),
            ("tmp/scan.DCM", ".DCM"),
        ],
    )
    def test_extension_like_suffixes_are_kept(self, name: str, expected: str) -> None:
        assert safe_suffix(Path(name)) == expected

    @pytest.mark.parametrize(
        "name",
        [
            "tmp/x.Lastname_Firstname_19700101",
            "tmp/..Lastname_Firstname",
            "tmp/scan.verylongsuffix",
            "tmp/report.J",
            "tmp/scan.has_underscore",
            "tmp/scan.has-hyphen",
        ],
    )
    def test_non_extension_suffixes_are_withheld(self, name: str) -> None:
        assert safe_suffix(Path(name)) == ""

    def test_shape_withholds_an_identifier_bearing_suffix(self) -> None:
        shape = path_shape(self._IDENTIFIER_SUFFIX, tracked=False)
        assert "<unlisted-suffix>" in shape
        for leak in ("Lastname", "Firstname", "19700101"):
            assert leak not in shape

    def test_shape_still_distinguishes_absent_from_withheld(self) -> None:
        """ "No suffix at all" and "suffix withheld" are different facts."""
        assert "<no-suffix>" in path_shape(Path("tmp/Makefile"), tracked=False)
        assert "<unlisted-suffix>" in path_shape(self._DOTTED_STEM, tracked=False)

    def test_masking_covers_the_whole_name_when_the_suffix_is_unsafe(self) -> None:
        assert masked_path(self._IDENTIFIER_SUFFIX) == "t…p/x…1"
        assert masked_path(self._DOTTED_STEM) == "t…p/.…e"

    @pytest.mark.parametrize("mode", [HINT_TOKEN, HINT_MASKED])
    def test_no_disclosure_level_below_full_leaks_the_identifier(self, mode: str) -> None:
        line = describe_change(self._IDENTIFIER_SUFFIX, tracked=False, mode=mode)
        for leak in ("Lastname", "Firstname", "19700101"):
            assert leak not in line


class TestAwkwardNames:
    """Names that are easy to mishandle; none may raise or over-disclose."""

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("tmp/.DS_Store", "t…p/.…e"),
            ("tmp/Makefile", "t…p/M…e"),
            ("tmp/a.log", "t…p/….log"),
            ("tmp/ab.log", "t…p/….log"),
            ("a/b/c.log", "…/…/….log"),
        ],
    )
    def test_masked_forms(self, name: str, expected: str) -> None:
        assert masked_path(Path(name)) == expected

    def test_non_ascii_names_are_masked_not_mangled(self) -> None:
        assert masked_path(Path("tmp/Ünïcödé_Pátient.dcm")) == "t…p/Ü…t.dcm"

    def test_length_is_not_disclosed(self) -> None:
        """A single ellipsis stands for any number of withheld characters."""
        short = masked_path(Path("tmp/abc.log"))
        long = masked_path(Path(f"tmp/a{'b' * 200}c.log"))
        assert short == "t…p/a…c.log"
        assert short == long

    def test_deep_paths_report_depth_without_naming_segments(self) -> None:
        shape = path_shape(Path("tmp/a/b/c/d/e.log"), tracked=False)
        assert "depth 6" in shape


class TestSingleCharacterExtensionIsNotSafe:
    """`.J` is a first initial dressed as an extension.

    A shape pattern like ``\\.[A-Za-z0-9]{1,8}`` admits it, which is why the
    suffix rule is an allowlist rather than a pattern.
    """

    def test_default_shape_withholds_a_single_character_suffix(self) -> None:
        shape = path_shape(Path("tmp/report.J"), tracked=False)
        assert "<unlisted-suffix>" in shape
        assert ".J" not in shape

    def test_default_line_never_contains_the_initial_as_a_suffix(self) -> None:
        line = describe_change(Path("tmp/report.J"), tracked=False, mode=HINT_TOKEN)
        assert "suffix .J" not in line

    def test_allowlist_matching_is_case_insensitive(self) -> None:
        """Extension case is not identifying; a `.DCM` fixture is still a DICOM."""
        assert safe_suffix(Path("scan.DCM")) == ".DCM"
        assert safe_suffix(Path("scan.dcm")) == ".dcm"


class TestEscalatedLevelsAreRefusedInCi:
    """The footer advertises `masked`/`full` in a log CI may publish.

    Fail closed rather than trust that nobody pastes that advice into a workflow.
    """

    @pytest.mark.parametrize("mode", [HINT_MASKED, HINT_FULL])
    @pytest.mark.parametrize("ci_var", ["CI", "GITHUB_ACTIONS"])
    def test_ci_forces_token_mode(self, mode: str, ci_var: str) -> None:
        assert hint_mode({CONTAINMENT_HINT_ENV: mode, ci_var: "true"}) == HINT_TOKEN

    @pytest.mark.parametrize("mode", [HINT_MASKED, HINT_FULL])
    def test_local_environment_still_honours_the_request(self, mode: str) -> None:
        assert hint_mode({CONTAINMENT_HINT_ENV: mode}) == mode

    @pytest.mark.parametrize("falsy", ["", "0", "false", "no"])
    def test_a_falsy_ci_variable_is_not_ci(self, falsy: str) -> None:
        assert hint_mode({CONTAINMENT_HINT_ENV: HINT_FULL, "CI": falsy}) == HINT_FULL

    def test_running_in_ci_detects_either_variable(self) -> None:
        assert running_in_ci({"CI": "1"})
        assert running_in_ci({"GITHUB_ACTIONS": "true"})
        assert not running_in_ci({})


class TestControlCharactersCannotForgeOutput:
    """A filename may contain a newline or an ANSI escape.

    Unsanitized, the escalated levels would let it fabricate log lines or move
    the terminal cursor.
    """

    _NEWLINE = Path("tmp/abc\nERROR: fake line/x.log")
    _ANSI = Path("tmp/abc\x1b[31mred/y.log")

    @pytest.mark.parametrize("mode", [HINT_TOKEN, HINT_MASKED, HINT_FULL])
    @pytest.mark.parametrize("path", [_NEWLINE, _ANSI])
    def test_no_control_characters_survive_into_output(self, mode: str, path: Path) -> None:
        line = describe_change(path, tracked=False, mode=mode)
        assert "\n" not in line
        assert "\x1b" not in line
        assert not any(ord(char) < 0x20 for char in line)

    def test_forged_text_cannot_start_its_own_line(self) -> None:
        report = change_report([(_ROOT / self._NEWLINE, False)], repo_root=_ROOT, mode=HINT_FULL)
        assert all("\n" not in line for line in report)


class TestModeFallbackInConsumers:
    """`describe_change` must fail closed on a mode it does not know."""

    @pytest.mark.parametrize("mode", ["bogus", "", "FULL", "Masked"])
    def test_unknown_mode_behaves_as_token(self, mode: str) -> None:
        line = describe_change(_SENSITIVE, tracked=False, mode=mode)
        assert line == describe_change(_SENSITIVE, tracked=False, mode=HINT_TOKEN)
        assert "path=" not in line
        assert "masked=" not in line


class TestHintModeToleratesOddEnvironments:
    @pytest.mark.parametrize("raw", [None, 1, b"full", 0.5])
    def test_non_string_values_do_not_raise(self, raw: object) -> None:
        assert hint_mode({CONTAINMENT_HINT_ENV: raw}) == HINT_TOKEN  # type: ignore[dict-item]

    def test_real_environment_is_read_when_none_is_passed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.setenv(CONTAINMENT_HINT_ENV, "masked")
        assert hint_mode() == HINT_MASKED


class TestAllowlistDoesNotDrift:
    def test_public_top_level_never_names_an_unwalked_directory(self, pytestconfig: pytest.Config) -> None:
        """Allowlisting a directory the snapshot skips is dead weight.

        Caught a stale `dist` entry, which `_EXCLUDED_DIRS` means can never be
        reported.
        """
        from containment_hint import _PUBLIC_TOP_LEVEL

        excluded = _root_conftest(pytestconfig)._EXCLUDED_DIRS
        assert not (_PUBLIC_TOP_LEVEL & excluded)

    def test_public_top_level_entries_exist_or_are_known_scratch_roots(self, pytestconfig: pytest.Config) -> None:
        from containment_hint import _PUBLIC_TOP_LEVEL

        repo_root = _root_conftest(pytestconfig)._REPO_ROOT
        scratch_roots = {"PlotOutputs", "backups", "tmp", "wiki"}
        for name in _PUBLIC_TOP_LEVEL - scratch_roots:
            assert (repo_root / name).is_dir(), f"{name} is allowlisted but absent"


class TestCapBoundaries:
    def test_exactly_the_cap_adds_no_remainder_line(self) -> None:
        changed = [(_ROOT / f"tmp/s{index}.log", False) for index in range(MAX_REPORTED_CHANGES)]
        report = change_report(changed, repo_root=_ROOT, mode=HINT_TOKEN)
        assert sum(1 for line in report if line.startswith("  - ")) == MAX_REPORTED_CHANGES
        assert not any("more" in line for line in report)

    def test_zero_cap_lists_nothing_but_still_reports(self) -> None:
        changed = [(_ROOT / "tmp/s.log", False)]
        report = change_report(changed, repo_root=_ROOT, mode=HINT_TOKEN, max_reported=0)
        assert not any(line.startswith("  - ") for line in report)
        assert "  ... and 1 more" in report


class TestHookWiring:
    """The refactor's premise is "the hook stays a thin, correct adapter".

    Exercises ``pytest_sessionfinish`` itself, since the pure helpers above
    cannot catch a wiring mistake — a wrong group index, a silent reporter, or a
    lost exit status.
    """

    @staticmethod
    def _fake_session(before: object) -> tuple[Any, list[str]]:
        lines: list[str] = []

        class _Reporter:
            def write_line(self, line: str, **_: object) -> None:
                lines.append(line)

        class _PluginManager:
            @staticmethod
            def get_plugin(name: str) -> object | None:
                return _Reporter() if name == "terminalreporter" else None

        class _Config:
            _privacy_workspace_snapshot = before
            pluginmanager = _PluginManager()

        class _Session:
            config = _Config()
            exitstatus = 0

        return _Session(), lines

    def test_clean_run_is_left_alone(self, pytestconfig: pytest.Config, monkeypatch: pytest.MonkeyPatch) -> None:
        conftest = _root_conftest(pytestconfig)
        snapshot = ({Path("/repo/src/a.py"): "aaa"}, {})
        monkeypatch.setattr(conftest, "_workspace_snapshot", lambda: snapshot)
        session, lines = self._fake_session(snapshot)
        conftest.pytest_sessionfinish(session, 0)
        assert session.exitstatus == 0
        assert lines == []

    def test_new_file_fails_the_run_and_is_reported(
        self, pytestconfig: pytest.Config, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conftest = _root_conftest(pytestconfig)
        stray = conftest._REPO_ROOT / "tmp" / "stray.log"
        monkeypatch.setattr(conftest, "_workspace_snapshot", lambda: ({}, {stray: "digest"}))
        session, lines = self._fake_session(({}, {}))
        conftest.pytest_sessionfinish(session, 0)
        assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
        body = "\n".join(lines)
        assert "tests changed the checkout" in body
        assert "new file in tmp/" in body
        assert path_token(Path("tmp/stray.log")) in body
        assert CONTAINMENT_HINT_ENV in body

    def test_modified_tracked_file_is_labelled_tracked(
        self, pytestconfig: pytest.Config, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conftest = _root_conftest(pytestconfig)
        tracked = conftest._REPO_ROOT / "src" / "guiskindose" / "main.py"
        monkeypatch.setattr(conftest, "_workspace_snapshot", lambda: ({tracked: "after"}, {}))
        session, lines = self._fake_session(({tracked: "before"}, {}))
        conftest.pytest_sessionfinish(session, 0)
        assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
        assert "modified tracked file in src/" in "\n".join(lines)

    def test_absent_snapshot_is_a_no_op(self, pytestconfig: pytest.Config, monkeypatch: pytest.MonkeyPatch) -> None:
        """A snapshot that could not be taken must not fail every run."""
        conftest = _root_conftest(pytestconfig)

        def _explode() -> object:
            raise AssertionError("must not be called when there is no baseline")

        monkeypatch.setattr(conftest, "_workspace_snapshot", _explode)
        session, lines = self._fake_session(None)
        conftest.pytest_sessionfinish(session, 0)
        assert session.exitstatus == 0
        assert lines == []

    def test_unreadable_second_snapshot_still_fails_the_run(
        self, pytestconfig: pytest.Config, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        conftest = _root_conftest(pytestconfig)

        def _raise() -> object:
            raise OSError("snapshot unavailable")

        monkeypatch.setattr(conftest, "_workspace_snapshot", _raise)
        session, _ = self._fake_session(({}, {}))
        conftest.pytest_sessionfinish(session, 0)
        assert session.exitstatus == pytest.ExitCode.TESTS_FAILED
