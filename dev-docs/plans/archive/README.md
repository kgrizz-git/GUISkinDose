# Archived execution plans

Completed or superseded phased work lives here for traceability. Do not start new plans in this folder.

| File | Status | Notes |
|---|---|---|
| [basedpyright-fix-plan.md](basedpyright-fix-plan.md) | **Completed** (2026) | 147 errors resolved; CI runs strict `basedpyright`. Moved from `src/mypyskindose/dev-docs/`. |
| [HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md](HARNESS_ENGINEERING_IMPROVEMENT_PLAN.md) | **Completed** (2026) | Phased roadmap to align the repository to agent-first harness standards (Phases 0–5 complete, Phase 6 closed, Phase 7 implemented/stubs tracked). |
| [recursion-to-iteration.md](recursion-to-iteration.md) | **Completed** (2026-06-16) | Replace per-event tail recursion in `calculate_irradiation_event_result()` with a loop; golden baseline + 1100-event stress test. |
| [hvl-invalid-event-crash.md](hvl-invalid-event-crash.md) | **Completed** (2026-06-13) | Fix HVL-lookup `IndexError` on out-of-grid kVp events; nearest-grid snap, fail-soft, count surfaced in GUI. |
| [multiple-exams.md](multiple-exams.md) | **Completed** (2026-06-19) | Multi-exam support: core data model, CLI multi-file, GUI Phases 1–2.5 (upload accumulation, per-exam overrides). GUI smoke check pending (see TO_DO). |

For active work, see [TO_DO.md](../../TO_DO.md) and execution plans in [../](../).
