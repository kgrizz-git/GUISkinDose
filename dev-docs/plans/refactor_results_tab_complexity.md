# Complexity Refactoring Plan: Results Tab

This is the detailed companion to Phase 4.2 of
[the SonarQube remediation plan](sonarqube_remediation_plan.md). It targets
`build` in [results.py](../../src/mypyskindose/gui/tabs/results.py#L50), whose
baseline cognitive complexity is **128**.

---

## 1. Target Architecture

Move layout and callback ownership into a new sibling module without importing
the owner module back:

```
src/mypyskindose/gui/tabs/
├── results.py              # public build(ctx), compatibility helpers as needed
└── results_builders.py     # controller, UI references, layout builders
```

`ResultsTabController` receives `PageContext` and the application state
explicitly. It owns Plotly/spinner/table references and the three refresh paths
(metrics, dose map, correction table), but it does not own or copy calculation
results. Pure helpers such as `compute_subset_aggregate` remain independently
testable and keep their current public import path unless a compatibility export
is retained.

```python
@dataclass
class ResultsViewRefs:
    dosemap_plot: ui.plotly
    dosemap_spinner: ui.spinner
    metric_labels: ResultsMetricLabels
    correction_table: ui.table

class ResultsTabController:
    def __init__(self, ctx: PageContext, app_state: AppState) -> None: ...
    def refresh_metrics(self) -> None: ...
    def refresh_dosemap(self) -> None: ...
    def refresh_corrections(self) -> None: ...
    def on_colorscale_changed(self) -> None: ...
```

Builder functions receive the controller and return or populate the references
they create. They may not reach into an enclosing `build` closure.

---

## 2. Complexity Budget

| Function/method | Maximum complexity |
|---|---:|
| `results.build` | 4 |
| `build_results_panel` | 5 |
| `build_metric_cards` | 10 |
| `build_plotly_canvas` | 6 |
| `build_results_settings` | 8 |
| `build_corrections_table` / per-exam subsection builder | 10 |
| Each controller refresh/event method | 12 |

The desired maximum is **12**, below the current Sonar threshold of 15. The
completion test is per function: a delegating `build` is not sufficient if a new
refresh callback becomes an `S3776` finding.

---

## 3. Behaviour Invariants

1. Preserve single- and multi-exam metrics, including the aggregate PSD being the
   peak of the summed selected maps rather than a sum of per-exam PSD values.
2. Preserve colorscale changes, manual regeneration, Plotly updates, and spinner
   visibility during refreshes.
3. Preserve `calculation_done`, `calculation_run_id`, selected-exam visibility,
   and stale-UI detection semantics. Timers must continue to use the same
   interval and must not register duplicate refresh loops.
4. Preserve correction-table values and no-result/empty-selection behaviour.
5. Keep the current UI layout and help integration unchanged; this is not a
   redesign.

Add helper-level tests for any new aggregate/formatting decision and NiceGUI
tests for the timer, control bindings, and rendered results state.

---

## 4. Reviewable Steps and Verification

1. Introduce controller/view-reference types and move one refresh path at a time,
   starting with pure metric formatting.
2. Move the Plotly/correction refresh paths and verify single- and multi-exam
   output before changing layout ownership.
3. Move card/canvas/control builders, leaving `results.build` as a thin public
   delegator. Remove obsolete closures only after the replacement is covered.
4. Re-run SonarQube and inspect every extracted function.

```bash
uv run pytest tests/gui/test_gui_results_refresh.py \
  tests/gui/test_results_per_exam_dosemap.py \
  tests/unittests/test_export_payload.py
uv run pytest tests/gui/
uv run ruff check src/mypyskindose/gui/tabs tests
uv run basedpyright
```

**Completion criterion:** `results.build` and every new helper are below the
configured complexity threshold; calculation results, map aggregation, controls,
and spinner behaviour remain covered; and the local SonarQube scan resolves the
baseline issue without adding another.
