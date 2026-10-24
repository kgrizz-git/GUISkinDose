# Pytest 9.1 GUI log capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `tests/gui` pass on pytest 9.1.1, with expected `ERROR` logs kept distinct from unexpected ones, and replace the `pytest>=7.0,<9.1` cap with `pytest>=7.0,<10`.

**Architecture:** Pytest 9.1's `catching_logs` attaches the capture handler to every logger that already has `propagate=False` when a phase starts (pytest-dev/pytest#3697, `src/_pytest/logging.py` in pytest 9.1.1). NiceGUI's `user` fixture then fails the test if `caplog.get_records("call")` contains any `ERROR`. `configure_logging()` sets `guiskindose.propagate = False` for the rest of the process, so later GUI tests start seeing those records. The fix stays in the GUI test harness: override the `user` fixture under `tests/gui/` so it deletes allowlisted `ERROR` records from the call-phase list before the same check runs. Production logging does not change. A separate reproduction step finds the `tests/gui/test_run_state_roundtrip.py` hang with a 180-second limit; that hang is not fixed by editing `reconnect_timeout` again.

**Tech Stack:** Python 3.11+, pytest 9.0.3 (locked) then 9.1.1, NiceGUI 3.18 `user` fixture, uv.

## Global Constraints

- Package version stays `1.0.0`. This is a dev-dependency and test-harness change. Record it in `dev-docs/MAINTENANCE_LOG.md`, not as a user-facing changelog feature.
- Do not change `configure_logging()` or `logging.getLogger("guiskindose").propagate`. Unit tests already depend on that logger staying non-propagating once configured (`tests/unittests/test_gui_figures.py`, `tests/unittests/test_rotational_envelope_dose.py`).
- Do not merge [PR 181](https://github.com/kgrizz-git/GUISkinDose/pull/181). It also bumps Playwright and pytest-playwright, and its `gui-smoke` job has been inside pytest since 2026-10-22 09:24 ET. This plan bumps pytest only.
- The new cap is exactly `pytest>=7.0,<10`. Pytest 9.1 deprecations become errors in pytest 10 (`request.getfixturevalue()` during teardown, class-scoped fixture methods that are not `classmethod`, non-`Collection` parametrize values). Those stay out of this change.
- Allowlist entries are `(logger_name, code)` pairs. `code` is the first whitespace-separated token of the log message and must match `privacy._CODE_RE`: `^[A-Za-z][A-Za-z0-9_.:-]{0,63}$`. That is the operation code `safe_error_event` already logs, for example `TABULAR_LOAD failed (error_type=ValueError at guiskindose/gui/exam_loaders.py:10 in load)`. The allowlist stores `TABULAR_LOAD`, not the `error_type` or the `at` location. A sentence or an absolute path is not an allowlist entry. Do not change `safe_error_event` or `privacy.py`.
- Do not log, print, or commit raw identifiers, source filenames, or absolute paths. The reproduction report written under `tmp/` is gitignored.
- Ruff `C901` stays at or below 10 for every new function. Line length stays 120.
- GUI tests must keep passing on the locked pytest 9.0.3 as well as on 9.1.1.
- Do not add `pytest-timeout` or any other dependency for the reproduction. Use GNU `timeout` on Linux.

---

## File structure

- Create `tests/gui/expected_gui_errors.py` — allowlist and the in-place filter. No pytest fixture here, so the unit test can import it without the `user` fixture.
- Create `tests/unittests/test_expected_gui_errors.py` — filter behavior without NiceGUI.
- Create `tests/gui/test_user_fixture_expected_errors.py` — one GUI test that emits an allowlisted `ERROR` and must still pass.
- Modify `tests/gui/conftest.py` — override `user` for `tests/gui/` only.
- Modify `pyproject.toml` and `uv.lock` — cap and locked pytest 9.1.1, in the last task only.
- Modify `dev-docs/TO_DO.md` — remove the Pytest 9.1 item once the suite is green (last task).
- Modify `dev-docs/MAINTENANCE_LOG.md` — record the harness change (last task).

`tests/conftest.py` keeps `pytest_plugins` pointing at `nicegui.testing.user_plugin`. Tests outside `tests/gui/` keep that fixture unchanged.

## Why the filter has to edit `get_records("call")`

NiceGUI 3.18 `nicegui/testing/user_plugin.py` does this after `yield`:

```python
logs = [record for record in caplog.get_records("call") if record.levelname == "ERROR"]
if logs:
    pytest.fail("There were unexpected ERROR logs.", pytrace=False)
```

`LogCaptureFixture.get_records` returns the list stored on the item stash for that phase. At the start of the call phase pytest assigns `stash["call"] = handler.records` (the same list object). The teardown phase then calls `handler.reset()`, which replaces `handler.records` with a new empty list. The stash still holds the call-phase list. During fixture teardown, `caplog.handler.records` is therefore the teardown list, and `caplog.get_records("call")` is the call list. Deleting from `handler.records` does not change what NiceGUI reads. The filter must assign into the call list in place: `records[:] = [...]`.

An autouse fixture that does not depend on `user` is torn down after `user`, which is too late. Overriding `user` in `tests/gui/conftest.py` runs the filter in the same place NiceGUI does, before the check.

`catching_logs` only sees loggers that are already non-propagating when the phase starts. It does not see a logger that flips `propagate` to `False` mid-test. That is why the failure shows up on later tests, after any earlier test has called `configure_logging()` (directly, or through `dprint()`).

---

### Task 1: Reproduce pytest 9.1.1 without a multi-hour job

**Files:**
- Create: `tmp/pytest91-gui-report.txt` (gitignored; do not commit)
- Test: `tests/gui/`

**Interfaces:**
- Consumes: locked environment on pytest 9.0.3
- Produces: a `tmp/pytest91-gui-report.txt` whose `ERROR` lines are `logger<TAB>code_or_FREE_TEXT`, plus either `HUNG <nodeid>` or `FAIL <nodeid>` or `PASS`

- [x] **Step 1: Install pytest 9.1.1 beside the lock**

Run from the repository root. This throwaway environment must not replace `.venv`.

```bash
export PATH="$HOME/.local/bin:$PATH"
UV_PROJECT_ENVIRONMENT="$PWD/tmp/venv-pytest91" \
  uv sync --extra dev --extra gui --locked
UV_PROJECT_ENVIRONMENT="$PWD/tmp/venv-pytest91" \
  uv pip install "pytest==9.1.1"
"$PWD/tmp/venv-pytest91/bin/python" -c "import pytest; print(pytest.__version__)"
```

Expected: `9.1.1`

- [x] **Step 2: Run the probe with a hard stop**

Write `tmp/pytest91_gui_probe.py` (gitignored) with the script below, then run it. This probe prints one `ERROR_RECORD` line per call-phase `ERROR` when a test tears down, because NiceGUI's failure text does not include the record. Run it on Linux. GNU `timeout` is not the Windows reproduction; the confirming run is the Ubuntu `gui-smoke` job after Task 5.

```python
"""Print call-phase ERROR records for a pytest 9.1 GUI run. Do not commit."""

from __future__ import annotations

import faulthandler
import re
import signal
import sys

import pytest
from _pytest.logging import caplog_records_key

_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")


def _token(message: str) -> str:
    parts = message.split()
    if not parts or _CODE.fullmatch(parts[0]) is None:
        return "FREE_TEXT"
    if len(parts) == 1 or parts[1] == "failed":
        return parts[0]
    return "FREE_TEXT"


class _Inventory:
    def pytest_runtest_makereport(self, item, call):
        if call.when != "teardown" or caplog_records_key not in item.stash:
            return
        records = item.stash[caplog_records_key].get("call", [])
        for record in records:
            if record.levelname != "ERROR":
                continue
            line = f"ERROR_RECORD\t{item.nodeid}\t{record.name}\t{_token(record.getMessage())}"
            print(line, flush=True)


def main() -> int:
    faulthandler.register(signal.SIGTERM, all_threads=True)
    return int(pytest.main(
        ["tests/gui", "-p", "no:xdist", "-vv", "--tb=line", "--maxfail=20"],
        plugins=[_Inventory()],
    ))


if __name__ == "__main__":
    sys.exit(main())
```

```bash
mkdir -p tmp
PYTHONFAULTHANDLER=1 timeout --foreground --signal=TERM 180 \
  "$PWD/tmp/venv-pytest91/bin/python" tmp/pytest91_gui_probe.py \
  | tee tmp/pytest91-gui-report.txt
echo "timeout_or_pytest_exit=${PIPESTATUS[0]}"
```

Expected: exit 1 with one or more `ERROR_RECORD` lines, or exit 124 with a faulthandler stack and the last `tests/gui/...::test_...` line. Exit 0 means pytest 9.1.1 did not fail this suite. Stop. Do not continue to Task 4, and do not treat Task 2's synthetic code as the production inventory. Do not rerun without the 180-second limit. Do not wait for the PR 181 `gui-smoke` job.

- [x] **Step 3: Confirm 9.0.3 still passes the same file that failed or hung**

```bash
uv run --extra dev --extra gui --locked python -m pytest \
  tests/gui/test_run_state_roundtrip.py -p no:xdist -q --tb=line
```

Expected: pass. If this fails on 9.0.3, stop. The failure is not the 9.1 capture change.

- [x] **Step 4: Keep the report**

`tmp/pytest91-gui-report.txt` already contains the `ERROR_RECORD` lines from the probe. Do not edit a committed test to print them. Commit nothing from this task. The report and the probe stay in `tmp/`.

If the probe exited 0, this task is not done.

---

### Task 2: Filter allowlisted call-phase ERROR records

**Files:**
- Create: `tests/gui/expected_gui_errors.py`
- Create: `tests/unittests/test_expected_gui_errors.py`
- Test: `tests/unittests/test_expected_gui_errors.py`

**Interfaces:**
- Consumes: nothing from Task 1 yet. The allowlist constant starts with one synthetic code used by Task 3.
- Produces:
  - `ExpectedGuiError` frozen dataclass with `logger: str` and `code: str`
  - `ALLOWED_GUI_ERRORS: tuple[ExpectedGuiError, ...]`
  - `drop_allowed_gui_errors(records: list[logging.LogRecord]) -> list[logging.LogRecord]`
    Mutates `records` in place, removes `ERROR` records whose logger name equals an entry and whose message contains that entry's `code`, and returns the removed records.

- [x] **Step 1: Write the failing unit test**

`tests/` is not a package. Load the module by file path. Do not add `tests/__init__.py` or `tests/gui/__init__.py`.

Create `tests/unittests/test_expected_gui_errors.py`:

```python
"""Allowlisted GUI ERROR records are removed in place; everything else stays."""

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "gui" / "expected_gui_errors.py"
_SPEC = importlib.util.spec_from_file_location("expected_gui_errors", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
drop_allowed_gui_errors = _MODULE.drop_allowed_gui_errors
ALLOWED_GUI_ERRORS = _MODULE.ALLOWED_GUI_ERRORS
ExpectedGuiError = _MODULE.ExpectedGuiError


def _record(name: str, level: int, message: str) -> logging.LogRecord:
    return logging.LogRecord(name, level, __file__, 1, message, (), None)


def test_drop_removes_only_matching_error_codes() -> None:
    allowed = ExpectedGuiError("guiskindose.gui.helpers", "gui_test_expected_error")
    assert allowed in ALLOWED_GUI_ERRORS
    keep_warning = _record("guiskindose.gui.helpers", logging.WARNING, "gui_test_expected_error")
    keep_other = _record("guiskindose.gui.helpers", logging.ERROR, "unlisted_code")
    keep_other_logger = _record("guiskindose.gui.app", logging.ERROR, "gui_test_expected_error")
    drop_me = _record("guiskindose.gui.helpers", logging.ERROR, "gui_test_expected_error")
    shaped = _record(
        "guiskindose.gui.helpers",
        logging.ERROR,
        "gui_test_expected_error failed (error_type=ValueError at guiskindose/gui/helpers.py:1 in fn)",
    )
    records = [keep_warning, keep_other, keep_other_logger, drop_me, shaped]
    removed = drop_allowed_gui_errors(records)
    assert removed == [drop_me, shaped]
    assert records == [keep_warning, keep_other, keep_other_logger]


def test_allowlist_codes_match_the_privacy_code_pattern() -> None:
    code_re = __import__("re").compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")
    for entry in ALLOWED_GUI_ERRORS:
        assert code_re.fullmatch(entry.code)
        assert " " not in entry.code
        assert "/" not in entry.code
        assert "\\" not in entry.code
```

- [x] **Step 2: Run the test to verify it fails**

```bash
uv run --extra dev --extra gui --locked python -m pytest \
  tests/unittests/test_expected_gui_errors.py -q --tb=short
```

Expected: collection error or `ModuleNotFoundError` / `ImportError` because `tests/gui/expected_gui_errors.py` does not exist yet.

- [x] **Step 3: Write the filter**

Create `tests/gui/expected_gui_errors.py`:

```python
"""ERROR logs the GUI user fixture may see after pytest 9.1 captures non-propagating loggers.

Allowlist entries are stable message codes. A path or a sentence must be fixed at the
call site, not added here. ``drop_allowed_gui_errors`` edits the call-phase record list
in place because that is the list ``caplog.get_records('call')`` returns during teardown.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

# Same alphabet as guiskindose.privacy._CODE_RE. Duplicated so this test helper
# does not import privacy (and so a privacy-rule change fails this module's tests
# only when the two patterns are compared in test_expected_gui_errors.py).
_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,63}$")


@dataclass(frozen=True, slots=True)
class ExpectedGuiError:
    """One ERROR the GUI harness accepts: exact logger name plus an operation code."""

    logger: str
    code: str

    def __post_init__(self) -> None:
        if _CODE.fullmatch(self.code) is None:
            raise ValueError("gui_error_code_not_stable")


# Synthetic code emitted by tests/gui/test_user_fixture_expected_errors.py.
# Task 4 appends codes from tmp/pytest91-gui-report.txt. Do not put FREE_TEXT here.
ALLOWED_GUI_ERRORS: tuple[ExpectedGuiError, ...] = (
    ExpectedGuiError("guiskindose.gui.helpers", "gui_test_expected_error"),
)


def _operation_code(record: logging.LogRecord) -> str:
    """Return the first token, which ``safe_error_event`` uses as the operation code."""
    parts = record.getMessage().split()
    return parts[0] if parts else ""


def _matches(record: logging.LogRecord) -> bool:
    if record.levelno < logging.ERROR:
        return False
    code = _operation_code(record)
    return any(record.name == entry.logger and code == entry.code for entry in ALLOWED_GUI_ERRORS)


def drop_allowed_gui_errors(records: list[logging.LogRecord]) -> list[logging.LogRecord]:
    """Remove allowlisted ERROR records from ``records`` and return those removed."""
    removed = [record for record in records if _matches(record)]
    records[:] = [record for record in records if record not in removed]
    return removed
```

`record not in removed` is identity comparison for the list objects created above; that is what we want. Do not compare by message text.

- [x] **Step 4: Run the unit test to verify it passes**

```bash
uv run --extra dev --extra gui --locked python -m pytest \
  tests/unittests/test_expected_gui_errors.py -q --tb=short
```

Expected: `2 passed`.

- [x] **Step 5: Commit**

```bash
git add tests/gui/expected_gui_errors.py tests/unittests/test_expected_gui_errors.py
git commit -m "Add a GUI ERROR allowlist that edits the call-phase record list"
```

---

### Task 3: Override the GUI `user` fixture and prove an allowlisted ERROR still passes

**Files:**
- Modify: `tests/gui/conftest.py`
- Create: `tests/gui/test_user_fixture_expected_errors.py`
- Test: `tests/gui/test_user_fixture_expected_errors.py`

**Interfaces:**
- Consumes: `drop_allowed_gui_errors` from Task 2
- Produces: a `user` fixture in `tests/gui/conftest.py` that shadows `nicegui.testing.user_plugin.user` for tests under `tests/gui/` only

- [x] **Step 1: Write the one GUI test that fails on today's fixture**

Create `tests/gui/test_user_fixture_expected_errors.py` with this body and no other variant. The autouse fixture runs during setup, so the helper logger is already non-propagating when the call phase attaches handlers, on both pytest 9.0.3 and 9.1.1. Setting `propagate = False` inside the test body is too late: `catching_logs` does not see loggers that flip during the call. On the stock NiceGUI fixture this test fails. On the override it passes.

```python
"""An allowlisted ERROR must not fail NiceGUI's user fixture."""

from __future__ import annotations

import logging

import pytest

pytest.importorskip("nicegui")

pytestmark = pytest.mark.nicegui_main_file("tests/gui/nicegui_main.py")


@pytest.fixture(autouse=True)
def _nonpropagating_helper_logger():
    logger = logging.getLogger("guiskindose.gui.helpers")
    previous = logger.propagate
    logger.propagate = False
    if not any(isinstance(handler, logging.NullHandler) for handler in logger.handlers):
        logger.addHandler(logging.NullHandler())
    yield
    logger.propagate = previous


async def test_allowlisted_error_does_not_fail_the_user_fixture(user) -> None:
    await user.open("/")
    logging.getLogger("guiskindose.gui.helpers").error("gui_test_expected_error")
```

- [x] **Step 2: Run the test to verify it fails**

```bash
uv run --extra dev --extra gui --locked python -m pytest \
  tests/gui/test_user_fixture_expected_errors.py -p no:xdist -vv --tb=short
```

Expected: `FAILED` with `There were unexpected ERROR logs.`

- [x] **Step 3: Override `user` in `tests/gui/conftest.py`**

Add these imports immediately after `pytest.importorskip("nicegui")` in `tests/gui/conftest.py`. Putting them above that line would break collection when the GUI extra is absent. `pytest` is already imported. Pytest puts the repository root on `sys.path`, not `tests/gui/`, so load the helper by file path. Do not add `tests/gui/__init__.py`.

```python
import importlib.util
import logging
from pathlib import Path

from nicegui.testing.general_fixtures import get_path_to_main_file
from nicegui.testing.user_simulation import user_simulation

_ERRORS_PATH = Path(__file__).with_name("expected_gui_errors.py")
_ERRORS_SPEC = importlib.util.spec_from_file_location("expected_gui_errors", _ERRORS_PATH)
assert _ERRORS_SPEC is not None and _ERRORS_SPEC.loader is not None
_ERRORS = importlib.util.module_from_spec(_ERRORS_SPEC)
_ERRORS_SPEC.loader.exec_module(_ERRORS)
drop_allowed_gui_errors = _ERRORS.drop_allowed_gui_errors
```

Append this fixture at the end of the file. It must be named `user` so it shadows the plugin fixture:

```python
@pytest.fixture
async def user(caplog: pytest.LogCaptureFixture, request: pytest.FixtureRequest):
    """Same simulation as NiceGUI's fixture, after dropping allowlisted call-phase ERRORs.

    Shadows ``nicegui.testing.user_plugin.user`` for tests under ``tests/gui`` only.
    NiceGUI 3.18 checks ``caplog.get_records('call')`` inside the ``async with``,
    after ``yield`` and before ``user_simulation`` exits. The filter has to run
    in that same place. Logs emitted while the context exits are teardown-phase
    records and are not part of this check.
    """
    async with user_simulation(main_file=get_path_to_main_file(request)) as simulated:
        yield simulated
        call_records = caplog.get_records("call")
        drop_allowed_gui_errors(call_records)
        errors = [record for record in call_records if record.levelname == "ERROR"]
        if errors:
            pytest.fail("There were unexpected ERROR logs.", pytrace=False)
```

Leave the existing autouse fixtures in this file unchanged. They do not request `user`.

- [x] **Step 4: Run the test to verify it passes, and that an unlisted code still fails**

```bash
uv run --extra dev --extra gui --locked python -m pytest \
  tests/gui/test_user_fixture_expected_errors.py -p no:xdist -q --tb=short
```

Expected: pass.

Then temporarily change the test's message from `gui_test_expected_error` to `gui_test_unexpected_error`, rerun the same command, and confirm `There were unexpected ERROR logs.` Put the message back. Do not leave the unexpected string in the file.

- [x] **Step 5: Commit**

```bash
git add tests/gui/conftest.py tests/gui/test_user_fixture_expected_errors.py
git commit -m "Drop allowlisted GUI errors before NiceGUI checks the user fixture"
```

---

### Task 4: Classify the 9.1.1 report and fix the hang or the real errors

**Files:**
- Modify: `tests/gui/expected_gui_errors.py` (`ALLOWED_GUI_ERRORS` only, for code tokens)
- Modify: whichever call site Task 1 names for `FREE_TEXT` or for the hung stack
- Test: the node id from `tmp/pytest91-gui-report.txt`

**Interfaces:**
- Consumes: `tmp/pytest91-gui-report.txt` from Task 1, and `drop_allowed_gui_errors` from Task 2
- Produces: an allowlist of operation codes the 9.1.1 run actually emitted, and a GUI suite that finishes within 180 seconds on pytest 9.1.1

- [x] **Step 1: Split the report into three buckets**

From `ERROR_RECORD` lines in `tmp/pytest91-gui-report.txt`, make three lists in the PR description (not a new tracked file):

1. `code` — the fourth field is an operation code (`TABULAR_LOAD`, `gui_test_expected_error`), not `FREE_TEXT`. The logger is `guiskindose` or a `guiskindose.*` child.
2. `FREE_TEXT` — the fourth field is `FREE_TEXT`, or the logger is not under `guiskindose`.
3. `HUNG` — present only when the probe exit was 124. Record the node id that was running and the first faulthandler frame in `guiskindose` or `tests/`.

If bucket 3 is `tests/gui/test_run_state_roundtrip.py` and the stack is inside `reconnect_timeout` or `ui.timer` sleep only, do not change `src/guiskindose/gui/app.py` `reconnect_timeout=30.0`. That change was already tried and did not clear the failure.

A `nicegui` `ERROR` emitted while `user_simulation` exits is a teardown-phase record. NiceGUI's check reads the call phase only, so those lines do not fail the fixture. Do not allowlist the `nicegui` logger. If an `ERROR_RECORD` line names logger `nicegui`, it was emitted during the test body: find the project call that provoked it and fix that call. Do not edit NiceGUI.

- [x] **Step 2: Allowlist only bucket `code`**

For each `code` line, append `ExpectedGuiError(logger, code)` using the logger and the operation code from that line. The relative `at ...` location stays in the log message and stays out of the allowlist. Do not weaken `test_allowlist_codes_match_the_privacy_code_pattern`.

- [x] **Step 3: Fix `FREE_TEXT` without rewriting `safe_error_event`**

`safe_error_event` messages are bucket `code`, not `FREE_TEXT`. Their shape is `{CODE} failed (error_type={Class} at {relative_path}:{lineno} in {func})`. Leave `src/guiskindose/privacy.py` unchanged.

For a `FREE_TEXT` record whose logger is under `guiskindose`, change that call site to `safe_error_event` (or `safe_warning` when the event is not a failure). Then it becomes a `code` record: allowlist the operation code only if the test is deliberately exercising that failure. If the inputs are valid, stop emitting it.

For a `FREE_TEXT` record whose logger is `nicegui` or a third-party logger, change the project code that provoked it. If the stack does not enter this repository, stop and add a redacted note to this plan. Do not allowlist that logger.

Do not wrap the `user` fixture in `pytest.raises` and do not clear the whole call list.

- [x] **Step 4: Fix a hang from the stack, or stop**

If bucket `HUNG` is empty, skip this step.

If the top project frame is a `guiskindose` or `tests` function, change that function so the awaited simulation completes. The usual shape in this file is `await user.open("/")` or `await run_config_mod._do_load(...)`. A missing simulated JavaScript response must be answered in the test's `user.javascript_rules` entry, not by raising `reconnect_timeout`.

If the faulthandler stack has no frame in `guiskindose` or `tests`, stop and add the stack (paths redacted) to this plan under a new "Blocked" note. Do not guess a patch.

- [x] **Step 5: Rerun pytest 9.1.1 and the locked suite**

```bash
PYTHONFAULTHANDLER=1 timeout --foreground --signal=TERM 180 \
  "$PWD/tmp/venv-pytest91/bin/python" -m pytest tests/gui -p no:xdist -q --tb=line
uv run --extra dev --extra gui --locked python -m pytest tests/gui -p no:xdist -q --tb=line
uv run --extra dev --extra gui --locked python -m pytest --ignore=tests/gui -n auto -q --tb=line
```

Expected: the 9.1.1 command exits 0 in under 180 seconds. The two locked commands pass. `timeout` exit 124 means this task is not done.

- [x] **Step 6: Commit**

```bash
git add tests/gui/expected_gui_errors.py
# plus any call-site files this task edited
git commit -m "Accept known GUI error codes and fix the pytest 9.1 hang"
```

---

### Task 5: Scan pytest 9.1 deprecations, then move the cap to `<10`

**Files:**
- Modify: `pyproject.toml` (the `pytest>=7.0,<9.1` line and the comment above it)
- Modify: `uv.lock` (via `uv lock`)
- Modify: `dev-docs/TO_DO.md` (delete the Pytest 9.1 bullet)
- Modify: `dev-docs/MAINTENANCE_LOG.md`
- Modify: `dev-docs/plans/PYTEST_91_GUI_LOG_CAPTURE_PLAN.md` (check the task boxes that are done)
- Test: `tests/gui` and `tests/unittests/test_expected_gui_errors.py` on pytest 9.1.1

**Interfaces:**
- Consumes: a green Task 4 run
- Produces: locked pytest 9.1.1 and the requirement `pytest>=7.0,<10`

- [x] **Step 1: Search for the three pytest 10 removals**

```bash
rg -n "getfixturevalue\\(" tests src
rg -n "scope=.class.|scope = .class." tests
rg -n "pytest.mark.parametrize|metafunc.parametrize" tests src
```

For each `getfixturevalue` hit, confirm it is not called from a fixture teardown. For each class-scoped fixture written as an instance method, convert it to `@classmethod` or to a function fixture in this task. For parametrize values, confirm each `argvalues` argument is a list or tuple, not a generator. If a hit needs a behavior change beyond that, stop and add it to this plan. Do not ignore the warning.

- [x] **Step 2: Update the requirement**

In `pyproject.toml`, replace the comment and the pin:

```toml
    # pytest 9.1 captures logs from loggers with propagate=False
    # (pytest-dev/pytest#3697). tests/gui/conftest.py drops allowlisted
    # ERROR codes before NiceGUI's user fixture reads caplog. The upper
    # bound stays at 10 because that release turns 9.1 deprecations into errors.
    "pytest>=7.0,<10",
```

- [x] **Step 3: Lock pytest 9.1.1**

```bash
uv lock
uv run --extra dev --extra gui --locked python -c "import pytest; print(pytest.__version__)"
```

Expected: `9.1.1`. The `uv.lock` diff for pytest is the version, the sdist, and the wheel. If `uv lock` also upgrades unrelated packages, revert those hunks and run `uv lock` again only after confirming the pytest requirement is the sole `pyproject.toml` change. Do not upgrade Playwright in this lock update.

- [x] **Step 4: Run the suites on the lock**

```bash
uv run --extra dev --extra gui --locked python -m pytest tests/gui -p no:xdist -q --tb=line
uv run --extra dev --extra gui --locked python -m pytest --ignore=tests/gui -n auto -q --tb=line
```

Expected: both exit 0. `tests/gui` must finish well under 180 seconds. If `tests/gui` hangs, return to Task 4. Do not raise the timeout to hide it.

- [x] **Step 5: Docs**

Delete the Pytest 9.1 bullet from `dev-docs/TO_DO.md`. Add an Unreleased bullet to `dev-docs/MAINTENANCE_LOG.md` stating that pytest is locked at 9.1.1, the GUI `user` fixture drops allowlisted non-propagating `ERROR` codes, and `pytest>=7.0,<10` replaces `pytest>=7.0,<9.1`. Check off the boxes in this plan for the tasks that landed.

- [x] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock dev-docs/TO_DO.md dev-docs/MAINTENANCE_LOG.md \
  dev-docs/plans/PYTEST_91_GUI_LOG_CAPTURE_PLAN.md
git commit -m "Lock pytest 9.1.1 and cap the next major at 10"
```

After that commit, close PR 181 without merging it. A later Dependabot group may try to relax `<10`; review that separately.

---

## Self-review

- Spec coverage: capture behavior, distinct expected and unexpected errors, round-trip hang, cap removal, no Playwright bump, no production logging change, and pytest 10 staying out are each a task above.
- The allowlist starts with one synthetic code so Task 2 and Task 3 are testable before the reproduction inventory exists. Task 4 adds real operation codes from `ERROR_RECORD` lines only. `safe_error_event` messages match on their first token, so the relative location in the message is not an allowlist entry.
- The `user` override filters and fails inside the `async with`, after `yield`, which is where NiceGUI 3.18 reads `get_records("call")`.
- Task 1 exit 0 stops the effort. A green 9.1.1 run with no `ERROR_RECORD` lines is not an inventory.
- `drop_allowed_gui_errors` edits the list object `get_records("call")` returns. The plan does not delete from `caplog.handler.records`.
- Placeholder scan: Task 4 step 4 has an explicit stop when the stack is outside this repository. That is a stop, not an open implementation note.

## Review

Reviewed by Composer against NiceGUI 3.18 `user_plugin.py`, pytest 9.1.1 `catching_logs`, and `privacy.safe_error_event`. The plan was updated so the filter runs inside the `async with` after `yield`, allowlist codes use the same pattern as `privacy._CODE_RE` and match the first message token, and `safe_error_event` is not rewritten. Task 1 now fails closed when pytest 9.1.1 exits 0, and the probe prints `ERROR_RECORD` lines because NiceGUI's failure text does not include the records.

## Execution Handoff

Implementation is a separate change from the plan commit.
