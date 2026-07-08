# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Version source of truth:** the package version in `pyproject.toml` (currently `25.1.1`).
This changelog tracks user- and maintainer-visible changes; bump `pyproject.toml` when releasing.

## [Unreleased]

### Added

- **Local CI gate and reproducible CI installs** (2026-07-07) — `scripts/ci_local.py` runs the CI
  static checks plus the tests in one command before pushing; its core-test step blocks `nicegui`
  (via `scripts/check_gui_test_placement.py --run`) to reproduce the no-`gui`-extra core matrix that
  local envs otherwise hide. The `ci` workflow's `static-analysis` and `gui-smoke` jobs now install
  the exact versions pinned in `uv.lock` (`uv sync --locked`), so PR/main runs are reproducible and
  an upstream release cannot turn an unrelated PR red. A new scheduled `ci-latest` workflow installs
  the **latest** dependencies weekly (and on demand) to surface upstream breakage deliberately. CI
  runner minutes reduced: the main-push matrix drops the priciest jobs (macOS/Windows only on the
  oldest+newest Python; 12 → 8 jobs) and `gitleaks` no longer double-scans PR-branch pushes.

- **Documentation/help harness checks** (2026-07-04) — added JSON metadata and CI/pre-commit checks for GUI help
  coverage (`dev-docs/help_registry.json`, `scripts/check_help_registry.py`), high-risk UI copy and glossary
  terminology (`dev-docs/ui_copy.json`, `dev-docs/glossary.json`, `scripts/check_ui_copy.py`), feature-to-doc
  traceability (`dev-docs/feature_doc_matrix.json`, `scripts/check_feature_doc_matrix.py`), and stale prose/backtick
  path references in active docs (`scripts/check_doc_freshness.py`). Added missing Upload/Data/Results/Export GUI
  help pages and registry ids on `HelpButton` uses.
- **Total DAP and fluoro time are now reported** (2026-07-03) — tabular inputs that carry per-event
  dose-area-product and fluoro-time columns (e.g. Radimetrics `DAP (Total) Gy-cm2` and
  `Fluoro time (Total) ms`) are now summed into procedure totals and shown in the **rich report**
  dosimetric summary (previously `N/A`) and on the **Results tab** (new *Total DAP* and *Total
  Fluoro Time* cards; the multi-exam aggregate banner gains a totals line). Fluoro time is displayed
  as minutes + seconds (e.g. `5 min 30.8 s (330.8 s)`). The input-adapter pipeline
  (`input_adapters/base.attach_procedure_dose_totals`) detects the DAP column's units from its
  header, converts to internal units, and records the interpretation in the provenance
  unit-conversions. **DAP units that cannot be confirmed from the header are assumed to be Gy·cm²
  and flagged with an import warning** (surfaced in the report's alert block and the GUI) so the
  operator can verify before clinical use; fluoro time is assumed to be milliseconds. As a
  side-effect, DoseTrack DAP totals (which were also dropped during normalization) now report too.
- **DAP unit handling is now uniform across tabular adapters** (2026-07-03) — the DoseTrack adapter
  previously hard-assumed Gy·cm² (unconditional `/10000`) regardless of the column header, and did
  not flag it. All adapters (Radimetrics, DoseTrack, generic capture) now route DAP through the
  shared `input_adapters/base.convert_dap_series_to_gym2`, which reads the unit from the source
  column header (Gy·cm², mGy·cm², cGy·cm², µGy·cm², Gy·m², µGy·m²), records the interpretation in
  provenance, and only falls back to an assumed Gy·cm² **with a flagged warning** when the header
  carries no recognisable unit. Files with a `Gy·cm²` header convert exactly as before.

### Fixed

- **GUI handlers now guard NiceGUI `run.io_bound` results against `None`** (2026-07-07) —
  NiceGUI 3.14 types `run.io_bound`/`run.cpu_bound` as returning `T | None` (it returns `None`
  when a call is cancelled or the app is shutting down), which surfaced 12 strict type errors in
  the upload/calculate/export/import-preview handlers that unpacked or used the result directly.
  Added `gui.concurrency.require_io_result()` to unwrap these results (failing fast with a clear
  message on the interim `None`) and applied it at every call site. Also suppressed the optional
  gui-native `AppKit`/`webview` import diagnostics (runtime-guarded, not installed in core/CI type
  environments). Restores a green `basedpyright` static-analysis job.
- **Backup cleanup no longer deletes in-progress backups with an old mtime** (2026-07-07) —
  `scripts/cleanup_old_backups.py` `_is_stale_backup` now treats pending staged/unstaged changes
  as an absolute keep signal before the commit-age *mtime fallback*. Previously a `backups/*.bak`
  file with local changes but a filesystem mtime older than `HEAD~max_commits` could be removed,
  causing backup data loss. Added `test_cleanup_keeps_*_with_old_mtime` regression tests.
- **GUI calculation failures no longer leak tracebacks to the UI** (2026-07-07) —
  `gui/helpers.run_calculation` now logs the exception (type + traceback via the logger) and
  returns a generic "Calculation failed. See the application log for details." message instead of
  returning `traceback.format_exc()`, which could expose internal filesystem paths and exception
  details in the interface.
- **Dose calculation no longer crashes over the notebook progress bar** (2026-07-07) —
  `calculate_dose` selected `tqdm_notebook` whenever `settings.plot.notebook_mode` was set (true in
  the bundled `settings_example.json`), which raises `ImportError: IProgress not found` in headless
  CLI/export runs without `ipywidgets`. It now falls back to the plain `tqdm` bar
  (`_make_progress_bar`) when the notebook widget backend is unavailable.
- **GUI unit tests relocated so core CI passes without the `gui` extra** (2026-07-07) —
  several GUI tests imported `nicegui` (directly or via `mypyskindose.gui.*`) at load but lived under
  `tests/unittests/`, which the core build matrix runs with `--ignore=tests/gui` and no `gui` extra,
  breaking collection/execution on every platform. Moved `test_gui_helpers`,
  `test_gui_operation_guard`, `test_gui_results_refresh`, and the `TestGui*` classes from
  `test_multi_exam.py` into `tests/gui/`. Added `scripts/check_gui_test_placement.py` (wired into CI
  and the pre-push hook) which blocks `nicegui` and collects the core suite, so a misplaced GUI test
  is caught locally in seconds instead of only in full CI.
- **`test_audit_dependencies` `--frozen` assertions made CI-independent** (2026-07-07) —
  `audit_dependencies.py` emits `--locked` when `CI` is set and `--frozen` otherwise; two tests
  asserted `--frozen` without pinning `CI`, so they passed locally but failed under GitHub Actions.
  They now pin `CI` to a falsy value.
- **Spreadsheet formula injection on Data tab exports** (2026-07-07) — RDSR and tabular
  event-table exports (CSV/XLSX/TXT on the Data tab, plus rich-report XLSX cells) now
  prefix attacker-controlled strings that start with formula trigger characters (`=`, `+`,
  `-`, `@`, tab, CR) so Excel and similar tools treat them as text instead of evaluating
  formulas (CWE-1236).
- **Native "Save As" dialog for exports** (2026-07-03) — in native (pywebview) window mode, the
  export/save-path helper (`gui/io_helpers._get_save_path`) called NiceGUI's async
  `create_file_dialog` without awaiting it, so the returned coroutine was passed to `Path(...)`
  and every save crashed with `TypeError: argument should be a str ... not 'coroutine'`. The
  helper is now an awaited coroutine (and uses the non-deprecated `webview.FileDialog.SAVE`),
  restoring the ability to choose the file location and name in native mode. All callers in the
  Export and Data tabs await it.

### Changed

- **CLI `--input-schema` now defaults to `auto`** (2026-07-03) — tabular inputs (.csv/.tsv/.xlsx)
  are detected from their column headers by default, matching the GUI (which already defaults to
  `auto`). Previously the CLI fell back to the `normalized` schema, so a Radimetrics or DoseTrack
  export run without an explicit `--input-schema` failed to locate a header row. Auto-detection
  scores every real schema (normalized, generic_rdsr_like, radimetrics, dosetrack) and errors with
  a clear "pass `--input-schema` explicitly" message if two schemas are ambiguous. The
  library-level `read_and_normalize_input(input_schema=None)` default is unchanged (`normalized`).
  Detection, per-schema fingerprints, and the DAP-unit / equipment-manufacturer caveat are now
  documented in `dev-docs/INPUT_SCHEMA_DETECTION.md`, kept in sync with the code by
  `tests/unittests/test_input_schema_doc.py`.
- **GUI toasts appear at the top and linger longer** (2026-07-03) — `gui/notifications.py` patches
  `ui.notify` once at startup so notifications default to `position="top"` and an 8 s timeout
  (up from Quasar's 5 s at the bottom). Explicit per-call `position`/`timeout` still win, so
  persistent (`timeout=0`) toasts are unaffected.
- **Native window is now the default GUI mode from the launchers** (2026-07-03) — `run_gui.sh` and
  `run_gui.bat` now default to option **[2] Native Window** when the user presses Enter without a
  choice (previously defaulted to browser). Browser mode remains selectable as **[1]**.
- **Rich report export dependencies are now core** (2026-07-03) — `reportlab` (PDF) and
  `python-docx` (DOCX) moved from the optional `export` extra into the main dependency list so
  every install can produce all report formats out of the box. The `export` extra is retained as a
  no-op alias for backward compatibility. If an export backend is ever missing (e.g. a partial
  install), `export.writers.render_bytes()` now raises `MissingExportDependencyError` — with a
  copy-pasteable `pip install` hint — instead of a bare `ModuleNotFoundError`; the GUI Export tab
  surfaces this as a persistent, actionable dialog (with a Copy-command button) rather than a brief
  error toast.

### Added

- **Rich Report Export** (2026-07-02) — new `mypyskindose.export` package produces a single
  self-contained audit document (**XLSX / PDF / HTML / DOCX**) from a completed dose calculation,
  bundling dosimetric results, effective settings, input provenance (DICOM RDSR + tabular
  branches), correction-factor statistics, warnings/discarded events, and dose-map images
  (whole-body context + a view zoomed to the irradiated region). `collect_export_payload()`
  normalizes single-exam (dict) and multi-exam (`MultiExamResult`) results into one payload;
  writers under `export/writers/` consume it. GUI: Export tab **"Rich report…"** modal
  (format + optional title; native save-path vs browser download). CLI: `--export-format`,
  `--export-path`, `--export-title` on the headless path (rejects `--aggregate` /
  `--input-preview-only`). `reportlab` added as a new optional `export` extra
  (`pip install -e '.[gui,export]'`); XLSX/images reuse core `openpyxl`/`kaleido`.
  `gui/figures.py` now delegates dose-map figure construction to the GUI-free
  `export/images.py`. DOCX writer uses `python-docx` (also in the `export` extra).
  Plan: `dev-docs/plans/RICH_EXPORT_PLAN.md`.

- **Vendor X/Z coordinate clarification** (2026-06-28) — Geometry and dose-map plots now label the
  normalized frame as `X - LON / PT L-R`, `Y - VER / PT A-P`, and `Z - LAT / PT S-I`;
  Data tab and Geometry/Per-exam controls use the same frame; Geometry and Calculate help explain
  Siemens/Philips DICOM/operator naming versus GE patient-anatomy raw naming. Plan:
  `dev-docs/plans/archive/VENDOR_XZ_CLARIFICATION_PLAN.md`.
- **Lockfile-based dependency auditing** (2026-06-28) — `scripts/audit_dependencies.py` wraps
  `uv audit` on `uv.lock` (requires `uv` >= 0.11.19; `--frozen` locally, `--locked` in CI) with
  fallback to `pip-audit` on the active environment. Pre-push hook and CI `static-analysis` job now
  call the wrapper; CI installs `uv` via `astral-sh/setup-uv@v8.2.0`. Tracked suppressions live in
  `[tool.uv.audit]` (`ignore-until-fixed` for dev-only `nltk` via `safety`, GHSA-p4gq-832x-fm9v).
  Plan: `dev-docs/plans/DEPENDENCY_AUDIT_PLAN.md`.
- **One-command hook installer** (2026-06-27) — `scripts/setup-dev.sh` (macOS/Linux)
  and `scripts/setup-dev.bat` (Windows) run both `pre-commit install` and
  `pre-commit install --hook-type pre-push` in one step, ensuring all pre-push hooks
  (semgrep, pip-audit, basedpyright, check-changelog) fire automatically on `git push`.
  Added `pip-audit --desc on` as a pre-push hook in `.pre-commit-config.yaml` to match the
  existing CI gate. Expanded the CI shellcheck step to cover `scripts/setup-dev.sh`.
  `AGENTS.md` Development setup block simplified to reference the scripts. Plan:
  `dev-docs/plans/archive/ENABLE_SECURITY_HOOKS_DEFAULT_PLAN.md`.
- **Security tooling in CI and pre-push** (2026-06-27) — semgrep (OWASP Top 10 SAST) in
  the `static-analysis` CI job and as a pre-push hook, scanning `src`, `scripts`,
  `.github/workflows`, and `docs/source/conf.py`; safety dependency scan in CI (skipped when
  `SAFETY_API_KEY` is unset; `pip-audit` remains the no-key gate); shellcheck (`shellcheck-py`)
  pre-commit hook + CI step for shell scripts. Hardened `ci.yml` to avoid `${{ github.* }}`
  shell-injection by passing context through `env:` variables, and fixed latent `set -e`
  error-handling bugs in `run_gui.sh` surfaced by shellcheck. Plan:
  `dev-docs/plans/SECURITY_TOOLS_CI_PLAN.md`.
- **Body-habitus cm readouts** (2026-06-26) — Settings → Phantom body-habitus
  sliders now show the scaled human-mesh dimension in centimeters beside the
  scale factor, update on slider drag and mesh switch, and fail soft to `—` for
  unknown or unreadable STL meshes. Plan:
  `dev-docs/plans/archive/BODY_HABITUS_CM_DISPLAY_PLAN.md`.
- **First-run GUI onboarding** (2026-06-25) — first GUI page render shows a persistent onboarding
  modal explaining accepted input files, workflow steps, local-only processing, and result exports.
  Users can persist "Don't show this again" in `~/.mypyskindose/gui.json`; native window geometry
  preferences are preserved when the onboarding flag changes. Plan:
  `dev-docs/plans/archive/FIRST_RUN_ONBOARDING_PLAN.md`.
- **Native window geometry persistence** (2026-06-25) — `--native` mode restores window size,
  position, and maximized state from `~/.mypyskindose/gui.json`. First launch starts maximized
  with normal bounds at 75% of the primary screen (centered). Plan:
  `dev-docs/plans/NATIVE_WINDOW_GEOMETRY_PLAN.md`.
- **Agent guidance playbook and advisory check** (2026-06-25): added `dev-docs/AGENT_PLAYBOOK.md`,
  thin `GEMINI.md` / `QWEN.md` pointer files, and `scripts/check_agent_guidance.py` (pre-commit advisory;
  `--strict` available) to flag duplicated or drifting agent instructions, overgrown `TO_DO.md`, and
  completed-looking active execution plans.
- **Beam-miss warnings** (2026-06-24) — when an irradiation event deposits zero dose (beam does not intersect the patient phantom), a per-event `WARNING` identifies the event index, kVp, filtration, and field area. Configurable via `beam_miss_warn` setting (`"per_event"` / `"summary"` / `"off"`; CLI default `"per_event"`, GUI default `"summary"`); an all-miss sentinel always fires. Multi-exam auto-downgrades per-event to `"summary"`. GUI toast throttle at 5 messages (`_MAX_TOASTS`). Plan: `dev-docs/plans/archive/NO_PATIENT_INTERSECTION_WARNING_PLAN.md`.
- **Interactive Geometry offset sliders** (2026-06-24) — single-exam **patient offset** sliders and **table-origin override** sliders in the Geometry tab with debounced live 3D preview; read-only auto-detected table offsets in Settings and Calculate tabs; reset buttons. Plan: `dev-docs/plans/INTERACTIVE_TABLE_OFFSETS_PLAN.md`.
- **Human phantom body-habitus scaling** (2026-06-25) — human STL phantoms can be directionally scaled with `phantom.scale_lat`, `phantom.scale_ap`, and `phantom.scale_lon` (defaults `1.0`, clamped to `0.5–2.0`). Scaling is applied before patient/table positioning, non-uniform scaling recomputes normals, and Settings → Phantom exposes human-only sliders that refresh Geometry preview and invalidate prior results. Plan: `dev-docs/plans/archive/PATIENT_SIZE_SCALING_PLAN.md`.

### Fixed

- **Geometry slider label placement** (2026-06-26) — Geometry tab slider value
  labels now sit adjacent to their sliders instead of wrapping to the following
  row. Plan: `dev-docs/plans/archive/SLIDER_LABEL_REPOSITION_PLAN.md`.
- **Cross-tab slider sync in GUI** (2026-06-25) — table-origin spinbox changes in Settings → Per-exam corrections now refresh Geometry sliders; switching to the Geometry tab (via the tab strip or the left nav drawer) refreshes sliders, value labels, and the live preview figure. Plan: `dev-docs/plans/archive/CROSS_TAB_SLIDER_SYNC_PLAN.md`.
- **Geometry tab render loop** (2026-06-25) — stop Plotly re-rendering on a 0.25 s timer after slider drags or external refresh; break the cycle with an `_in_render_chain` closure flag. Plan: `dev-docs/plans/archive/GEO_TAB_SPINNING_WHEEL_PLAN.md`.
- **`_CalcWarningCollector` handler leak in GUI** (2026-06-24) — multi-exam `run_calculation` branch in `gui/helpers.py` never removed the temporary log handler, causing exponentially duplicated toasts across runs. Fixed by widening the `try/finally` to wrap both single-exam and multi-exam branches. (Phase 0 of no-patient-intersection warning plan.)
- **Single-exam Geometry preview pause regression** (2026-06-24) — `live_preview_allowed` no longer pauses single-exam `plot_procedure` at >30 events; composite multi-exam pause threshold unchanged (R12).
- **GUI offset display and state leaks** (2026-06-24) — Calculate tab patient/table offset summaries now update when any axis changes; per-exam corrections global-offset label refreshes after Settings edits; patient offsets and coordinate-correction flags reset on new file load; `_remove_exam` multi→single restores globals from surviving exam meta.
- **Dose map figure exports** (2026-06-24) — restore `make_dosemap_fig` / `make_dosemap_html` / `make_dosemap_png` in `gui/figures.py` (accidentally dropped during Part II `make_geometry_fig` refactor).

### Changed

- **Agent and backlog docs** (2026-06-25): `CLAUDE.md` now imports `AGENTS.md` and points to
  `dev-docs/AGENT_PLAYBOOK.md`; `dev-docs/TO_DO.md` is trimmed to an active backlog with completed history
  redirected to `CHANGELOG.md` and archived plans.
- **GUI module split for multi-exam geometry prep** (2026-06-24) — Part I of `MULTI_EXAM_GEOMETRY_OFFSETS_PLAN`: split `gui/helpers.py` into `settings_builder`, `exam_loaders`, `exam_transforms`, and `geometry_preview` (stub); `helpers.py` is now a thin facade under the CI line cap. Loader seeds per-exam `d_*` from globals before reset (T20); Settings per-exam offset edits refresh Geometry sliders (T25).
- **Multi-exam Geometry Phase 0** (2026-06-24) — Part II: `geometry_preview.py` lifecycle/slice helpers, `EXAM_INDEX_COLUMN` for stable preview slicing, C1 banner + exam selector, `make_geometry_fig` active-exam/composite args; `reset_results` no longer clears `active_exam_index` (T2).
- **Multi-exam table-origin sliders (Geometry)** (2026-06-24) — Part III: table-origin card visible per active exam in multi-exam mode; slider limits refresh on exam switch; reset commits `meta[active]` (T3, T5a).
- **Multi-exam patient-offset sliders (Geometry)** (2026-06-24) — Part IV: patient card in multi-exam; sliders write `meta[active].d_*` only; composite preview checkbox + C3/C4 captions (T4, T5b, T29, T31).
- **Multi-exam Geometry cross-cutting (Part V)** (2026-06-24) — Calculate per-exam patient-offset summary (`lon/ver/lat`); Settings hides global Phantom spinboxes in multi-exam (C6); `per_exam_offsets_version` refresh; Settings transform → Geometry refresh + event-index clamp (N4); Upload→Geometry exam click; help/docs updated (T10).
- **Fix Geometry exam selector startup** (2026-06-24) — avoid `Invalid value: 0` when no exams are loaded (NiceGUI select requires value in options or None).
- **Fix multi-exam Results stale UI after recalc** (2026-06-24) — rebuild per-exam PSD/metrics and dose-map dialogs when `calc_run_id` changes; clear cached aggregate dose map on each run.
- **GUI decomposition (refactor plan Phase 3, 2026-06-23):** `gui/app.py` slimmed from ~1275 to 245 lines — `index()` now orchestrates layout + `PageContext` and delegates to per-tab `build(ctx)` modules (`gui/tabs/{upload,data,settings,geometry,calculate,results,export}.py`). Shared upload widgets in `gui/widgets/{import_preview,event_table}.py`; concurrency guard and upload temp-file lifecycle in `gui/concurrency.py` and `gui/upload_temp_files.py`. Below-floor kVp pre-calc prompt moved to `gui/tabs/calculate.py`. `app.py` removed from the file-size CI whitelist. Plan archived as `dev-docs/plans/archive/refactor-execution.md`.
- **Export `schema_version` (refactor plan Phase 4.3, 2026-06-23):** JSON/dict exports from `PySkinDoseOutput.to_dict()` and `MultiExamResult.to_dict()` now include top-level `schema_version` (currently `1`) so downstream consumers can detect format changes without relying on package semver.
- **Plotly layout helpers (refactor plan Phase 4.2, 2026-06-23):** `plotting/plot_layout.py` centralizes shared `go.Layout` builders for CLI/notebook geometry, procedure, and dose-map plots; `create_setup_and_event_plot`, `plot_procedure`, and `create_layout_for_dose_map_plots` delegate to it (`gui/figures.py` unchanged).
- **GUI help single source of truth** (2026-06-24): in-app help markdown now lives in `docs/source/gui_help/` and is mirrored to `src/mypyskindose/gui/help/` by `scripts/sync_gui_help.py` (enforced by pre-commit + CI). `positioning_offsets.md` merged from the prior `docs/source/user_guide/` copy and the original GUI version (Overview + 6-step workflow + Tips from the GUI; Coordinate System, Troubleshooting, and Getting More Help from the docs version; 4-row Quick Reference with `Lateral/Longitudinal/Vertical/Rotation` and a MyST footnote). `geometry_workflow.md` and `below_floor_kvp.md` relocated unchanged. New Sphinx toctree entries between `user/user_guide.md` and `getting_started/`. `scripts/check_doc_freshness.py` extended to scan the new directory. `AGENTS.md` Conventions section documents the rule. Plans archived under `dev-docs/plans/archive/`.

### Added

- **Ignored asset advisory check** (2026-06-24): `scripts/check_ignored_asset_files.py` warns (pre-commit hook; `--strict` to fail) when `.png` or `.html` files outside `PlotOutputs/` are untracked or gitignored, including tracked-but-ignored paths that can be dropped from version control while `*.png` / `*.html` remain in `.gitignore`. Restored `wiki/*.png` illustrations after accidental untracking in commit `e856ccd`.

- **User options for below-floor kVp events** (2026-06-19): events with a kVp below the 25 kV HVL table floor can now be handled by an explicit policy instead of being silently clamped. A new setting `below_floor_kvp_policy ∈ {snap (default), skip, manual, exam_average}` (+ `below_floor_kvp_manual`) is applied per exam in `geom_calc.apply_below_floor_kvp_policy()`, called at the top of `calculate_dose()` before the HVL lookup: `snap` keeps the status quo (clamp + flag), `skip` drops the events, `manual` substitutes a fixed kVp, and `exam_average` substitutes that exam's mean in-floor kVp (falls back to `snap` + warns if an exam is all below floor). `geom_calc.count_below_floor_events()` detects affected events; every policy emits a `logger.warning` → `state.calc_warnings`. GUI: a "Below-floor kVp handling" control under Physics settings (`gui/tabs/settings.py`) holds the persistent default, and a pre-calc prompt (`gui/app.py`) appears only when sub-floor events are detected, offering the policy + "don't ask again". Defaults preserve existing results (`snap`). Wired through `PyskindoseSettings`, `settings_example.json`, and `gui/helpers.build_settings`. Tests in `tests/unittests/test_geom_calc.py` (per-policy transforms, detection, all-below fallback) and `tests/unittests/test_gui_below_floor_kvp.py` (detection sum, settings propagation). Completes `dev-docs/plans/archive/hvl-interpolation-and-below-floor-kvp.md`.

- **Multi-exam Data Table exam column** (2026-06-19): in multi-exam mode the normalized event table (`state.rdsr_df`) now tags every row with a display-only `Exam` column (`"#<n> · <file>"`) so it is clear which loaded exam a row came from. Centralized in `gui/helpers.rebuild_rdsr_df()` (replaces four inline `pd.concat` sites); single-exam frames stay untagged and the tag is stripped before the single-exam calculation, so dose output is unchanged. Pinned first in the Data Table; included in normalized CSV/XLSX exports, omitted from raw exports. Unit tests in `tests/unittests/test_gui_rdsr_df.py`.

- **Recursion-to-iteration prep** (2026-06-16): golden baseline test and pinned `dose_map` fixture for `siemens_axiom_artis.dcm` (cylinder phantom); 1100-event stress test; `tests/calculate_dose_recursion_helpers.py` for synthetic normalized events; `slow` pytest marker. Plan in `dev-docs/plans/recursion-to-iteration.md`.

### Changed

- **Dependencies unified into `pyproject.toml` extras** (2026-06-19): removed the legacy `requirements.txt`, `requirements-dev.txt`, and `docs/requirements.txt`, which had drifted out of sync with the `pyproject.toml` extras (e.g. `requirements-dev.txt` installed black/isort/pydocstyle — tools the project no longer runs — while omitting the actual CI toolchain). `pyproject.toml` is now the single source of truth: new `[docs]` (Sphinx, sphinx-rtd-theme, myst-parser, nbsphinx, ipykernel, ipywidgets, pandoc) and `[notebooks]` (JupyterLab) extras hold the previously-requirements-only toolchains, and the `[dev]` extra gained `pytest` and `ruff` to be a true superset of the CI lint/type/test stack. `.readthedocs.yml` now installs `.[docs]` via `extra_requirements`; README/AGENTS install instructions point at the extras. `scripts/check_licenses.py` inventories the full declared extra set (`dev,gui,gui-native,docs,notebooks`) and `dev-docs/THIRD_PARTY_NOTICES.md` is regenerated from `uv sync --all-extras` (pinned by `uv.lock`), making the notices reproducible regardless of which extras a venv installed; the `license-notices` pre-commit hook now also triggers on `uv.lock`. Also dropped the dead `[tool.black]` and `[tool.isort]` config blocks — ruff is the sole formatter/linter.

- **HVL lookup now interpolates off-grid filtration** (2026-06-19): `geom_calc.fetch_and_append_hvl()` replaces the exact-match-with-nearest-snap lookup with **2-D bilinear interpolation over (kVp, Cu)** on the selected `(inherent, Al)` grid slice (`scipy.interpolate.RegularGridInterpolator`, cached per slice). Off-grid copper filtration (tabulated gaps at 0.5/0.7/0.8 mmCu) is now linearly interpolated instead of snapped; out-of-range queries are **clamped** to the nearest grid edge (never extrapolated). Anode angle is **selected** (first-occurrence dedup ≈ 11° where present, else 8°), not interpolated — a discrete tube property. kVp is rounded to its nearest integer node (table is 1-kV dense), so **in-grid results are unchanged** (golden PSD identical; `test_fetch_hvl_from_database` characterization preserved). Per-event `interpolated`/`clamped` warnings flow through the `mypyskindose` logger to `state.calc_warnings` (calc-tab status line + toasts). New tests in `tests/unittests/test_geom_calc.py` (interpolation betweenness, edge clamping, on-grid silence). HVL drives `k_bs` and `k_med`. Shared 2-D clamped-interpolation helper extracted to `src/mypyskindose/grid_interp.py`. First slice of `dev-docs/plans/archive/hvl-interpolation-and-below-floor-kvp.md`; below-floor-kVp user options still pending.

- **k_tab table-attenuation lookup guarded + interpolated** (2026-06-19): `corrections.calculate_k_tab()` no longer crashes on off-grid or unknown beam/device parameters. The old exact-match SQL ending in `c.fetchone()[0]` raised `TypeError` (`None[0]`) and aborted the whole calculation on any untabulated `(kVp, Cu, Al)` tuple or unknown device/plane (e.g. a non-Siemens/Philips export such as GE). Now: exact match stays the primary path (in-table results bit-for-bit unchanged — `test_fetch_correct_table_correction_*` preserved); an unknown device/plane **fails soft to `k_tab=1.0`** with a warning; off-grid copper within a known device is **interpolated over (kVp, Cu)** (per-`(model, plane, Al)` slice, all complete grids) and out-of-range queries are **clamped** to the grid edge. Per-event `no-device`/`interpolated`/`clamped` warnings surface via `state.calc_warnings`. New robustness tests in `tests/unittests/test_corrections.py`. `k_med` intentionally left as nearest-tabulated (cannot crash; documented <1% field-size dependence).

### Fixed

- **Per-event dose loop** (2026-06-16): `calculate_irradiation_event_result()` no longer recurses once per irradiation event; uses an iterative loop so procedures with >1000 events (and future multi-exam runs) do not hit Python's recursion limit. Output verified bit-identical to the prior implementation via golden baseline test.

- **Tabular input Phase 1** (2026-06-09): `src/mypyskindose/input_adapters/` package — shared loader, column mapper, registry, `normalized` schema adapter; handles CSV/TSV/XLSX with encoding fallback (UTF-8/BOM/cp1252), delimiter sniffing, decimal-comma normalization, and offset header detection. CLI flags `--input-schema`, `--sheet-name`, `--input-preview-only`. Python API `analyze_input_file()` and `preview_input_file()`. Architecture layer tests. Full unit test suite with six fixture variants.
- **Tabular input Phase 2** (2026-06-09): `generic_rdsr_like` schema adapter — maps `rdsr_parser()`-style columns to `rdsr_normalizer()` input and produces the normalized DataFrame; `--input-schema auto` with ≥0.20 margin scoring. `GENERIC_RDSR_PATTERNS` and `GENERIC_RDSR_COLUMN_NAMES` in `column_mapper.py`; `NORMALIZED_COLUMN_CANONICAL` for proper-case output matching `rdsr_normalizer()`. Test fixture `generic_rdsr_events.csv` (21-event Siemens AXIOM-Artis).
- **Tabular input Phase 3** (2026-06-10): `radimetrics` schema adapter in `input_adapters/radimetrics.py`; `RADIMETRICS_PATTERNS` and `RADIMETRICS_COLUMN_NAMES` in `column_mapper.py`; unit conversions (reference dose mGy→Gy, field area cm²→m², exposure mAs→µAs) with provenance tracking; unknown model warning (non-blocking); auto-detection support; synthetic fixture `radimetrics_events.csv` (5-event Siemens AXIOM-Artis); 8 new tests (46 total for input_adapters). GUI schema selector updated to include "Radimetrics CSV".
- **Tabular input Phase 4** (2026-06-10): `dosetrack` schema adapter in `input_adapters/dosetrack.py`; `DOSETRACK_PATTERNS` and `DOSETRACK_COLUMN_NAMES` in `column_mapper.py`; Equipment Name → Manufacturer/ModelName inference via `MODEL2MANUF` (`AXIOM-Artis`→Siemens, `Azurion`/`Allura Clarity`→Philips); `ffill()` for hierarchical DoseTrack row format; integer Plane Code → "Single Plane"/"Plane A"/"Plane B"; unit conversions (Air Kerma mGy→Gy, DAP Gy·cm²→Gy·m², Tube Current µA→mA); `CollimatedFieldArea_m2` derived from `DAP / (DoseRP * ((DSI-150)/DSD)²)` formula; Siemens filter thickness max=min; Philips semicolon-split Al;Cu filter thickness; Philips lat/lon swap warning; registered in registry with auto-detection support; synthetic fixture `dosetrack_events.csv` (5-event AXIOM-Artis); 10 new tests (56 total for input_adapters).
- **Vendor adapter stubs** (2026-06-10): `qaelum.py`, `dosemonitor.py`, `dosewatch.py` — each has empty `VENDOR_COLUMN_NAMES`/`VENDOR_PATTERNS` with `TODO` notes and an `adapt()` that raises `NotImplementedError` with step-by-step implementation instructions. Wired into registry for explicit `--input-schema` selection; excluded from auto-detection until column maps are populated. Qaelum, DoseMonitor, and DoseWatch documented as Phase 5+ placeholders in `TABULAR_RDSR_INPUT_PLAN.md` and `FEATURE_INVENTORY.md`.
- **Header-row detection fix** (2026-06-10): `detect_header_row` threshold changed from fraction-based (`matched/total_cells ≥ 0.05`) to absolute hit count (`matched_columns ≥ 5`). Fixes false-negative on exports with 100+ columns where few columns are in the known set. `_score_row` now also normalizes `known_names` before comparison so underscore-containing entries in `GENERIC_RDSR_COLUMN_NAMES` (e.g. `"distancesourcetodetector_mm"`) correctly match normalized cell values (`"distancesourcetodetector mm"`). `_score_schema` (auto-detection) is unaffected — it uses its own `.lower()`-only normalization.
- **Tabular input Phase 5** (2026-06-10): GUI upload tab now accepts `.csv`, `.tsv`, `.xlsx`, `.xlsm` in addition to `.dcm`; routes to `load_tabular()` helper; schema selector dropdown (Auto-detect / Normalized / Raw RDSR-like / Radimetrics CSV / DoseTrack XLSX/CSV); import preview panel showing schema, encoding, delimiter, header row index, column mapping table, warnings, and first 5 normalized events; **individual coordinate correction toggles** (Swap lateral ↔ longitudinal `Tx↔Tz`, Flip primary angle `Ap1×−1`, Flip secondary angle `Ap2×−1`) with tooltips, each its own inverse applied live to `state.rdsr_df`; **intelligent transform defaults** auto-set from detected manufacturer (GE Radimetrics and Philips DoseTrack auto-enable lat/lon swap) with override hint label; **XLSX sheet picker** shown only for multi-sheet files, re-parses on change without overwriting user transform choices; Calculate tab blocked on import errors; Data Table tab shows source filename and schema. Tabular provenance now preserved in JSON exports (`tabular_input` key) and HTML exports (HTML comment in `<head>`).
- **Vendor coordinate documentation**: new "Tabular input coordinate handling" section in `VENDOR_COORDINATE_SYSTEMS.md`; `TabularImportOptions` plan (Phase 3+) documented in `TABULAR_RDSR_INPUT_PLAN.md`; DoseTrack Philips lat/lon swap finding added.
- **Reference implementations saved**: `dev-docs/references/` now contains `dhen2714_radimetrics.py`, `dhen2714_dosetrack.py` (from `github.com/dhen2714/PySkinDose`), and `psdcalcrework_io_utils.py` (from private repo) with findings summary.

- Harness docs: `TO_DO.md` cleanup (pending vs open questions vs completed); `FEATURE_INVENTORY.md` §0 harness/CI shipped features; GUI doc consolidation (`GUI_PLAN.md` §0 supersedes `UI_ANALYSIS.md`); `scripts/generate_ui_values.py` for auto-generated `UI_values.md`; `dev-docs/references/` stub; Phase 6 plan lifecycle closed.
- Harness docs: `check_doc_freshness.py` now scans `CHANGELOG.md` for `FEATURE_INVENTORY` contradictions; doc-gardening cadence documented in `HARNESS_ENGINEERING.md`.
- Harness CI: **basedpyright** `typecheck` job (strict — any type error fails); optional baseline helpers in `scripts/type_baseline.sh`; `[dev]` optional dependency.
- Harness CI: **gitleaks** secret scanning workflow on push/PR.
- Harness CI: **bandit** `bandit` job (Python SAST on `src/mypyskindose` + `scripts`; medium+ severity gate).
- Harness CI: **pip-audit** `dependency-audit` job (core + `[dev]` + `[gui]` extras; fails on known CVEs).
- Harness CI: **license compliance** — `scripts/check_licenses.py` in `dependency-audit` job; policy in `dev-docs/LICENSE_COMPLIANCE.md`; inventory in `dev-docs/THIRD_PARTY_NOTICES.md`.
- Harness local hooks: **pre-commit** config (commit: ruff, gitleaks, bandit, doc-freshness; pre-push: basedpyright).
- Harness Phase 5: GUI smoke tests (`tests/gui/`) with NiceGUI user simulation; `gui-smoke` CI job; `tests/scripts/launch_gui_headless.py`.
- Harness Phase 4: package layering documented in `CODEBASE_OVERVIEW.md`; structural layer tests in `tests/unittests/test_architecture_layers.py`.
- Harness Phase 3: `python -m build` in CI (`package-build` job on Ubuntu, Python 3.12); local full checks now match CI.
- Harness Phase 2: root `CHANGELOG.md`; `python -m compileall src/mypyskindose` in CI; GitHub Actions upgraded to current majors.
- Harness Phase 1: `scripts/check_doc_freshness.py` and Ubuntu CI job for broken internal markdown links and checkable `FEATURE_INVENTORY.md` contradictions.
- Harness Phase 0: `dev-docs/index.md` documentation catalog; expanded source-of-truth map in `dev-docs/HARNESS_ENGINEERING.md`; `design.md` renamed to `DESIGN.md`.

### Changed

- **Per-exam corrections moved to Settings tab** (2026-06-19): the editable per-exam controls (patient offsets, coordinate corrections, table-origin override, "Apply global to all") now live in a new **Settings → Per-exam corrections** section (`gui/tabs/_per_exam.py`, registered via `ctx.refresh_per_exam`) instead of the Upload tab, so each exam is edited separately and apart from the global settings. The Upload tab keeps a compact loaded-files summary (badges, event count, warnings, remove button) and points to Settings for edits. Trims `gui/app.py` by ~225 lines.
- Harness docs: document master vs execution vs archive plan conventions in `HARNESS_ENGINEERING.md`; add `dev-docs/plans/archive/` (basedpyright plan); sync `TO_DO.md` with shipped tabular Phases 3–5; update `dev-docs/index.md` catalog.
- Repository hygiene: stop tracking build artifacts (`dist/`), Jupyter checkpoint notebooks, legacy `phantom_data/old/` meshes, local `debug.json`, ad-hoc `_test_gui_import.py`, and duplicate `.windsurf/` rules; expand `.gitignore` for `PlotOutputs/`, coverage output, and local agent config.
- Type checking: resolved all 147 basedpyright errors; CI now runs strict `basedpyright` (no baseline). Optional incremental baseline workflow documented in `.basedpyright/README.md` with `scripts/type_baseline.sh`.
- Pre-commit: `cleanup-old-backups` hook removes `backups/*.bak` files last touched more than 5 commits ago; `backups/` added to `.gitignore`.
- Harness Phase 2: stop tracking generated `src/mypyskindose.egg-info/`; `.gitignore` covers egg-info and standard Python build artifacts.
- Harness Phase 2: CI `flake8` limited to syntax/fatal errors (`E9,F63,F7,F82`); style overlap with `ruff` (120-column) removed from CI.
- Harness Phase 2: `.github/workflows/ci.yml` and `release.yml` use `actions/checkout@v4` and `actions/setup-python@v5`.
- CI test matrix: full 3 OS × 4 Python on pull requests and `main` pushes only; other branch pushes run a single Ubuntu + Python 3.12 `build` cell (other jobs unchanged).
- Local hooks: **basedpyright** moved to pre-push only via pre-commit (`pre-commit install --hook-type pre-push`); removed manual `scripts/pre-push.sh`.

### Fixed

- Dose calculation: `calculate_k_isq` now returns one inverse-square-law factor per hit cell for any number of hits. A `len(cells) > 3` guard previously fell back to `norm(axis=0)` for events hitting ≤3 skin cells, which crashed (`operands could not be broadcast (2,) (3,)`) for 1–2 hits and silently mis-dosed exactly-3-hit events. Affected exports whose geometry clips the phantom at only a few cells.
- Dose output template: `k_med` placeholder aligned to scalar `float`; zero-hit events now write explicit correction slots (`k_bs` empty array, `k_med` 0.0 meaning not applied, real per-event `k_tab`) instead of leaking template placeholders. New-geometry zero-hit events no longer carry stale `k_isq` / `field_area` from the prior event.
- Pre-commit backup cleanup: new untracked `backups/*.bak` files are no longer deleted just because the same path was touched in older git history.
- Pre-commit backup cleanup: a backup whose path is still tracked in `HEAD` but was recreated/force-staged (or locally modified) with new content is now protected too — commit-age deletion is skipped when the path has pending staged/unstaged changes, deferring to the mtime fallback.
- Normalization settings: `update_translation_offset` and `update_rotation_direction` now apply vendor overrides from JSON/settings (previously no-ops when values were already initialized).
- Phantom: cylinder mesh resolution assertions run after resolution is assigned (basedpyright refactor had broken cylinder phantom creation).
- Type-check fixes for unit tests (2026-06-24): resolved 10 basedpyright errors blocking the pre-push type check. `tests/unittests/test_check_doc_pruning.py` now passes a structural lambda matching the `GitAgeProvider` protocol's `relative_path` parameter (and wrapping `dict.get`) instead of binding the `dict.get` bound method directly; `tests/unittests/test_plot_layout.py` reads margin values through `to_plotly_json()` to avoid basedpyright's spurious `tuple[Unknown, ...] | None` inference for the untyped plotly `Layout.margin` property. No behavior change.

## [25.1.1] - 2025-01-01

### Added

- MyPySkinDose fork baseline: peak skin dose estimation and 3D skin dose maps from fluoroscopic RDSR data.
- NiceGUI application (`python -m mypyskindose --mode gui`).

[Unreleased]: https://github.com/kgrizz-git/MyPySkinDose/compare/v25.1.1...HEAD
[25.1.1]: https://github.com/kgrizz-git/MyPySkinDose/releases/tag/v25.1.1
