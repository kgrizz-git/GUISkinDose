# Documentation Tooling Decision — 2026-09-11

_Decision log closing the `TO_DO.md` "User-Facing Documentation Tooling
Evaluation" item. Spike memo (no decision) is
[DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md](DOCUMENTATION_TOOLING_EVALUATION_2026-09-06.md)._

## Decision

**Keep Sphinx + ReadTheDocs; restyle with the PyData Sphinx Theme.**
No migration to MkDocs/Material, Zensical, or a hosted SaaS (Mintlify/GitBook).

- Implementation (theme swap in `docs/source/conf.py` + `pyproject.toml`
  `docs` extra) is a separate small follow-up, not this record. Expected
  near-zero migration: theme + config swap only; autodoc, nbsphinx, MyST, and
  RTD hosting stay unchanged.
- Revisit triggers (§4). Until one fires, tooling threads are closed.

## 1. Criteria (solo-maintained OSS, Python library + GUI)

1. Native Python API autodoc from docstrings (no manual API pages).
2. Executable getting-started notebook in the docs build.
3. Zero license/hosting cost; no vendor lock-in for content or build.
4. Near-zero migration (maintainer time is the binding constraint).
5. Healthy upstream (no maintenance-mode / rewrite risk on the critical path).

## 2. Re-verification deltas since 2026-09-06 (all accessed 2026-09-11)

- **MkDocs path is now worse.** Material for MkDocs is in maintenance mode
  (12-month critical-fix support from the Nov 2025 Zensical announcement);
  MkDocs 1.x is unmaintained (supply-chain risk); MkDocs 2.0 is a ground-up
  rewrite incompatible with Material and existing plugins; `mkdocstrings` is
  officially in maintenance mode (bug fixes only, maintained "at least until
  end of 2026", then possibly archived). The old shortlist #1 now fails
  criterion 5 on two load-bearing dependencies.
- **Zensical** (MIT, by the Material team, reads `mkdocs.yml`) is the
  designated MkDocs successor, but module/feature parity is incomplete and its
  Python-autodoc story still routes through the same maintenance-mode
  `mkdocstrings`. Not yet evaluable against criteria 1–2; watch, do not adopt.
- **Mintlify** repriced again (Starter free with outcome-based AI credits since
  Sept 2026), but the project-relevant facts are unchanged: no Python
  docstring renderer, no Jupyter execution, high migration (RST→MDX plus JS
  toolchain), proprietary components/search. Fails criteria 1, 2, 4.
- **PyData Sphinx Theme** is healthy (v0.20/v0.21, Sphinx 8.2+–<10) and is a
  config-only swap over the existing Sphinx + nbsphinx + RTD stack. Passes all
  five criteria; the polish gain from RTD-theme → PyData is the largest
  available at zero migration cost.

## 3. Options verdict

| Option | Verdict |
|---|---|
| Sphinx + PyData theme | **Adopt** (theme swap follow-up) |
| Sphinx + RTD theme (status quo) | Fallback if the swap regresses the build |
| sphinx-immaterial / Furo | Co-candidates if PyData proves heavy; same zero-migration class |
| MkDocs + Material / mkdocstrings | Rejected: maintenance-mode stack (criterion 5) |
| Zensical | Rejected for now: parity + autodoc story incomplete; re-evaluate on triggers |
| Mintlify / GitBook / Docusaurus / Starlight / VitePress | Rejected: no autodoc/notebooks, high migration, and/or lock-in |

## 4. Revisit triggers

- PyData theme becomes unmaintained or incompatible with supported Sphinx.
- Zensical reaches plugin/autodoc parity with a documented Python-API path.
- A hosted option gains native docstring + notebook support with portable Markdown.

## 5. Follow-ups (not this record)

- Theme-swap PR: `pyproject.toml` `docs` extra + `docs/source/conf.py`, rebuild
  + RTD preview, screenshot before/after.
- Keep `mkdocs`-adjacent ideas out of the backlog until a trigger fires.

## 6. Sources (all accessed 2026-09-11 unless noted)

- Zensical announcement / Material maintenance + MkDocs supply-chain risk —
  https://squidfunk.github.io/mkdocs-material/blog/2025/11/05/zensical/ (2025-11-05)
- mkdocstrings maintenance mode, bug-fix-only, horizon end of 2026 —
  https://github.com/mkdocstrings/mkdocstrings/issues/807 and
  https://github.com/mkdocstrings/mkdocstrings/discussions/806 (2025-11-30)
- Zensical MkDocs-compatibility / migration path —
  https://zensical.org/docs/compatibility/mkdocs/migration/
- MkDocs 2.0 rewrite impact analysis — https://mail.zensical.org/monthly/2026/02/ (2026-02-01)
- Mintlify pricing (Starter free tier) — https://www.mintlify.com/pricing
- Mintlify outcome-based AI credit pricing — https://www.mintlify.com/blog/outcome-based-ai-pricing (2026-09-08)
- PyData Sphinx Theme releases / Sphinx support range —
  https://pypi.org/project/pydata-sphinx-theme/0.20.0/ and
  https://github.com/pydata/pydata-sphinx-theme
