# Settings Phantom Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development`
> (recommended) or `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax. Mark a checkbox only after the step is fully done and verified.
>
> **Related:** Settings UI in `src/guiskindose/gui/tabs/settings.py`; contrast (do **not** reuse)
> RDSR Geometry path in `gui/figures.py` / `plotting/plot_setup.py`; positioning in
> `geom_calc.position_patient_phantom_on_table`.
>
> **Plan review (2026-07-22):** Subagent review → **major revision** (live scales, orientation,
> reduced-mesh resolve, Settings-owned async debounce).
>
> **Assessment fold-in (2026-07-22):** `tmp/20260722_settings_phantom_preview_plan_assessment.md` —
> explicit `patient_offset` list; lightweight `mesh_text`; `ctx.refresh_phantom_preview`; Plotly
> `uirevision` keyed by mesh; harness registry steps; panel height 340–380 px; reuse shipped
> `COLOR_*` (not new palette). Cylinder/plane preview deferred (Phase 1.5).
>
> **Assessment r2 fold-in (2026-07-22):** `tmp/20260722_settings_phantom_preview_plan_assessment_r2.md`
> — `PreviewSnapshot` contract (no global `state` on worker); multi-exam offsets = active-exam via
> `effective_patient_offset_for_preview`; cross-tab refresh call sites; initial mount refresh;
> reuse `GEOMETRY_DEBOUNCE_SEC`; consume-only layout helpers; preview controller extraction;
> `copy_text` + `feature_doc_matrix`; float offsets; package-relative mesh resolve; placeholder UX.

**Goal:** On the Settings tab, under the phantom model / human-mesh selectors (near body-habitus
controls), show a live 3D preview of the **currently selected human** phantom so users can confirm
mesh identity, **face-up / back-on-support** orientation, **patient offsets**, and **body-habitus
scaling** without leaving Settings and without uploading an RDSR.

**Architecture:** Add a compact Plotly `ui.plotly` panel driven by `make_phantom_preview_fig` (no
RDSR). On the UI thread, build a **`PreviewSnapshot`** (never pass the live singleton into the
worker). From the snapshot: `build_settings` → resolve preview mesh stem (prefer `_reduced_1000t`)
→ `Phantom(..., human_scale=(scale_lat, scale_ap, scale_lon))` → table/pad →
`position_patient_phantom_on_table` with orientation **and** patient offsets →
`create_mesh_3d_general` with shipped `COLOR_PATIENT` / `COLOR_TABLE` / `COLOR_PAD`.
Refresh is **Settings-owned**: debounce (`GEOMETRY_DEBOUNCE_SEC`) → `run.io_bound` on the
snapshot → apply only if a monotonic request id is still current. Register
`ctx.refresh_phantom_preview` so Settings **and** other pose-changing call sites schedule the same
refresh. Prefer a small preview controller module so `settings.py` stays layout-focused.

**Tech stack:** NiceGUI + Plotly (`ui.plotly`), `Phantom`, `position_patient_phantom_on_table`,
`create_mesh_3d_general` (`plotting/create_mesh3d.py`), consume `default_geometry_layout` /
`get_camera_view` (do not expand their APIs for Settings-only `uirevision`), `build_settings`,
`effective_patient_offset_for_preview`, `GEOMETRY_DEBOUNCE_SEC`, `safe_error_event`,
`guiskindose.constants` colors, `copy_text` for catalogued UI strings.

## Global constraints

- **No RDSR required** for the Settings preview (users pick phantoms before upload).
- **Do not call** `make_geometry_fig`, `create_geometry_plot`, or `plot_setup` — those paths need
  RDSR / event data. Build meshes directly per the construction path below.
- **Live habitus scaling (required):** Preview **must** reflect habitus scales exactly as
  calculation does — via snapshot → `build_settings` → `settings.phantom.scale_*` →
  `Phantom(..., human_scale=(lat, ap, lon))`. Do **not** manually scale Plotly coordinates
  (wrong anchors / normals).
- **Scale order in Phantom:** `_apply_human_scale` anchors X at mid, Y at max (table-contact /
  back), Z at max (crown). Using `Phantom` preserves that.
- **Orientation:** Apply `settings.phantom.patient_orientation` through
  `position_patient_phantom_on_table` (feet-first must be visually distinct).
- **Offsets (required):** Pass floats into positioning — same order as Geometry /
  `build_settings`:
  `[float(po.d_lon), float(po.d_ver), float(po.d_lat)]`.
  (`position_patient_phantom_on_table` is annotated `List[int]` legacy; production and Geometry
  already pass floats — do **not** `int()`-truncate.)
- **Multi-exam offsets (v1 decision):** Snapshot offsets via
  `effective_patient_offset_for_preview(state, active_exam_index=...)` — **active exam** when
  multi-exam, else globals. Caption must say so (not “always global”). Per-exam *composite*
  previews remain out of scope.
- **Bound value stays mesh stem** if using display→stem options maps.
- **Performance:** Prefer `{stem}_reduced_1000t` when that STL exists under the **package**
  `phantom_data/` directory (same root `Phantom` uses); dose still uses full STL. Reduced
  silhouette is approximate — tests assert scale **ratios**, not equality to full mesh.
- **Hover text:** `create_mesh_3d_general` needs `mesh_text` length `len(obj.r)`. Use **lightweight
  static** labels (e.g. one short string repeated), not rich per-vertex HTML — slider drags must stay cheap.
- **Camera orbit:** After building the figure, set `layout.uirevision` to the **logical mesh stem**
  (and/or phantom model) so habitus slider updates keep the user’s orbit/zoom; camera may reset when
  mesh/model changes. Prefer `fig.update_layout(uirevision=...)` / dict assignment — **do not**
  change `default_geometry_layout` unless a shared kwarg is clearly reusable.
- **Debounce:** Settings-owned; reuse **`GEOMETRY_DEBOUNCE_SEC`** (`0.25`) from
  `gui/constants.py`. Cancel unstarted timer; generation id so in-flight `io_bound` cannot
  overwrite newer scales/offsets.
- **PageContext:** Add `refresh_phantom_preview: Callable[[], None]` (default no-op). Settings
  registers the schedule function. Do **not** repurpose `ctx.refresh_geometry_preview()` as the
  Settings renderer (Geometry remains RDSR-based). Pose-changing handlers may call **both**.
- **Visibility (v1):** Keep `ui.plotly` mounted. When `phantom_model == "human"`, show the plot and
  clear the status label. When plane/cylinder (or build returns `None`), set figure to `{}` and
  show a sibling status `ui.label` (“Preview available for human mesh” / “Preview unavailable”).
  **Phase 1.5** (out of v1): optional cylinder/plane on the same support — not a ship blocker.
- **Styling:** Reuse shipped `COLOR_PATIENT`, `COLOR_TABLE`, `COLOR_PAD` and Geometry dark theme
  (`rgb(5,5,5)` paper/plot as in `figures.py`) — **always dark preview panel** even if
  `state.dark_mode` is false (matches Geometry preview). Do **not** invent a new patient palette.
  Match setup-plot readability: patient opaque; table/pad may use the same opacity pattern as
  `create_setup_and_event_plot` if that helps the silhouette read clearly.
- **Panel size:** `ui.plotly` height **340–380 px**, `w-full`.
- **Face-up cue:** Prefer `get_camera_view()`; caption uses support wording, **not** “Y ≈ 0”.
- **Failures / cancel:** Builder returns `None` on failure → status “Preview unavailable”;
  `safe_error_event` with a stable non-identifying operation code; no paths/filenames/exception
  text in UI. NiceGUI `run.io_bound` cancel also yields `None` — treat like unavailable **without**
  raising `require_io_result` into the UI (do not confuse users on shutdown).
- **Initial paint:** After registering `ctx.refresh_phantom_preview`, **schedule one refresh on
  mount** so Settings is not blank until the user moves a control.
- **Harness:** Caption / unavailable / help strings via `copy_text` + `dev-docs/ui_copy.json`;
  help under `docs/source/gui_help/` + `sync_gui_help.py`; update `help_registry.json`,
  `feature_doc_matrix.json`, and `glossary.json` if new terms ship.
- **Modularity:** Prefer a small controller next to the fig builder from Task 2 (do not wait for
  the ~750-line cliff). Keep `settings.py` as layout + handler wiring.

---

## PreviewSnapshot contract

Built **on the UI thread** immediately before `run.io_bound`. The fig builder and any worker-side
helpers **must not** read the global `state` singleton.

Minimum fields (plain dataclass or TypedDict):

| Field | Source |
|-------|--------|
| `phantom_model` | `state.phantom_model` |
| `human_mesh` | logical stem (`state.human_mesh`) |
| `patient_orientation` | `state.patient_orientation` |
| `scale_lat` / `scale_ap` / `scale_lon` | `state.phantom_scale_*` |
| `d_lon` / `d_ver` / `d_lat` | `effective_patient_offset_for_preview(state, …)` |
| (optional) `logical_mesh_stem` | same as `human_mesh` — used for `uirevision` / captions |

`make_phantom_preview_fig(snapshot)` may call `build_settings` only from snapshot fields (or from a
temporary `AppState`-like object constructed from the snapshot — **not** the live singleton).
Dimension / pad thickness come from `build_settings` → example-settings defaults (not GUI-editable
today).

Helper: `capture_phantom_preview_snapshot(app_state) -> PreviewSnapshot`.

---

## File map

| Path | Role |
|------|------|
| `src/guiskindose/gui/phantom_preview.py` (new) | `PreviewSnapshot`, `capture_phantom_preview_snapshot`, `resolve_preview_mesh`, `make_phantom_preview_fig` |
| `src/guiskindose/gui/phantom_preview_controller.py` (new, preferred) | Debounce, request id, `io_bound`, `update_figure` / status label; exposes `schedule_refresh` for `ctx` |
| `src/guiskindose/gui/tabs/settings.py` | Mount plot + status label + caption; wire shared handlers; register `ctx.refresh_phantom_preview`; call schedule once on mount |
| `src/guiskindose/gui/page_context.py` | Add `refresh_phantom_preview` no-op field |
| `src/guiskindose/gui/offset_handlers.py` | From `on_global_patient_offset_change`, also `ctx.refresh_phantom_preview()` (and keep Geometry refresh if added there) |
| `src/guiskindose/gui/tabs/geometry_builders.py` | Patient-offset slider commit / reset paths call `ctx.refresh_phantom_preview()` |
| `src/guiskindose/gui/app.py` | Any restore/preset path that already calls `refresh_geometry_preview` also calls `refresh_phantom_preview` |
| `src/guiskindose/gui/constants.py` | Consume `GEOMETRY_DEBOUNCE_SEC` (no second debounce constant) |
| `src/guiskindose/plotting/create_mesh3d.py` | Consume `create_mesh_3d_general` |
| `src/guiskindose/plotting/plot_layout.py` | **Consume-only** `default_geometry_layout` |
| `src/guiskindose/plotting/get_camera_view.py` | **Consume-only** |
| `src/guiskindose/geom_calc.py` | Consume `position_patient_phantom_on_table` |
| `src/guiskindose/gui/settings_builder.py` | Consume `build_settings` |
| `src/guiskindose/gui/geometry_preview.py` | Consume `effective_patient_offset_for_preview` when capturing snapshot |
| `src/guiskindose/constants.py` | `COLOR_PATIENT` / `COLOR_TABLE` / `COLOR_PAD` |
| `tests/unittests/test_gui_phantom_preview.py` (new) | Fig + scale + offset + mesh resolve + orientation + snapshot (no NiceGUI; not under `tests/gui/`) |
| Help / `ui_copy.json` / `help_registry.json` / `feature_doc_matrix.json` / glossary / CHANGELOG / FEATURE_INVENTORY | Docs + harness |

---

## Required construction path

```python
# Worker receives PreviewSnapshot only — never the live state singleton.
settings = build_settings_from_snapshot(snapshot, mode="plot_setup", output_format="dict")
# human only in v1; guard before calling
logical_stem = snapshot.human_mesh
preview_mesh = resolve_preview_mesh(logical_stem)
patient = Phantom(
    phantom_model="human",
    phantom_dim=settings.phantom.dimension,
    human_mesh=preview_mesh,
    human_scale=(
        settings.phantom.scale_lat,
        settings.phantom.scale_ap,
        settings.phantom.scale_lon,
    ),
)
table = Phantom(phantom_model="table", phantom_dim=settings.phantom.dimension)
pad = Phantom(phantom_model="pad", phantom_dim=settings.phantom.dimension)
po = settings.phantom.patient_offset
position_patient_phantom_on_table(
    patient,
    table,
    pad,
    settings.phantom.dimension.pad_thickness,
    [float(po.d_lon), float(po.d_ver), float(po.d_lat)],
    settings.phantom.patient_orientation,
)
# Mesh traces: COLOR_*; mesh_text = [short_label] * len(obj.r)
# After layout: fig["layout"]["uirevision"] = logical_stem
```

`resolve_preview_mesh(stem)`:

1. Resolve against package `src/guiskindose/phantom_data/` (same directory `Phantom` loads from),
   not CWD / repo root.
2. If `{stem}_reduced_1000t.stl` exists → return `f"{stem}_reduced_1000t"`.
3. Else return `stem`.
4. Never double-append if `stem` already ends with `_reduced_1000t`; UI captions still show the
   logical (non-reduced) stem.

`build_settings_from_snapshot` may be a thin wrapper that builds a throwaway field object for
`build_settings`, or inlines the phantom fields into a temporary settings dict — either is fine as
long as the live singleton is untouched on the worker.

---

### Task 1: Preview figure builder + scale tests

**Files:**
- Create: `src/guiskindose/gui/phantom_preview.py`
- Test: `tests/unittests/test_gui_phantom_preview.py`

**Interfaces:**
- Consumes: `PreviewSnapshot` (or equivalent); no `rdsr_df`; no global `state` reads in the builder
- Produces: `capture_phantom_preview_snapshot`, `resolve_preview_mesh(stem) -> str`,
  `make_phantom_preview_fig(snapshot) -> dict | None`

- [x] **Step 1: Write failing tests** (inject snapshot — avoid global singleton pollution):
  - Known mesh (`hudfrid`) → Plotly dict with patient + table/pad Mesh3d.
  - Unknown stem → `None`, no raise.
  - **Scaling:** `scale_lat=1.2` / `scale_ap=1.2` / `scale_lon=1.2` and nonuniform `(1.2, 0.8, 1.4)`
    change the corresponding spans (ratios on preview mesh).
  - **Offsets:** nonzero `d_lon` (etc.) shifts the positioned patient vs zero offsets.
  - `resolve_preview_mesh` picks reduced when present, full when absent; package-relative; no
    double-append.
  - Feet-first ≠ head-first after positioning.
  - Figure layout includes `uirevision` equal to logical stem.
  - No RDSR still builds.
  - Builder does not require the global `state` singleton.

- [x] **Step 2: Run** `pytest tests/unittests/test_gui_phantom_preview.py -v` — expect FAIL.

- [x] **Step 3: Implement** per construction path; lightweight `mesh_text`; `COLOR_*`;
  `get_camera_view()`; post-layout `uirevision`; Geometry-consistent always-dark theme;
  `safe_error_event` + `None`. (Expand Plotly `bdata` to lists in returned dict.)

- [x] **Step 4: Run tests** — expect PASS. (12 passed)

- [ ] **Step 5: Commit.** (deferred until user requests commit)


---

### Task 2: Mount on Settings + PageContext + async debounce + cross-tab wiring

**Files:**
- Create: `src/guiskindose/gui/phantom_preview_controller.py` (preferred)
- Modify: `page_context.py`, `tabs/settings.py`, `offset_handlers.py`,
  `tabs/geometry_builders.py`, and `app.py` where pose-affecting restore already refreshes Geometry

- [x] **Step 1: PageContext** — add `refresh_phantom_preview: Callable[[], None] = field(default=_noop)`.

- [x] **Step 2: UI** — under phantom model/mesh (near habitus scaling), add:
  - `ui.plotly` height **340–380 px**, `w-full`
  - sibling status `ui.label` (empty when plot OK)
  - caption via `copy_text(...)` covering setup pose, back on support, habitus scales, and
    **active-exam offsets when multiple exams are loaded** (else global offsets)

- [x] **Step 3: Preview controller** — owns timer, `preview_request_id`, plot + status refs:
  - `schedule_refresh()` bumps id, cancels pending timer, starts `GEOMETRY_DEBOUNCE_SEC` one-shot
  - On fire: `snapshot = capture_phantom_preview_snapshot(state)` on UI thread →
    `fig = await run.io_bound(make_phantom_preview_fig, snapshot)` → apply only if id current
  - `None` (build failure or NiceGUI cancel): `update_figure({})` + “Preview unavailable” status
    (no exception text; do not raise `require_io_result` into the UI)
  - Non-human model: `update_figure({})` + “Preview available for human mesh”
  - Assign `ctx.refresh_phantom_preview = controller.schedule_refresh`
  - **Call `schedule_refresh()` once at end of Settings `build(ctx)`** (initial paint)

- [x] **Step 4: Shared Settings handlers** for `phantom_model`, `human_mesh`,
  `patient_orientation`, `phantom_scale_lat/ap/lon`, and Settings patient-offset fields:
  - `reset_results()`
  - `ctx.refresh_geometry_preview()` where Geometry needs it
  - `ctx.refresh_phantom_preview()`

- [x] **Step 5: Cross-tab call sites** — also invoke `ctx.refresh_phantom_preview()` from:
  - `on_global_patient_offset_change` (Settings numbers + any shared path)
  - Geometry patient-offset slider commit / reset (`geometry_builders.py`)
  - `app.py` (or equivalent) restore/preset paths that already call `refresh_geometry_preview`
  - Per-exam offset changes (`_per_exam.py`); Settings tab navigation in `app.py`

- [ ] **Step 6: Manual smoke** — no RDSR; `hudfrid` + pediatric; each scale slider; nonuniform
  scales; offset nudges; head-first vs feet-first; orbit preserved while dragging scales; face-up
  readable; **initial paint non-blank**; multi-exam active-exam offset change updates preview;
  plane/cylinder shows human-only placeholder.

- [ ] **Step 7: Commit.** (deferred until user requests commit)

---

### Task 3: Help, copy, docs, validation

- [x] **Step 1: Help** — orientation + habitus + offsets check (incl. multi-exam active-exam note);
  reduced mesh when available; dose uses full STL. Prefer a short dedicated page under
  `docs/source/gui_help/` (e.g. `phantom_preview.md`) with a HelpButton near the plot, and/or
  extend `positioning_offsets.md` with a cross-link. Then `python scripts/sync_gui_help.py`.

- [x] **Step 2: Registries** — update `dev-docs/ui_copy.json` (caption, unavailable, human-only
  placeholder via `copy_text`), `help_registry.json`, `feature_doc_matrix.json`, and
  `glossary.json` if new terms ship. Run `check_ui_copy` / `check_help_registry` /
  `check_feature_doc_matrix`.

- [x] **Step 3: FEATURE_INVENTORY + CHANGELOG** Unreleased feature note.

- [x] **Step 4: Gates** — targeted pytest; ruff as needed; `check_file_sizes.py`; doc freshness.

- [ ] **Step 5: Commit.** (deferred until user requests commit)

---

### Task 4: Close-out

- [ ] Acceptance checklist green; update `TO_DO.md` / `index.md`; archive plan when done.

---

## Acceptance criteria

1. Settings shows a 3D **human** mesh preview **without RDSR**, including **on initial mount**
   (not only after the first control change).
2. Changing any lat/ap/lon habitus scale refreshes the preview (debounced) with correct span ratios.
3. Changing patient offsets refreshes the preview and shifts the positioned patient; in multi-exam
   mode the preview uses **active-exam** offsets (`effective_patient_offset_for_preview`).
4. Mesh, orientation changes refresh; feet-first ≠ head-first.
5. Prefers `_reduced_1000t` when present under package `phantom_data/`; dose path still uses full STL.
6. Stale in-flight renders cannot overwrite newer scale/offset selections; worker never reads live
   `state`.
7. User camera orbit is preserved across scale updates (`uirevision`); may reset on mesh change.
8. Face-up vs face-down distinguishable; caption does not claim `Y ≈ 0` with pad present.
9. `ctx.refresh_phantom_preview` registered and called from Settings **and** the listed cross-tab
   pose-changing call sites.
10. Failure or cancel → privacy-safe “Preview unavailable” status + empty figure (no exception text).
11. Colors match shipped `COLOR_*`; always-dark preview panel; hover text is lightweight.
12. Unit tests cover scales, offsets, mesh resolve, orientation, `uirevision`, no-RDSR, snapshot
    injection (under `tests/unittests/`).
13. Help + `ui_copy` / `help_registry` / `feature_doc_matrix` updated when new strings/features ship;
    CHANGELOG noted.

## Out of scope (v1)

- Replacing the Geometry tab live preview.
- Editing mesh AP orientation in the GUI (`force_flip_y` / ingest remains the fix path).
- Per-exam **composite** previews on Settings (active-exam offsets only).
- Streaming full high-poly STLs when a reduced companion exists.
- Claiming reduced-preview bounds equal full-mesh calculation bounds.
- **Cylinder / plane Settings preview** (optional Phase 1.5 after human path ships).
- New patient/table color palette unrelated to `COLOR_*` constants.
- Expanding `default_geometry_layout` solely for Settings `uirevision` (set on the figure instead).
- Optional first-load spinner (nice-to-have only if full-STL fallback feels hitchy).
