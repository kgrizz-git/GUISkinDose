# Run configuration

## Privacy

Run configurations are de-identified by default: source filenames, absolute
paths, equipment labels, study and sheet names are stored as `null` unless you
opt in with **Include source identifiers**. Path-valued fields are stored as
the user-facing basename only — never an absolute path — even when identifiers
are included, except `corrections_db_path`, which is stored verbatim so the
calculation can resolve it. Store every exported configuration in an approved
destination and apply the appropriate retention policy.

Use the Settings tab card to save the full GUI run state (settings, physics,
phantom geometry, corrections, and per-exam offsets) as a single JSON
document, or load one back to reproduce a run exactly.

Saving writes the document through a native save dialog (native mode) or a
browser download. Loading accepts a `.json` run-configuration document:

1. Load the same input files first, in the same order and count — the import
   applies per-exam corrections positionally and cannot pair documents to
   different inputs.
2. Choose the file with **Load run configuration**. Mismatches (a document
   referencing files that are not loaded, or differing basenames) warn loudly
   and leave the live session untouched — a basename can never restore a file
   location, so re-select the referenced files instead.
3. If the document changes the input schema or sheet, tabular inputs re-parse
   before per-exam offsets are restored. With multiple exams loaded, reload
   the files and re-import instead.
4. Calculation results reset on import; recalculate to reproduce the run.

Documents carry a `schema_version`: newer-than-supported documents are
rejected, and unknown future keys are preserved across re-export. A document
whose mode is not `calculate_dose` imports its settings but still calculates
with `calculate_dose`, which is the only mode the GUI runs.
