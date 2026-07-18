# Complexity Refactoring Plan: Geometry Tab

This is the detailed companion to Phase 4.1 of
[the SonarQube remediation plan](sonarqube_remediation_plan.md). It targets
`build` in [geometry.py](../../src/mypyskindose/gui/tabs/geometry.py#L81), whose
baseline cognitive complexity is **158**. The function currently spans almost the
whole 794-line file, so adding a controller to `geometry.py` before moving code
would violate the repository's ~800-line size limit.

---

## 1. Refactoring Boundary

Create `geometry_builders.py` before adding new logic. `geometry.py` becomes the
thin public entry point and compatibility owner; it imports a single
`build_geometry_tab` function. The new module contains the controller, view
references, and layout builders, and imports domain helpers directly rather than
importing `geometry.py` back.

```
src/mypyskindose/gui/tabs/
├── geometry.py             # public build(ctx), compatibility imports only
└── geometry_builders.py    # controller, view references, builders, callbacks
```

`geometry_preview.py` remains the source for pure active-exam and caption logic;
this refactor must not move it into a tab module or create an import cycle.

### State and UI contract

Use a controller to replace the existing closure web. It receives the current
`PageContext` and `AppState` explicitly, owns only tab-local UI references and
guard/timer state, and calls the existing helpers for data transformations and
figure generation.

```python
class GeometryTabController:
    def __init__(self, ctx: PageContext, app_state: AppState) -> None: ...

    def refresh(self) -> None: ...
    def request_render(self) -> None: ...
    def schedule_debounced_render(self) -> None: ...
    def on_exam_changed(self, event: ValueChangeEventArguments) -> None: ...
    def on_event_changed(self, event: ValueChangeEventArguments) -> None: ...
    def on_patient_offset_changed(self, axis: str, value: float) -> None: ...
    def on_table_origin_changed(self, axis: str, value: float) -> None: ...

@dataclass
class GeometryViewRefs:
    plot: ui.plotly
    spinner: ui.spinner
    exam_select: ui.select
    event_select: ui.select
    # Sliders/labels only where a callback needs them.
```

Keep suppression flags, the pending timer, the active/composite preview mode,
and table-origin scrub state on the controller. Do not store a loaded DataFrame,
patient data, or duplicate offsets there; `AppState` remains the source of truth.
The controller must expose the same refresh function(s) through `PageContext`
that the rest of the app already calls.

---

## 2. Builder Boundaries and Complexity Budget

The top-level builder owns only the tab-panel context and calls these pieces:

| Function/method | Responsibility | Maximum complexity |
|---|---|---:|
| `geometry.build` | Construct controller and delegate to `build_geometry_tab` | 4 |
| `build_geometry_tab` | Tab-panel/container composition only | 5 |
| `build_header` | Title and help control | 2 |
| `build_exam_controls` | Exam selector, composite mode, notices, and event selector | 12 |
| `build_preview` | Plotly element, spinner, caption/status references | 7 |
| `build_patient_offset_controls` | Three patient-offset controls | 12 |
| `build_table_origin_controls` | Table-origin controls and visibility | 12 |
| Any controller callback/render helper | One event/render concern | 12 |

This is a strict per-function ceiling: moving 158 points of branching into a
single `refresh` method is not a successful refactor. After the split, SonarQube
must report every listed unit and any newly extracted helper at or below the
configured threshold, with no new `S3776` finding.

---

## 3. Behaviour Invariants

The extraction must preserve all of the following:

1. **Debounce and render-loop protection:** `GEOMETRY_DEBOUNCE_SEC` timing and
   guards permit one pending preview render for a slider scrub, not a render loop.
2. **Exam semantics:** active exam selection, composite preview, event bounds,
   initial/middle-event selection, and event labels stay tied to the same sliced
   data as before.
3. **Offset semantics:** patient and table-origin controls update the active
   exam's existing settings, invalidate stale results where they did before, and
   retain the table-origin commit/auto-detected behaviour.
4. **Cross-tab wiring:** `PageContext` refresh hooks and user navigation keep
   Geometry, Settings, Data, and calculation summaries synchronized.
5. **Presentation:** Plotly element identity, spinner lifecycle, caption/vendor
   warning content, and current Quasar layout classes remain stable. Do not make
   a visual change under cover of the complexity refactor.

Add characterization tests before moving each non-trivial callback; no raw
patient or source data belongs in test output or diagnostics.

---

## 4. Reviewable Steps and Verification

1. Add `geometry_builders.py`, the controller/view-reference types, and unit
   tests for pure controller decisions. Keep `geometry.py` below the file-size
   limit throughout.
2. Move exam/event controls and preview rendering, then verify selector and
   composite behaviour before moving sliders.
3. Move patient/table-origin controls and debounced callbacks. Reconnect the
   existing `PageContext` refresh contract and remove obsolete closures only once
   the replacement has tests.
4. Run SonarQube and inspect every new function's complexity rather than checking
   only the original `build` issue.

```bash
uv run pytest tests/unittests/test_gui_multi_exam_geometry_offsets.py \
  tests/unittests/test_gui_offset_reset.py \
  tests/unittests/test_gui_cross_tab_sync.py
uv run pytest tests/gui/test_gui_flows.py
uv run ruff check src/mypyskindose/gui/tabs tests
uv run basedpyright
```

**Completion criterion:** the original `geometry.build` finding and all new
helper findings are resolved; the tests above demonstrate preserved exam,
offset, debounce, and cross-tab behaviour; and the local SonarQube scan confirms
the result.
