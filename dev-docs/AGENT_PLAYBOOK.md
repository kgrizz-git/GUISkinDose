# Agent Playbook

Shared operating guidance for coding agents and human maintainers. Tool-specific files should point here rather
than duplicating these rules.

## Recognized Agent Files

Use the smallest set of tool-specific files with documented behavior:

| Tool | File | Notes |
|---|---|---|
| Codex and other AGENTS-aware tools | `AGENTS.md` | Primary project orientation. |
| Claude Code | `CLAUDE.md` | Imports `AGENTS.md`; Claude Code reads `CLAUDE.md`, not `AGENTS.md` directly. |
| Gemini CLI | `GEMINI.md` | Gemini CLI defaults to `GEMINI.md`; it can also be configured to use `AGENTS.md`. |
| Qwen Code | `QWEN.md` | Qwen Code defaults to `QWEN.md`; `context.fileName` can be customized. |

Do not add model-family files such as `KIMI.md` unless that tool has a documented repository-context filename.

## Before Editing

- Read `AGENTS.md` first, then this file.
- Use `dev-docs/index.md` to find the source-of-truth doc before changing behavior or docs.
- Search existing code and tests before adding abstractions.
- Check `git status --short` and avoid overwriting unrelated user changes.
- Do not use bare `python` for the third-party license inventory: it may select a
  global interpreter. Use `uv run --extra dev --extra gui --locked python
  scripts/check_licenses.py` (add `--write-notices` or `--check-notices` as needed)
  so local results match CI.

## While Editing

- Keep changes **cross-platform** (Windows, macOS, Linux): portable Python in `src/`, guarded fallbacks instead of
  platform-only code paths, and CI-safe tests without optional GUI extras unless the test is explicitly skipped or
  lives under `tests/gui/`. See `AGENTS.md` → Conventions → Cross-platform.
- Keep Python source and Markdown docs under the 800-line limit enforced by `scripts/check_file_sizes.py`.
- Update `AGENTS.md` and the relevant `dev-docs/` page when a change adds, removes, or wires behavior.
- Edit GUI help source under `docs/source/gui_help/`; mirrored files under `src/guiskindose/gui/help/` are generated.
- Put diagnostics and assessments under `dev-docs/assessments/` and register them in `dev-docs/index.md`.
- **TO_DO.md rules:** 
  - Ensure `dev-docs/TO_DO.md` has a **Next Up** section near the top containing 3-5 items. These must be short pointers to main, detailed todo items, not full entries themselves.
  - Every active execution plan must have a corresponding todo item linking to it in `dev-docs/TO_DO.md`.
  - When completing a task, **remove it entirely** from `dev-docs/TO_DO.md`. Log user-facing changes in `CHANGELOG.md` under the 'Unreleased' section. Ensure under-the-hood work (like tests or refactoring) is captured in the commit history or an archived plan rather than left as checked-off in the TO_DO.
  - **Manual Smokes:** If a plan or todo item is completely finished except for a pending manual smoke test, archive the plan (or remove the todo item) and bundle its manual smoke requirement into a consolidated "Manual Smokes" pointer in the **Next Up** section.
- Archive completed or superseded execution plans under `dev-docs/plans/archive/` and update `dev-docs/index.md`.
- Keep scratch scripts and temporary outputs in gitignored paths such as `tmp/`, `scripts/scratch_*`, `*.tmp`, or
  `debug_*`, or delete them before finishing.

## Privacy and sensitive data

Treat PHI/PII exposure as a first-class defect — in committed content **and** in what code emits at runtime.

- **Never log, print, or write raw identifiers** — patient/study/institution/physician fields, DICOM header values,
  source filenames, or absolute paths. Log a non-identifying summary or route the value through a redaction helper.
  Writes must target gitignored, user-known output paths (e.g. `PlotOutputs/`, `tmp/`) and the destination should be
  surfaced to the user; never write sensitive content to tracked files.
- **Run the scanner that matches the change, and triage its findings — do not ignore advisories:**
  - Before committing, inspect the staged route with `python scripts/privacy_admission.py route --mode staged`, then
    run `python scripts/privacy_admission.py run --mode staged`. The receipt hook blocks when an applicable scanner did
    not complete cleanly against the exact staged content/configuration. Receipts are private under Git metadata.
  - Tracked text, docs, or fixtures that could carry identifiers → the blocking gate runs automatically
    (`scripts/check_sensitive_content.py --require-approved-assets`); for a structured-identifier NLP second opinion run
    `uv run --no-sync python scripts/run_presidio_advisory.py`. Add `--include-person --verbose-paths` only for a
    targeted local free-text/name review.
  - Source code that logs or writes → the blocking privacy rules
    (`python scripts/run_semgrep_privacy.py`, also a pre-push/CI hook) and required local HoundDog receipt when routed.
  - Adding or changing a DICOM/image asset → the route requires the safe local DICOM or image-OCR wrapper before
    recording the review in `dev-docs/approved_asset_inventory.json`.
- **Cadence:** phi-scan (Thu) and calibrated Presidio (Mon) run on a weekly schedule + manual dispatch;
  Presidio no longer auto-runs on PRs (removed Jul 2026). Run phi-scan/Presidio for new tracked CSV/TSV or likely
  identifier-bearing text; run Semgrep plus HoundDog for logging/write/export/ingestion/API/database changes; run the
  DICOM scanner and full human checklist for every added or changed DICOM.
- **Advisory ≠ optional.** Every advisory finding must be fixed, or annotated as a reviewed false positive with a
  trailing `# nosemgrep: <rule-id>` (or an allowlist/inventory entry) plus a one-line reason — never silently dropped.
- Run commands live in `dev-docs/references/LOCAL_PII_MODELS.md`; policy is in `dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md`.
- Never weaken a protected ignore rule or force-add a path under a never-track root. The blocking policy is
  `dev-docs/privacy_admission_policy.json`; standard Git has no dependable pre-add hook, so commit/push/CI are the
  enforcement boundaries.

## Before Finishing

Run the smallest meaningful verification set for the change. Common checks:

```bash
python scripts/check_agent_guidance.py
python scripts/check_doc_freshness.py
python scripts/check_doc_pruning.py
python scripts/check_file_sizes.py
python scripts/check_changelog.py
pre-commit run --all-files
python -m pytest tests/ -q
basedpyright
```

For narrow script changes, run that script's unit tests and the script itself. For GUI changes, run the relevant
NiceGUI user-simulation tests under `tests/gui/` or `tests/unittests/test_gui_*.py`.

`playwright` and `pytest-playwright` are installed (part of `[dev]`) with a Chromium headless shell. Use Playwright
only when explicitly asked to verify visual layout — for example, when running the `/verify` skill on a CSS or
layout-only change where the NiceGUI test client cannot observe the rendered result. Do not add Playwright to the
routine pre-commit or CI verification loop.
