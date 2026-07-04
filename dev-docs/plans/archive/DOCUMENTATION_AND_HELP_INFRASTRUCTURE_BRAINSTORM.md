# Plan: Documentation and Help Infrastructure Integration

This document outlines a high-level plan and brainstorming ideas for ensuring that all developer documentation, user help files, inline tooltips, and informational popups stay accurate, complete, and synchronized with the codebase.

---

## 1. Current State Assessment

MyPySkinDose already has a solid foundation for documentation consistency:
- **`docs/source/gui_help/`**: Single source of truth for in-app markdown help pages.
- **[scripts/sync_gui_help.py](../../../scripts/sync_gui_help.py)**: Mirrors the markdown help files to `src/mypyskindose/gui/help/`. Checked via pre-commit and CI.
- **[scripts/check_doc_freshness.py](../../../scripts/check_doc_freshness.py)**: Validates markdown files for broken relative links, absolute path references, stale terms, and FEATURE_INVENTORY inconsistencies.
- **[tests/unittests/test_input_schema_doc.py](../../../tests/unittests/test_input_schema_doc.py)**: Ensures `INPUT_SCHEMA_DETECTION.md` matches unit-test expectations and code facts.

### Main Gaps
1. **Hardcoded Inline Tooltips**: Many UI field tooltips and short explanations in the GUI files are hardcoded strings, which are not checked for accuracy or presence.
2. **Feature Coverage Tracking**: There is no automated verification that new features implemented in the code are documented in the user manual or feature inventory.
3. **No Direct Code-to-Doc Linkage**: Coordinate conventions, offset behaviors, and normalization data flows are described in prose (e.g., [VENDOR_COORDINATE_SYSTEMS.md](../../VENDOR_COORDINATE_SYSTEMS.md)), but there's no programmatic check ensuring the code conforms to the documented matrices/labels.
4. **Prose and Backtick Link Drift**: The doc-freshness script does not verify relative file paths mentioned in backticks (e.g. `` `dev-docs/plans/foo.md` ``) or as bare text, causing links to break when files are archived or renamed.

---

## 2. Brainstorming Ideas for Documentation Infrastructure

Here are six concrete ideas to improve documentation quality, completeness, and synchronization:

### Idea 1: UI Tooltip & Label Centralization
* **Concept**: Move all UI labels, helper texts, tooltips, and popup contents from inline Python strings into a unified schema-backed file (e.g., `gui_strings.yaml` or `gui_strings.json`).
* **Why**: Prevents UI copy-paste drift, facilitates future localization/internationalization, and makes it easy to audit every single UI tooltip in one place.
* **Infrastructure**: 
  - A validation test checking that every form component (`ui.input`, `ui.slider`, etc.) references a key in `gui_strings.yaml`.
  - A static analysis script that fails if any string in `gui_strings.yaml` is unused, or if a component is added without a tooltip.

### Idea 2: Automated Help-Tab Coverage Testing
* **Concept**: Statically analyze GUI component files to assert that every tab/view contains a `HelpButton` pointing to a valid markdown help page.
* **Why**: Ensures that no page is left undocumented and that users always have immediate context.
* **Infrastructure**: 
  - A unittest that imports the GUI tabs and verifies that a `HelpButton` object exists and that the `content_path` target is a valid `.md` file in `docs/source/gui_help/`.
  - Check for "orphaned" help files (markdown files in `docs/source/gui_help/` that are never referenced by any Python UI tab).

### Idea 3: Code-to-Doc Assertions (Executable Documentation)
* **Concept**: Use unit tests to verify that values and definitions in technical documentation match the code.
* **Why**: Prevents documentation from lying to developers when features change.
* **Infrastructure**:
  - Extend the pattern from `test_input_schema_doc.py` to other areas.
  - **Coordinate Mapping Check**: Parse the coordinate mapping tables in [VENDOR_COORDINATE_SYSTEMS.md](../../VENDOR_COORDINATE_SYSTEMS.md) and assert that they match the mappings configured in `mypyskindose/geom_calc.py` and `mypyskindose/gui/helpers.py`.
  - **Phantom Meshes Check**: Automatically parse [AGENTS.md](../../../AGENTS.md) and assert that the listed human meshes in the table match the actual mesh directories/files in the codebase.

### Idea 4: Enhance Doc-Freshness for Backticks and Prose Paths
* **Concept**: Extend [scripts/check_doc_freshness.py](../../../scripts/check_doc_freshness.py) to parse file paths listed in backticks (e.g. `` `dev-docs/plans/foo.md` ``) or bare paths in text.
* **Why**: Many plans and changelogs mention files in backticks. When these files are moved or archived (e.g., into `dev-docs/plans/archive/`), these references become stale but are currently ignored by the Markdown link regex checker.
* **Infrastructure**:
  - Add a regex scanner for backticked paths and verify that the target exists.
  - If a path points to a file that has been moved to `plans/archive/`, suggest the new archived path.

### Idea 5: In-App Documentation Search & Developer Overlay
* **Concept**: Introduce a "Help Center" tab or overlay in the GUI.
* **Why**: Makes the documentation interactive and accessible without leaving the app.
* **Infrastructure**:
  - Parse all markdown help files and render them dynamically in a collapsible navigation drawer or modal dialog.
  - Implement a developer debug mode toggled by an environment variable (`MYPYSKINDOSE_DEV_MODE=1`). When enabled, hover tooltips display their resource key from the strings catalog, making it easy to identify which string or help file needs editing.

### Idea 6: Automated Documentation Generation for Data Normalization Flows
* **Concept**: Automatically generate visual diagrams (such as Mermaid graphs) of the normalization and data extraction pipelines directly from the code metadata.
* **Why**: Data flows from DICOM RDSR or Tabular inputs (like DoseTrack/Radimetrics) down to the internal DataFrame contract can be extremely complex. A diagram that updates automatically ensures developers always understand the pipeline.
* **Infrastructure**:
  - Use Python introspection/decorators on input adapters to trace how columns are mapped, renamed, scaled, and flipped.
  - Write a script that runs in CI to generate a `normalization_flow.mermaid` file and embed it in `INPUT_DATA_FLOW_AND_OFFSETS.md`.

---

## Additional Brainstorming Ideas

The following ideas complement the infrastructure above and focus on *thoroughness*, *data-processing transparency*, and *sustained accuracy* over time.

### Idea 7: Living Glossary & Terminology Enforcement
* **Concept**: Maintain a single `GLOSSARY.md` (or `gui/glossary.yaml`) that canonically defines domain terms (PSD, HVL, k_tab, DAP, RDSR, CFA, beam-miss, below-floor kVp, etc.). All tooltips, help pages, and user-facing error messages must draw from or match these definitions.
* **Why**: Eliminates inconsistent explanations across tabs (e.g., one tooltip calls it "peak skin dose" and another calls it "maximum skin dose"). It also gives users a searchable reference.
* **Infrastructure**:
  - A linter script that flags any GUI string or markdown help file using a glossary term in a way that deviates from the canonical definition.
  - Optionally, a "Glossary" tab or drawer in the GUI that renders `GLOSSARY.md` with anchor links from highlighted terms in tooltips.

### Idea 8: Auto-Generated Data-Provenance Narrative
* **Concept**: Every time a calculation runs, produce a human-readable "Processing log" summarizing the exact pipeline steps for *this* dataset: which offsets were applied, which HVL interpolation method was used, whether any events were skipped due to below-floor kVp policy, what phantom scaling was active, and which vendor coordinate swaps occurred.
* **Why**: Turns the opaque data-normalization and correction logic into transparent, per-run documentation. Users and auditors can see *why* a PSD value is what it is without reading source code.
* **Infrastructure**:
  - Add a lightweight `ProcessingLog` collector in `analyze_data.py` (or the calculation pipeline) that appends a sentence per major stage.
  - Render the log in the Results tab and embed it in exported reports (HTML/PDF/XLSX).
  - A unit test asserting that every correction factor applied by `corrections.py` has a corresponding human-readable sentence template in the log registry.

### Idea 9: Feature-to-Documentation Traceability Matrix
* **Concept**: A machine-readable YAML/JSON matrix mapping each major feature (e.g., "multi-exam upload", "DoseTrack adapter", "body-habitus scaling") to its code entry points, test files, user manual section, GUI help page, and relevant settings fields.
* **Why**: Prevents features from shipping undocumented. When a PR modifies a code path listed in the matrix but does not touch the linked docs, CI can emit a warning or block merge.
* **Infrastructure**:
  - A `docs/feature_matrix.yaml` file checked into the repo.
  - A CI check (or local script) that compares `git diff --name-only` against the matrix and flags missing doc updates.
  - The matrix can also be rendered as a nice table in `FEATURE_INVENTORY.md` so it stays visible.

### Idea 10: In-App "Report Inaccurate Help" Feedback Loop
* **Concept**: Add a subtle feedback widget (e.g., a thumbs-up/thumbs-down or "Report" link) at the bottom of every GUI help modal and tooltip.
* **Why**: Creates a continuous, user-driven accuracy signal. Even with perfect automated checks, users are the ultimate arbiters of whether a help popup actually helps.
* **Infrastructure**:
  - Store feedback in a local SQLite file or `gui.json` for privacy.
  - A maintenance script (`scripts/review_help_feedback.py`) that aggregates reports and suggests which help files or tooltips need attention.
  - Could auto-generate a GitHub issue template pre-filled with the help page name and user comment.

### Idea 11: Doc-Impact Git Hook & Stale-Doc Detector
* **Concept**: A pre-commit or pre-push script that, when Python source files change, lists the documentation and help files that *should* probably be reviewed based on the feature matrix (Idea 9) or simple heuristics (e.g., `corrections.py` changed → check `gui/help/calculations.md`).
* **Why**: Shifts doc maintenance left. Developers see the doc implications of their changes before opening a PR.
* **Infrastructure**:
  - A lightweight Python script using `git diff` and the feature matrix to print advisory warnings (non-blocking by default, can be made strict later).
  - A complementary "stale-doc detector" that uses `git log` to find docs/help files not updated in N days while their linked source files *have* been updated, flagging likely drift.

### Idea 12: Screenshot-Driven Help Regression Tests
* **Concept**: Use a headless browser or NiceGUI CDP smoke tests to capture screenshots of every help modal, tooltip, and info popup after GUI startup.
* **Why**: Catches visual regressions (e.g., a tooltip rendered off-screen, a markdown table broken by a CSS change, or a popup truncated in native mode) that text-based linters cannot see.
* **Infrastructure**:
  - Extend existing GUI smoke tests in `tests/gui/` to trigger each `HelpButton` and save a PNG.
  - Store baseline screenshots in `tests/gui/baselines/`; fail CI if a pixel diff exceeds a threshold. Start as an *advisory* job to avoid flaky blocking.

### Idea 13: Per-Release Documentation Audit Checklist Generator
* **Concept**: A script that runs at release time (or on-demand) and auto-generates a Markdown checklist of every doc, help file, and tooltip touched since the last tag, plus any items flagged by the stale-doc detector (Idea 11).
* **Why**: Ensures no doc debt slips into a release. The checklist becomes a mandatory part of the release PR.
* **Infrastructure**:
  - `scripts/generate_release_doc_audit.py` that queries `git log <last-tag>..HEAD --name-only` filtered to `docs/`, `dev-docs/`, `src/mypyskindose/gui/help/`, and GUI source files with tooltip strings.
  - The output is appended to the release PR description or a `RELEASE_DOC_AUDIT.md` artifact.

---

## 3. Recommended Next Steps

For a phased roll-out, we suggest prioritizing:

1. **Phase 1: Deepen Freshness Checks**
   - Implement **Idea 4** (backtick and prose path scanning) in `scripts/check_doc_freshness.py`. This is low-risk and immediately cleans up documentation debt.
2. **Phase 2: UI Help Button Coverage Test**
   - Implement **Idea 2** to guarantee every tab has verified help button context.
3. **Phase 3: Code-to-Doc Mappings**
   - Programmatically verify that coordinate axes conventions in `VENDOR_COORDINATE_SYSTEMS.md` correspond to internal variables.
4. **Phase 4: UI String Centralization**
   - Refactor UI tooltips and labels into a catalog (`gui_strings.yaml`) to decouple UI copy from layouts.
