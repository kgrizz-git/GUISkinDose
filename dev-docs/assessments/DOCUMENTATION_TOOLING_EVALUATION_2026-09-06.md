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

## 5. Cross-review outcome

- **Agreed**: Starter $0 terms, Pro-gated AI, no self-hosting below Enterprise,
  portability split (content portable / platform proprietary), shortlist order.
- **Open verification items** (single-sourced, confirm before committing to a path):
  - `mkdocstrings` maintenance-mode / sponsorware-sunset status (MkDocs API-docs risk).
  - Mintlify Pro price figure ($450/mo annual quoted by one agent; the other's page
    render garbled the number — pin to a clean capture).
  - Mintlify OSS "Pro free" grant in practice (existence of program confirmed; grant
    for *this* project requires the application).
  - Jupyter Book V2 vs V1-maintenance status.
- Review gap noted: ReadTheDocs (free hosting for public OSS, supports Sphinx and
  MkDocs) deserves explicit weight in the final decision.

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
