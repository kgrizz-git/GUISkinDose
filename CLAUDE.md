# MyPySkinDose — Claude Code instructions

Read **[AGENTS.md](AGENTS.md)** first for full project orientation, architecture, conventions, and development setup. This file is the quick-reference layer auto-loaded by Claude Code.

---

## Plan lifecycle (most commonly forgotten)

When every checklist item and exit condition in an execution plan (`dev-docs/plans/*.md`) is met:

1. `git mv dev-docs/plans/<file>.md dev-docs/plans/archive/`
2. Add a row to `dev-docs/plans/archive/README.md`
3. Add the file to the **Archived plans** table in `dev-docs/index.md` (remove it from the Execution plans table if it was listed there)
4. Update any links in `dev-docs/TO_DO.md` to point to the new `plans/archive/` path
5. Include all of the above in the same commit/PR as the final implementation change

---

## Doc update rule

Any change that adds, removes, or wires a feature must update `AGENTS.md` and the relevant `dev-docs/` page in the same PR.

---

## Validation commands

```bash
python scripts/check_doc_freshness.py    # broken links + inventory contradictions
python scripts/check_file_sizes.py       # enforce <800 lines per file
python scripts/check_changelog.py        # CHANGELOG.md updated when src/tests changed
pre-commit run --all-files               # ruff, gitleaks, bandit, doc + size checks
python -m pytest tests/ -q              # unit + GUI smoke
basedpyright                             # type check (also runs as pre-push hook)
```
