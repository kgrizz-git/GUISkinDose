# Harness Engineering Improvement Plan

_Date: 2026-06-06_

This document assesses MyPySkinDose against OpenAI's harness engineering principles (from [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/)) and provides a concrete plan to close gaps.

## Executive summary

MyPySkinDose already follows many harness engineering principles well:
- ✅ Short `AGENTS.md` as a table of contents (not an encyclopedia)
- ✅ Structured `dev-docs/` directory as the system of record
- ✅ Source-of-truth map with clear pointers
- ✅ CI validation on multiple platforms
- ✅ Golden rules documented
- ✅ Validation commands documented

Key gaps to address:
- ✅ CI runs all checks documented under **Full checks** in `HARNESS_ENGINEERING.md` (Phase 3)
- ✅ Doc-freshness script and CI link check (Phase 1; stale-pattern scan is advisory)
- ✅ Layer dependency rules documented and partially enforced in CI via structural tests (Phase 4)
- ⚠️ Plans lack a standardized active/completed lifecycle (see `dev-docs/plans/`)
- ⚠️ Supply-chain tooling partially adopted (dependabot done; gitleaks/grype/basedpyright deferred)
- ⚠️ No GUI smoke-test harness (NiceGUI exists; automated validation does not)

---

## Detailed assessment

### 1. AGENTS.md as a map, not encyclopedia ✅ STRONG

**OpenAI principle:** A short `AGENTS.md` (~100 lines) serves as a table of contents with pointers to deeper sources of truth.

**Current state:**
- `AGENTS.md` is ~90 lines, well-structured with clear sections
- Points to `dev-docs/` for detailed documentation
- Contains quick orientation (entry point, key files, run modes)
- Documents conventions and current development focus

**Verdict:** This is well-aligned. No changes needed.

---

### 2. Repository knowledge as system of record ✅ STRONG

**OpenAI principle:** The knowledge base lives in a structured `docs/` directory, versioned, co-located with code, and mechanically validated.

**Current state:**
- `dev-docs/` directory contains structured documentation
- Source-of-truth map in `HARNESS_ENGINEERING.md` documents locations
- Documentation is version-controlled alongside code

**Gaps:**
- ~~No mechanical validation of doc freshness or cross-links~~ — link/inventory checks via `scripts/check_doc_freshness.py` (Phase 1); stale-pattern scan is advisory
- ~~No `index.md` catalog of all documentation~~ — added in Phase 0 (`dev-docs/index.md`)
- ~~`HARNESS_ENGINEERING.md` source-of-truth map omits several existing docs~~ — expanded in Phase 0
- Plans exist in multiple places (`GUI_PLAN.md`, `TABULAR_RDSR_INPUT_PLAN.md`, `dev-docs/plans/`) but lack a standardized active/completed lifecycle

**Recommendations:**
1. Expand the source-of-truth map in `HARNESS_ENGINEERING.md` (Phase 0)
2. Add `dev-docs/index.md` as a catalog of all documentation
3. Add CI job to validate documentation structure (after doc-freshness script exists)
4. Optionally add `dev-docs/exec-plans/` with `active/` and `completed/` subdirectories — reconcile with existing `dev-docs/plans/` rather than creating a third plan home

---

### 3. Progressive disclosure ⚠️ PARTIAL

**OpenAI principle:** Agents start with a small, stable entry point and are taught where to look next, rather than being overwhelmed up front.

**Current state:**
- `AGENTS.md` provides quick orientation
- Detailed docs in `dev-docs/` with specific purposes (CODEBASE_OVERVIEW, FEATURE_INVENTORY, etc.)

**Gaps:**
- Layering and dependency rules are not documented separately from module layout
- Golden rules exist but are not cross-linked from every entry doc
- `FEATURE_INVENTORY.md` tracks feature status but is not mechanically validated against code

**Recommendations:**
1. Add a **Layering and dependency rules** section to `dev-docs/CODEBASE_OVERVIEW.md` rather than a separate root `ARCHITECTURE.md` (avoids duplicating the module map and data-flow content already there)
2. Defer `CORE_BELIEFS.md` and `QUALITY_SCORE.md` unless maintainers find `HARNESS_ENGINEERING.md` golden rules + `FEATURE_INVENTORY.md` insufficient
3. Use `FEATURE_INVENTORY.md` as the primary status ledger for doc-freshness automation

---

### 4. Mechanical enforcement of architecture ✅ PARTIAL (Phase 4)

**OpenAI principle:** Enforce invariants mechanically via custom linters and structural tests. Constraints are what allow speed without decay.

**Current state:**
- CI runs ruff, flake8 (syntax/fatal), pytest (including `test_architecture_layers.py`)
- Three layer contracts enforced: settings independence, GUI must not import `calculate_dose`, dose pipeline must not import GUI/plotting
- Layer rules documented in `dev-docs/CODEBASE_OVERVIEW.md`

**Remaining gaps:**
- No custom linters for clinical-data validation rules
- No file size limits in CI
- Golden rules 1 and 4–6 not mechanically enforced (by design in Phase 4)

**Recommendations (deferred):**
1. Add `import-linter` if contract count grows beyond pytest AST checks
2. Clinical-data validation ruff rules or pre-commit hooks
3. File size limit checks to CI

---

### 5. Doc-freshness validation ⚠️ MISSING

**OpenAI principle:** Dedicated linters and CI jobs validate that the knowledge base is up to date, cross-linked, and structured correctly. A recurring "doc-gardening" agent scans for stale documentation.

**Current state:**
- `scripts/check_doc_freshness.py` validates relative links and checkable `FEATURE_INVENTORY.md` contradictions; CI runs it on Ubuntu
- Advisory stale-pattern scan flags `not implemented`, `not wired`, `planned`, etc. (warnings only)
- No recurring doc-gardening agent yet

**Gaps:**
- Stale-pattern rules are not CI-blocking (intentional in Phase 1)
- No automated doc-gardening process (manual or agent-driven cadence only)

**Recommendations:**
1. Create `scripts/check_doc_freshness.py` (cross-ref `TO_DO.md` item: doc-freshness/harness check) that:
   - Validates relative markdown links under `AGENTS.md`, `README.md`, and `dev-docs/`
   - Flags contradictions against `FEATURE_INVENTORY.md` status tables where checkable
   - Reports (does not fail on) stale-pattern hits: `not implemented`, `not wired`, `planned`, etc.
2. Add a CI job to run doc-freshness checks (link rot and inventory contradictions should fail; pattern scan may warn initially)
3. Document a manual doc-gardening cadence (per-release minimum; weekly optional) before automating a recurring agent

---

### 6. Plans as first-class artifacts ⚠️ PARTIAL

**OpenAI principle:** Plans are treated as first-class artifacts with progress and decision logs that are checked into the repository.

**Current state:**
- Plans exist in `dev-docs/` (GUI_PLAN.md, TABULAR_RDSR_INPUT_PLAN.md, etc.)
- `dev-docs/plans/` directory for additional plans

**Gaps:**
- No standardized active/completed lifecycle for plans
- No shared plan template with progress/decision logs
- Backlog split across `TO_DO.md`, feature plans, and `dev-docs/plans/`

**Recommendations:**
1. Either migrate `dev-docs/plans/` into `dev-docs/exec-plans/active/` or treat `exec-plans/` as the lifecycle wrapper and keep topical plans in place with symlinks/pointers in `dev-docs/index.md`
2. Define a plan template with: objective, acceptance criteria, progress log, decision log
3. Keep `TO_DO.md` as the short-term scratch list; link long-running work to exec-plan files
4. Optionally create `dev-docs/exec-plans/tech-debt-tracker.md` for durable debt (supply chain, lint consolidation, semver)

---

### 7. Agent legibility ✅ GOOD

**OpenAI principle:** Anything the agent can't access in-context effectively doesn't exist. Repository-local, versioned artifacts are all it can see.

**Current state:**
- All critical documentation is in-repo (AGENTS.md, dev-docs/)
- No reliance on external Google Docs or wikis
- Code, tests, and CI are all version-controlled

**Strengths:**
- Good separation of concerns in documentation
- Clear source-of-truth map

**Minor improvements:**
- Add `references/` directory for external library documentation (like OpenAI's `nixpacks-llms.txt`, `uv-llms.txt`)
- Consider adding `LLMS.txt` files for complex external dependencies

---

### 8. Observability for validation ⚠️ MISSING (for GUI)

**OpenAI principle:** Logs, metrics, and traces are exposed to agents via a local observability stack. Agents can query logs and metrics to validate behavior.

**Current state:**
- Core calculation code produces deterministic outputs suitable for unit testing
- GUI has no automated testing infrastructure
- No observability stack for GUI validation

**Gaps:**
- No automated GUI browser/screenshot tests
- No way for agents to "drive" the GUI to validate changes
- No logging/metrics infrastructure for GUI

**Recommendations:**
1. Create `tests/gui/` smoke tests that launch NiceGUI headlessly and assert key tabs/routes render (start with import/startup, then one interaction per tab)
2. Prefer NiceGUI user-simulation or CDP-based driving over raw Selenium unless necessary
3. Add a maintainer script (e.g. `tests/scripts/launch_gui_headless.py`) for local agent validation
4. Defer a full observability stack (logs/metrics/traces) until basic smoke tests exist

---

### 9. Layered architecture enforcement ✅ STRONG (Phase 4)

**OpenAI principle:** Each business domain is divided into a fixed set of layers, with strictly validated dependency directions and limited permissible edges.

**Current state:**
- Layers L0–L8 documented in `dev-docs/CODEBASE_OVERVIEW.md` with mermaid diagram
- CI enforces three contracts via `tests/unittests/test_architecture_layers.py`
- Known legacy exception documented: `phantom_class` → `plotting` mesh helper

**Remaining:** broader contracts (e.g. plotting ↔ domain) deferred until refactors reduce legacy coupling.

---

### 10. Golden principles / taste invariants ⚠️ DOCUMENTED BUT NOT ENFORCED

**OpenAI principle:** Encode "golden principles" directly into the repository. These are opinionated, mechanical rules that keep the codebase legible and consistent.

**Current state:**
- Six golden rules documented in `HARNESS_ENGINEERING.md`
- Rules are clear and actionable
- No mechanical enforcement

**Recommendations:**
1. Create custom linters or pre-commit hooks for each golden rule:
   - Rule 1: Check that code changes include doc updates (harder)
   - Rule 2-6: Add specific lint rules where possible
2. Add CI job to validate golden rules
3. Document remediation instructions in lint error messages

---

### 11. Garbage collection / entropy management ⚠️ MISSING

**OpenAI principle:** Repositories accumulate stale artifacts, duplicated tooling, and doc drift. Periodic garbage collection keeps the harness trustworthy.

**Current state:**
- ~~Generated `src/mypyskindose.egg-info/` tracked in git~~ — untracked in Phase 2; `.gitignore` covers egg-info
- `pyproject.toml` uses semver (`25.1.1`); root `CHANGELOG.md` added in Phase 2
- `DESIGN.md` (root GUI aesthetic spec; renamed from `design.md` in Phase 0)
- ~~CI runs both flake8 and ruff with mismatched line-length policy (127 vs 120)~~ — Phase 2: flake8 limited to syntax/fatal; ruff is primary style linter (120 cols)
- ~~flake8 broad pass uses `--exit-zero` (warnings do not fail CI)~~ — removed in Phase 2
- ~~GitHub Actions uses `checkout@v2` and `setup-python@v2`~~ — upgraded to v4/v5 in Phase 2
- `TO_DO.md` lists supply-chain tooling (dependabot, gitleaks/trufflehog, grype, basedpyright) not yet adopted

**Recommendations:**
1. Remove tracked `egg-info` from version control; ensure `.gitignore` covers it
2. Add `CHANGELOG.md` and tie releases to semver (see `.github/workflows/release.yml`)
3. ~~Fix filename/reference drift (`design.md` vs `DESIGN.md`)~~ — done in Phase 0 (`design.md` → `DESIGN.md`)
4. Consolidate lint story: ruff as primary; flake8 limited to syntax/fatal errors or remove overlap
5. Upgrade GitHub Actions to current major versions
6. Adopt dependabot (and optionally gitleaks/grype) in a focused hygiene PR

---

### 12. CI ↔ harness alignment ✅ STRONG

**OpenAI principle:** Documented validation commands and CI must tell the same story; agents trust whichever runs in CI.

**Current state:** Local **Full checks** in `HARNESS_ENGINEERING.md` are mirrored in CI (see table below). Remaining CI gap: GUI smoke tests (Phase 5).

| Check | `HARNESS_ENGINEERING.md` | `.github/workflows/ci.yml` |
|---|---|---|
| `pytest` | Full checks | ✅ All platforms × Python 3.10–3.13 |
| `ruff check` | Full checks | ✅ |
| `flake8` | Not listed locally | ✅ CI only (syntax/fatal: E9,F63,F7,F82) |
| `python -m compileall` | Fast checks | ✅ All matrix cells (Phase 2) |
| `python -m build` | Full checks | ✅ Ubuntu `package-build` job (Python 3.12; Phase 3) |
| Doc-freshness / link check | `python scripts/check_doc_freshness.py` | ✅ Ubuntu job |
| GUI smoke tests | Known gap | ❌ |

**Recommendations:**
1. Add `python -m compileall src/mypyskindose` to CI (cheap, catches syntax errors early)
2. Add `python -m build` to CI on at least one matrix cell (Ubuntu + one Python version) or document it explicitly as a **release maintainer check**
3. Add doc-freshness script to CI once implemented (Phase 1)
4. Clarify in `HARNESS_ENGINEERING.md` which checks are CI-blocking vs maintainer-only until wired

---

## Prioritized roadmap

Execute in order. Each phase should update `HARNESS_ENGINEERING.md` known gaps when complete.

### Phase 0 — Harness map and doc hygiene (1 PR)

**Objective:** Make the source-of-truth map accurate before adding automation.

**Tasks:**
- [x] Expand `HARNESS_ENGINEERING.md` source-of-truth map (see table below)
- [x] Add this plan to the map
- [x] Create `dev-docs/index.md` listing every doc under `dev-docs/` with one-line purpose
- [x] Fix `design.md` / `DESIGN.md` reference drift
- [x] Link `INPUT_DATA_FLOW_AND_OFFSETS.md` from `AGENTS.md` or golden rule 2 context

**Docs to add to source-of-truth map:**

| Topic | File |
|---|---|
| Harness improvement plan | `dev-docs/HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md` |
| RDSR normalization, offsets, DataFrame contract | `dev-docs/INPUT_DATA_FLOW_AND_OFFSETS.md` |
| Vendor coordinate systems | `dev-docs/VENDOR_COORDINATE_SYSTEMS.md` |
| In-app positioning help plan | `dev-docs/POSITIONING_HELP_PLAN.md` |
| Fork vs upstream migration status | `dev-docs/MYPYSKINDOSE_MIGRATION_STATUS.md` |
| Package install and build | `dev-docs/info/PACKAGE_INSTALL.md` |
| Secondary plans | `dev-docs/plans/` |

**Acceptance criteria:** An agent reading only `AGENTS.md` → `HARNESS_ENGINEERING.md` can find all major docs without searching.

---

### Phase 1 — Doc-freshness automation (1–2 PRs)

**Objective:** Replace manual `rg` grep with a failing CI check for link rot and checkable status contradictions.

**Tasks:**
- [x] Implement `scripts/check_doc_freshness.py`
- [x] Add CI step (Ubuntu, one Python version is enough initially)
- [x] Close `TO_DO.md` doc-freshness item when merged
- [x] Document maintainer cadence in `HARNESS_ENGINEERING.md`

**Acceptance criteria:** Broken relative links in tracked docs fail CI; `FEATURE_INVENTORY.md` contradictions fail when rules are defined.

---

### Phase 2 — Repository entropy cleanup (1 PR)

**Objective:** Remove generated artifacts and align tooling expectations.

**Tasks:**
- [x] Untrack `src/mypyskindose.egg-info/`
- [x] Add `CHANGELOG.md` with entry for harness work
- [x] Align flake8/ruff policy (single line-length story)
- [x] Upgrade `actions/checkout` and `actions/setup-python`
- [x] Add `python -m compileall` to CI

**Acceptance criteria:** No generated packaging metadata in git; CI uses current action majors; changelog documents user-visible harness changes.

---

### Phase 3 — CI full-check parity (1 PR)

**Objective:** CI matches documented full checks or docs are corrected to match CI.

**Tasks:**
- [x] Add `python -m build` to CI (Ubuntu `package-build` job, Python 3.12)
- [x] Dependabot configured for pip and GitHub Actions (2026-06-06) — `.github/dependabot.yml`

**Acceptance criteria:** No undocumented gap between local full checks and CI without an explicit note in the harness doc.

---

### Phase 4 — Architecture layers (1–2 PRs)

**Objective:** Document and optionally enforce dependency direction.

**Tasks:**
- [x] Add layering section to `dev-docs/CODEBASE_OVERVIEW.md`
- [x] Evaluate `import-linter` contracts against real imports — pytest AST structural tests chosen (no new dependency); `import-linter` optional later
- [x] Add structural tests for settings independence, GUI→orchestration, and dose pipeline isolation

**Acceptance criteria:** Written layer rules exist; CI enforces at least one non-controversial contract.

---

### Phase 5 — GUI smoke harness (2+ PRs)

**Objective:** Agents and CI can verify the GUI still starts and core tabs load.

**Tasks:**
- [ ] Headless launch script under `tests/scripts/`
- [ ] Minimal smoke tests under `tests/gui/`
- [ ] Optional CI job (may start as manual/scheduled if flaky)

**Acceptance criteria:** One automated test proves GUI module imports and primary page renders without error.

---

### Phase 6 — Plan lifecycle (optional, defer)

**Objective:** Standardize long-running plans without duplicating `dev-docs/plans/`.

**Tasks:**
- [ ] Plan template in `dev-docs/exec-plans/`
- [ ] Migrate or link existing plans
- [ ] `tech-debt-tracker.md` for durable items from `TO_DO.md`

**Defer if:** Phase 0–1 index + TO_DO linking is sufficient for current team size.

---

### Phase 7 — Low priority (defer)

- `references/` or `LLMS.txt` for pydicom, NiceGUI, Plotly
- Recurring doc-gardening agent automation
- Full GUI observability stack
- Per-golden-rule custom linters (start with doc-freshness + import contracts only)

---

## Harness self-maintenance

When any phase completes, update in the **same PR**:

1. **`HARNESS_ENGINEERING.md`** — remove or revise matching known alignment gaps
2. **`AGENTS.md`** — only if agent entry behavior or doc pointers changed
3. **`FEATURE_INVENTORY.md`** — if feature status changed
4. **`dev-docs/index.md`** — if docs were added, renamed, or retired
5. **`CHANGELOG.md`** — for user-visible or maintainer-visible harness changes (once Phase 2 adds it)

---

## Success criteria

The harness improvement effort is **done enough** when:

| Criterion | Target |
|---|---|
| Source-of-truth map | Lists all major `dev-docs/` pages; no known doc omitted from Phase 0 table |
| Doc-freshness | CI fails on broken internal markdown links |
| CI parity | Documented full checks match CI or are explicitly labeled maintainer-only |
| Entropy | `egg-info` not tracked; lint line-length consistent |
| GUI validation | At least one automated smoke test for NiceGUI startup |
| Golden rules | At least rules 2–3 backed by tests/docs cross-links (`INPUT_DATA_FLOW_AND_OFFSETS.md`) |
| Plans | `TO_DO.md` harness items closed or linked to exec-plan files |

---

## What not to build yet

Avoid harness bloat:

- **Separate root `ARCHITECTURE.md`** — extend `CODEBASE_OVERVIEW.md` instead
- **`CORE_BELIEFS.md` / `QUALITY_SCORE.md`** — unless golden rules + feature inventory prove insufficient
- **Full observability stack** — until GUI smoke tests exist
- **Automated doc-gardening agent** — until `check_doc_freshness.py` exists and manual cadence is documented
- **Strict “every code change must touch docs” linter** — high false-positive rate; rely on PR checklist + feature inventory checks first

---

## Related backlog

Cross-reference `dev-docs/TO_DO.md`:

- Doc-freshness/harness check (lines ~24)
- Tabular event-table inputs (lines ~19–23) — separate feature track; doc-freshness should read status from `FEATURE_INVENTORY.md`
- Semver / supply-chain tooling (lines ~43–44) — Phase 2–3 entropy work
- GUI help and positioning docs — `POSITIONING_HELP_PLAN.md`, not harness-core

---

_Last updated: 2026-06-06 — complements `dev-docs/HARNESS_ENGINEERING.md`._

