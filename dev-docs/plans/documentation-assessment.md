# Documentation Assessment — execution plan

> **Status:** ACTIVE — implements the "Documentation & Docstrings Assessment" item in
> `dev-docs/TO_DO.md` (Active Work). Archive to `dev-docs/plans/archive/` when all
> phases land; the Phase 4 infrastructure (matrix + triggers) persists after archival.

**Goal:** Verify that hub docs, docstrings, and user-facing docs match current code
behavior, fix what drifted, and leave behind a repeatable assessment record plus clear
triggers for re-running it — so docs never again need a from-scratch audit.

**Non-goals:** No docs-generator migration (see
[DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md](../assessments/DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md)).
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

- [ ] Walk the Phase 0 inventory file by file; fix inaccurate docstrings, add missing
  ones for public behavior, flag (don't silently rewrite) anything describing changed
  behavior for a behavior-vs-doc decision.
- [ ] Keep fixes behavior-neutral: no signature or logic changes in this phase.
- [ ] Acceptance: zero public undocumented symbols or an explicit accepted-gap list.

## Phase 3 — User-facing cross-check

- [ ] `docs/source/` (incl. `gui_help/` source), `README.md`, `CONTRIBUTING.md`,
  `SUPPORT.md` vs GUI/CLI behavior; GUI tooltips covered by `ui_copy.json` scope check.
- [ ] Acceptance: discrepancies fixed or filed as follow-up TO_DO items with owners.

## Phase 4 — Standing infrastructure (persists after archival)

- [ ] Write the record: `dev-docs/assessments/DOCUMENTATION_ASSESSMENT_<date>.md`
  (date-stamped like `DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md`; matrix: per-doc
  verdict, docstring coverage numbers, gaps accepted, reviewer, date).
  Register it in `dev-docs/index.md`.
- [ ] Triggers (any one fires a re-assessment of the affected area):
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
- [ ] Wire the TO_DO item to this plan (done) and archive this plan when Phases 0–4 land.

## Files

- Create: `scripts/check_docstring_inventory.py`, `dev-docs/assessments/DOCUMENTATION_ASSESSMENT_<date>.md`
- Modify: hub docs + docstrings (Phases 1–3), `dev-docs/RELEASES_AND_DISTRIBUTION.md` (trigger 1),
  `dev-docs/HARNESS_ENGINEERING.md` + `dev-docs/index.md` (script registration),
  `dev-docs/TO_DO.md`
