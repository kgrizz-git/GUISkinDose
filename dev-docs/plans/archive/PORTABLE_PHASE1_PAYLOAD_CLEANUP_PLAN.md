# Phase 1 portable payload cleanup

_Status: complete (2026-11-05). Implementation plan for the open Phase 1 payload items in
[../PORTABLE_APP_PLAN.md](../PORTABLE_APP_PLAN.md)._
_Parent checklist: Phase 1 lines for the pywebview pin, the `_reduced_1000t` payload,
the packaging note, the Light/Full build proofs, and the first one-shot `--png-check` timing._
_Branch: `portable/phase1-payload-cleanup`._

This slice closes five open Phase 1 items. macOS and Linux CI builds, signing, the
choreographer wrapper, and clean-VM or manual checks stay in the parent plan.

Do the chunks in order. Each chunk lists the files, the edit, the tests, and the
commands. Leave `dev-docs/TO_DO.md` until chunk 4. The portable-app items already
point at the parent plan.

SemVer: no version bump. The package stays `1.1.1` in `pyproject.toml`. The extra
floor is a patch-level requirement change and belongs under `[Unreleased]` in
`CHANGELOG.md`. Tests, CI assertions, and doc edits belong in
`dev-docs/MAINTENANCE_LOG.md`.

## Chunk 1 — Pin `pywebview>=6.1` on the published extra

The freeze group is already pinned. The published extra is not.

Evidence:

- `pyproject.toml` line 40: the `gui-native` extra lists `"pywebview"` with no floor.
- `pyproject.toml` lines 275–278: the `portable` dependency group already requires
  `pywebview>=6.1` (and `pyinstaller>=6.15`).
- `uv.lock` line 1345: `requires-dist` records `{ name = "pywebview", marker = "extra == 'gui-native'" }`
  with no specifier.
- `uv.lock` lines 1366–1368: the `portable` group already has `specifier = ">=6.1"`.
- `uv.lock` lines 3910–3911: the locked package is `pywebview` `6.2.1`.
- `tests/gui/test_webview2_check.py` lines 260–261 already describe the floor as
  `pywebview>=6.1`. That sentence matches the group and the intended extra. It does
  not match line 40 today.

The two include lists are already one list per edition. Do not add another.

- `src/guiskindose/edition.py` lines 68–77: `light_phantom_stl_names()` is the Light
  list (7 bases × both poses × full STL and `_reduced_3000t`, 28 names).
  `full_phantom_stl_names()` drops every name ending in `_reduced_1000t.stl`.
- `src/guiskindose/edition.py` lines 80–95: `edition_phantom_stl_names()` is the only
  dispatcher. An unknown edition or a missing Light file raises `ValueError`.
- `packaging/portable/guiskindose.spec` lines 100–105 and 130–140: the spec loads
  `edition.py` and builds `_PACKAGE_DATA` from `edition_phantom_stl_names`. The
  phantom globs are that list plus the shared package data. There is no second STL
  list in `.github/workflows/portable-spike.yml`.
- The wheel tree is 138 `phantom_data/*.stl` files: 46 full, 46 `_reduced_3000t`,
  and 46 `_reduced_1000t`. Full therefore freezes 92 STLs. That matches the parent
  plan's Full count.

### Files

- `pyproject.toml`
- `uv.lock` (only through the command below)
- `tests/unittests/test_pywebview_floor.py` (new)
- `CHANGELOG.md`
- `dev-docs/MAINTENANCE_LOG.md` (Unreleased bullet for the extra floor; chunk 4 extends the same bullet when the chunks share a PR)
- `dev-docs/plans/PORTABLE_APP_PLAN.md` (the one Phase 1 checkbox at line 302)

### Edits

In `pyproject.toml` line 40, change the `gui-native` entry from `"pywebview"` to
`"pywebview>=6.1"`. Leave the `portable` group as it is.

Re-lock with a plain lock, so unrelated packages stay put:

```bash
uv lock
```

Do not pass `--upgrade`. Do not run `uv sync`. After the lock, the `gui-native`
`requires-dist` entry gains `specifier = ">=6.1"`. The `[[package]]` block for
`pywebview` stays on `6.2.1` with the same wheel URL. The `portable` group entry
already has the specifier. If `uv lock` changes any other package version, stop
and restore `uv.lock`. The only `pyproject.toml` change is that one string, so
the resolver has no cause to upgrade.

Add `tests/unittests/test_pywebview_floor.py`:

```python
"""The native extra and the freeze group both require pywebview 6.1 or newer."""

from __future__ import annotations

import tomllib
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]


def test_pywebview_floor_is_at_least_6_1() -> None:
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    gui_native = data["project"]["optional-dependencies"]["gui-native"]
    portable = data["dependency-groups"]["portable"]
    assert "pywebview>=6.1" in gui_native
    assert "pywebview>=6.1" in portable
```

Under `CHANGELOG.md` `[Unreleased]` / `### Changed`, add one bullet: installing
the `gui-native` extra requires `pywebview>=6.1`. The lock already resolves
6.2.1. The `portable` group already had the same floor.

Under `dev-docs/MAINTENANCE_LOG.md` `[Unreleased]`, add one bullet for the same
floor and for `tests/unittests/test_pywebview_floor.py`. Chunk 4 appends the
preview, packaging-note, and PNG-gate sentences to that bullet when this is one
PR.

In `PORTABLE_APP_PLAN.md` line 302, mark the checkbox done. Keep both facts in
the sentence: the extra now requires `pywebview>=6.1`, and Light and Full each
already take their STL list from `edition.py` through `guiskindose.spec`.

### Verify

```bash
uv run --extra dev --extra gui --locked python -m pytest tests/unittests/test_pywebview_floor.py -q
uv run --extra dev --extra gui --locked python scripts/check_changelog.py
```

## Chunk 2 — Prove previews resolve to `_reduced_3000t`

Both app payloads already omit `_reduced_1000t`. The preview helper already
prefers `_reduced_3000t`. What is missing is a test on a tree that has the 3000t
file and lacks the 1000t file, plus the same fact in `--self-check` and in
`portable-spike.yml`.

Evidence of the current behavior:

- `src/guiskindose/edition.py` lines 10–11 and 37–38: neither edition ships
  `_reduced_1000t`. Light's suffixes are `""` and `_reduced_3000t`.
- `src/guiskindose/phantom_mesh_names.py` lines 45–48 and 265–287:
  `prefer_reduced_preview_stem` tries `_reduced_3000t`, then `_reduced_1000t`,
  then the full stem.
- `src/guiskindose/gui/helpers.py` lines 571–577: `get_human_mesh_names()` lists
  full stems only. Any stem containing `_reduced_` is skipped. The selector
  therefore never offers a preview file.
  `tests/unittests/test_phantom_library_integration.py` lines 94–95 already
  assert that. Do not add another discovery test.
- `src/guiskindose/gui/phantom_preview.py` lines 120–128: the Settings preview
  calls `prefer_reduced_preview_stem` through `resolve_preview_mesh`.
- `src/guiskindose/plotting/create_geometry_plot.py` lines 49–50: `plot_procedure`
  on a human phantom uses the same helper. Other plot modes keep the full stem.
- `src/guiskindose/calculate_dose/calculate_dose.py` lines 207–211 and
  `src/guiskindose/phantom_class.py` lines 227–231: dose loading passes
  `settings.phantom.human_mesh` to `resolve_human_mesh_stl_path`. That path is
  the full STL. Dose does not call `prefer_reduced_preview_stem`.
- `tests/unittests/test_gui_phantom_preview.py` lines 58–60: the existing
  preference test uses the real `phantom_data/` tree, which still contains both
  preview files (46 of each). It does not prove the app payload, where the 1000t
  file is absent.
- `packaging/portable/selfcheck.py` lines 243–261: the frozen check counts
  `_reduced_1000t.stl` and fails when that count is non-zero. It loads
  `adult_male` and expects `senior_male` to be `not_installed` on Light and
  `loads` on Full. It never asks which preview stem resolves.
- `.github/workflows/portable-spike.yml` lines 221–222: the job gates
  `reduced_1000t_stl` and `starter_mesh_loads`. It has no preview-stem gate.

`adult_male` is in `LIGHT_BASE_MESHES` (`edition.py` lines 27–35), so both
editions ship `adult_male.stl` and `adult_male_reduced_3000t.stl`.

### Files

- `packaging/portable/selfcheck.py`
- `.github/workflows/portable-spike.yml`
- `tests/unittests/test_human_mesh_path_safety.py`
- `tests/unittests/test_gui_phantom_preview.py`
- `tests/unittests/test_portable_selfcheck.py` (new)
- `dev-docs/plans/PORTABLE_APP_PLAN.md` (checkbox at line 310)
- `dev-docs/MAINTENANCE_LOG.md` (one Unreleased bullet, with chunk 4 if that is
  the same PR; otherwise add it here)

### Edits

Add `_require_preview_stem(stem: str) -> None` in `selfcheck.py`. It raises
`ValueError("edition_phantom_payload_wrong")` when `stem` is anything other
than `adult_male_reduced_3000t`. In `_check_edition` (lines 228–262), import
`prefer_reduced_preview_stem` beside the existing `phantom_mesh_names` import,
set `found["preview_stem"]` to `prefer_reduced_preview_stem("adult_male")`, and
call `_require_preview_stem` on that value. The unfrozen self-check runs the
same function on the source tree. Both preview files exist there, and the
helper still returns the 3000t stem first, so the unfrozen job keeps passing.

`packaging/` is outside the CI lint paths. `ruff check` in CI is `ruff check src tests`
(`.github/workflows/ci.yml`). `scripts/check_complexity.py` scans only `src` and
`scripts` (`scripts/complexity_caps_helpers.py`, `SCAN_DIRS`). basedpyright's
`include` is those trees plus `tests` (`pyproject.toml` under
`[tool.basedpyright]`). The project Ruff `select` list also omits `C901`. Keep
the helper split anyway. After editing `selfcheck.py`, run Ruff on that file
by hand (see Verify). Do not treat `scripts/check_complexity.py` as a result
for this path.

In `portable-spike.yml`, immediately after the `reduced_1000t_stl` throw
(line 221), add:

```powershell
if ($ed.preview_stem -ne 'adult_male_reduced_3000t') { throw "preview did not resolve to adult_male_reduced_3000t" }
```

Both matrix legs run this step.

Add `test_preview_uses_3000t_when_1000t_is_absent` to
`tests/unittests/test_human_mesh_path_safety.py`. Build a temp directory with
two empty files, `adult_male.stl` and `adult_male_reduced_3000t.stl`, and no
1000t file. Assert:

- `prefer_reduced_preview_stem("adult_male", phantom_data_dir=tmp)` equals
  `adult_male_reduced_3000t`
- `resolve_human_mesh_stl_path("adult_male", phantom_data_dir=tmp).name` equals
  `adult_male.stl`

The second assertion is the dose path: the full stem still resolves to the full
file when the 3000t companion sits beside it.

Add `test_resolve_preview_mesh_uses_3000t_when_1000t_is_absent` to
`tests/unittests/test_gui_phantom_preview.py`. Follow the object-form
`monkeypatch.setattr(phantom_preview_mod, "_PHANTOM_DATA_DIR", tmp_path)`
pattern at lines 62–75 of that file. Use the same two filenames. Assert
`resolve_preview_mesh("adult_male") == "adult_male_reduced_3000t"`.

Leave the 1000t fallback in `prefer_reduced_preview_stem`. The pip wheel still
ships those files (`edition.py` lines 10–11).

Add `tests/unittests/test_portable_selfcheck.py`. Load `selfcheck` the way
`tests/unittests/test_portable_pngcheck.py` lines 15–24 load `pngcheck`: insert
`packaging/portable` on `sys.path`, then `importlib.import_module("selfcheck")`.
Call `_require_preview_stem("adult_male_reduced_3000t")` and expect no raise.
Call it with `adult_male` and with `adult_male_reduced_1000t` and expect
`ValueError` matching `edition_phantom_payload_wrong`. That is the test for the
new self-check behavior. The phantom-dir tests above cover the resolver.

Mark parent-plan line 310 done. State that both payloads omit the 1000t files,
and that `--self-check` now requires the `adult_male` preview stem
`adult_male_reduced_3000t`.

### Verify

```bash
uv run --extra dev --extra gui --locked python -m pytest \
  tests/unittests/test_human_mesh_path_safety.py \
  tests/unittests/test_gui_phantom_preview.py \
  tests/unittests/test_portable_selfcheck.py \
  tests/unittests/test_edition.py -q
uv run --extra dev --extra gui --locked ruff check packaging/portable/selfcheck.py
uv run --extra dev --extra gui --locked ruff check --select C901 packaging/portable/selfcheck.py
```

`scripts/check_complexity.py` does not see `packaging/`. The two `ruff` commands
are the check for this file.

The Windows freeze job is the runtime proof. It runs on this branch because
`portable-spike.yml` lines 15–16 trigger on `portable/**`. Do not push in order
to run it.

## Chunk 3 — Refresh the packaging research note

`dev-docs/references/PORTABLE_EXECUTABLE_PACKAGING.md` still describes a future
spike. The parent plan calls that out at line 315. Replace the stale claims
with the freeze that exists. Keep the Java non-goal (lines 49–57).

### Files

- `dev-docs/references/PORTABLE_EXECUTABLE_PACKAGING.md`
- `dev-docs/plans/PORTABLE_APP_PLAN.md` (checkbox at line 315)
- `dev-docs/MAINTENANCE_LOG.md` (the same Unreleased bullet as chunk 2, or a
  second bullet if the chunks land separately)

### What each stale claim becomes

| Current claim | Where | Replacement |
|---|---|---|
| Status "not started"; "no frozen-app or installer pipeline" | lines 1–3 and 12–13 | A Windows PyInstaller onedir exists. The spec is `packaging/portable/guiskindose.spec`. The workflow is `.github/workflows/portable-spike.yml`. There is still no installer. macOS and Linux release zips remain open in the parent plan. |
| Backlog "(not started)" | line 6 | The Active Work item is in progress. Point it at `plans/PORTABLE_APP_PLAN.md`. |
| Freeze the CLI entry `python -m guiskindose --mode gui` / `run_gui` | lines 33–34 | The frozen program is `packaging/portable/entry.py`. It is outside the wheel, so `guiskindose.__main__:cli` stays the console script (`entry.py` lines 1–5). Windows and macOS call `run_gui(native=True)`. Linux v1 calls `run_gui(native=False)` (`entry.py` lines 154–156 for `_native_window`, and line 191 for the `run_gui` call). |
| Bundle every STL, including reduced previews, and ship `corrections.db` | lines 36–37 | Phantom files come from `edition.py`: Light is the 28-file starter set; Full is every clinical STL except `_reduced_1000t` (92 files). Ship `table_data/*.csv` (the spec lists them at lines 141–142). `resolve_corrections_source` (`src/guiskindose/correction_data.py` lines 192–215) only classifies the setting. The default (empty or the exact string `corrections.db`) returns `("packaged", None)`. It does not open a database file. Later readers use the packaged CSV tables. The spec does not list `corrections.db`. The parent plan says the same at lines 39 and 132. |
| Smoke HTML and PNG on each OS | line 45 | Windows Full smokes offline PNG with `GUISkinDose.exe --png-check` (`portable-spike.yml` lines 242–268). Light proves PNG never starts: `to_image` call count stays 0 (`selfcheck.py` lines 200–225, workflow lines 223–227). Frozen macOS and Linux Full fail PNG closed until the choreographer wrapper (`PORTABLE_APP_PLAN.md` line 304). Do not write a per-OS PNG smoke for those builds. |
| "Preconditions before implementation" | lines 59–66 | The Windows spike and the package-data proof are done (`--self-check` opens data through `importlib.resources`). Replace the `corrections.db` failure mode with the classification above: a default path is packaged data, and a file of that name in the working directory is ignored. Leave per-OS release smoke as still open. Drop the "spike PR" item that asks for a first freeze. |

Also update the summary and the "Recommended approach" list so they match that
table. Point the execution-plan link at `plans/PORTABLE_APP_PLAN.md` and drop
every "not started" status, including line 6. Mention this cleanup plan with a
repo-relative link.

Mark parent-plan line 315 done once the note matches the table.

### Verify

```bash
uv run --extra dev --extra gui --locked python scripts/check_doc_freshness.py
uv run --extra dev --extra gui --locked python scripts/check_file_sizes.py
```

Read the note once and confirm it contains no absolute filesystem path and no
`file://` URI.

## Chunk 4 — Close the build-test gap and record the PNG timing

The Light mesh proof and the Full PNG proof already run. Add only the gates
the workflow does not enforce, then write the timing into the parent plan.

### What already runs

Light, frozen `--self-check` (`selfcheck.py` lines 244–261):

- `resolve_human_mesh_stl_path("adult_male")` must be a file
  (`starter_mesh_loads`).
- `senior_male` must raise `HumanMeshNotInstalledError` (`non_starter_mesh` is
  `not_installed`).
- The workflow throws unless both are true (`portable-spike.yml` lines 222–227).
- `tests/unittests/test_edition.py` lines 185–196 cover the same missing-mesh
  message without a freeze. Leave that test as it is.

Full, frozen `--png-check` (`pngcheck.py` lines 213–261 and 277–289):

- `png_images` counts buffers that start with the PNG magic. Zero images raise
  `no_png_rendered`, and `run_png_check` then returns exit code 1.
- `_describe_launch` (lines 130–153) records each descendant whose executable
  name contains `chrom`. On Windows the executable comes from CIM
  `ExecutablePath` (lines 65–92). The command line is read, and only the flag
  names are kept.
- The report field `launched_from_onedir` holds onedir-relative paths.
  `launched_outside_onedir` counts the rest.
- The workflow sets `BROWSER_PATH` to the runner's system Chrome when that file
  exists, then throws if any browser started outside the onedir, and throws
  unless `launched_from_onedir` contains `chromium/chrome.exe`
  (`portable-spike.yml` lines 246–265).
- `tests/unittests/test_portable_pngcheck.py` lines 225–254 already expect
  `png_images == 1` and `launched_from_onedir == ["chromium/chrome.exe"]` with
  the process list faked. Do not add another unit test for that.

### The gap

`figure_to_png` always passes `kopts["path"]` to Kaleido
(`src/guiskindose/export/png_browser.py` line 165). That call bypasses
`BROWSER_PATH`. Requiring the runner's installed Chrome ties the job to the
image, and a throw after the render cannot show that the decoy was set.

`_describe_launch` keeps every descendant whose executable name contains
`chrom` (`pngcheck.py` line 135) and stores the relative path in a set (line
136). Chromium helpers such as `chrome_crashpad_handler.exe` match that filter.
A gate that requires `launched_from_onedir` to have length 1 fails a correct
render when one of those helpers is inside `chromium/`. A filter that drops
only the exact string `chromium/chrome.exe` and then requires a count of 0 has
the same result: the helper is a second path, so the count is not 0.

Two holes remain in the Full step (`portable-spike.yml` lines 242–268):

1. `png_images` and `png_bytes_total` are copied to the environment and are not
   gated. The exit code covers an empty render today (`pngcheck.py` lines
   255–256). Gate the fields themselves.
2. The path check is a contains-check. It already allows extra onedir paths.
   Keep that allowance for other files under `chromium/`, still require
   `chromium/chrome.exe`, and keep `launched_outside_onedir -eq 0`.

Do not download Chrome for Testing. Do not require a system Chrome. Run
42107015732 used the runner's preinstalled Chrome. This slice replaces that
with a missing-path decoy. `ExecutablePath` is the identity the report stores.
Leave `_render_pngs` as it is: a hardcoded `chrome.exe` comparison there would
break the Linux unit tests, which fake a `chrome.exe` path while
`bundled_browser()` uses `chrome` off Windows (`png_browser.py` lines 66–70).

### Files

- `.github/workflows/portable-spike.yml`
- `dev-docs/plans/PORTABLE_APP_PLAN.md`
- `dev-docs/plans/archive/PORTABLE_PNG_BUNDLED_BROWSER_PLAN.md` (status line only)
- `dev-docs/MAINTENANCE_LOG.md`
- `dev-docs/TO_DO.md` (the two portable parentheticals only)
- `dev-docs/index.md` (when this plan is archived at the end of the chunk)

### Workflow edit

Replace the system-Chrome lookup (lines 246–253) before `Start-Process`. Set
the decoy, then assert it, then render:

```powershell
$decoy = Join-Path $env:RUNNER_TEMP "no-such-chrome\chrome.exe"
$env:BROWSER_PATH = $decoy
if ($env:BROWSER_PATH -ne $decoy) { throw "BROWSER_PATH decoy was not set" }
if (Test-Path $env:BROWSER_PATH) { throw "BROWSER_PATH decoy exists on disk" }
```

Drop `if (-not $system) { throw ... }`. Do not point `BROWSER_PATH` at an
installed Chrome.

After the report is parsed (line 262), keep the `http_script_refs` throw and
the `launched_outside_onedir -eq 0` throw. Add:

```powershell
if ([int]$r.render.png_images -lt 1) { throw "png-check returned no PNG" }
if ([int]$r.render.png_bytes_total -le 0) { throw "png-check returned empty PNG bytes" }
$bins = @($r.render.launched_from_onedir)
if ($bins -notcontains 'chromium/chrome.exe') { throw "bundled chrome.exe not seen" }
$outsideChromium = @($bins | Where-Object { $_ -notlike 'chromium/*' })
if ($outsideChromium.Count -ne 0) { throw "png-check browser was $($outsideChromium -join ', ')" }
```

Other `chromium/*` paths stay allowed. `launched_outside_onedir -eq 0` still
rejects a browser that started outside the onedir.

Do not mark parent-plan line 309 done with its current Full clause. That clause
asks for a downloaded Chrome for Testing. Run 42107015732 used the runner's
preinstalled Chrome, which is another Chrome-family browser already on the
machine, and the new job does not install one. Rewrite the Full clause before
checking the box: PNG bytes come back, the launched binaries are the bundled
`chromium/chrome.exe` plus any other `chromium/*` helper, and `BROWSER_PATH` is
the missing decoy `$env:RUNNER_TEMP\no-such-chrome\chrome.exe` set before the
render. The Light clause (starter mesh loads, non-starter stem reported
missing) can be checked as written. Name that decoy in the sentence.

### Record the timing

Compare two totals. Both cover two PNGs. Do not divide by `png_images`.

Phase 0, shared Kaleido server, run
[41230921691](https://github.com/kgrizz-git/GUISkinDose/actions/runs/41230921691):
`dev-docs/references/PORTABLE_CHROMIUM_ARTIFACT.md` lines 124–127 record 2 PNGs
in 9.9 s and 7 browser processes, all from `chromium/chrome.exe`. The parent
plan's Phase 0 paragraph (line 247) names that run, the 2 PNGs, and the 7
processes, and omits the seconds.

First one-shot `figure_to_png` run, portable-spike
[42107015732](https://github.com/kgrizz-git/GUISkinDose/actions/runs/42107015732)
on `main` (2026-11-05): passed with `png_images` 2, `render_seconds` 9.92,
`browser_processes` 14, `launched_outside_onedir` 0. The field is the whole
`_render_pngs` duration (`pngcheck.py` line 250), which wraps
`collect_export_payload` for both images. Fourteen processes is two one-shot
browsers (one per image) against the Phase 0 server's seven. The archived
follow-up uses time, not process count
(`plans/archive/PORTABLE_PNG_BUNDLED_BROWSER_PLAN.md` lines 108–112).

9.92 / 9.9 is about 1.00. "More than about twice as slow" would be a total
above about 19.8 seconds. The threshold is unmet. Do not open a batching
follow-up. Do not batch renders in this slice.

Write that comparison in two places in `PORTABLE_APP_PLAN.md`:

- Line 304: replace the open clause that asks to record `render_seconds` after
  the next Windows Full run. Keep the manual offline PNG check in the GUI open.
  State the run id, the date, `png_images` 2, `render_seconds` 9.92,
  `browser_processes` 14, `launched_outside_onedir` 0, the Phase 0 figure of
  9.9 s from the artifact note, and that the twice-as-slow follow-up stays closed.
- Progress log: one bullet dated 2026-11-05 with the same numbers.

On the archived plan's status line (line 3), remove the clause that the
`render_seconds` recording is still open. Leave the manual Windows GUI offline
PNG check open.

Leave `dev-docs/references/PORTABLE_CHROMIUM_ARTIFACT.md` unchanged. It remains
the Phase 0 source for the 9.9 s figure.

### TO_DO parentheticals

The portable item stays. Phase 1 is still open beyond this slice.

- `dev-docs/TO_DO.md` line 31: extend the Phase 1 parenthetical so it also names
  the pywebview floor, the preview proof, the packaging note, and the PNG timing.
- Lines 59–60: in the "are in / remain" sentence, drop "the Kaleido browser path
  in the app" (that path shipped through `figure_to_png`). Add the four items
  this slice closes to the "are in" list. The remaining list is macOS and Linux
  CI, macOS release signing, the choreographer wrapper, the manual offline PNG
  check, and the clean-VM checks. Leave the sentences after that parenthetical
  as they are.

### Maintenance log

Under `dev-docs/MAINTENANCE_LOG.md` `[Unreleased]`, one bullet: `gui-native`
requires `pywebview>=6.1`; `--self-check` requires the `adult_male` preview
stem `adult_male_reduced_3000t`; the packaging note matches the freeze; the
Full PNG job gates `png_images`, `png_bytes_total`, and bundled `chromium/*`
binaries with `BROWSER_PATH` set to a missing `chrome.exe` before the render;
run 42107015732 took 9.92 s against the Phase 0 9.9 s,
so no batching follow-up was opened.

### Archive this plan

When chunks 1–4 are all in the same PR, move this file to
`dev-docs/plans/archive/PORTABLE_PHASE1_PAYLOAD_CLEANUP_PLAN.md`, set its
status to complete, and move the `dev-docs/index.md` row from the execution
table to the archived table. Add a Related docs row on the parent plan that
links to that archive path. Do this only after the code and the parent
checkboxes above are updated. Leave the parent plan itself active.

### Verify

```bash
uv run --extra dev --extra gui --locked python -m pytest \
  tests/unittests/test_portable_pngcheck.py \
  tests/unittests/test_portable_entry.py -q
uv run --extra dev --extra gui --locked python scripts/check_doc_freshness.py
uv run --extra dev --extra gui --locked python scripts/check_file_sizes.py
uv run --extra dev --extra gui --locked python scripts/check_changelog.py
```

Workflow YAML is not executed by those commands. Read the new PowerShell
conditions against `pngcheck_report.json` fields `render.png_images`,
`render.png_bytes_total`, `render.launched_from_onedir`, and
`render.launched_outside_onedir` (`pngcheck.py` lines 246–252).

## Out of scope

- macOS and Linux CI onedir jobs
- macOS signing, notarization, and stapling
- the choreographer wrapper that frozen macOS and Linux Full need before PNG can succeed
- clean-VM WebView2 checks, Mark-of-the-Web smokes, and the manual GUI PNG download
- removing `_reduced_1000t` from the pip wheel
- batching several PNG views into one Kaleido session

## Chunk summary

1. Change the `gui-native` extra to `pywebview>=6.1`, run `uv lock`, and add a
   tomllib test. The Light and Full STL lists already live in `edition.py` and
   the spec.
2. Assert `prefer_reduced_preview_stem("adult_male")` is
   `adult_male_reduced_3000t` in a unit test, in `--self-check`, and in both
   Windows matrix legs. `_require_preview_stem` is the self-check gate, loaded
   in a unit test through `importlib`. Dose still loads the full STL.
3. Rewrite `PORTABLE_EXECUTABLE_PACKAGING.md`, including the line 6 backlog
   status and the preconditions block. The entry is `packaging/portable/entry.py`
   (`run_gui` at line 191). A default corrections path is classified as packaged
   data. PNG smoke is the Windows Full `--png-check` only.
4. Before `--png-check`, set `BROWSER_PATH` to a missing
   `no-such-chrome\chrome.exe` and assert that. Gate `png_images`,
   `png_bytes_total`, `chromium/chrome.exe`, other `chromium/*` helpers, and
   `launched_outside_onedir -eq 0`. Record run 42107015732 at 9.92 s next to
   the Phase 0 9.9 s. The twice-as-slow batching follow-up stays closed. Reword
   parent-plan line 309 before checking it.
