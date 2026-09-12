# README Polish Plan

_Date: 2026-09-11. Status: proposed. Implements the TO_DO "README review and
polish" Next Up item._

## Goal

Make `README.md` sell the GUI-first project in 60 seconds: what it does, what
it looks like (screenshots), how to launch it, then headless/API detail. Fix
stale claims and close the Windows launcher gap. No behavior change.

## Pre-flight verification (done 2026-09-11, re-check at implementation)

- `run_gui.sh` **and** `run_gui.bat` exist — README documents only `.sh`.
- `siemens_axiom_example_procedure.dcm`, `hudfrid` mesh family,
  `--host`/`--allow-network`, `settings.plot.plot_dosemap`, and
  `analyze_normalized_data_with_custom_settings_object(..., output_format=...)`
  all exist as documented. No stale code references found; the work is
  restructure + additions, not corrections.

## Work items

### 1. Restructure (move, don't rewrite)

Proposed order: header + fork identity → **screenshots** → Intended use →
Quick launch (GUI) → What it does (condense current "What this code is for" +
workflow, move up) → Installation → Headless/API → Settings & modes →
Documentation → Notes for this fork.

Rationale: the project's stated focus is GUI usability, but the README buries
the GUI under install detail and never shows it.

### 2. Screenshots (privacy-gated)

- Captures: Upload tab (example RDSR loaded), Geometry preview, Results
  (dose map + PSD), Export tab. Prefer the bundled
  `siemens_axiom_example_procedure.dcm` session so captures are reproducible.
- Privacy bar (blocking): synthetic/example-data sessions only; no PHI/PII,
  patient names, MRNs, accessions, source filenames, or absolute paths visible
  in any capture (check window chrome, tooltips, file labels). Each image needs
  hash-pinned approved-asset clearance per
  `dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md` before commit.
- Hosting: commit under `docs/source/user/figures/` (or a `docs/`-adjacent
  asset dir already covered by inventory) and reference with relative links so
  both GitHub and RTD render them.
- Suggested reviewer: second pair of eyes on every capture before the PR
  merges (QUIS custodiet: the author is blind to their own paths).

### 3. Content additions

- Windows launcher: document `run_gui.bat` alongside `run_gui.sh`.
- Feature highlights (one line each, link to docs): multi-exam aggregation,
  tabular DoseTrack/Radimetrics imports, kerma-meter correction, rich
  XLSX/PDF/DOCX reports, human phantom library + habitus scaling.
- Keep the headless/API examples (verified current); trim duplication between
  "Typical usage" and "Useful helpers" if the restructure exposes it.

### 4. Explicit non-goals

- No behavior or CLI changes. No new docs pages (user guide owns depth).
- No real-patient captures, ever. No video/GIF (size + review burden).

## Acceptance

- Fresh-eyes test: a new user can state what the app does, launch the GUI on
  their OS, and run the headless example from the README alone.
- `python scripts/check_doc_freshness.py` passes (new image links resolve).
- All images cleared via the approved-asset inventory; no privacy-gate
  failures.
- CHANGELOG entry under `[Unreleased]`.

## Follow-ups (not this plan)

- PyData-theme RTD screenshots once the theme swap is live (before/after).
- Translated or video walkthroughs — deferred, see non-goals.
