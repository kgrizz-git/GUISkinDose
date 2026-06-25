# Archived execution plans

Completed or superseded phased work lives here for traceability. Do not start new plans in this folder.

| File | Status | Notes |
|---|---|---|
| [basedpyright-fix-plan.md](basedpyright-fix-plan.md) | **Completed** (2026) | 147 errors resolved; CI runs strict `basedpyright`. Moved from `src/mypyskindose/dev-docs/`. |
| [HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md) | **Completed** (2026) | Phased roadmap to align the repository to agent-first harness standards (Phases 0–5 complete, Phase 6 closed, Phase 7 implemented/stubs tracked). |
| [recursion-to-iteration.md](recursion-to-iteration.md) | **Completed** (2026-06-16) | Replace per-event tail recursion in `calculate_irradiation_event_result()` with a loop; golden baseline + 1100-event stress test. |
| [hvl-invalid-event-crash.md](hvl-invalid-event-crash.md) | **Completed** (2026-06-13) | Fix HVL-lookup `IndexError` on out-of-grid kVp events; nearest-grid snap, fail-soft, count surfaced in GUI. |
| [multiple-exams.md](multiple-exams.md) | **Completed** (2026-06-19) | Multi-exam support: core data model, CLI multi-file, GUI Phases 1–2.5 (upload accumulation, per-exam overrides). GUI smoke check pending (see TO_DO). |
| [multi-exam-data-table-and-settings.md](multi-exam-data-table-and-settings.md) | **Completed** (2026-06-19) | Data Table `Exam` tag column (`rebuild_rdsr_df`); per-exam corrections moved to Settings → Per-exam corrections (`gui/tabs/_per_exam.py`). |
| [hvl-interpolation-and-below-floor-kvp.md](hvl-interpolation-and-below-floor-kvp.md) | **Completed** (2026-06-19) | HVL + `k_tab` linear interpolation with exact/interpolated/clamped flags (`grid_interp.py`); below-floor (kVp < 25) policy `snap`/`skip`/`manual`/`exam_average` (`geom_calc.apply_below_floor_kvp_policy`) with a Settings control + pre-calc prompt. Manual GUI smoke check pending (see TO_DO). |
| [refactor-execution.md](refactor-execution.md) | **Completed** (2026-06-23) | Phased refactor from [REFACTOR_ASSESSMENT.md](../../assessments/REFACTOR_ASSESSMENT.md): Phases 0–3 (temp uploads, logging, busy guard, adapter consolidation, GUI decomposition). `app.py` 1275→245 lines; Phase 4 opportunistic. Companion: [gui-decomposition-design.md](gui-decomposition-design.md). |
| [gui-decomposition-design.md](gui-decomposition-design.md) | **Completed** (2026-06-23) | Wiring map and extraction design for Phase 3 GUI split; archived with refactor-execution. |
| [NO_PATIENT_INTERSECTION_WARNING_PLAN.md](NO_PATIENT_INTERSECTION_WARNING_PLAN.md) | **Completed** (2026-06-24) | Beam-miss warnings: per-event WARNING when beam does not intersect patient phantom; `beam_miss_warn` setting (off/summary/per_event); all-miss sentinel; GUI toast throttle; handler leak fix. |
| [PATIENT_SIZE_SCALING_PLAN.md](PATIENT_SIZE_SCALING_PLAN.md) | **Completed** (2026-06-25) | Human STL body-habitus scaling: `scale_lat`/`scale_ap`/`scale_lon`, anchored mesh scaling, recomputed normals, Settings sliders, and geometry/dose plumbing. |
| [GEO_TAB_SPINNING_WHEEL_PLAN.md](GEO_TAB_SPINNING_WHEEL_PLAN.md) | **Completed** (2026-06-25) | Break the self-reinforcing render cycle in the Geometry tab with an `_in_render_chain` closure flag; preserves external `ctx.refresh_per_exam()` paths; adds parametrized regression tests for patient and table-origin sliders. |
| [FIRST_RUN_ONBOARDING_PLAN.md](FIRST_RUN_ONBOARDING_PLAN.md) | **Completed** (2026-06-25) | First-run GUI onboarding modal with persistent "Don't show again" preference in `~/.mypyskindose/gui.json`. |
| [GEOMETRY_TABLE_ORIGIN_SLIDER_VALUES_PLAN.md](GEOMETRY_TABLE_ORIGIN_SLIDER_VALUES_PLAN.md) | **Completed** (2026-06-25) | Geometry table-origin slider value labels mirror patient-offset labels. |
| [CROSS_TAB_SLIDER_SYNC_PLAN.md](CROSS_TAB_SLIDER_SYNC_PLAN.md) | **Completed** (2026-06-25) | Settings edits refresh Geometry sliders, labels, and preview on tab entry. |

For active work, see [TO_DO.md](../../TO_DO.md) and execution plans in [../](../).
