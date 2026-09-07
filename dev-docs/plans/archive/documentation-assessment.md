# Documentation Assessment — execution plan

> **Status:** COMPLETE / ARCHIVED (2026-09-07) — all phases (0–3.5, 4) landed. The standing
> Phase 4 infrastructure (matrix + triggers) persists in
> [../../assessments/DOCUMENTATION_ASSESSMENT_2026-09-07.md](../../assessments/DOCUMENTATION_ASSESSMENT_2026-09-07.md).
> Implemented the "Documentation & Docstrings Assessment" item in `dev-docs/TO_DO.md`.

**Goal:** Verify that hub docs, docstrings, and user-facing docs match current code
behavior, fix what drifted, and leave behind a repeatable assessment record plus clear
triggers for re-running it — so docs never again need a from-scratch audit.

**Non-goals:** No docs-generator migration (see
[DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md](../../assessments/DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md)).
No prose rewrite for style; accuracy and completeness only.

---

## Scope

- **Hub docs:** `CODEBASE_OVERVIEW.md`, `FEATURE_INVENTORY.md`, `AGENTS.md`,
  `HARNESS_ENGINEERING.md` vs current behavior.
- **Docstrings:** every Python module under `src/` (module, class, method, function) —
  missing, outdated, or inaccurate.
- **User-facing docs:** `docs/source/`, `dev-docs/` (including
  `INPUT_DATA_FLOW_AND_OFFSETS.md`, `VENDOR_COORDINATE_SYSTEMS.md`,
  `INPUT_SCHEMA_DETECTION.md`), `README.md`, `CONTRIBUTING.md`,
  `SUPPORT.md`, in-app `gui_help/` pages vs actual behavior.
- Existing harness already covers: stale links/paths (`check_doc_freshness.py`), help
  coverage (`check_help_registry.py`), UI copy/glossary (`check_ui_copy.py`),
  feature traceability (`check_feature_doc_matrix.py`). This plan covers what scripts
  cannot: semantic accuracy.

## Phase 0 — Script-assisted inventory (advisory, not a gate)

- [x] Add `scripts/check_docstring_inventory.py` (stdlib `ast` only): per-file counts of
  public modules/classes/functions/methods missing docstrings under `src/`; advisory report,
  no CI failure. Reuse the `check_doc_pruning.py` output style.
- [x] Register the script in the `dev-docs/index.md` Harness table and the
  `HARNESS_ENGINEERING.md` validation-commands map when it lands.
- [x] Run it once to size Phase 2; attach the summary to the Phase 4 matrix.
  Result (2026-09-06): 137 files, 175 missing docstrings in 72 files, 0.2 s.
  Reviewed by two independent agents (approve-with-fixes; findings stderr, guard-block
  descent, pluralization, skipped-count, frozen dataclass — all applied; linters clean).
- [x] Acceptance: script runs in `<30 s`, output lists every public undocumented symbol.

## Phase 1 — Hub-doc accuracy pass

- [x] `CODEBASE_OVERVIEW.md`: settings table, class/function inventory, layering rules,
  repo layout vs code.
- [x] `FEATURE_INVENTORY.md`: status ledger vs shipped behavior; harness/CI §0.
- [x] `AGENTS.md` + `HARNESS_ENGINEERING.md`: commands, file maps, conventions vs repo.
- [x] Fix drift in place (same PR per golden rule 1); record per-doc verdict in matrix.
- [x] Acceptance: each hub doc marked accurate + dated, or fixed with the fix commit linked.
  Result (2026-09-06, commit `4b64a98`, dual-agent two-round review): CODEBASE_OVERVIEW —
  15 fixes, accurate; FEATURE_INVENTORY — 8 fixes + header re-dated, accurate; AGENTS.md —
  2 fixes, accurate; HARNESS_ENGINEERING.md — no drift found, accurate. Verdicts held for
  the Phase 4 matrix.

## Phase 2 — Docstring sweep

- [x] Walk the Phase 0 inventory file by file; fix inaccurate docstrings, add missing
  ones for public behavior, flag (don't silently rewrite) anything describing changed
  behavior for a behavior-vs-doc decision.
- [x] Keep fixes behavior-neutral: no signature or logic changes in this phase.
- [x] Acceptance: zero public undocumented symbols or an explicit accepted-gap list.
  Result (2026-09-06): **0 missing** across 137 public modules (was 175 in 72 files).
  Branch `docs/phase-2-docstring-sweep`; four commits (API/settings, pipeline/export,
  plotting, GUI). Orchestrator fixed accidental `attrs_dict` removal in
  `create_attributes_string.py`; split `geometry_builders.py` into controller/layout/view-ref
  modules after docstrings exceeded the 800-line harness limit (facade re-exports preserved).

## Phase 3 — User-facing cross-check

> **Execution checklist:** [DOCUMENTATION_PHASE3_CROSSCHECK_CHECKLIST.md](../../assessments/DOCUMENTATION_PHASE3_CROSSCHECK_CHECKLIST.md)
> (seeded from `help_registry.json`, `feature_doc_matrix.json`, and `docs/source/` layout).

Phase 3 verifies **semantic accuracy** of user-facing prose. Harness scripts (§0 of the
checklist) already enforce file existence, help wiring, and catalog shape; this phase is
the human/agent pass for “does it match behavior?”

### Workflow

1. **Preflight** — run structural checks in checklist §0; fix any red harness failures first.
2. **Cross-check** — work checklist §1–§7; mark each row `ACC` / `FIX` / `GAP` / `N/A`.
3. **Fix in place** — same PR per golden rule 1 when drift is clear; do not silently change
   behavior to match stale docs.
4. **File gaps** — unclear or large drift → `dev-docs/TO_DO.md` with owner, not drive-by scope creep.
5. **Summarize** — complete the verdict table in the checklist; Phase 4 copies counts into the
   assessment matrix.

### Checklist sections (detailed)

- [x] **§0 Harness preflight** — `check_doc_freshness`, `sync_gui_help --check`,
  `check_help_registry`, `check_ui_copy`, `check_feature_doc_matrix`, docstring inventory.
- [x] **§1 In-app help** — all 10 `help_registry.json` entries vs live GUI workflows
  (`docs/source/gui_help/*.md`).
- [x] **§2 Feature traceability** — each `feature_doc_matrix.json` row (skip `demo_phantoms`
  as retired); docs + help vs code paths listed in the matrix.
- [x] **§3 Sphinx user docs** — `docs/source/user/*`, getting-started notebook vs install/GUI/CLI.
- [x] **§4 Community + policy** — `README.md`, `CONTRIBUTING.md`, `SUPPORT.md`, `SECURITY.md`,
  `CHANGELOG.md`, privacy and license compliance docs.
- [x] **§5 Dev-docs user paths** — `INPUT_*`, `VENDOR_COORDINATE_SYSTEMS.md`, release hub.
- [x] **§6 UI copy + glossary** — `ui_copy.json` mandatory keys + glossary vs in-app labels.
- [x] **§7 CLI vs docs** — `cli_args.py` / `--help` vs README, AGENTS, and export/tabular docs.
- [x] **Verdict summary** — checklist bottom table filled; Phase 3 acceptance met.

### Acceptance

- [x] Every checklist row has a verdict (`ACC`, `FIX`, `GAP`, or `N/A` with reason).
- [x] All **FIX** items merged on the Phase 3 branch (or follow-up PR linked).
- [x] All **GAP** items filed in `dev-docs/TO_DO.md` with enough context to execute later.
- [x] No known inaccurate user-facing claims left unrecorded.

## Phase 3.5 — Close documentation GAPs (follow-up PR)

> **Scope:** documentation and harness only — **no** calculation, GUI behavior, or CLI flag changes.
> **Branch:** `docs/phase-3.5-doc-gaps` (or equivalent) after Phase 3 PR #81 merges.
> **Plan:** this section; execution tracked in `dev-docs/TO_DO.md`.

Phase 3 filed two **GAP** rows that are still user-facing debt but were intentionally deferred
from PR #81 to keep that pass reviewable and doc-only. Phase 3.5 closes them in one small PR.

### In scope

- [x] **Getting-started notebook** (Phase 3 §3 GAP) — refreshed
  `docs/source/getting_started/getting_started.ipynb` for GUISkinDose product identity, current
  `main()`/settings examples, and portable example paths; keep PySkinDose where upstream/historical.
  TO_DO: [Getting-started notebook refresh](../../TO_DO.md).
- [x] **Glossary plot-axis labels** (Phase 3 §6 GAP) — added LON/LAT/VER and PT L-R / A-P / S-I aliases
  to `dev-docs/glossary.json`; tick checklist §6 glossary row when done.
  TO_DO: [Glossary plot-axis labels](../../TO_DO.md).
- [x] Update [DOCUMENTATION_PHASE3_CROSSCHECK_CHECKLIST.md](../../assessments/DOCUMENTATION_PHASE3_CROSSCHECK_CHECKLIST.md)
  §3 and §6 verdict rows from **GAP** → **FIX** (or **ACC** after refresh).
- [x] Note Phase 3.5 completion in the Phase 4 assessment matrix when written.

### Out of scope (product backlog, not Phase 3.5)

These were discovered during Phase 3 audits; docs were corrected to match **current** behavior.
Implementation stays in `TO_DO.md` under Product Backlog / separate feature PRs:

| Item | Why deferred |
|------|----------------|
| **Native GUI optional file logging** | Requires wiring `log_file` at startup — behavior change. See [Current logging behavior](#current-logging-behavior) below. |
| **`TabularImportOptions` + CLI coordinate flags** | API/CLI feature; GUI toggles already ship via `AppState` / `exam_transforms.py`. |

### Current logging behavior

Today every entry point calls `configure_logging()` **without** `log_file`:

- **CLI** (`__main__.py`) and **GUI** (`gui/app.py` → `run_gui()`) set up the `guiskindose`
  logger tree with a **console handler only** (stderr via `logging.StreamHandler`).
- **`dprint` categories** (GUI / PROCESSING / CALCULATION / RENDERING) map to child loggers;
  levels come from optional `debug.json` in the working directory (default: categories off).
- **Module loggers** (`logging.getLogger(__name__)`) under the `guiskindose` tree also flow to
  that console once configured.
- **Optional file sink** already exists in `guiskindose.debug`: pass `log_file=` to
  `configure_logging()` to attach a `RotatingFileHandler` (~1 MiB × 4 files, fresh session
  purge, `0o600` on POSIX). **Nothing passes `log_file` today**, so no log file is written in any
  mode — including `--native` / pywebview, where stderr still exists but is easy to miss without a
  terminal.

**Redaction / privacy (stderr today; file would mirror this — see
[TO_DO.md](../../TO_DO.md) → Native GUI optional file logging):**

- There is **no separate redaction layer** on stderr or on file write. Privacy relies on value-free
  APIs (`safe_error_event`, `safe_user_error`, `safe_warning` in `guiskindose.privacy`), conventions
  on INFO/WARNING call sites (no source paths/filenames), and **file-handler level gating** (INFO
  on file unless a `dprint` category is enabled, then DEBUG).
- Error paths on GUI/CLI boundaries log operation codes and exception **types**, not exception
  messages or patient/source strings. CLI uncaught exceptions use `install_value_safe_excepthook()`.
- Opt-in `debug.json` / `dprint` DEBUG output is developer diagnostics — review before sharing;
  not treated as automatically PHI-safe.
- Enabling a native temp log file is tracked as optional product work in `TO_DO.md`, not a Phase 3
  doc-accuracy gap. README and `PRIVACY_AND_SENSITIVE_ASSETS.md` describe console-only default
  after Phase 3 §4 FIX; expand them again when file logging ships.

### Acceptance

- [x] Both Phase 3.5 TO_DO bullets complete (notebook + glossary).
- [x] Checklist §3 notebook and §6 glossary rows updated; no remaining Phase 3 **GAP** rows
  for documentation-only items.
- [x] Harness checks pass (`check_doc_freshness`, glossary/ui_copy, canonical-notebook guard, and
  focused launcher/guard tests; notebook execution smoke remains optional).
- [x] `CHANGELOG.md` entry for the user-visible notebook prose and safe local launcher.

## Phase 4 — Standing infrastructure (persists after archival)

- [x] Write the record: `dev-docs/assessments/DOCUMENTATION_ASSESSMENT_<date>.md`
  (date-stamped like `DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md`; matrix: per-doc
  verdict, docstring coverage numbers, gaps accepted, reviewer, date).
  Register it in `dev-docs/index.md`.
  Result (2026-09-07): [../../assessments/DOCUMENTATION_ASSESSMENT_2026-09-07.md](../../assessments/DOCUMENTATION_ASSESSMENT_2026-09-07.md),
  registered in the index Assessments table.
- [x] Triggers (any one fires a re-assessment of the affected area):
  1. **Pre-release** — extend `RELEASES_AND_DISTRIBUTION.md` step 4 with: "docs
     assessment current (matrix touched this cycle, or N/A with reason)".
  2. **Calculation-pipeline change** — PRs touching `calculate_dose/`,
     `corrections.py`, `geom_calc.py`, `grid_interp.py`, `input_adapters/`, or other
     geometry/dose modules must update affected hub docs + `feature_doc_matrix.json`
     (advisory impact script already warns).
  3. **Major feature** — new GUI tab, adapter, or setting must wire help registry +
     `ui_copy` + matrix + hub docs before merge.
  4. **Backstop** — `check_doc_pruning.py` review queue (30 days / 10 commits);
     the matrix carries a "last reviewed" stamp so staleness is visible.
  Result (2026-09-07): trigger 1 wired into `RELEASES_AND_DISTRIBUTION.md` step 4;
  triggers 2–4 recorded in the standing record's "Re-assessment triggers" section.
- [x] Wire the TO_DO item to this plan (done) and archive this plan when Phases 0–3.5–4 land.

## Files

- Create: `scripts/check_docstring_inventory.py`, `dev-docs/assessments/DOCUMENTATION_ASSESSMENT_<date>.md`,
  `dev-docs/assessments/DOCUMENTATION_PHASE3_CROSSCHECK_CHECKLIST.md` (Phase 3 working checklist;
  seeded from `help_registry.json`, `feature_doc_matrix.json`, `ui_copy.json`, `glossary.json`)
- Modify: hub docs + docstrings (Phases 1–3), `dev-docs/RELEASES_AND_DISTRIBUTION.md` (trigger 1),
  `dev-docs/HARNESS_ENGINEERING.md` + `dev-docs/index.md` (script registration),
  `dev-docs/TO_DO.md`
