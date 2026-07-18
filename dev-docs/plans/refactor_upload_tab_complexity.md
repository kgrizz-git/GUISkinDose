# Complexity Refactoring Plan: Upload Tab

This is the detailed companion to Phase 4.3 of
[the SonarQube remediation plan](sonarqube_remediation_plan.md). It targets
`build` in [upload.py](../../src/mypyskindose/gui/tabs/upload.py#L57), whose
baseline cognitive complexity is **97**.

The Import Preview widget has its own baseline complexity finding and is covered
by the remaining-GUI-components plan. This plan must use that widget's public
contract; it must not duplicate sheet-picker or coordinate-correction logic.

---

## 1. Target Architecture

Use a sibling module for the tab-local controller and layout builders:

```
src/mypyskindose/gui/tabs/
├── upload.py              # public build(ctx), compatibility constants/helpers
└── upload_builders.py     # UploadTabController, view refs, tab sections
```

`UploadTabController` receives `PageContext`, `AppState`, and the
`ImportPreviewWidget` it coordinates with. It owns uploader/status/exam-list
references and the upload/example/schema/remove/clear actions. It must call the
existing loader, transform, temporary-upload, and state helpers rather than
reimplementing their policies.

```python
class UploadTabController:
    def __init__(
        self,
        ctx: PageContext,
        app_state: AppState,
        import_preview: ImportPreviewWidget,
    ) -> None: ...

    async def handle_upload(self, event: UploadEventArguments) -> None: ...
    async def load_example(self) -> None: ...
    async def reparse_schema(self) -> None: ...
    def clear_all_exams(self) -> None: ...
    def remove_exam(self, index: int) -> None: ...
    def refresh_exams_table(self) -> None: ...
```

`handle_upload` remains the only owner of the `upload_lock` boundary. Keep the
small, independently tested `upload_exceeds_limit` helper at its stable public
location or re-export it during the transition.

---

## 2. Complexity Budget

| Function/method | Maximum complexity |
|---|---:|
| `upload.build` | 4 |
| `build_upload_panel` | 8 |
| `build_example_and_schema_controls` | 8 |
| `build_loaded_exams_section` | 10 |
| `handle_upload`, `load_example`, `reparse_schema` | 12 each |
| `clear_all_exams`, `remove_exam`, `refresh_exams_table` | 12 each |
| Any other extracted helper | 12 |

The desired maximum is **12**. Verify all newly created helpers with SonarQube;
moving a long closure into `handle_upload` unchanged is not an acceptable result.

---

## 3. Behaviour and Privacy Invariants

1. Keep client and server size limits (`MAX_UPLOAD_BYTES`), accepted suffixes,
   automatic uploader reset, and the operation/upload locks.
2. Preserve the temporary-file lifecycle: create only via the private temporary
   upload helper, retain files needed by multi-exam state, remove a file only when
   no loaded exam references it, and clear all through the existing helper.
3. Preserve DICOM versus tabular routing, schema re-parse behaviour, Excel-sheet
   discovery, import-preview refresh/default-transform calls, and error messages.
4. Preserve loaded-exam ordering, active-exam selection, remove/clear behaviour,
   Data/Settings/Geometry refreshes, and result invalidation.
5. Keep source filenames and paths out of runtime diagnostics beyond the existing
   user-facing state; do not introduce raw logging while moving callbacks.
6. Retain existing UI copy, help registration, and layout classes.

---

## 4. Reviewable Steps and Verification

1. Introduce the controller/view references and move refresh/remove/clear paths
   first, with tests for multi-exam state and temporary-file reference handling.
2. Move upload/example/schema async paths while preserving lock and error paths.
3. Move layout builders and reconnect the Import Preview widget only through its
   public fields/callbacks. Delete the obsolete closures once their replacements
   are covered.
4. Re-run SonarQube and inspect the complexity of each controller action.

```bash
uv run pytest tests/unittests/test_gui_temp_uploads.py \
  tests/unittests/test_gui_rdsr_df.py \
  tests/unittests/test_input_adapters.py
uv run pytest tests/gui/test_gui_security.py \
  tests/gui/test_gui_flows.py \
  tests/gui/test_multi_exam_gui.py
uv run ruff check src/mypyskindose/gui/tabs tests
uv run basedpyright
```

**Completion criterion:** the baseline `upload.build` finding and all new helper
findings are below the configured threshold, upload/privacy/multi-exam contracts
remain covered, and the local SonarQube scan resolves the original issue without
creating another.
