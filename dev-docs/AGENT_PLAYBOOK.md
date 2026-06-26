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

## While Editing

- Keep changes **cross-platform** (Windows, macOS, Linux): portable Python in `src/`, guarded fallbacks instead of
  platform-only code paths, and CI-safe tests without optional GUI extras unless the test is explicitly skipped or
  lives under `tests/gui/`. See `AGENTS.md` → Conventions → Cross-platform.
- Keep Python source and Markdown docs under the 800-line limit enforced by `scripts/check_file_sizes.py`.
- Update `AGENTS.md` and the relevant `dev-docs/` page when a change adds, removes, or wires behavior.
- Edit GUI help source under `docs/source/gui_help/`; mirrored files under `src/mypyskindose/gui/help/` are generated.
- Put diagnostics and assessments under `dev-docs/assessments/` and register them in `dev-docs/index.md`.
- Archive completed or superseded execution plans under `dev-docs/plans/archive/` and update `dev-docs/index.md`.
- Keep scratch scripts and temporary outputs in gitignored paths such as `tmp/`, `scripts/scratch_*`, `*.tmp`, or
  `debug_*`, or delete them before finishing.

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
