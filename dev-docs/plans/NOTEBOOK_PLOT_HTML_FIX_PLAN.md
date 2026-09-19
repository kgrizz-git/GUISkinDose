# Notebook Plot-HTML Fix Plan — `analyze_data` None-Output Guard

Status: Active — awaiting Kilo + Composer plan review BEFORE implementation.
Created: 2026-09-18
Branch: `fix/notebook-plot-html`
Related backlog: `TO_DO.md` "Getting-started notebook execution failure in docs builds"

## Diagnosis (verified by reproduction, not hypothesized)

Sphinx/nbsphinx execution of `docs/source/getting_started/getting_started.ipynb`
fails with `RuntimeError: Expected HTML output but dose calculation returned
no data.` (`src/guiskindose/analyze_data.py:138`). Known since 2026-09-11;
broken since 2026-06-07.

Commit `803b748` ("fix pyright errors and improve ci", 2026-06-07) added to
`analyze_data()`:

```python
if settings.output_format == c.RUN_ARGUMENTS_OUTPUT_HTML:
    if output is None:
        raise RuntimeError("Expected HTML output but dose calculation returned no data.")
    return output
```

But `calculate_dose()` returns `(None, None, None)` BY DESIGN in plot modes
(`calculate_dose.py:114-116`: mode not calculate_dose/plot_dosemap), and the
default `output_format` is `"html"` (`pyskindose_settings.py:92`). So EVERY
plot-mode call with default settings raises — notebook cells 14/16/24
(`plot_setup`/`plot_procedure`) can never execute.

Evidence: full-notebook `nbclient` execution fails with the exact signature;
a bare cell-14 equivalent (`plot_setup` + defaults) raises immediately in an
otherwise fresh process; the dose cells are innocent (cell-28 equivalent
returns PSD ~10.4 headlessly); full unit suite green. NOT a Phase A/B
regression, NOT RTD resources, NOT dependency drift.

## Objective

Make plot modes + html format return gracefully (plots render for side effect,
as before) while genuine dose-mode failures still raise. Unblock the notebook
and the Sphinx docs build.

## Scope

**In scope:**
- `src/guiskindose/analyze_data.py:136-139` — gate the raise on
  dose-producing modes, mirroring the dose_map guard at `:127`:
  `if output is None and settings.mode in (c.MODE_CALCULATE_DOSE,
  c.MODE_PLOT_DOSEMAP): raise ...`.
- Tests: `plot_setup` + html returns None without raising; `plot_procedure` +
  html likewise; `calculate_dose` + html with forced-None output still raises
  (mock `calculate_dose` to return Nones or drive a zero-event frame —
  decided at implementation, documented in the PR).
- Verification: headless full-notebook `nbclient` execution clean (run with
  CWD outside the repo so `PlotOutputs/` and any artifacts stay out of the
  tree); Sphinx renders (execution failure was the only blocker); full
  `pytest -q`; `ruff`; `basedpyright`; doc freshness unaffected (no docs
  changed).
- `CHANGELOG.md` brief entry (user-visible behavior fix for plot+html API
  users) + `MAINTENANCE_LOG.md` detail.

**Out of scope:** the `tqdm_notebook.disp` AttributeError in CI build logs
(separate notebook-mode progress-bar incompatibility — independent TO_DO
candidate, not this fix); RTD log forensics; notebook content changes.

## Global Constraints

- Minimal diff: the guard condition plus tests plus changelog/maintenance-log
  lines. No refactoring of surrounding logic.
- No PHI/PII, paths, or identifiers in logs or errors (the raised message is
  already value-free; keep it so).
- Privacy receipts via the normal pre-commit path.

## File Map

| File | Role in this plan |
|------|-------------------|
| `src/guiskindose/analyze_data.py:136-139` | The one-condition fix |
| `tests/unittests/test_analyze_data.py` (new) | Mode/format matrix tests |
| `CHANGELOG.md` | Brief Fixed entry |
| `dev-docs/MAINTENANCE_LOG.md` | Detail entry |
| `dev-docs/index.md` | Catalog this plan (same PR) |

## Tasks

- [ ] **Step 1: Apply the guard** — mode-gated raise per Scope; nothing else
  in the function changes.
- [ ] **Step 2: Tests** — plot modes + html return None cleanly; dose mode +
  forced-None output still raises; existing analyze/calculate tests unmodified
  and green.
- [ ] **Step 3: Notebook proof** — headless `nbclient` full execution clean
  (outside-tree CWD); Sphinx build renders past the notebook step (remaining
  pre-existing failure modes, if any, reported — not fixed — here).
- [ ] **Step 4: Docs + ladder** — CHANGELOG + MAINTENANCE_LOG; ladder: new
  tests → full `pytest -q` → `ruff` → `basedpyright` → freshness →
  `check_changelog`.
- [ ] **Step 5: Push, PR, reviews** — push branch, open PR, request Kilo +
  Composer implementation reviews. Merge only on approval + green CI.
- [ ] **Step 6: Archive** — flip this plan's `Status:` to Complete, move it to
  `dev-docs/plans/archive/`, update the `index.md` row to the archive path,
  in the same PR as the fix (per the closeout discipline).

## Acceptance Criteria

- `plot_setup`/`plot_event`/`plot_procedure` + html return without raising.
- `calculate_dose`/`plot_dosemap` + html with missing output still raise the
  exact existing message.
- Full notebook executes headlessly with no errors.
- Diff: guard + tests + changelog/maintenance-log/index docs. No other
  behavior changes.
