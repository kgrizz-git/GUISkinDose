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
- ⚠️ No mechanical doc-freshness validation (only manual checklist)
- ⚠️ No recurring "doc-gardening" agent process
- ⚠️ No structural tests for architecture enforcement
- ⚠️ No quality scoring or domain grading
- ⚠️ Plans not treated as first-class versioned artifacts
- ⚠️ No execution plans with progress/decision logs
- ⚠️ Missing `ARCHITECTURE.md` as a top-level map
- ⚠️ No observability stack for GUI testing

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
- No mechanical validation of doc freshness or cross-links
- No `index.md` files to catalog and index design documentation
- Plans exist but not in a structured `exec-plans/` directory

**Recommendations:**
1. Add `dev-docs/index.md` as a catalog of all documentation
2. Create `dev-docs/exec-plans/` with `active/` and `completed/` subdirectories
3. Add CI job to validate documentation structure

---

### 3. Progressive disclosure ⚠️ PARTIAL

**OpenAI principle:** Agents start with a small, stable entry point and are taught where to look next, rather than being overwhelmed up front.

**Current state:**
- `AGENTS.md` provides quick orientation
- Detailed docs in `dev-docs/` with specific purposes (CODEBASE_OVERVIEW, FEATURE_INVENTORY, etc.)

**Gaps:**
- Missing `ARCHITECTURE.md` as a top-level architectural map
- No explicit "core beliefs" or operating principles document
- No quality document grading each domain

**Recommendations:**
1. Create `ARCHITECTURE.md` at repo root for package layering and domain overview
2. Add `dev-docs/CORE_BELIEFS.md` for agent-first operating principles
3. Add `dev-docs/QUALITY_SCORE.md` grading each product domain

---

### 4. Mechanical enforcement of architecture ⚠️ PARTIAL

**OpenAI principle:** Enforce invariants mechanically via custom linters and structural tests. Constraints are what allow speed without decay.

**Current state:**
- CI runs ruff and flake8 linting
- Tests run on every push/PR
- Cross-platform matrix (Windows, macOS, Linux)

**Gaps:**
- No structural tests enforcing dependency direction
- No custom linters for domain-specific rules (e.g., clinical-data validation)
- No file size limits or naming convention enforcement beyond standard linters
- Golden rules are documented but not mechanically enforced

**Recommendations:**
1. Create structural tests to enforce architecture constraints
2. Add custom ruff rules or pre-commit hooks for:
   - Clinical-data validation requirements
   - Documentation update requirements for code changes
3. Add file size limit checks to CI

---

### 5. Doc-freshness validation ⚠️ MISSING

**OpenAI principle:** Dedicated linters and CI jobs validate that the knowledge base is up to date, cross-linked, and structured correctly. A recurring "doc-gardening" agent scans for stale documentation.

**Current state:**
- Manual search command documented: `rg -n "not implemented|TODO|planned..." AGENTS.md README.md dev-docs`
- No automated validation
- No recurring cleanup process

**Gaps:**
- No CI job for doc-freshness checking
- No automatic detection of stale references
- No doc-gardening process (manual or automated)

**Recommendations:**
1. Create a script `scripts/check_doc_freshness.py` that:
   - Scans for stale patterns (TODO, not implemented, planned)
   - Checks that documented features exist in code
   - Validates cross-links in documentation
2. Add CI job to run doc-freshness checks
3. Document a doc-gardening cadence (weekly or per-release)

---

### 6. Plans as first-class artifacts ⚠️ PARTIAL

**OpenAI principle:** Plans are treated as first-class artifacts with progress and decision logs that are checked into the repository.

**Current state:**
- Plans exist in `dev-docs/` (GUI_PLAN.md, TABULAR_RDSR_INPUT_PLAN.md, etc.)
- `dev-docs/plans/` directory for additional plans

**Gaps:**
- No structured `exec-plans/` directory with `active/` and `completed/`
- No standardized plan format with progress/decision logs
- No tech-debt tracker as a versioned artifact

**Recommendations:**
1. Create `dev-docs/exec-plans/active/` and `dev-docs/exec-plans/completed/`
2. Define plan template with:
   - Objective
   - Acceptance criteria
   - Progress log (date, status, blockers)
   - Decision log (choices made, rationale)
3. Create `dev-docs/exec-plans/tech-debt-tracker.md`

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
1. Add Playwright or Selenium tests for GUI smoke tests
2. Create a script to launch GUI in headless mode for validation
3. Consider adding Chrome DevTools Protocol integration for agent-driven GUI testing (advanced)

---

### 9. Layered architecture enforcement ⚠️ PARTIAL

**OpenAI principle:** Each business domain is divided into a fixed set of layers, with strictly validated dependency directions and limited permissible edges.

**Current state:**
- Code is organized into logical modules (settings, plotting, calculate_dose, etc.)
- No explicit layer definitions or dependency direction enforcement
- No structural tests to prevent circular dependencies or layer violations

**Recommendations:**
1. Document the intended layer structure in `ARCHITECTURE.md`
2. Create structural tests using `import-linter` or similar to enforce:
   - No circular imports
   - GUI code doesn't directly import calculation internals
   - Settings remain independent of runtime code
3. Add layer violation checks to CI

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

