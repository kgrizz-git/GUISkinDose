# Documentation Assessment — standing record

> **Status:** CURRENT (last reviewed 2026-09-07). This is the durable Phase 4 artifact of the
> Documentation & Docstrings Assessment (plan:
> [plans/archive/documentation-assessment.md](../plans/archive/documentation-assessment.md)).
> It persists after the execution plan is archived. Update the "last reviewed" stamp and the
> affected matrix rows whenever a trigger below fires.

**Reviewer(s):** Kevin Grizzard + independent audit agents (StepFun / MiniMax / Muse Spark,
2026-09-06–07).

**Purpose:** Record the verified accuracy state of hub docs, docstrings, and user-facing docs
so the codebase never again needs a from-scratch documentation audit. Re-assessment is
event-driven (see [Re-assessment triggers](#re-assessment-triggers)), not calendar-driven.

**Non-goals:** No docs-generator migration (tracked separately in
[DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md](DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md)).
No prose/style rewrites — accuracy and completeness only.

---

## Summary verdict

As of 2026-09-07, all hub docs, all public docstrings, and every user-facing doc row in the
Phase 3 cross-check have a recorded verdict of **accurate** or **fixed**. No documentation-only
**GAP** remains open. Two behavior-change items surfaced during the audit stay in
`dev-docs/TO_DO.md` Product Backlog (they require code changes, not doc fixes):

- **Native GUI optional file logging** — docs corrected to describe the console-only default; the
  file-sink feature itself is backlog.
- **`TabularImportOptions` + CLI coordinate-override flags** — docs corrected to describe shipped
  GUI toggles vs. unshipped API/CLI parity; the API/CLI surface is backlog.

## Docstring coverage (Phase 0 / Phase 2)

Source: `python scripts/check_docstring_inventory.py` (stdlib `ast`; advisory, not a CI gate).

| Metric | Phase 0 baseline (2026-09-06) | Current (2026-09-07) |
|--------|-------------------------------|----------------------|
| Files scanned under `src/` | 137 | 137 |
| Public modules | — | 137 |
| Public classes | — | 63 |
| Public functions | — | 286 |
| Public methods | — | 102 |
| **Missing docstrings** | **175 in 72 files** | **0 in 0 files** |
| Runtime | 0.2 s | < 1 s |

Phase 2 (`docs/phase-2-docstring-sweep`) drove missing docstrings to zero. No accepted-gap list is
needed. Re-run the inventory whenever new public symbols land under `src/`.

## Hub-doc verdicts (Phase 1)

Fixed on 2026-09-06, commit `4b64a98` (dual-agent two-round review).

| Hub doc | Verdict | Notes |
|---------|---------|-------|
| `CODEBASE_OVERVIEW.md` | Accurate (fixed) | 15 fixes: settings table, class/function inventory, layering, repo layout |
| `FEATURE_INVENTORY.md` | Accurate (fixed) | 8 fixes + header re-dated; status ledger vs shipped behavior |
| `AGENTS.md` | Accurate (fixed) | 2 fixes: commands / file maps |
| `HARNESS_ENGINEERING.md` | Accurate | No drift found |

## User-facing cross-check verdicts (Phase 3 / Phase 3.5)

Full working checklist:
[DOCUMENTATION_PHASE3_CROSSCHECK_CHECKLIST.md](DOCUMENTATION_PHASE3_CROSSCHECK_CHECKLIST.md)
(COMPLETE 2026-09-07). Counts copied from its verdict summary:

| Section | Items | ACC | FIX | GAP | N/A | Review date |
|---------|-------|-----|-----|-----|-----|-------------|
| §1 In-app help pages | 10 | 3 | 7 | 0 | 0 | 2026-09-06 |
| §2 Feature traceability | 10 | 8 | 1 | 0 | 1 | 2026-09-06 |
| §3 Sphinx user docs | 6 | 0 | 6 | 0 | 0 | 2026-09-07 |
| §4 Community + policy | 7 | 4 | 3 | 0 | 0 | 2026-09-07 |
| §5 Dev-docs user paths | 5 | 3 | 2 | 0 | 0 | 2026-09-07 |
| §6 UI copy + glossary | 5 | 4 | 1 | 0 | 0 | 2026-09-07 |
| §7 CLI vs docs | 4 | 4 | 0 | 0 | 0 | 2026-09-06 |
| **Total** | **47** | **26** | **20** | **0** | **1** | — |

The single **N/A** is `demo_phantoms` (retired; non-clinical demo STLs are not shipped).

### Phase 3.5 closeout (documentation GAPs)

Both Phase 3 documentation **GAP** rows were closed in Phase 3.5 (branch
`docs/phase-3.5-doc-gaps`, merged as PR #82):

- **Getting-started notebook** (§3) — refreshed `docs/source/getting_started/getting_started.ipynb`
  for GUISkinDose identity, current `main()`/settings examples, and portable example paths; stored
  outputs and execution counts cleared. A canonical-notebook cleanliness guard
  (`scripts/check_notebook_cleanliness.py`) now runs in pre-commit and CI, and a safe local launcher
  (`scripts/open_getting_started_notebook.py`) opens an ignored `tmp/notebooks/` copy so the tracked
  source stays clean. Verdict now **FIX** (was **GAP**).
- **Glossary plot-axis labels** (§6) — added `LON`/`LAT`/`VER` and `PT L-R` / `A-P` / `S-I`
  aliases to `dev-docs/glossary.json`. Verdict now **FIX** (was **GAP**).

## Accepted gaps

None for documentation. Two behavior-change follow-ups remain in `dev-docs/TO_DO.md` Product
Backlog (see [Summary verdict](#summary-verdict)); docs already describe current behavior
accurately, so they are not documentation gaps.

## Harness coverage that keeps this record honest

Structural drift is caught automatically; this record covers only the semantic layer.

| Concern | Enforced by |
|---------|-------------|
| Broken links / absolute paths / stale patterns | `scripts/check_doc_freshness.py` |
| In-app help coverage + wiring | `scripts/check_help_registry.py` |
| UI copy + glossary catalog | `scripts/check_ui_copy.py` |
| Feature ↔ doc traceability | `scripts/check_feature_doc_matrix.py` |
| GUI help mirror sync | `scripts/sync_gui_help.py --check` |
| Public docstring coverage (advisory) | `scripts/check_docstring_inventory.py` |
| Canonical getting-started notebook cleanliness | `scripts/check_notebook_cleanliness.py` |
| Stale active plans/assessments (advisory queue) | `scripts/check_doc_pruning.py` |

## Re-assessment triggers

Any one of these fires a re-assessment of the affected area; update the relevant matrix rows and
the "last reviewed" stamp at the top of this file.

1. **Pre-release** — release checklist step 4 in
   [RELEASES_AND_DISTRIBUTION.md](../RELEASES_AND_DISTRIBUTION.md) requires confirming this
   assessment is current (matrix touched this cycle, or explicitly N/A with a reason).
2. **Calculation-pipeline change** — PRs touching `calculate_dose/`, `corrections.py`,
   `geom_calc.py`, `grid_interp.py`, `input_adapters/`, or other geometry/dose modules must update
   the affected hub docs and `feature_doc_matrix.json` (the advisory impact check already warns).
3. **Major feature** — a new GUI tab, input adapter, or user-facing setting must wire the help
   registry, `ui_copy.json`, `feature_doc_matrix.json`, and the affected hub docs before merge.
4. **Backstop** — the `check_doc_pruning.py` review queue (30 days / 10 commits) surfaces staleness;
   the "last reviewed" stamp above makes it visible.
