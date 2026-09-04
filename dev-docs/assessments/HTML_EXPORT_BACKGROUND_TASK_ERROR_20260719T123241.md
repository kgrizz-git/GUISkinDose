> **REVIEWED** — 2026-07-19. Symptom mechanism confirmed against code; underlying Plotly/`to_html` failure mode still needs a captured exception (Fix 2). User confirmation: Results aggregate dose map **did render** before HTML export failed.
>
> **Fix plan:** [plans/HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md](../plans/HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md) (Phase 0 = capture exception; Phase 1 = error semantics; Phase 2 = root-cause fix).

# HTML Export "Background task was cancelled" Error

Investigated: 2026-07-19  
Reviewed: 2026-07-19

## Summary

The HTML export error `RuntimeError: Background task was cancelled or the application is shutting down.` is **misleading**. NiceGUI’s `run.io_bound` returns `None` on cancel/shutdown, and `require_io_result` treats **every** `None` as that case. The export callbacks (`make_dosemap_html` / `make_dosemap_png`) also return `None` on failure, so a real render failure is reported as a cancelled background task.

**Important observation (user, high confidence):** the Results tab **aggregate dose map rendered successfully** for the same multi-exam run that then failed HTML export. Results and Export both call `make_dosemap_fig` with the same multi-exam inputs (`aggregate_dose_map` + `exams[0].output.to_dict()["patient"]`). That largely **rules out** mesh/patient structural mismatch and a broken figure builder as the explanation for this incident.

The remaining likely failure is therefore in the **HTML-specific path after (or around) figure build** — especially `fig.to_html(...)` inside `make_dosemap_html`, which swallows all exceptions with **no logging** — combined with `require_io_result` mislabeling the resulting `None`.

PNG export uses the same `require_io_result` + silent-`None` pattern and is at equal risk.

---

## Error Trace

```text
RuntimeError: Background task was cancelled or the application is shutting down.
  File "gui/tabs/export.py", line 210, in download_html
    content = require_io_result(await run.io_bound(make_dosemap_html, ...))
  File "gui/concurrency.py", line 42, in require_io_result
    raise RuntimeError("Background task was cancelled ...")
```

(Line numbers in the original session may differ slightly; the call site is `download_html` → `require_io_result`.)

The preceding log line (`Mode not set to plot dosemap. Returning without doing anything`) is from the main calculation pipeline (`plotting/create_dose_map_plot.py:55`) and is **unrelated** to the HTML export failure — it is a normal debug message when `mode != "calculate_dose"`.

---

## Evidence: Results rendered, Export failed

| Path | Call site | Concurrency | On failure |
|------|-----------|-------------|------------|
| Results aggregate map | `results_builders.refresh_aggregate_dosemap` → `make_dosemap_fig(aggregate, exams[0] patient)` | Sync on UI thread; **no** `require_io_result` | Empty plot if `None`; user saw a rendered map |
| HTML export | `export.download_html` → `run.io_bound(make_dosemap_html, …)` → `require_io_result` | Worker thread | `None` → misleading cancel `RuntimeError` |
| PDF / rich report | `_rich_report_bytes_titled` → `collect_export_payload` | Worker thread | Own error handling; **does not** use `make_dosemap_html` (explains PDF succeeding) |

Same multi-exam data, same `make_dosemap_fig` inputs → Results success implies the aggregate map and patient dict were compatible enough to build a figure. A length-mismatch / wrong patient-dict shape is **not** the primary explanation for this incident (though still worth hardening elsewhere).

`download_html` also has a dead branch: after `require_io_result`, `if not content: ui.notify("Failed to generate HTML")` never runs when the builder returns `None`, because `require_io_result` raises first.

---

## Root Cause Analysis

### 1. `require_io_result` conflates two distinct `None` meanings — confirmed

`gui/concurrency.py:32-43` — treats **any** `None` from `run.io_bound` as cancellation:

```python
def require_io_result(result: _T | None) -> _T:
    if result is None:
        raise RuntimeError("Background task was cancelled or the application is shutting down.")
    return result
```

NiceGUI’s interim contract: `run.io_bound` returns `None` when the call is cancelled or the app is shutting down; NiceGUI 4.0 will raise `CancelledError` instead. Callbacks that themselves return `None` are indistinguishable from cancel until then.

### 2. `make_dosemap_html` silently swallows all errors — confirmed; most suspicious for this incident

`gui/figures.py:152-163`:

```python
def make_dosemap_html(...) -> bytes | None:
    try:
        fig_dict = make_dosemap_fig(...)
        if fig_dict is None:
            return None
        fig = go.Figure(fig_dict)
        return fig.to_html(full_html=True).encode()
    except Exception:
        return None  # no logging
```

Given Results already built the figure, the unlogged branch around **`to_html` / `Figure` rebuild** is the leading candidate for this incident. Until logging is added, the concrete exception remains unknown (memory, Plotly, threading, etc.).

`make_dosemap_fig` still swallows exceptions (DEBUG only). That matters for other failure modes, but is a weaker fit here because Results already succeeded with the same inputs.

### 3. Multi-exam data flow — downgraded for this incident

Export and Results share:

```python
explicit_dose_map = state.multi_exam_result.aggregate_dose_map
explicit_patient = state.multi_exam_result.exams[0].output.to_dict()["patient"]
```

Fragile assumptions (empty aggregate, phantom size mismatch across exams) remain real edge cases in the codebase, but they are **unlikely** for a run where the Results aggregate map already rendered. Multi-exam length mismatch during aggregation would typically fail earlier at `aggregate_dose_map + exam_dose_map` in `analyze_data.py` (outside that function’s per-exam `try`).

### 4. PDF export works because it uses a different code path — confirmed

Rich-report PDF does not go through `make_dosemap_html` / `require_io_result`’s HTML-None trap.

---

## Why the Error Appears After Calculate

The error is **not** triggered by calculation. Calc completes; the error occurs when the user clicks HTML export. The `Mode not set to plot dosemap` debug line during calc is normal and unrelated.

---

## Recommended Fixes (priority order)

### Fix 1 (do first): Log exceptions in `make_dosemap_html` / `make_dosemap_png`

Without this, the real `to_html` (or other) failure stays invisible.

```python
except Exception as exc:
    safe_error_event(logger, "dosemap_html_render", exc)  # WARNING, not silent
    raise  # prefer Fix 2, or return None only if callers handle it
```

### Fix 2: Prefer raise-on-failure over returning `None` from export builders

Have `make_dosemap_html` / `make_dosemap_png` raise on failure instead of returning `None`. Then `require_io_result` only sees `None` for genuine NiceGUI cancel/shutdown.

```python
def make_dosemap_html(...) -> bytes:
    fig_dict = make_dosemap_fig(...)
    if fig_dict is None:
        raise RuntimeError("Dose map figure could not be built")
    ...
```

A Result/sentinel wrapper is possible but heavier; NiceGUI itself dropped a similar interim sentinel in favor of raising `CancelledError` in 4.0. Prefer raise-on-failure.

Do **not** remove `require_io_result` until NiceGUI 4.0; keep it for real cancel, but stop feeding it legitimate failure `None`s.

### Fix 3: Actionable UI errors on the export path

Catch builder failures (and keep cancel as a separate message). Example:

```text
Could not generate HTML dose map. See the log for details.
```

Wire this so the existing `"Failed to generate HTML"` path can actually run (or replace it with try/except around `require_io_result` + builder errors).

### Fix 4 (secondary): Multi-exam length validation

Still useful defense-in-depth, but **not** the explanation for this incident given Results already rendered the same data. Optional while fixing the error-reporting path.

### Optional investigation after logging

- Whether `to_html` fails only on the worker thread (`run.io_bound`) vs UI thread  
- Whether reusing `state.dosemap_fig` (already built by Results) avoids a second Plotly build  
- Whether PNG export fails the same way (same pattern)

---

## Files Involved

| File | Lines | Role |
|------|-------|------|
| `src/guiskindose/gui/concurrency.py` | 32-43 | `require_io_result` — conflates `None` meanings |
| `src/guiskindose/gui/figures.py` | 117-178 | `make_dosemap_fig` / `make_dosemap_html` / `make_dosemap_png` |
| `src/guiskindose/gui/tabs/export.py` | 196-245 | HTML/PNG download; multi-exam args; dead `"Failed to generate HTML"` branch |
| `src/guiskindose/gui/tabs/results_builders.py` | 160-175 | Aggregate map uses same fig inputs **without** `require_io_result` (rendered OK) |
| `src/guiskindose/export/images.py` | 59-117 | Shared Plotly figure builder |

---

## Open Questions

1. **What exception does `make_dosemap_html` swallow?** Still unknown. Fix 1 (logging) is required to answer this. Leading guess: failure in `go.Figure` / `to_html` after a successful `make_dosemap_fig`, or a second-call/`io_bound` interaction — not aggregate mesh mismatch.

2. **Does PNG fail the same way?** Same architecture; should be smoke-tested with the same run.

3. **Single-exam HTML export?** Still worth a quick check; the misleading `None`→cancel path is schema-agnostic.

4. **Remove `require_io_result`?** Not yet. Keep until NiceGUI 4.0 raises `CancelledError`; stop returning failure `None` from exporters.

---

## Phase 0 finding (2026-07-19)

Instrumented `make_dosemap_html` / `make_dosemap_png` (`src/guiskindose/gui/figures.py`) with
`safe_error_event(logger, "dosemap_html_render"/"dosemap_png_render", exc)` in the previously-silent
`except Exception:` blocks (still returning `None`, per Task 0 Step 0.1 — no behavior change yet).
Confirmed via a manual negative-control call (monkeypatched `make_dosemap_fig` to return an
invalid Plotly figure dict) that the log line fires correctly and is privacy-safe:
`ERROR mypyskindose.gui.figures: dosemap_html_render failed (error_type=ValueError)`.

**Experiment A (non-interactive repro, preferred per task brief):** Built a real
`MultiExamResult` from two approved bundled de-identified example RDSR fixtures via
`analyze_multiple_exams`, mirroring the CLI multi-file RDSR path exactly. Called
`make_dosemap_html` / `make_dosemap_png` with the same argument shape `export.py` uses
(`aggregate_dose_map` + `exams[0].output.to_dict()["patient"]`), tried with both `cylinder`
and `human` phantom models. **Could not reproduce a failure** in any case — every call
returned non-empty bytes, and neither `dosemap_html_render` nor `dosemap_png_render` log
lines fired (i.e. no exception was ever raised). Interactive GUI reproduction (Step 0.2) was
**not attempted** in this dispatch — the task brief allows skipping it when a non-interactive
repro is used, but that also means the user's exact original dataset/session state was not
exercised, so **absence of failure here does not rule out the original bug**.

**Experiment B (isolate `to_html` off the UI thread):** Using the same multi-exam figures,
called `go.Figure(fig_dict).to_html(full_html=True)` and `fig.to_image(format="png")`
directly (bypassing `make_dosemap_html`'s own try/except) on the main thread and inside a
`concurrent.futures.ThreadPoolExecutor` (mirrors NiceGUI's `run.io_bound`). Compared output
**lengths only** (no byte-for-byte content check): main thread vs worker thread matched for
both HTML (16,288,624 bytes with the `human` phantom) and PNG (71,802 bytes). Also ran two
concurrent `make_dosemap_html` calls (race/state-mutation probe) — both returned non-empty
bytes of the same length, no evidence of a
`state.dosemap_fig`-related race in this scenario.

- Exception type: none captured (no exception raised in any experiment)
- Operation key: `dosemap_html_render` / `dosemap_png_render` (instrumented; did not fire)
- Happened after Results aggregate rendered: n/a — failure did not reproduce in this session
- PNG tried: yes — result: succeeded on main thread, worker thread, and concurrently, same as HTML
- Worker-thread only?: **no** — `to_html`/`to_image` succeeded on main and worker threads with the bundled fixtures (output lengths matched; content not compared); no thread-only failure mode found

**Interpretation / Phase 2 routing:** Neither of Task 0's gate conditions (Step 0.5) is met —
no captured exception, and no thread-only failure with a clear stack. Per the plan, **Phase 2
must not start from this evidence alone**. The most likely explanations for the original
incident that remain open, given a clean run with the bundled fixtures:

1. The user's actual (larger/real) multi-exam dataset triggers a data-shape or size issue
   (e.g., NaNs, degenerate mesh, or a much larger figure) not present in the bundled fixtures.
2. A genuine NiceGUI-level cancellation (client disconnect, app shutdown, or `run.io_bound`
   executor contention) produced a real `None` from `run.io_bound` — i.e. `require_io_result`
   correctly reported a cancel, and the "misleading" framing needs revisiting for this
   specific incident (decision-table row: "No exception; genuine NiceGUI `None` (cancel)").
3. Something specific to the live NiceGUI/uvicorn process (e.g. kaleido's Chromium subprocess
   already busy from a concurrent request, or event-loop interaction not present in a
   standalone script) that only manifests inside the running app.

Phase 1 (stop returning misleading `None`; raise-on-failure with actionable UI errors) remains
valuable regardless and should proceed. Phase 2's root-cause fix should stay open pending either
(a) a future interactive-GUI reproduction with the user's real session, or (b) the Phase 1
raise-on-failure change surfacing a concrete exception the next time this occurs in the wild.
