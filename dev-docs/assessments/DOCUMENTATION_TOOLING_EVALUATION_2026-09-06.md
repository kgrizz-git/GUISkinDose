# Documentation Tooling Evaluation — 2026-09-06

_Spike memo, not a decision. Linked from `TO_DO.md` ("User-Facing Documentation Tooling Evaluation").
Produced by two independent web-research subagents (Kilo `stepfun-3.7-flash:free`, Opencode
`nvidia/deepseek-v4-flash-0731`) with cross-review; convergence notes in §5._

## 1. Context

GUISkinDose currently documents with **Sphinx + RTD theme + `myst-parser` + `nbsphinx`**
(see the `docs` extra in `pyproject.toml` and `.readthedocs.yml`), hosted via ReadTheDocs.
That stack already covers Python API autodoc and notebook execution — the migration pain
point for any move. There is **no migration commitment**: the Documentation & Docstrings
Assessment (`TO_DO.md`) lands first; any tooling change is recorded in a decision log.

## 2. Mintlify free tier (converged findings)

Both agents confirmed against the live pricing page (accessed 2026-09-06):

- **Starter $0/mo**: 5 editor seats, custom domain, web editor, Git sync, search, API
  playground, MCP server, Auth. AI features (assistant, writing agent, automations) are
  excluded; AI usage is a separate metered layer (Pro bucket 10,000 credits/mo, then
  $0.01/credit). No published page-count or bandwidth caps.
- **OSS Program**: non-commercial OSS projects with an OSI-approved license (e.g. MIT)
  that are not venture-backed or for-profit-owned can get **Pro free** via manual
  (Typeform) application. Approval is review-based, not automatic.
- **Portability**: docs content lives as Markdown/MDX in your Git repo (portable), but
  Mintlify-specific components, AI search, playground, and analytics are proprietary —
  leaving means re-hosting plus component rework; there is no styled-site export.
- Older third-party write-ups describing a "Hobby" tier (1 editor, no custom domain) are
  **stale** against the live page. Mintlify repriced during 2026, so re-verify at decision time.

## 3. Landscape survey (2026 state)

| Tool | Python API autodoc | Notebooks | Hosting / cost for OSS | Migration from Sphinx RST+MyST |
|---|---|---|---|---|
| MkDocs + Material 9.x (+ `mkdocstrings`, `mkdocs-jupyter`) | `mkdocstrings` handler — **see maintenance-mode caveat (§5)** | `mkdocs-jupyter` | Self / GitHub Pages / Cloudflare Pages / RTD; free, MIT | Medium (MyST ports cleanly; RST + `:autodoc:` rework) |
| PyData Sphinx Theme / Sphinx Book Theme | Native autodoc (unchanged) | nbsphinx (unchanged) | RTD (unchanged); free | Near-zero (theme + config swap) |
| Jupyter Book (V2 active; V1 maintenance) | Via Sphinx | First-class, executable | RTD; free | Low (it *is* Sphinx + MyST) |
| Docusaurus 3.10 | Not native (community plugins) | No native Jupyter | Netlify/Cloudflare/Vercel/GH Pages; free, MIT | High (RST→MDX, JS toolchain) |
| Quarto (Posit) | Weak (no native docstring→API) | Native `.qmd`/`.ipynb` execution | Quarto Pub / GH Pages / Netlify; free | Medium |
| Starlight (Astro) | Community plugins only | No | Cloudflare/Vercel/Netlify; free | High |
| VitePress | None native | No | Cloudflare/Vercel; free | High |
| Mintlify (hosted SaaS) | OpenAPI/AI extraction, no docstring renderer | No real Jupyter | Managed; Starter $0, Pro paid (see §2) | High (conversion + lock-in) |
| GitBook (hosted SaaS) | None | No | Free OSS tier limited; closed source | High |

## 4. Ranked shortlist for this project

1. **MkDocs + Material** — biggest visible polish upgrade at zero cost with the richest
   Python ecosystem; gated on the mkdocstrings verification item (§5).
2. **PyData Sphinx Theme** — zero-migration drop-in restyle of the existing
   Sphinx/nbsphinx/RTD setup; near-zero risk.
3. **Mintlify** — only if a hosted, AI-native look outweighs lock-in *and* the OSS
   approval is actually granted for this project.

## 5. Claim verification (maintainer, 2026-09-06)

The dual-agent review agreed on the Starter terms, Pro-gated AI, Enterprise-only
self-hosting, the portability split, and the shortlist order. Its four single-sourced
items were re-checked against primary sources:

- **mkdocstrings maintenance mode: CONFIRMED** — the homepage banner at
  https://mkdocstrings.github.io/ reads "mkdocstrings is in maintenance mode". The
  MkDocs API-docs risk is real; any MkDocs move needs a docstring-renderer decision
  (pin, fork, or alternative) first.
- **Mintlify Pro $450/mo annual billing: CONFIRMED** — https://mintlify.com/pricing
  shows Pro at $450 on the annual toggle. The month-to-month figure ($540, quoted by one
  agent) was not legible in the page render and stays single-sourced.
- **Mintlify OSS "Pro free forever": CONFIRMED as a program** —
  https://www.mintlify.com/oss-program offers Pro free to non-commercial OSS (recognized
  license; not venture-backed or revenue-funded; not owned/maintained by a for-profit
  company). GUISkinDose (MIT, solo-maintained, non-commercial) looks eligible, but the
  grant itself still requires an application.
- **Jupyter Book V1 maintenance / V2 active: CONFIRMED** —
  https://jupyter-book.readthedocs.io/v1/intro.html banners V1 as maintenance-only and
  points to https://jupyterbook.org for the current version.

## 6. Sources (all accessed 2026-09-05/06 unless noted)

- Mintlify pricing — https://mintlify.com/pricing
- Mintlify OSS Program — https://www.mintlify.com/oss-program
- Mintlify credit pricing — https://www.mintlify.com/docs/credits
- Mintlify pricing blueprint — https://www.usagepricing.com/blueprint/mintlify (2026-08-11)
- Mintlify free-plan guide — https://writechoice.io/blog/mintlify-pricing-2026-free-plan-guide (2026-08-21)
- Material for MkDocs 9.x — https://squidfunk.github.io/mkdocs-material/getting-started/ (2025-11-07)
- mkdocstrings maintenance banner — https://mkdocstrings.github.io/
- Docusaurus — https://docusaurus.io/
- PyData Sphinx Theme — https://pydata-sphinx-theme.readthedocs.io/en/stable/
- Jupyter Book V1 banner — https://jupyter-book.readthedocs.io/v1/intro.html
- Quarto websites — https://quarto.org/docs/websites/
- Starlight — https://starlight.astro.build/

## 7. Wider landscape (maintainer survey, 2026-09-06)

Beyond §3. Only starred items are material to the decision; the rest lose to the
shortlist on Python-autodoc or notebook grounds.

**Sphinx path** — ★ `sphinx-immaterial` (Material look on Sphinx; keeps autodoc,
nbsphinx, RTD — strengthens shortlist option 2 as a co-candidate); `furo` (minimal
restyle, e.g. pip's docs); `sphinx-autoapi` (API refs without importing modules);
`pdoc` / `pydoc-markdown` / `lazydocs` (lightweight Python API generators — de-risk
option 1's mkdocstrings caveat); `sphinx-autobuild` (live-reload dev server).

**MkDocs context** — ★ `Zensical` (Material-for-MkDocs fork by the mkdocstrings author;
the maintenance story is a maintainer split — evaluate Zensical vs Material explicitly
if option 1 proceeds).

**JS frameworks** — `Nextra`, `Fumadocs` (Next.js/MDX), `Hextra`/`Doks`/`Geekdoc`
(Hugo), `Just the Docs` (Jekyll, GitHub-Pages-native), `VuePress`, `Docus` (Nuxt),
`Antora` (AsciiDoc, multi-repo): same verdict as the §3 bucket — polished, but no
Python autodoc or notebook story and high migration cost.

**API-docs SaaS (not applicable today)** — `Fern`, `Redocly`, `Bump.sh`, `Stainless`
are OpenAPI-driven; this project has a Python library + GUI, no web API.

**Quality infrastructure (complements the harness, not the generator)** — `Vale`
(prose/terminology lint; upgrade path for the glossary checks), `codespell` (CI typo
check), `Diátaxis` (tutorials/how-tos/reference/explanation framework — cite in
assessment criteria), `llms.txt` (AI-consumable docs; Mintlify generates it, static
builds need a plugin or manual file).

Net effect: shortlist (§4) unchanged.
