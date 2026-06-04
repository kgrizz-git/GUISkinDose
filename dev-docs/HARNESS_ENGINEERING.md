# Harness engineering alignment

_Date: 2026-06-04_

This document turns the repository into a more reliable harness for AI agents and human maintainers. It is based on the OpenAI harness-engineering pattern: keep project knowledge in the repo, make `AGENTS.md` a concise map, encode recurring checks as commands, and prefer mechanical validation over tribal knowledge.

## Repository contract for agents

Agents working in this repository should be able to answer three questions quickly:

1. **What is this system?**
   MyPySkinDose estimates peak skin dose and 3D skin dose maps from fluoroscopic irradiation event data.
2. **Where is the authoritative context?**
   `AGENTS.md` is the short entry point. Detailed context lives in `dev-docs/`.
3. **How do I validate changes?**
   Use the checks listed below and add/extend tests when changing behavior.

## Source-of-truth map

| Topic | File |
|---|---|
| Agent quickstart, conventions, current development focus | `AGENTS.md` |
| Architecture and data flow | `dev-docs/CODEBASE_OVERVIEW.md` |
| Feature inventory and known missing features | `dev-docs/FEATURE_INVENTORY.md` |
| GUI implementation status and plan | `dev-docs/GUI_PLAN.md` |
| GUI current-state analysis | `dev-docs/UI_ANALYSIS.md` |
| Tabular CSV/TSV/XLSX input plan | `dev-docs/TABULAR_RDSR_INPUT_PLAN.md` |
| Short-term task list | `dev-docs/TO_DO.md` |
| Project packaging and tool configuration | `pyproject.toml` |
| CI | `.github/workflows/ci.yml` |

## Golden rules

1. **Keep docs current with behavior.**
   If a change adds, removes, or wires a feature, update `AGENTS.md` and the relevant `dev-docs/` page in the same PR.
2. **Do not hide input transformations.**
   RDSR parsing, tabular imports, unit conversions, and normalization offsets must be documented and tested.
3. **One internal calculation contract.**
   All input sources should feed the same normalized DataFrame contract before dose calculation.
4. **Optional UX dependencies stay optional.**
   GUI and Excel-specific dependencies should remain extras unless maintainers intentionally promote them to core.
5. **Cross-platform by default.**
   Use `pathlib.Path`, avoid shell-specific path assumptions in Python code, and keep CI on Windows/macOS/Linux.
6. **Fail loudly on clinical-data ambiguity.**
   Unknown units, missing geometry, unsupported scanner models, or ambiguous tabular schemas should produce actionable errors or explicit warnings before calculation.

## Validation commands

Run the smallest relevant set locally before committing, and run the full set before changes that affect calculations, parsing, packaging, or CI.

### Fast checks

```bash
python -m compileall src/mypyskindose
python -m pytest tests/unittests
```

### Full checks

```bash
python -m pytest
python -m ruff check src tests
python -m build
```

### Documentation freshness check

Before committing a feature/status change, search for stale references:

```bash
rg -n "not implemented|not wired|TODO|planned|Phase|csv|xlsx|tsv|gui" AGENTS.md README.md dev-docs src tests
```

Then update any text that is no longer true.

## CI expectations

CI should be treated as a blocking quality gate, not only as telemetry:

- syntax/lint checks should fail the workflow on errors
- tests should fail the workflow on errors
- cross-platform matrix should remain active
- docs-only changes may run a smaller check set, but should still pass basic syntax and markdown/link sanity when such tooling exists

## PR checklist

Every PR should answer:

- What changed?
- Which user workflow is affected?
- Which files are the source of truth for this behavior?
- Which commands were run?
- Were docs updated with code behavior?
- Are there new clinical-data assumptions, unit conversions, or normalization rules?
- Are dependencies still correctly classified as core vs optional extras?

## Known alignment gaps

- The repo still has generated `src/mypyskindose.egg-info/` files tracked. Decide whether to keep them synchronized intentionally or remove them from version control in a cleanup PR.
- There is no dedicated doc-freshness linter yet; currently this is a manual search/checklist step.
- There are no automated GUI browser/screenshot smoke tests yet.
- Tabular input adapters are planned but not implemented.
