# Sonar gate repair + privacy-gated external scans

_Status: **Archived 2026-09-03** — implementation complete (PR #32). The
`cloud-scans-main` job this plan describes (Safety/Codecov main-only) was retired in
GUISkinDose 1.0.0 when the `safety` dev dependency was dropped_
_Created: 2026-07-25_
_Branch: `plan/sonar-privacy-gated-scans`_
_Owners: Maintainers; coding agents may implement phases in order_
_Related: [HARNESS_ENGINEERING.md](../../HARNESS_ENGINEERING.md), [PRIVACY_AND_SENSITIVE_ASSETS.md](../../PRIVACY_AND_SENSITIVE_ASSETS.md), [SONARQUBE_LOCAL.md](../../SONARQUBE_LOCAL.md), [sonarqube_remediation_plan.md](../sonarqube_remediation_plan.md)_

> **For agentic workers:** implement phase-by-phase with checkbox tracking. Prefer
> `superpowers:subagent-driven-development` or `superpowers:executing-plans` after the plan is approved.
> Do not mark a checklist item complete until it is fully done and verified.

**Goal:** Fix SonarCloud security findings, restore privacy-gated Sonar analysis on pull
requests (not only `main`), and ensure Semgrep (OWASP), SonarCloud, and CodeRabbit only run
after local privacy admission gates pass. Improve GUI test coverage fed into Sonar. If the
org **cannot** customize the quality gate (plain Free plan stuck on Sonar way ≥80% new
coverage), **remove the README Sonar quality-gate badge** rather than advertising a
permanently failed status; keep Sonar as an internal CI signal.

**Architecture:** Split CI into a fast **privacy-gates** job, then gate third-party / network
SAST and review tools on that job’s success. Fix the two open HIGH Sonar security findings in
dev scripts. Keep GUI in Sonar coverage: feed `tests/gui/` into the Sonar `coverage.xml` and
add targeted GUI tests. **Coverage gate policy (D2):** if the org plan allows custom quality
gates (OSS / Team / Enterprise), set temporary **new_coverage ≥ 50%** and raise later
(50% → 60% → 80%); if not (plain Free / read-only Sonar way at 80%), **remove the README
badge** and treat Sonar coverage as best-effort until tests approach 80%. Align **cloud**
analyzer exclusions (SonarCloud, CodeRabbit) so asset/fixture/binary paths are not uploaded;
keep **local** privacy scanners scanning source. Prefer CI-based Sonar on PR+main with
Automatic Analysis disabled. Semgrep continues as **local CLI in GitHub Actions / pre-push**
(not Semgrep Cloud).

**Tech stack:** GitHub Actions, SonarQube Cloud (`sonarqube-scan-action`), Semgrep, CodeRabbit
(GitHub App + `.coderabbit.yaml`), existing privacy scripts under `scripts/`.

## Global constraints

- Privacy-first: no third-party cloud analyzer (SonarCloud upload, CodeRabbit review of PR
  content, Semgrep registry OWASP fetch is lower risk but still gated per this plan) until
  the **privacy-gates** job succeeds on that commit/PR.
- Do not weaken `check_sensitive_content.py`, `privacy_admission.py`, or project privacy
  Semgrep (`.semgrep/mypyskindose-privacy.yml`) — those stay **inside** privacy-gates.
- Keep Codecov and Safety **main-only** unless a later decision expands them (out of scope).
- Cross-platform: workflow logic must remain portable; no OS-specific scanner behavior in `src/`.
- Plan/docs paths stay repo-relative; update `CHANGELOG.md` `[Unreleased]` and
  `dev-docs/HARNESS_ENGINEERING.md` when CI wiring changes.
- SemVer: CI/config/docs → **patch** notes in changelog; no `pyproject.toml` bump until a release.
- File size: keep workflow YAML and touched scripts under the 800-line harness limit.

---

## 0. Problem statement (2026-07-25)

### 0.1 SonarCloud badge / quality gate

Public API (`qualitygates/project_status?projectKey=kgrizz-git_MyPySkinDose`) reports
`status=ERROR` on **new code** (period mode `previous_version` since `2026-07-11`):

| Condition | Threshold | Actual | Result |
|---|---|---|---|
| `new_security_rating` | ≤ 1 (A) | **3 (C)** | FAIL |
| `new_coverage` | ≥ 80% | **17.7%** | FAIL |
| `new_reliability_rating` | ≤ 1 | 1 | OK |
| `new_maintainability_rating` | ≤ 1 | 1 | OK |
| `new_duplicated_lines_density` | ≤ 3% | 0.1% | OK |
| `new_security_hotspots_reviewed` | 100% | 100% | OK |

Open HIGH vulnerabilities (drive Security Rating C):

1. **`pythonsecurity:S8707`** — `scripts/phantom_gen/run_catalog.py:549`
   (`report_path.write_text(...)`). Taint from CLI → JSON report path. Existing
   `resolve_under_roots()` is not recognized as a sanitizer.
2. **`pythonsecurity:S8705`** — `scripts/audit_dependencies.py:127`
   (`subprocess.run([uv_bin, "audit"] + uv_args, ...)`). Taint from `sys.argv`. Existing
   control-character / whitespace checks are not recognized as a sanitizer.

Coverage drag: ~2,103 of ~2,214 uncovered new lines are under `src/guiskindose/gui/`.
Non-GUI new code is already ~80.8%. Sonar’s uploaded `coverage.xml` currently comes from
`pytest --ignore=tests/gui`, so existing GUI smoke tests do not count toward the gate.
Scripts remain in `sonar.coverage.exclusions` (dev tooling only).

GitHub check **SonarCloud Code Analysis** is failing on `main` even while the `ci` workflow
is green — Automatic Analysis (or a prior analysis) still owns the gate; CI Sonar today runs
only on `main` inside `cloud-scans-after-gates` and only after all jobs succeed.

### 0.2 Current CI ordering (relevant excerpt)

```text
ci.yml today
├── schedule-gate
├── static-analysis   ← privacy steps + OWASP semgrep + privacy semgrep + bandit + …
├── gui-smoke
├── matrix-prep → build
└── cloud-scans-after-gates   ← MAIN ONLY; coverage.xml + Codecov + Sonar + Safety
      needs: [static-analysis, gui-smoke, build]
```

Gaps vs desired state:

- Sonar does **not** run on PRs (intentionally narrowed earlier; this plan undoes that).
- OWASP Semgrep shares a job with privacy but is not a separate gated job; if we want a hard
  “privacy must pass before semgrep starts”, split jobs.
- CodeRabbit (GitHub App) auto-reviews PRs with **no** dependency on privacy CI.
- Automatic Analysis can update the quality gate independently of CI privacy gates.

### 0.3 Desired end state

```text
ci.yml target
├── schedule-gate
├── privacy-gates          ← sensitive content, admission, metadata, inventories,
│                             project privacy Semgrep (blocking)
├── static-analysis        ← needs privacy-gates; docs/help/licenses/bandit/basedpyright/…
│                             (NO OWASP semgrep)
├── owasp-semgrep          ← needs privacy-gates only (or privacy-gates + static-analysis)
├── gui-smoke              ← needs schedule-gate + privacy-gates (locked)
├── matrix-prep → build    ← build needs privacy-gates (locked)
├── sonar-scan             ← PR + main; needs privacy-gates + build (coverage); not Safety/Codecov
└── cloud-scans-main       ← MAIN ONLY: Codecov + Safety (optional rename of leftover job)

coderabbit
├── .coderabbit.yaml: reviews.auto_review.enabled: false
└── workflow: after privacy-gates success on a PR → comment `@coderabbitai review`
```

Maintainer one-time SonarCloud UI: **disable Automatic Analysis** so CI-based analysis is the
sole source of truth (already noted in `ci.yml` comments).

---

## 1. Decisions locked for this plan

| # | Decision | Choice |
|---|---|---|
| D1 | Clear Security Rating | **Code fix** sanitizers Sonar accepts (preferred); Sonar UI “False Positive” only as last resort after code attempt |
| D2 | Coverage + README badge | **Keep GUI in Sonar coverage** (no GUI exclusion). Feed `tests/gui/` into `coverage.xml` and write GUI tests. **Branch on plan capability:** (A) If custom quality gates are available → set temporary **new_coverage ≥ 50%**, raise 50→60→80 later, keep/restore badge when green. (B) If stuck on read-only **Sonar way** (80%, typical plain Free) → **remove the README Quality Gate badge** immediately so the repo does not advertise a red/failed gate we cannot tune; keep Sonar CI for security + incremental coverage; re-add the badge only when new coverage can honestly pass 80% (or after upgrading to OSS/Team with a custom gate). |
| D3 | Sonar on PRs | **Yes** — restore CI Sonar for `pull_request` and `push` to `main` after privacy + coverage generation |
| D4 | Safety / Codecov | Stay **main-only** |
| D5 | What counts as “privacy checks” | Early admission stack + **project** privacy Semgrep (`run_semgrep_privacy.py`). OWASP Semgrep is **not** a privacy check. |
| D6 | CodeRabbit | Disable auto-review; trigger only after `privacy-gates` succeeds on the PR head |
| D7 | Automatic Analysis | **Disabled by maintainer 2026-07-25** — CI-based analysis is authoritative. |
| D8 | Pre-push OWASP Semgrep | Keep local pre-push as developer convenience; CI is the privacy-ordered gate. Do not remove the hook in this plan. |
| D9 | Local CI `fail-under` | Keep matrix `coverage report --fail-under=60` on non-GUI runs (`--ignore=tests/gui`). Do not lower the local pytest coverage floor; only the SonarCloud quality-gate condition changes. |
| D10 | Semgrep Cloud vs Actions | **Semgrep Cloud App stays disabled** (user confirmed). Continue running Semgrep as **local CLI** in GitHub Actions + pre-push with `--metrics=off` and **no** `SEMGREP_APP_TOKEN`. OWASP pack still *downloads rules* from the Semgrep registry (network); analysis does not upload the repo to Semgrep Cloud. |
| D11 | Cloud scanner path exclusions | **Yes** — keep/expand shared exclusions for **third-party cloud** analyzers (SonarCloud, CodeRabbit) covering asset dirs, binaries, notebooks, logs, tabular exports, and `tests/fixtures/**`. Do **not** strip those paths from **local** privacy gates (`check_sensitive_content`, privacy Semgrep, admission) — those scanners are the containment layer. |
| D12 | Future DeepSource (and similar SaaS SAST) | **Not enabled now.** If DeepSource (or any similar cloud analyzer / PR bot) is added later, apply the **same two protections** as Sonar/CodeRabbit: (1) run / trigger only **after `privacy-gates` succeeds**, (2) configure path/file exclusions aligned with the §2c sensitive-surface list. Document in HARNESS when introduced; do not auto-review or upload before admission. |
| D13 | `gui-smoke` / `build` vs privacy | **Both wait on `privacy-gates`** (locked 2026-07-25). |
| D14 | CodeRabbit trigger | **After `privacy-gates` only** — do not wait for full CI/matrix (locked 2026-07-25). |
| D15 | Free-tier quality gate | **Confirmed untunable** (2026-07-25) — cannot lower new_coverage below Sonar way 80%. Stay on **B2-B** (no README badge). |

---

## 2. File map

| File | Role |
|---|---|
| `.github/workflows/ci.yml` | Split `privacy-gates`; move OWASP Semgrep; restore Sonar on PR+main; keep Safety/Codecov main-only |
| `.github/workflows/coderabbit-after-privacy.yml` | New: request CodeRabbit review after privacy-gates success |
| `.coderabbit.yaml` | Disable auto-review; path ignore filters aligned with Sonar cloud exclusions; manual `@coderabbitai review` escape hatch |
| `sonar-project.properties` | Leave coverage exclusions as `tests/**,scripts/**` only (GUI stays measured); keep asset/binary `sonar.exclusions` |
| `.sonarcloud.properties` | Same shared exclusions (parity); no GUI coverage exclusion |
| `scripts/phantom_gen/path_safety.py` | Strengthen / clarify sanitizer for S8707 |
| `scripts/phantom_gen/run_catalog.py` | Rebuild trusted write path after resolve |
| `scripts/audit_dependencies.py` | Allowlist rebuild of `uv audit` argv for S8705 |
| `tests/unittests/test_path_safety.py` (or extend existing) | Path confinement regressions |
| `tests/unittests/test_audit_dependencies.py` (new/extend) | Arg allowlist regressions |
| `tests/gui/test_*.py` (new/extend) | Raise line coverage on largest GUI modules (builders, calculate, export, …) |
| `dev-docs/HARNESS_ENGINEERING.md` | Document job DAG, privacy-before-cloud, Semgrep Actions vs Cloud, scanner scope |
| `README.md` | Remove Sonar quality-gate badge if custom gates unavailable (D2-B); optional re-add later |
| `dev-docs/SONARQUBE_LOCAL.md` | Document plan check (Free vs OSS), badge policy, combined coverage, exclusions |
| `dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md` | Cloud vs local scanner exclusion policy |
| `CHANGELOG.md` | Unreleased Security / Fixed / Changed notes |
| `dev-docs/index.md` | Register this plan under Master plans |
| SonarCloud Quality Gate (UI) | Only if custom gates exist: temporary `new_coverage` **50%**; else leave Sonar way and remove README badge |

---

## 2b. Semgrep today: Cloud vs Actions (answer)

| Channel | Status on this repo | What it does |
|---|---|---|
| **Semgrep Cloud / App** | Disabled (correct) | Would upload PR diffs / findings to Semgrep’s SaaS |
| **GitHub Actions (`ci.yml`)** | **Active** | Local `semgrep` CLI on the runner |
| **Pre-push hook** | **Active** | Same local CLI on developer machines |
| **Project privacy rules** | **Active** | `python scripts/run_semgrep_privacy.py` → `.semgrep/mypyskindose-privacy.yml` |

Actions commands today:

```bash
# OWASP (static-analysis job) — fetches rule pack from registry, analyzes locally
semgrep --config=p/owasp-top-ten --error --metrics=off src scripts .github/workflows docs/source/conf.py

# Privacy (same job) — fully local config file, metrics off
python scripts/run_semgrep_privacy.py
```

There is **no** `SEMGREP_APP_TOKEN` and no Semgrep Cloud GitHub App workflow. Disabling
Semgrep Cloud does **not** turn off Actions Semgrep. This plan keeps Actions Semgrep, moves
OWASP after `privacy-gates`, and keeps `--metrics=off`.

Optional hardening in Phase C: export `SEMGREP_SEND_METRICS=off` in the job env; never add
`semgrep ci` / App login.

---

## 2c. Scanner path exclusions (privacy containment) — required audit

**Principle:** exclude asset/fixture/binary paths from **third-party cloud** consumers;
keep **local** privacy gates scanning source (and admission of tracked content).

### Shared “sensitive surface” patterns (canonical list)

Use this as the checklist when reviewing each tool. Patterns match today’s Sonar
`sonar.exclusions` / `sonar.test.exclusions` intent:

| Pattern / path | Why exclude from cloud |
|---|---|
| `src/**/example_data/**` | Bundled RDSR/demo clinical-like files |
| `src/**/phantom_data/**`, `src/**/table_data/**` | Large meshes / table assets |
| `tests/fixtures/**` | Synthetic or clinical-like fixtures |
| `dev-docs/**` | Plans/assessments; not product source (Sonar already) |
| `**/*.{dcm,ipynb,log,txt}` | DICOM, notebooks, logs, free text |
| `**/*.{png,jpg,jpeg,gif,svg}` | Images (hash-gated elsewhere) |
| `**/*.{csv,tsv,xlsx,xls,json,db,sqlite,parquet}` | Tabular / DB / structured dumps |
| `**/__pycache__/**`, `**/*.pyc` | Build noise |
| `tmp/**`, `PlotOutputs/**`, `htmlcov/**`, `coverage.xml` | Runtime/coverage outputs (usually gitignored) |

Do **not** put `src/guiskindose/gui/**` on this list (coverage / review of GUI code is wanted).

### Per-tool policy (what “makes most sense”)

| Tool | Kind | Exclude the sensitive-surface list? | Notes |
|---|---|---|---|
| **SonarCloud** | Cloud upload | **Yes** — already largely via `sonar.exclusions` + `sonar.test.exclusions` | Audit for gaps vs canonical list; keep GUI in coverage; `scripts/**` stay coverage-excluded only |
| **CodeRabbit** | Cloud PR review | **Yes** — `reviews.path_filters` with quoted `!` globs | Mirror Sonar asset/fixture/binary ignores; also skip lockfiles/generated noise |
| **OWASP Semgrep** | Local Actions CLI | **Include-list, not exclude-list** | Keep scan roots = `src scripts .github/workflows docs/source/conf.py` only — do **not** expand into `example_data` / phantoms / fixtures |
| **Privacy Semgrep** | Local Actions CLI | **No broad asset exclude** | Keep `src scripts tests` so leak rules see application + test **code**; fixture *data* files are mostly non-Python |
| `check_sensitive_content` / admission | Local gates | **Never exclude** | Containment layer |

### Task B0 — audit + wire exclusions (checklist)

- [x] **B0.1** **Sonar:** Diff canonical list vs `sonar-project.properties` /
  `.sonarcloud.properties`; add any missing globs; run `check_sonar_properties.py`
- [x] **B0.2** **CodeRabbit:** Add `.coderabbit.yaml` with `reviews.auto_review.enabled: false`
  and `reviews.path_filters` excluding the sensitive-surface list (quoted `!` patterns), e.g.:

```yaml
# yaml-language-server: $schema=https://coderabbit.ai/integrations/schema.v2.json
language: en-US
reviews:
  auto_review:
    enabled: false
  path_filters:
    - "!src/**/example_data/**"
    - "!src/**/phantom_data/**"
    - "!src/**/table_data/**"
    - "!tests/fixtures/**"
    - "!dev-docs/**"
    - "!**/*.dcm"
    - "!**/*.ipynb"
    - "!**/*.log"
    - "!**/*.{png,jpg,jpeg,gif,svg,csv,tsv,xlsx,xls,db,sqlite,parquet}"
    - "!**/uv.lock"
    - "!**/__pycache__/**"
```

  (Tune exact globs to CodeRabbit’s glob rules at implement time; keep parity with Sonar intent.)

- [x] **B0.3** **OWASP Semgrep:** Confirm CI + pre-push still use the include-list roots above;
  document “do not scan asset dirs”; optionally add explicit `--exclude` for
  `**/example_data/**`, `**/phantom_data/**`, `**/table_data/**`, `tests/fixtures/**` as
  belt-and-suspenders if a future command widens the tree
- [x] **B0.4** **Privacy Semgrep:** Confirm still scans `src`/`scripts`/`tests` code paths;
  do **not** strip those for “privacy” — only consider excluding non-code under
  `tests/fixtures` if noise appears
- [x] **B0.5** Document the matrix in `PRIVACY_AND_SENSITIVE_ASSETS.md` +
  `HARNESS_ENGINEERING.md` (“Cloud vs local scanner scope”)
- [x] **B0.6** Changelog note (Changed — scanner exclusion audit / CodeRabbit path filters)

### Future SaaS scanners (DeepSource, etc.)

DeepSource is **not** in scope for this plan’s implementation PRs. If it is enabled later:

1. Gate activation / PR analysis behind **`privacy-gates` success** (same pattern as
   CodeRabbit-after-privacy / Sonar after privacy).
2. Apply **§2c sensitive-surface exclusions** in DeepSource’s ignore/exclude config (or
   equivalent path filters) so fixtures, `example_data`, phantoms, DICOM/images/tabular
   dumps are not sent for cloud analysis.
3. Prefer local or metrics-off modes where available; never weaken admission scanners to
   “make DeepSource quieter.”
4. Update `HARNESS_ENGINEERING.md` and this plan’s archive note when wired.

Treat any new third-party code analyzer the same way unless an explicit exception is approved.

---

## Phase A — Sonar security findings (clear Security Rating A)

### Task A1: Make `resolve_under_roots` a trusted path factory for report writes

**Files:**
- Modify: `scripts/phantom_gen/path_safety.py`
- Modify: `scripts/phantom_gen/run_catalog.py` (~545–549)
- Test: `tests/unittests/` (extend existing path_safety tests or add `test_run_catalog_path_safety.py`)

**Approach:** Sonar’s taint engine often ignores custom validators that return the same
`Path` object derived from tainted input. After `resolve_under_roots`, rebuild the final path
from **trusted root + relative parts** (string parts taken only from
`candidate.relative_to(matched_root)`), then `write_text` on that rebuilt path. Optionally add
a narrow helper:

```python
def trusted_path_under_roots(path: Path | str, **kwargs) -> Path:
    """Resolve under roots, then rebuild from the matched root + relative parts."""
    resolved = resolve_under_roots(path, **kwargs)
    for root in default_allowed_roots():
        root = root.resolve()
        if resolved == root or resolved.is_relative_to(root):
            return root.joinpath(*resolved.relative_to(root).parts)
    raise ValueError("path escaped allowed roots")
```

Use `trusted_path_under_roots` for the JSON report write in `run_catalog.main`.

- [x] **A1.1** Add/extend unit tests for escape rejection and trusted rebuild
- [x] **A1.2** Implement helper + switch `run_catalog` report write to it
- [x] **A1.3** Run `pytest` on the new/changed tests
- [x] **A1.4** Changelog note under `[Unreleased]` → Security/Fixed

### Task A2: Rebuild `uv audit` argv from an allowlist (S8705)

**Files:**
- Modify: `scripts/audit_dependencies.py`
- Test: new or existing unittest that imports the filter helper

**Approach:** Do not append raw `sys.argv` fragments to `subprocess.run`. Parse known safe
flags only (e.g. `--frozen`, `--locked`, and explicitly allowlisted long options with
validated values). Reject anything else. Pass a freshly built `list[str]` of literals +
validated tokens.

```python
_ALLOWED_UV_AUDIT_FLAGS = frozenset({"--frozen", "--locked"})

def build_uv_audit_argv(uv_bin: str, extra_args: list[str]) -> list[str]:
    argv = [uv_bin, "audit"]
    for arg in extra_args:
        if arg in _ALLOWED_UV_AUDIT_FLAGS:
            argv.append(arg)
            continue
        raise ValueError("unsupported or unsafe audit argument")
    # CI / local defaults already append --locked / --frozen when missing
    return argv
```

If passthrough of ignore flags is required later, add them explicitly with value validation —
do not reintroduce free-form passthrough.

- [x] **A2.1** Failing tests for rejected args / accepted `--frozen`/`--locked`
- [x] **A2.2** Implement allowlisted argv builder; wire into `subprocess.run`
- [x] **A2.3** Run tests; confirm `scripts/audit_dependencies.py` still works with no args
- [x] **A2.4** Changelog note

### Task A3: Fallback if Sonar still flags after code fix

Only if a post-merge Sonar analysis still reports S8707/S8705:

- [ ] **A3.1** Prefer SonarCloud issue disposition **False Positive** with reason linking to
  the sanitizer tests (dev CLI only; not runtime package code)
- [ ] **A3.2** Last resort: exclude `scripts/**` from `sonar.sources` (keep tests covering
  behavior). Update both property files + docs. Do **not** do this in the first PR unless
  A1/A2 fail to clear the gate after a CI scan.

---

## Phase B — Sonar coverage (keep GUI; lower gate; write tests)

### Why 50% (not 80%) as the temporary gate

Live new-code totals (~2026-07-25): **2,689** lines to cover, **475** covered → **17.7%**.
About **2,110** of those lines are under `src/guiskindose/gui/`, almost all at **0%**, because
Sonar’s `coverage.xml` is produced with `--ignore=tests/gui`.

| If GUI coverage reaches… | Approx overall new coverage |
|---|---|
| 20% | ~33% |
| 30% | ~41% |
| 40% | ~49% |
| **45%** | **~53%** (clears 50% gate) |
| 50% | ~57% |
| 60% | ~65% |

Hitting **80%** overall while keeping GUI measured would require ~**75%+** GUI line coverage
on the current new-code window — unrealistic in one PR. **50%** overall needs roughly
**≥42% of GUI new lines** covered (~876 GUI lines) after feeding `tests/gui/` into Sonar.
Raise the gate later: **50% → 60% → 80%** as milestones (track in this plan).

Local CI `fail-under=60` on non-GUI pytest stays unchanged (D9).

### Task B1: Feed GUI tests into Sonar `coverage.xml`

**Files:**
- Modify: `.github/workflows/ci.yml` (today’s `cloud-scans-after-gates`; later `sonar-scan`)
- Docs: `dev-docs/SONARQUBE_LOCAL.md`, `dev-docs/HARNESS_ENGINEERING.md`

Sonar coverage generation must install the `gui` extra and combine non-GUI + GUI runs, e.g.:

```bash
uv sync --extra dev --extra gui --locked
uv run --no-sync coverage erase
uv run --no-sync coverage run -m pytest --ignore=tests/gui
uv run --no-sync coverage run --append -m pytest tests/gui/
uv run --no-sync coverage xml
```

Keep the matrix `build` job on `--ignore=tests/gui` + `fail-under=60` (fast, no NiceGUI).
Keep `gui-smoke` as the dedicated NiceGUI job; Sonar’s combined coverage is separate.

- [x] **B1.1** Change Sonar coverage steps to `dev+gui` and `--append` GUI tests
- [x] **B1.2** Document the two-pass coverage command in `SONARQUBE_LOCAL.md`
- [x] **B1.3** Confirm `coverage.xml` includes `src/guiskindose/gui/` paths

### Task B2: Quality gate threshold **or** remove README badge

**First check (maintainer):** SonarCloud org → subscription / plan, then **Quality Gates**:
can you Create/Copy a gate and edit “Coverage on New Code”?

| Outcome | Action |
|---|---|
| **Custom gates available** (OSS / Team / Enterprise) | Set project gate `new_coverage` ≥ **50%**. Keep README badge; expect green after security + ~45% GUI coverage. Raise later 50→60→80. |
| **Read-only Sonar way only** (typical Free) | **Cannot** lower 80%. **Remove** the README badge (see below). Keep Sonar analysis in CI. Do not block the plan on badge green. |

**B2-A — lower gate to 50% (only if editable):**

- [ ] **B2.A1** Create/adjust project gate; set `new_coverage` ≥ **50**
- [ ] **B2.A2** Document gate name + raise roadmap in `SONARQUBE_LOCAL.md`
- [ ] **B2.A3** Changelog note (Changed — temporary Sonar new-coverage gate 50%)
- [ ] **B2.R1** Later: raise to **60%** when overall new coverage sustains ≥65%
- [ ] **B2.R2** Later: raise to **80%** when overall new coverage sustains ≥80%

**B2-B — remove badge (gate not editable) — SELECTED:**

- [x] **B2.B1** Delete the Quality Gate Status badge from `README.md` (done 2026-07-25 on
  `plan/sonar-privacy-gated-scans`)
- [x] **B2.B2** In `SONARQUBE_LOCAL.md` / HARNESS: note badge removed because Free/Sonar-way
  80% is not tunable; Sonar remains in CI; badge may return when coverage or plan allows
- [x] **B2.B3** Changelog note under Changed (done with badge removal)
- [ ] **B2.B4** Optional later: re-add badge only when `alert_status=OK` is sustainable

**B2-A** remains available if the org later gets editable custom gates; do not re-add a red badge.

### Task B3: Write GUI tests for the largest uncovered modules

Priority order by Sonar `new_uncovered_lines` (approx):

| Priority | Module | ~Uncovered new lines | Test strategy |
|---|---|---|---|
| P0 | `gui/tabs/geometry_builders.py` | ~461 | Extend `tests/gui/test_gui_flows.py`; drive geometry tab / builder helpers with NiceGUI `User` + monkeypatches for Plotly |
| P0 | `gui/tabs/upload_builders.py` | ~313 | Upload-tab smoke: schema selector, file accept paths, error banners (no real PHI fixtures) |
| P0 | `gui/tabs/results_builders.py` | ~295 | Results render with synthetic `PageContext` / fake dose output |
| P1 | `gui/widgets/import_preview.py` | ~141 | Widget-level tests with synthetic tabular preview rows |
| P1 | `gui/tabs/export.py` | ~140 | Extend `test_export_*.py` for writer dispatch / button enablement |
| P1 | `gui/tabs/calculate.py` | ~116 | Pre-calc prompts / guard paths with mocked `main()` |
| P2 | `gui/window_prefs.py`, `phantom_preview*.py`, `helpers.py`, `_per_exam.py`, … | remaining | Incremental smoke + unit-style tests where logic is pure |

Constraints (existing harness rules):

- NiceGUI imports **only** under `tests/gui/` (`check_gui_test_placement.py`).
- Use de-identified / synthetic fixtures only; no new PHI assets.
- Prefer exercising real builders with mocks at I/O and Plotly boundaries over excluding code.
- Cancel NiceGUI timers via existing `tests/gui/conftest.py` autouse fixture.

- [x] **B3.1** Add/extend tests covering ≥1 major path through each P0 module
- [x] **B3.2** Add/extend tests for P1 modules
- [x] **B3.3** Run `pytest tests/gui/ -q` locally; fix flakes before CI
- [x] **B3.4** After Sonar upload, record new_coverage %; if on B2-A, confirm ≥ **50%**
  (PR #32: quality gate OK; `new_lines_to_cover=0` / `new_uncovered_lines=0` on the PR
  delta; overall coverage 83.4%; Security Rating A. Main’s older new-code window may still
  differ until the period rolls — re-check after merge.)
- [x] **B3.5** Changelog note (Added — GUI coverage tests)

Prefer shipping B3 with B1 in the same merge train. Badge green is **only** required under
B2-A; under B2-B the badge is already gone.

---

## Phase C — CI: privacy-gates job + Semgrep after privacy

### Task C1: Extract `privacy-gates` job

**Files:**
- Modify: `.github/workflows/ci.yml`

Move these steps from `static-analysis` into a new job `privacy-gates`
(`needs: schedule-gate`, same `if` as today):

1. checkout (`fetch-depth: 0` optional here; `1` is enough for admission)
2. setup uv + Python 3.12
3. `uv sync --extra dev --locked` (privacy scripts + semgrep for project rules)
4. `python scripts/check_sensitive_content.py --require-approved-assets`
5. `privacy_admission.py check` + `route` (same PR/push branching as today)
6. `python scripts/check_ci_metadata.py "$GITHUB_EVENT_PATH"`
7. `python scripts/check_ignored_asset_files.py --strict`
8. `python scripts/render_asset_inventory.py --check`
9. `python scripts/render_privacy_tool_inventory.py --check`
10. `python scripts/run_semgrep_privacy.py`  ← stays here (privacy SAST)

Leave changelog/doc-freshness/sonar-properties-parity/help/licenses/bandit/basedpyright/
shellcheck/build in `static-analysis`, with:

```yaml
needs: [schedule-gate, privacy-gates]
if: needs.schedule-gate.outputs.should_run == 'true'
```

- [x] **C1.1** Add `privacy-gates` job; remove duplicated steps from `static-analysis`
- [x] **C1.2** Wire `static-analysis.needs` to include `privacy-gates`
- [x] **C1.3** Wire `gui-smoke` and `build` with `needs: privacy-gates` (D13 locked) so a
  privacy fail cancels wasted matrix / smoke minutes

### Task C2: OWASP Semgrep only after privacy-gates

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `dev-docs/HARNESS_ENGINEERING.md` CI table

New job:

```yaml
owasp-semgrep:
  needs: [schedule-gate, privacy-gates]
  if: needs.schedule-gate.outputs.should_run == 'true'
  runs-on: ubuntu-latest
  permissions:
    contents: read
  steps:
    - uses: actions/checkout@...
    - uses: astral-sh/setup-uv@...
    - uses: actions/setup-python@...
      with:
        python-version: '3.12'
    - run: uv sync --extra dev --locked
    - name: Semgrep (OWASP Top 10 SAST)
      env:
        SEMGREP_SEND_METRICS: "off"
      run: uv run --no-sync semgrep --config=p/owasp-top-ten --error --metrics=off src scripts .github/workflows docs/source/conf.py
```

Remove the OWASP Semgrep step from `static-analysis`. Optionally add the same
`SEMGREP_SEND_METRICS=off` to the privacy Semgrep wrapper env in `privacy-gates`.

- [x] **C2.1** Add job; delete old step
- [x] **C2.2** Update harness docs table (semgrep OWASP row → `owasp-semgrep` after privacy; note Cloud App disabled / Actions CLI only)

---

## Phase D — Restore Sonar on PRs after privacy (undo main-only)

### Task D1: Split Sonar from main-only cloud scans

**Files:**
- Modify: `.github/workflows/ci.yml`

Replace today’s single `cloud-scans-after-gates` with:

1. **`sonar-scan`** — runs on:
   - `pull_request`
   - `push` to `main`
   - not on `schedule` unless desired (default: skip schedule to save minutes)
   - `needs: [privacy-gates, build]` (build ensures tests compile; regenerate coverage in this job)
   - steps: checkout `fetch-depth: 0`, `uv sync --extra dev --extra gui --locked`,
     two-pass coverage (non-GUI then `tests/gui/` with `--append`) per Task B1,
     `SonarSource/sonarqube-scan-action` when `SONAR_TOKEN` present
   - For PRs, the official action decorates with PR parameters when `GITHUB_TOKEN` /
     event context is available — keep `permissions: contents: read` and add
     `pull-requests: read` if required by the action version in use (verify against action
     README for the pinned digest).

2. **`cloud-scans-main`** — `if: github.event_name == 'push' && github.ref == 'refs/heads/main'`
   - `needs: [privacy-gates, static-analysis, gui-smoke, build]` (or `sonar-scan`)
   - Codecov upload + Safety only (no Sonar duplication)

- [x] **D1.1** Implement `sonar-scan` for PR + main
- [x] **D1.2** Slim main-only job to Codecov + Safety
- [x] **D1.3** Changelog + HARNESS_ENGINEERING updates (remove “Sonar main only” wording)

### Task D2: Maintainer SonarCloud UI checklist (manual)

Document in `dev-docs/SONARQUBE_LOCAL.md` and HARNESS:

- [x] **D2.1** Administration → Analysis Method → **disable Automatic Analysis**
  (done by maintainer 2026-07-25)
- [x] **D2.2** Confirm CI-based analysis succeeds on a test PR
  (PR #32: `SonarCloud scan` + `SonarCloud Code Analysis` both pass; QG status OK)
- [ ] **D2.3** If badge still present (B2-A): confirm it can go green after security + coverage work
- [x] **D2.4** If badge removed (B2-B): confirm README has no Sonar QG badge
- [x] **D2.5** Free tier: custom `new_coverage` gate **not** available — stay B2-B (confirmed 2026-07-25)

Without D2.1, Automatic Analysis can still fail GitHub’s “SonarCloud Code Analysis” check
independently of privacy-gated CI.

---

## Phase E — CodeRabbit only after privacy-gates

### Task E1: Disable auto-review

**Files:**
- Create: `.coderabbit.yaml`

```yaml
# yaml-language-server: $schema=https://coderabbit.ai/integrations/schema.v2.json
language: en-US
reviews:
  auto_review:
    enabled: false
  # Manual escape hatch remains: comment `@coderabbitai review` on the PR.
```

- [x] **E1.1** Add `.coderabbit.yaml` with auto_review disabled
- [x] **E1.2** Note in HARNESS / AGENTS that CodeRabbit is privacy-gated

### Task E2: Request review after privacy-gates

**Files:**
- Create: `.github/workflows/privacy-gates.yml` (reusable `workflow_call`)
- Modify: `.github/workflows/ci.yml` (`uses:` + `request-coderabbit` job)

Implemented as: extract reusable `privacy-gates.yml`; add in-ci `request-coderabbit`
job with `needs: [privacy-gates]` so review is requested as soon as admission passes
(D14), without waiting for the matrix / Sonar. Draft PRs are skipped.

- [x] **E2.1** Extract reusable/standalone `privacy-gates` workflow used by `ci.yml`
- [x] **E2.2** Add CodeRabbit request job after `privacy-gates` success for non-draft PRs
- [x] **E2.3** Deduplicate `@coderabbitai review` comments per head SHA
- [x] **E2.4** Document that drafts are skipped (`draft == false` + `.coderabbit.yaml` drafts: false)

---

## Phase F — Docs, changelog, verification

- [x] **F1** Update `dev-docs/index.md` Master plans table (this file)
- [x] **F2** Update `dev-docs/HARNESS_ENGINEERING.md` CI DAG + “privacy before cloud” rule
- [x] **F3** Update `CHANGELOG.md` `[Unreleased]` (Security / Fixed / Changed as appropriate)
- [x] **F4** Update `AGENTS.md` / playbook only if operator workflow changes for agents
- [x] **F5** Open PR from `plan/sonar-privacy-gated-scans` (or implementation branch) with
  test plan:
  - Privacy fail → OWASP Semgrep / Sonar / CodeRabbit do not run
  - Privacy pass → OWASP Semgrep runs; Sonar runs on PR; CodeRabbit comment appears
  - After merge to main: Security Rating A on new code; README has no red Sonar badge
    (removed under B2-B, or green under B2-A)

  Opened as https://github.com/kgrizz-git/MyPySkinDose/pull/32

---

## 3. Suggested PR slicing

| PR | Contents | Risk |
|---|---|---|
| **PR1** | Phase A + B0 + B1 + B3 + **B2-B badge removal** (default) + changelog | Medium |
| **PR1b / manual** | Confirm plan type; if custom gates work, B2-A (50% gate) instead of/after badge removal; D7 disable Automatic Analysis | Maintainer UI |
| **PR2** | Phase C + D (privacy-gates, OWASP split, Sonar on PR+main with combined coverage) | Medium |
| **PR3** | Phase E (CodeRabbit after privacy) | Medium |
| **Follow-ups** | Re-add badge when green is honest; B2.R* raise custom gate if using B2-A; **post-merge main:** clear residual S8707 + push new_coverage past 80% (branch `fix/sonar-s8707-and-coverage`, 2026-07-26) | Low |


Default merge train assumes **B2-B** (no README badge) unless you confirm custom gates.

---

## 4. Out of scope

- Excluding `src/guiskindose/gui/**` from Sonar coverage (explicitly rejected)
- Making Safety/Codecov run on PRs
- Closing all historical Sonar code smells (see `sonarqube_remediation_plan.md`)
- Changing Semgrep pre-push hooks’ local ordering
- Disabling bandit or basedpyright
- Lowering the local matrix `fail-under=60` non-GUI coverage floor
- **Enabling DeepSource** (or other new SaaS SAST) in this workstream — only the forward-looking
  policy note (D12 / §2c “Future SaaS scanners”); implement when/if adopted

---

## 5. Acceptance criteria

1. Security findings cleared (or properly dispositioned); new Security Rating can be A.
2. README either has **no** Sonar quality-gate badge (B2-B) **or** a custom gate at 50%+ and
   a sustainably green badge (B2-A).
3. GUI remains in Sonar coverage measures.
4. Sonar `coverage.xml` includes non-GUI **and** `tests/gui/` runs; P0 GUI tests exist.
5. Cloud analyzers exclude asset/fixture/binary patterns; local privacy scanners keep source scope.
6. Semgrep Cloud remains disabled; OWASP + privacy Semgrep still run as local CLI in Actions.
7. Sonar / OWASP Semgrep / CodeRabbit run only after `privacy-gates` succeeds.
8. Docs match the DAG, Semgrep Cloud vs Actions, badge policy, and Free vs custom-gate fork.

---

## 6. Open questions — **locked 2026-07-25**

1. **Should `gui-smoke` and `build` wait on `privacy-gates`?** **Yes.** Both wait on
   `privacy-gates` (stronger privacy ordering; avoid burning matrix minutes on commits that
   fail admission).
2. **CodeRabbit trigger granularity:** **privacy-only** — request `@coderabbitai review`
   after `privacy-gates` succeeds (do not wait for full `ci` / matrix).
3. **Sonar quality gate as a required GitHub check on PRs?** Still optional follow-up; not
   required for this workstream (badge already removed under B2-B).
