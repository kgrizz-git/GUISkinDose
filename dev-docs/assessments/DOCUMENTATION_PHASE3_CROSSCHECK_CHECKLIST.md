# Phase 3 user-facing documentation cross-check — execution checklist

> **Status:** IN PROGRESS — working artifact for
> [documentation-assessment.md](../plans/documentation-assessment.md) Phase 3.
> Fill verdicts here during the pass; Phase 4 rolls summaries into
> `DOCUMENTATION_ASSESSMENT_<date>.md`.

**Started:** 2026-09-06  
**Reviewer(s):** _(fill on completion)_  
**Branch:** `docs/phase-3-user-facing-cross-check`

## How to use this checklist

1. Run **§0 Harness preflight** first — fixes broken links, missing help wiring, and
   catalog drift before semantic review.
2. Work **§1–§7** in any order; each item needs a **verdict**:
   - **Accurate** — prose matches current GUI/CLI behavior (note review date).
   - **Fixed** — drift corrected in the same PR (link commit).
   - **Gap filed** — intentional deferral; add a line to `dev-docs/TO_DO.md` with owner.
   - **N/A** — retired feature or doc not user-facing (one-line reason).
3. Do **not** rewrite for style; accuracy and completeness only (same rule as Phases 1–2).
4. When a fix changes behavior descriptions, cross-check the linked **code** and **tests**
   listed in `feature_doc_matrix.json` for that feature.
5. Record blockers in the **Verdict summary** table at the bottom.

**Verdict legend:** `ACC` | `FIX` | `GAP` | `N/A` — use exactly one code in each row's **Verdict** column; add review date in **Notes** for `ACC`.

**Registries (source of truth for seeding):** [help_registry.json](../help_registry.json),
[feature_doc_matrix.json](../feature_doc_matrix.json), [ui_copy.json](../ui_copy.json),
[glossary.json](../glossary.json).

---

## §0 — Harness preflight (structural)

These checks catch missing files and wiring; they do **not** prove semantic accuracy.

- [x] `python scripts/check_doc_freshness.py` _(2026-09-06 — pass)_
- [x] `python scripts/sync_gui_help.py --check` _(2026-09-06 — pass)_
- [x] `python scripts/check_help_registry.py` _(2026-09-06 — pass)_
- [x] `python scripts/check_ui_copy.py` _(2026-09-06 — pass)_
- [x] `python scripts/check_feature_doc_matrix.py` _(2026-09-06 — pass)_
- [x] `python scripts/check_docstring_inventory.py` _(2026-09-06 — 0 missing)_

---

## §1 — In-app help (`docs/source/gui_help/`)

Source of truth for mirrored pages under `src/guiskindose/gui/help/`. Compare each page
to the live GUI tab/workflow and the wired `HelpButton` entry in `help_registry.json`.

| ID | Help page | GUI wiring | Verdict (`ACC`/`FIX`/`GAP`/`N/A`) | Notes / fix commit |
|----|-----------|------------|-----------------------------------|-------------------|
| `upload` | [upload_workflow.md](../../docs/source/gui_help/upload_workflow.md) | `upload_builders.py` | **FIX** | 2026-09-06 — coord toggle scope + example auto-load (StepFun audit) |
| `data` | [data_table_workflow.md](../../docs/source/gui_help/data_table_workflow.md) | `data.py` | **ACC** | 2026-09-06 — StepFun audit |
| `settings_positioning` | [positioning_offsets.md](../../docs/source/gui_help/positioning_offsets.md) | `settings.py` | **FIX** | 2026-09-06 — removed nonexistent Rotation control row |
| `settings_phantom_preview` | [phantom_preview.md](../../docs/source/gui_help/phantom_preview.md) | `settings.py`, `phantom_preview*.py` | **ACC** | 2026-09-06 — StepFun audit |
| `settings_below_floor_kvp` | [below_floor_kvp.md](../../docs/source/gui_help/below_floor_kvp.md) | `settings.py`, `calculate.py`; policy in `geom_calc.py` | **ACC** | 2026-09-06 — StepFun audit |
| `settings_kerma_meter_correction` | [kerma_meter_correction.md](../../docs/source/gui_help/kerma_meter_correction.md) | `settings.py`, `calculate.py` | **FIX** | 2026-09-06 — Results tab shows uncorrected kerma |
| `geometry` | [geometry_workflow.md](../../docs/source/gui_help/geometry_workflow.md) | `geometry_layout_builders.py`, `geometry_builders.py` | **FIX** | 2026-09-06 — event stepper 1-based; table-origin key names |
| `calculate` | [calculation_workflow.md](../../docs/source/gui_help/calculation_workflow.md) | `calculate.py` | **FIX** | 2026-09-06 — `below_floor_kvp_manual` setting name |
| `results` | [results_workflow.md](../../docs/source/gui_help/results_workflow.md) | `results_builders.py` | **FIX** | 2026-09-06 — dose map dialog is modal, not full-screen |
| `export` | [export_workflow.md](../../docs/source/gui_help/export_workflow.md) | `export.py` | **ACC** | 2026-09-06 — StepFun audit |

---

## §2 — Feature traceability (`feature_doc_matrix.json`)

For each shipped feature, read every listed **doc** and **help** page against the **code**
paths. Skip or mark **N/A** for retired rows.

| Feature key | Status | Docs to verify | Help to verify | Code spot-check | Verdict | Notes / TO_DO |
|-------------|--------|----------------|----------------|-----------------|---------|---------------|
| `tabular_input` | shipped | `INPUT_SCHEMA_DETECTION.md`, `INPUT_DATA_FLOW_AND_OFFSETS.md`, `INPUT_FIELD_REFERENCE.md`, `FEATURE_INVENTORY.md`, `AGENTS.md` | `upload_workflow.md` | `input_adapters/`, `upload.py`, `import_preview.py` | | |
| `vendor_coordinates` | shipped_with_open_validation | `VENDOR_COORDINATE_SYSTEMS.md`, `INPUT_DATA_FLOW_AND_OFFSETS.md`, `AGENTS.md` | `geometry_workflow.md`, `positioning_offsets.md` | `helpers.py`, `exam_transforms.py`, adapters | | Open validation items → TO_DO if still true |
| `below_floor_kvp` | shipped | `FEATURE_INVENTORY.md`, `AGENTS.md` | `below_floor_kvp.md`, `calculation_workflow.md` | `geom_calc.py`, `calculate.py`, `settings.py` | | |
| `kerma_meter_correction` | shipped | `FEATURE_INVENTORY.md`, `CODEBASE_OVERVIEW.md`, `CHANGELOG.md` | `kerma_meter_correction.md` | `kerma_correction.py`, calculate/settings tabs | | No standalone operator dev-doc beyond help + inventory — file **GAP** if drift found |
| `body_habitus_scaling` | shipped | `AGENTS.md`, `FEATURE_INVENTORY.md`, `CHANGELOG.md` | `positioning_offsets.md`, `phantom_preview.md` | `phantom_class.py`, settings + preview | | |
| `arms_down_phantoms` | shipped | `FEATURE_INVENTORY.md`, `ADDITIONAL_PHANTOMS.md`, archived plan + assessment | `phantom_preview.md` | `phantom_mesh_names.py`, catalog | | |
| `settings_phantom_preview` | shipped | `FEATURE_INVENTORY.md`, `SETTINGS_PHANTOM_PREVIEW_PLAN.md`, `CHANGELOG.md` | `phantom_preview.md`, `positioning_offsets.md` | `phantom_preview_controller.py`, settings tab | | |
| `demo_phantoms` | retired | _(archive docs only)_ | `phantom_preview.md` | — | **N/A** | Retired; grep help for demo/fun mesh names (`steamboat`, `popeye`, etc.) |
| `rich_exports` | shipped_with_leftovers | `RICH_EXPORT_PLAN.md`, `FEATURE_INVENTORY.md`, `CHANGELOG.md` | `export_workflow.md` | `export/`, `export.py`, CLI | | Leftovers → GAP or FIX |
| `dose_map_per_exam` | shipped | `FEATURE_INVENTORY.md`, `AGENTS.md` | `results_workflow.md` | `results.py`, `figures.py` | | |

---

## §3 — Sphinx / published user docs (`docs/source/user/`)

| Doc | Verdict | Cross-check against |
|-----|---------|---------------------|
| [install.md](../../docs/source/user/install.md) | | `pyproject.toml` extras (`gui`, `dev`, `docs`), `uv`/`pip` install paths |
| [user_guide.md](../../docs/source/user/user_guide.md) | | GUI tabs, CLI `--mode`, example RDSR paths, settings JSON |
| [description.md](../../docs/source/user/description.md) | | Product scope, PSD output, non-FDA disclaimer |
| [background.md](../../docs/source/user/background.md) | | Physics/correction narrative vs `corrections.py` / FEATURE_INVENTORY |
| [contribute.md](../../docs/source/user/contribute.md) | | Overlap with root `CONTRIBUTING.md`; keep consistent |
| [getting_started/getting_started.ipynb](../../docs/source/getting_started/getting_started.ipynb) | | `main()` API, example file paths, modes in `settings_example.json` |

---

## §4 — Community and policy files (repo root)

| Doc | Verdict (`ACC`/`FIX`/`GAP`/`N/A`) | Cross-check against |
|-----|-----------------------------------|---------------------|
| [README.md](../../README.md) | | Install, GUI launch, CLI one-liner, links, version badge source |
| [CONTRIBUTING.md](../../CONTRIBUTING.md) | | Dev setup, hooks, privacy gates, unsolicited-PR policy |
| [SUPPORT.md](../../SUPPORT.md) | | Issue vs Discussion routing, intended use disclaimer |
| [SECURITY.md](../../SECURITY.md) | | Vulnerability reporting path vs GitHub security advisories |
| [CHANGELOG.md](../../CHANGELOG.md) | | User-facing release notes vs shipped behavior (recent `[Unreleased]` / `[1.0.0]`) |
| [PRIVACY_AND_SENSITIVE_ASSETS.md](../PRIVACY_AND_SENSITIVE_ASSETS.md) | | Upload/export privacy copy in GUI vs policy |
| [LICENSE_COMPLIANCE.md](../LICENSE_COMPLIANCE.md) | | Third-party notices workflow vs `NOTICES` / `pyproject.toml` |

---

## §5 — Dev-docs user paths (maintainer-written, user-relevant)

| Doc | Verdict | Cross-check against |
|-----|---------|---------------------|
| [INPUT_SCHEMA_DETECTION.md](../INPUT_SCHEMA_DETECTION.md) | | `--input-schema`, adapter scoring, GUI schema selector |
| [INPUT_DATA_FLOW_AND_OFFSETS.md](../INPUT_DATA_FLOW_AND_OFFSETS.md) | | Normalization, per-exam meta, Geometry/Settings sliders |
| [INPUT_FIELD_REFERENCE.md](../INPUT_FIELD_REFERENCE.md) | | Column names vs adapters + Data table |
| [VENDOR_COORDINATE_SYSTEMS.md](../VENDOR_COORDINATE_SYSTEMS.md) | | Vendor normalizer, `INPUT_DATA_FLOW_AND_OFFSETS.md`, GUI Tx↔Tz toggle scope |
| [RELEASES_AND_DISTRIBUTION.md](../RELEASES_AND_DISTRIBUTION.md) | | PyPI identity `guiskindose`, version 1.0.0 story |

---

## §6 — UI copy catalog (`ui_copy.json` + glossary)

**Scope pass:** every `copy_text("…")` key used in GUI code should either appear in
`ui_copy.json` or be filed as a **GAP** to add. High-risk strings (privacy, PHI, clinical
warnings) are mandatory.

**Mandatory catalog keys (must match owner file text):** `upload.privacy_notice`,
`onboarding.privacy_notice`, `export.include_identifiers.label`,
`export.include_identifiers.explanation`, `per_exam.tx_tz_swap.tooltip`,
`settings.phantom_preview.caption`.

- [x] Run `python scripts/check_ui_copy.py` _(2026-09-06 — pass)_
- [ ] Review each cataloged key in [ui_copy.json](../ui_copy.json) against owner file text
- [ ] Spot-check uncatalogued user-visible strings in `gui/tabs/`, `gui/app.py`, widgets
- [ ] [glossary.json](../glossary.json) terms match in-app labels (LON/LAT/VER, exam, offset)

| Area | Verdict | Notes |
|------|---------|-------|
| Catalog completeness | | |
| Privacy / PHI notices (`upload.privacy_notice`, `onboarding.privacy_notice`, export identifiers) | | |
| Per-exam correction tooltips (`per_exam.*`) | | |
| Settings phantom preview captions | | |

---

## §7 — CLI vs documentation

| Surface | Verdict | Cross-check against |
|---------|---------|---------------------|
| `python -m guiskindose --help` | | [cli_args.py](../../src/guiskindose/cli_args.py), `main.py` modes |
| Tabular flags (`--input-schema`, `--sheet-name`, `--input-preview-only`) | | `AGENTS.md`, `INPUT_SCHEMA_DETECTION.md`, upload help |
| `--mode gui` / `--native` | | README, user_guide, FEATURE_INVENTORY |
| Export CLI subcommands / formats | | [cli_args.py](../../src/guiskindose/cli_args.py), `export_workflow.md`, `tests/unittests/test_export_cli.py` |

---

## Verdict summary (for Phase 4 matrix)

| Section | Items | ACC | FIX | GAP | N/A | Review date |
|---------|-------|-----|-----|-----|-----|-------------|
| §1 Help pages | 10 | 4 | 6 | 0 | 0 | 2026-09-06 |
| §2 Features | 10 | | | | | |
| §3 Sphinx user | 6 | | | | | |
| §4 Community + policy | 7 | | | | | |
| §5 Dev-docs user | 5 | | | | | |
| §6 UI copy | 4 | | | | | |
| §7 CLI | 4 | | | | | |

**Phase 3 acceptance:** all **GAP** rows have a linked `TO_DO.md` bullet; all **FIX**
rows merged; summary table complete.
