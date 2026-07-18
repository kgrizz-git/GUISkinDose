# Complexity Refactoring Plan: Remaining GUI Components

> **Status:** Completed and archived (2026-07-18). Shipped controllers/builders for
> export, per-exam, calculate, data, geometry-preview helpers, and import preview.

This is the detailed companion to Phase 4.4 of
[the SonarQube remediation plan](../sonarqube_remediation_plan.md). It covers the
six remaining GUI findings in that phase:

| Component | Function | Baseline complexity |
|---|---|---:|
| [export.py](../../../src/mypyskindose/gui/tabs/export.py#L82) | `build` | 72 |
| [_per_exam.py](../../../src/mypyskindose/gui/tabs/_per_exam.py#L36) | `build_per_exam_section` | 42 |
| [calculate.py](../../../src/mypyskindose/gui/tabs/calculate.py#L70) | `build` | 32 |
| [data.py](../../../src/mypyskindose/gui/tabs/data.py#L38) | `build` | 27 |
| [geometry_preview.py](../../../src/mypyskindose/gui/geometry_preview.py#L13) | `geometry_vendor_notice` | 17 |
| [import_preview.py](../../../src/mypyskindose/gui/widgets/import_preview.py#L37) | `build` | 46 |

The function name in `_per_exam.py` is deliberately recorded as
`build_per_exam_section`, not `build`. Reconfirm rule/component/line against the
private Phase-0 Sonar inventory before work, since a prior refactor may move it.

---

## 1. Refactoring Boundaries

Do not create a generic GUI utility module. It would obscure ownership and risks
another oversized file. Keep pure transformations in their current domain module,
and create a narrowly named sibling controller/view module only when keeping the
owner file below the repository's ~800-line limit requires it.

| Component | Target split | State contract |
|---|---|---|
| Export | Module-local cards plus an `ExportTabController` if callbacks need shared dialog/widget references. | Controller owns UI references only; export payload construction continues through `build_export_source_from_gui` and existing safe-output helpers. |
| Per-exam | Extract card and slider-row builders; retain the section's refresh registration in one obvious owner. | `state.loaded_exam_meta` remains the source of truth. All transforms go through existing helpers and refresh the same cross-tab callbacks. |
| Calculate | Separate pre-calculation summary, confirmation, and calculation-run controller. | Preserve `PageContext` drawer references and the operation guard; calculation state remains in `state`. |
| Data | Extract table column/row projection and export-dialog builder from the tab layout. | Preserve the raw-versus-normalized choice, neutralization before export, and table refresh contract. |
| Geometry preview | Keep it pure. Extract small predicates/text-fragment helpers from `geometry_vendor_notice`; do not move it into the Geometry tab module. | Input remains metadata plus explicit overrides; return text only and retain the existing compatibility import from `geometry.py`. |
| Import preview | Introduce an `ImportPreviewController` and small builders for metadata, sheet picker, coordinate controls, and sample/mapping tables. | The controller holds widget references; parsing and transforms stay in `helpers`, and each event performs the existing refresh/invalidation sequence. |

Avoid an import cycle: a sibling builder/controller module may import
`PageContext`, `state`, and domain helpers, but must not import its owning tab
module. Use explicit state and controller arguments rather than reaching back
through a tab's closure.

---

## 2. Complexity Budget and Completion Rule

The numbers are maximum targets, not an assertion that extracting code
automatically makes it compliant. After implementation, query SonarQube to prove
that each extracted helper also remains below the configured threshold.

| Target | Budget |
|---|---:|
| Each public tab/section builder | <= 8 |
| Export/calculate/import-preview controller action | <= 12 |
| Per-exam card/slider builder | <= 12 |
| Data projection/export helper | <= 10 |
| `geometry_vendor_notice` and its predicates | <= 8 |
| Any other extracted helper | <= 12 |

**Per-component acceptance:** the named baseline finding is resolved, no new
`S3776` finding is introduced by the extraction, the owner and each new Python
file remain below the repository size limit, and no public import or `PageContext`
refresh callback silently disappears.

---

## 3. Behaviour Contracts

- **Export:** preserve JSON/HTML/PNG and rich-report choices, identifier opt-in,
  browser download versus native save behaviour, safe error reporting, and the
  existing calculation-done enablement state. A refactor must not expose raw
  source identifiers or paths in a notification.
- **Per-exam:** keep the active-exam selection, patient/table-origin edits,
  transform flags, result invalidation, and refreshes of the event table, import
  preview, per-exam panel, and Geometry tab in the same order/effect.
- **Calculate:** preserve below-floor-kVp prompt/cancel semantics, prevention of
  duplicate operations, progress/error state, and drawer PSD/run-button updates.
- **Data:** retain displayed-column labels, raw/normalized toggle semantics,
  per-exam tagging, and privacy-neutralized CSV/TXT/XLSX exports.
- **Geometry preview:** retain vendor warnings exactly for fallback, GE, Philips,
  manual Tx/Tz swap, and axis-flip cases; preserve a no-warning result for the
  same metadata.
- **Import preview:** preserve sheet re-parse behaviour, file/schema guards,
  one-exam-only coordinate controls, reset-results behaviour, and all refreshes
  after sheet or transform changes. `upload.py` owns upload locking and temporary
  files; this widget must not duplicate that lifecycle.

Before extracting a closure, add or identify a test that observes its behaviour.
Use helper-level unit tests for pure formatting/projection logic and NiceGUI user
tests for bindings, timers, modal/dialog interactions, and async handlers.

---

## 4. Reviewable PR Sequence and Verification

1. **Pure helpers first:** refactor `geometry_vendor_notice` and Data projection
   helpers, with targeted unit tests.
2. **Stateful settings/results actions:** refactor per-exam and Calculate while
   pinning state mutation and `PageContext` refresh contracts.
3. **Import/export boundaries:** refactor Import Preview and Export separately so
   sheet parsing, output privacy, and native/browser behaviour can each be
   reviewed in isolation.

Run the narrow tests that correspond to the changed component, then the GUI
suite for every stateful tab change:

```bash
uv run pytest tests/unittests/test_gui_data_labels.py \
  tests/unittests/test_gui_multi_exam_geometry_offsets.py \
  tests/unittests/test_gui_offset_reset.py \
  tests/unittests/test_gui_rdsr_df.py \
  tests/unittests/test_gui_temp_uploads.py \
  tests/unittests/test_export_payload.py
uv run pytest tests/gui/test_gui_flows.py \
  tests/gui/test_gui_security.py \
  tests/gui/test_gui_results_refresh.py \
  tests/gui/test_results_per_exam_dosemap.py
uv run ruff check src/mypyskindose/gui tests
uv run basedpyright
```

Finish each PR with the local SonarQube scan described in the parent plan. A
passing unit-test run alone does not demonstrate that the complexity finding was
removed.
