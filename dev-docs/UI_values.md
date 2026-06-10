# UI Values — MyPySkinDose

> **Auto-generated** — do not edit by hand. Regenerate with:
> `python scripts/generate_ui_values.py`

Design tokens extracted from `MODERN_CSS` in [src/mypyskindose/gui/app.py](../src/mypyskindose/gui/app.py). Aesthetic intent lives in [DESIGN.md](../DESIGN.md); implementation plan in [GUI_PLAN.md](GUI_PLAN.md).

## Color palette (CSS variables)

| Variable | Value | Purpose |
| :--- | :--- | :--- |
| `--bg-primary` | `#0e0e0e` | Main background |
| `--bg-secondary` | `#1d1d1d` | Secondary background (panels, drawer) |
| `--aurora-purple` | `#4338CA` | Navigation, primary actions, sidebar glow |
| `--aurora-teal` | `#0D9488` | Input and load accents |
| `--aurora-pink` | `#831843` | Status and highlights |
| `--text-main` | `#F8FAFC` | Primary text |
| `--text-muted` | `#94A3B8` | Secondary text |
| `--glass-bg` | `rgba(33, 33, 33, 0.70)` | Card background |
| `--glass-bg-hover` | `rgba(33, 33, 33, 0.85)` | Card hover background |
| `--glass-border` | `rgba(255, 255, 255, 0.15)` | Glass border color |
| `--shadow-soft` | `0 4px 24px rgba(0, 0, 0, 0.4)` | Default card shadow |
| `--shadow-hover` | `0 8px 32px rgba(0, 0, 0, 0.5)` | Card hover shadow |
| `--glow-blue` | `rgba(59, 130, 246, 0.3)` | Blue glow for hover effects |
| `--glow-purple` | `rgba(99, 102, 241, 0.3)` | Purple glow for secondary buttons |

## Aurora effects (radial gradients)

Extracted from `body` and `.q-drawer` background rules.

- **100% 0%:** `rgba(165, 141, 149, 0.17)` (55% radius)
- **0% 0%:** `rgba(126, 145, 194, 0.16)` (55% radius)
- **100% 100%:** `rgba(107, 125, 138, 0.15)` (60% radius)
- **0% 100%:** `rgba(126, 145, 194, 0.12)` (65% radius)

_Generated from `src/mypyskindose/gui/app.py`._
