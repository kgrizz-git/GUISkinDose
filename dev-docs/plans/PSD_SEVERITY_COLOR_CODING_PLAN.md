# PSD Severity Colour-Coding Plan

Created: 2026-09-28 · Status: **plan only, not implemented**

Make the peak-skin-dose (PSD) readout tell the reader at a glance where the estimate sits relative to
skin-reaction dose bands, and make every PSD readout in the GUI agree on colour and wording.

---

## 1. Why this is needed

### 1.1 The four PSD readouts disagree today

| Site | Element | Current colour | Placeholder when not calculated |
|------|---------|----------------|---------------------------------|
| Left sidebar (Status) | `psd_label` — `src/guiskindose/gui/app.py:244` | `text-pink-5` (Quasar pink) | `"PSD: 0.00 mGy"` |
| Results, single exam | `psd_metric` — `src/guiskindose/gui/tabs/results_builders.py:547` | `text-aurora-purple` (`#4338CA`) | `"—"` |
| Results, aggregate | `agg_psd_metric` — `results_builders.py:618` | `text-white` | `"—"` |
| Results, per-exam accordion | inline label — `results_builders.py:406` | `text-aurora-purple` | n/a (only built after a run) |

Three different colours for the same quantity, and none of them carries meaning. The sidebar's pink is
not even a design token — `--aurora-pink` is `#831843`, while `text-pink-5` is Quasar's own pink.

### 1.2 `0.00 mGy` is wrong before a run

The sidebar shows `PSD: 0.00 mGy` on load and after every invalidation
(`gui/tabs/calculate.py:539`, `gui/tabs/upload_builders.py:329` and `:373`,
`gui/tabs/_per_exam.py:48`). A literal zero reads as a computed result, not as "nothing computed yet".
Results already uses `"—"` for the same state. The sidebar should match.

---

## 2. Requested behaviour

Colour the PSD text **and** its value by band:

| Band | PSD | Meaning |
|------|-----|---------|
| Not calculated | no value | light grey |
| Low | `< 5000 mGy` | green |
| Elevated | `5000–10000 mGy` | yellow |
| High | `> 10000 mGy` | red |

The maintainer also asked whether a continuous gradient would be better than three steps. See §5.

### 2.1 Band-edge convention (must be pinned before coding)

The request reads `< 5000` / `5000–10000` / `> 10000`, so the edges belong to the *higher* band:
`psd < 5000` → green, `5000 <= psd <= 10000` → yellow, `psd > 10000` → red. Exactly `5000.00` is
yellow and exactly `10000.00` is red. This is the conservative reading and the one to implement.

### 2.2 Clinical note (maintainer's call, not a blocker)

The chosen 5 / 10 Gy edges sit inside the usual skin-reaction discussion, but the number that most
commonly appears in fluoroscopy QA is the **substantial radiation dose level (SRDL) of 3000 mGy peak
skin dose**, which is the trigger for patient follow-up rather than a reaction threshold. If a fourth
band is wanted later, `3000 mGy` is the natural extra edge (e.g. grey / green / amber at 3000 /
yellow at 5000 / red at 10000). The thresholds are therefore worth making **configurable constants**
rather than literals, so changing them is a one-line edit plus a doc update. Implement the three bands
as asked; the constant table makes a later fourth band cheap.

---

## 3. Design

### 3.1 New design tokens

Add severity tokens to `MODERN_CSS` in `src/guiskindose/gui/styles.py` next to the existing
`--aurora-*` block, so they are regenerated into `dev-docs/UI_values.md` by
`python scripts/generate_ui_values.py` like every other token:

```css
--dose-pending: #94A3B8;   /* same as --text-muted; light grey */
--dose-low:     #22C55E;
--dose-elevated:#FACC15;
--dose-high:    #EF4444;
```

with matching `.text-dose-pending`, `.text-dose-low`, `.text-dose-elevated`, `.text-dose-high`
utility classes mirroring the existing `.text-aurora-*` pattern.

Contrast against `--bg-primary` (`#0e0e0e`) is comfortably above WCAG AA for all four at the large
type sizes used (`text-h6` sidebar, `text-4xl`/`text-5xl` Results). `#FACC15` on `#0e0e0e` is the
tightest and still clears AA for large text. Do **not** darken the yellow to chase AAA — it stops
reading as yellow.

Two design-intent points to record in `DESIGN.md` §2 when this lands:

- These are the first *semantic* colours in the palette. Everything else is brand/accent. They are
  deliberately exempt from the "never use middle-greys, keep the accent vibe" rule because their job
  is clinical signalling, not aesthetics.
- Green/yellow/red is not distinguishable for the most common colour-vision deficiencies. Colour must
  therefore never be the only carrier — see §3.3.

### 3.2 One shared helper

Add a single pure function so all four sites cannot drift again. Suggested home:
`src/guiskindose/gui/dose_severity.py` (new, small, non-NiceGUI so it is unit-testable without the
`gui` extra — note `tests/gui/` vs `tests/unittests/` placement is enforced by a pre-push hook, and a
pure module means the tests can live in `tests/unittests/`).

```python
PSD_BAND_ELEVATED_MGY = 5000.0
PSD_BAND_HIGH_MGY = 10000.0

def psd_band(psd: float | None) -> str: ...        # "pending" | "low" | "elevated" | "high"
def psd_text_class(psd: float | None) -> str: ...  # "text-dose-pending" | ...
def psd_band_label(psd: float | None) -> str: ...  # "Not calculated" | "Low" | "Elevated" | "High"
```

`psd_band(None)` and any non-finite value return `"pending"`. A negative PSD cannot occur but should
also map to `"low"` rather than raising.

### 3.3 Call sites

Each site sets both the text and the class. NiceGUI needs the previous severity class removed before
the new one is added, so give every PSD element a small wrapper that does
`element.classes(remove="text-dose-pending text-dose-low text-dose-elevated text-dose-high", add=new)`.
Putting that wrapper in the same new module keeps the class list in one place.

1. **Sidebar** (`app.py:244`) — build with `"PSD: —"` and `text-dose-pending`. Replace the
   `text-pink-5` class. Keep `text-h6 font-bold q-mt-xs`.
2. **Sidebar reset paths** — `calculate.py:539`, `upload_builders.py:329`, `upload_builders.py:373`,
   `_per_exam.py:48` all currently set `"PSD: 0.00 mGy"`; they must set `"PSD: —"` plus the pending
   class. Best done by routing all four through one `reset_psd_label(ctx)` helper.
3. **Sidebar success path** (`calculate.py:545`) — set text and the banded class together.
4. **Results single-exam metric** (`results_builders.py:547` built, `:75` refreshed) — replace the
   hard-coded `text-aurora-purple` with the banded class; `"—"` placeholder already correct.
5. **Results aggregate metric** (`results_builders.py:618` built, `:239`/`:311`/`:327` refreshed) —
   replace `text-white` with the banded class. **Band the numeric aggregate only.** The subset branch
   writes `"— mGy (no exams selected)"` (`:318`), which must stay pending-grey, and
   `f"{subset_psd:.2f} mGy (subset)"`, which bands on `subset_psd`.
6. **Results per-exam accordion** (`results_builders.py:406`) — replace `text-aurora-purple` with the
   band for that exam's own PSD. This is the one site where several different bands appear at once,
   which is exactly the useful case.

### 3.4 Non-colour carriers (required, not optional)

Because green/yellow/red alone excludes colour-blind users, each banded readout also gets:

- a leading Material symbol keyed to the band (`check_circle` / `warning` / `error`, nothing for
  pending) — the icon font is already loaded (`material_symbols_stylesheet_href()` in `app.py`); and
- a tooltip / caption naming the band and its range, e.g.
  `"Elevated — 5000–10000 mGy"`. New `dev-docs/ui_copy.json` keys under a
  `results.psd_band.*` prefix, mirrored to `src/guiskindose/gui/ui_copy.json` by
  `python scripts/sync_ui_copy.py`.

The band names and numeric edges must appear in exactly one place in prose too: add them to the
`results_workflow.md` help page (canonical copy lives in `docs/source/gui_help/`, mirrored by
`python scripts/sync_gui_help.py`) with the "estimate, not a measurement" framing already used
elsewhere on that tab.

---

## 4. Harness obligations

Docs-and-copy checks that will fail if this lands without them:

- `python scripts/generate_ui_values.py` — regenerate `dev-docs/UI_values.md` after editing
  `styles.py`.
- `python scripts/sync_ui_copy.py` and `python scripts/sync_gui_help.py` — mirror canonical copy into
  `src/`; both are enforced by pre-commit and CI.
- `python scripts/check_ui_copy.py` — every `copy_text("…")` key must exist in
  `dev-docs/ui_copy.json` with an `owner`. Note its terminology rule: "maximum skin dose" is
  rejected, use **peak skin dose**.
- `python scripts/check_help_registry.py` — update `dev-docs/help_registry.json` if a new help
  anchor is added.
- `dev-docs/glossary.json` — add the band names if they are used as user-facing terms.

### 4.1 Tests that will break

Three tests assert the literal reset string and must be updated in the same PR:

- `tests/gui/test_per_exam_coverage.py:47` — `assert_called_with("PSD: 0.00 mGy")`
- `tests/gui/test_calculate_tab_coverage.py:95` — `assert_called_with("PSD: 9.50 mGy")` (text only,
  survives; the class assertion is new)
- `tests/gui/test_calculate_tab_coverage.py:121` — `assert_called_with("PSD: 0.00 mGy")`

New tests to add:

- `tests/unittests/` — `psd_band` table test covering `None`, `NaN`, `0`, `4999.99`, `5000.0`,
  `10000.0`, `10000.01`, and a large value. The two exact edges are the ones worth pinning.
- `tests/gui/` — each of the four call sites applies the expected class for a known PSD, and the
  reset paths apply `text-dose-pending` with `"PSD: —"`.

---

## 5. Continuous gradient — recommendation

**Keep the discrete bands.** A continuous hue ramp would be prettier and is technically easy (HSL
interpolation from green through yellow to red, clamped at the ends), but for this readout it is the
worse choice:

- A reader cannot recover a threshold from a hue. "Is this amber or is it yellow?" is not a question a
  dose readout should provoke, and the whole point of the colour is to answer "which band am I in?".
- It makes the state untestable in any meaningful way — you end up asserting interpolated hex strings.
- It cannot be paired with an icon or a band name, so it loses the colour-blind fallback in §3.4.

A reasonable middle ground, if the hard steps feel abrupt: keep discrete text colour, and add a thin
continuous meter bar underneath the Results PSD card whose fill fraction is
`min(psd / PSD_BAND_HIGH_MGY, 1.0)` and whose fill uses the band colour. That gives the "how far into
the band am I" feel without making the colour itself ambiguous. Treat it as an optional follow-on,
not part of this plan's acceptance.

---

## 6. Acceptance

1. All four PSD readouts use the same shared helper; no site hard-codes a PSD colour.
2. Before any calculation, and after every invalidation, the sidebar reads `PSD: —` in light grey —
   no `0.00`.
3. A run with PSD `4999`, `5000`, `9999`, `10000`, and `10001` mGy produces green, yellow, yellow,
   red, red respectively, in the sidebar and on Results, and the Results aggregate and per-exam rows
   band independently.
4. Each banded readout carries an icon and a band-name tooltip, so the band is readable without
   colour.
5. `python scripts/check_ui_copy.py`, `check_help_registry.py`, and the mirror/token generators pass;
   `dev-docs/UI_values.md` regenerated.
6. Band edges live in named constants with the clinical note from §2.2 recorded next to them.

## 7. Out of scope

- Colouring the dose-map plot or its colourscale — unrelated, and `COLORSCALES` is user-selectable.
- Banding air kerma, DAP, or fluoro time. Only PSD has agreed reaction bands.
- Exports (DOCX/XLSX/HTML). If banding is wanted there, that is a separate pass over
  `src/guiskindose/export/`.
