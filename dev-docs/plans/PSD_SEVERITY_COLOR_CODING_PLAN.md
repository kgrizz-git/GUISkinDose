# PSD Severity Colour-Coding Plan

Created: 2026-09-28 · Revised: 2026-09-28 (maintainer decisions folded in) · Status: **ready to implement**

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

**Decided:** show a dash placeholder instead of `0.00 mGy`. Use the **em dash `—`**, matching the
placeholder Results already builds with (`results_builders.py:547`, `:618`), rather than introducing a
second placeholder style — the maintainer asked for `---`, and one dash glyph used everywhere is the
same intent without two spellings to keep in sync. Drop the unit too: the sidebar reads `PSD: —`, not
`PSD: — mGy`.

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

### 3.2 One shared module — concrete

New file `src/guiskindose/gui/dose_severity.py`. It imports nothing from NiceGUI, so its tests live in
`tests/unittests/` (the `tests/gui/` vs `tests/unittests/` split is enforced by a pre-push hook and by
the core CI matrix, which has no `gui` extra).

```python
"""Peak-skin-dose severity bands and their presentation classes.

Single source of truth for how a PSD value is coloured and named. Every GUI
readout of PSD routes through here so the four call sites cannot drift apart.
"""

from __future__ import annotations

import math
from typing import Final

from nicegui import ui  # only for the type of `apply_psd_band`'s argument

# Band edges in mGy. The upper edge belongs to the higher band, so exactly
# 5000 mGy is "elevated" and exactly 10000 mGy is "high" — the conservative
# reading. See the SRDL note in the plan before changing these.
PSD_BAND_ELEVATED_MGY: Final = 5000.0
PSD_BAND_HIGH_MGY: Final = 10000.0

_BANDS: Final = ("pending", "low", "elevated", "high")
_TEXT_CLASSES: Final = {band: f"text-dose-{band}" for band in _BANDS}
_ALL_TEXT_CLASSES: Final = " ".join(_TEXT_CLASSES.values())
_ICONS: Final = {"pending": "", "low": "check_circle", "elevated": "warning", "high": "error"}
_COPY_KEYS: Final = {band: f"results.psd_band.{band}" for band in _BANDS}


def psd_band(psd: float | None) -> str:
    """Severity band for a PSD in mGy: pending / low / elevated / high.

    ``None`` and any non-finite value are ``"pending"`` — nothing has been
    calculated, or what was calculated is not a number. A negative value
    cannot occur physically but maps to ``"low"`` rather than raising.
    """
    if psd is None:
        return "pending"
    try:
        value = float(psd)
    except (TypeError, ValueError):
        return "pending"
    if not math.isfinite(value):
        return "pending"
    if value >= PSD_BAND_HIGH_MGY:
        return "high"
    if value >= PSD_BAND_ELEVATED_MGY:
        return "elevated"
    return "low"


def psd_text_class(psd: float | None) -> str:
    """Tailwind-style text colour class for ``psd``'s band."""
    return _TEXT_CLASSES[psd_band(psd)]


def psd_band_icon(psd: float | None) -> str:
    """Material symbol name for ``psd``'s band; empty string when pending."""
    return _ICONS[psd_band(psd)]


def psd_band_copy_key(psd: float | None) -> str:
    """``dev-docs/ui_copy.json`` key naming ``psd``'s band and its range."""
    return _COPY_KEYS[psd_band(psd)]


def apply_psd_band(element: ui.element, psd: float | None) -> None:
    """Swap ``element``'s severity class to the one matching ``psd``.

    The whole class family is removed first: NiceGUI appends classes, so
    re-banding without a remove would leave two colours fighting.
    """
    element.classes(remove=_ALL_TEXT_CLASSES, add=psd_text_class(psd))
```

Edge-case note worth stating in the test: `psd_band` is written with `>=` against the *upper* edge
first, so the band boundaries are `[0, 5000)` low, `[5000, 10000)` elevated, `[10000, ∞)` high. This
matches §2.1.

### 3.3 Call sites — concrete edits

Six edits. Each sets text and band together; none of them re-derives a threshold.

**1. Sidebar construction** — `src/guiskindose/gui/app.py:244`

```python
# before
psd_label = ui.label("PSD: 0.00 mGy").classes("text-h6 text-pink-5 font-bold q-mt-xs")
# after
psd_label = ui.label(PSD_PENDING_TEXT).classes("text-h6 font-bold q-mt-xs text-dose-pending")
```

**2. One reset helper, four callers.** Add to `dose_severity.py`:

```python
PSD_PENDING_TEXT: Final = "PSD: —"


def reset_psd_label(label: ui.label) -> None:
    """Return the sidebar PSD readout to its not-calculated state."""
    label.set_text(PSD_PENDING_TEXT)
    apply_psd_band(label, None)
```

and route all four current `set_text("PSD: 0.00 mGy")` sites through it —
`gui/tabs/calculate.py:539`, `gui/tabs/upload_builders.py:329`, `gui/tabs/upload_builders.py:373`,
`gui/tabs/_per_exam.py:48`. They become `reset_psd_label(self.ctx.psd_label)` (or `ctx.psd_label`).

**3. Sidebar success path** — `gui/tabs/calculate.py:545`

```python
self.ctx.psd_label.set_text(f"PSD: {state.psd:.2f} mGy")
apply_psd_band(self.ctx.psd_label, state.psd)
```

**4. Results single-exam metric.** Build (`results_builders.py:547`) drops the hard-coded
`text-aurora-purple` in favour of `text-dose-pending`; refresh (`results_builders.py:75`) adds
`apply_psd_band(self.refs.psd_metric, state.psd)` next to the existing `set_text`.

**5. Results aggregate metric.** Build (`results_builders.py:618`) drops `text-white` for
`text-dose-pending`. Three refresh sites, and they do **not** all band the same way:

| Line | Text today | Band on |
|------|-----------|---------|
| `:239` | `f"{res.aggregate_psd:.2f} mGy"` | `res.aggregate_psd` |
| `:311` | `f"{res.aggregate_psd:.2f} mGy"` | `res.aggregate_psd` |
| `:318` | `"— mGy (no exams selected)"` | `None` → pending grey |
| `:327` | `f"{subset_psd:.2f} mGy (subset)"` | `subset_psd`, **not** the full aggregate |

The `:318` and `:327` split is the one easy thing to get wrong here: a deselected subset must go grey,
and a selected subset must band on its own maximum, not on the whole-run aggregate.

**6. Results per-exam accordion** — `results_builders.py:406`. Replace `text-aurora-purple` with
`psd_text_class(exam_res.output.psd)` at construction time. This is the only place where several bands
are visible at once, which is the most useful case: it shows which exam in a multi-exam run drives the
peak.

### 3.4 Non-colour carriers (required, not optional)

Green/yellow/red alone excludes the most common colour-vision deficiencies, so colour is never the
only carrier. Each banded readout also gets:

- **a leading Material symbol** keyed to the band — `check_circle` / `warning` / `error`, and nothing
  at all when pending. The icon font is already loaded (`material_symbols_stylesheet_href()`,
  `app.py:217`), and the repo already uses the `icon-outlined` class convention.
- **a tooltip naming the band and its range**, so the number can be interpreted without seeing the
  colour at all.

Concrete `dev-docs/ui_copy.json` additions (canonical; mirrored to
`src/guiskindose/gui/ui_copy.json` by `python scripts/sync_ui_copy.py`):

```json
"results.psd_band.pending": {
  "text": "Not calculated yet",
  "owner": "gui/dose_severity.py"
},
"results.psd_band.low": {
  "text": "Low — peak skin dose below 5000 mGy",
  "owner": "gui/dose_severity.py"
},
"results.psd_band.elevated": {
  "text": "Elevated — peak skin dose 5000 to 10000 mGy",
  "owner": "gui/dose_severity.py"
},
"results.psd_band.high": {
  "text": "High — peak skin dose above 10000 mGy",
  "owner": "gui/dose_severity.py"
}
```

Two constraints on that copy: `check_ui_copy.py` rejects "maximum skin dose" (use **peak skin dose**),
and the band names must also be added to `dev-docs/glossary.json` since they are user-facing terms.

The numeric edges must appear in prose in exactly one place: the `results_workflow.md` help page
(canonical under `docs/source/gui_help/`, mirrored by `python scripts/sync_gui_help.py`). Write them
with the same "estimate, not a measurement" framing the tab already uses — the bands describe where a
*modelled* PSD sits, and do not claim a clinical finding.

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

### 4.1 Tests

Three existing tests assert the literal reset string and must be updated in the same PR:

- `tests/gui/test_per_exam_coverage.py:47` — `assert_called_with("PSD: 0.00 mGy")` → `"PSD: —"`.
- `tests/gui/test_calculate_tab_coverage.py:121` — `assert_called_with("PSD: 0.00 mGy")` → `"PSD: —"`.
- `tests/gui/test_calculate_tab_coverage.py:95` — `assert_called_with("PSD: 9.50 mGy")`. The text is
  unchanged, so this passes as-is; extend it to also assert the band class.

These use `MagicMock()` for `ctx.psd_label`, so `apply_psd_band`'s `.classes(remove=…, add=…)` call
records harmlessly and can be asserted directly.

New tests:

- `tests/unittests/test_dose_severity.py` — table test over `psd_band`: `None`, `float("nan")`,
  `float("inf")`, `0.0`, `4999.99`, **`5000.0`**, `9999.99`, **`10000.0`**, `10000.01`, `1e9`, and a
  negative. The two exact edges are the assertions that actually pin §2.1; everything else is
  regression padding.
- `tests/unittests/test_dose_severity.py` — `apply_psd_band` removes the whole class family before
  adding one, so re-banding the same element twice leaves exactly one severity class.
- `tests/gui/` — each of the six call sites in §3.3 applies the expected class for a known PSD; the
  four reset paths yield `"PSD: —"` + `text-dose-pending`; and the aggregate subset cases at `:318`
  and `:327` band on pending and on `subset_psd` respectively.

---

## 5. Continuous gradient — decided: no

**Decided: discrete bands only. No gradient, no meter bar.**

For the record, the maintainer asked what the meter bar idea actually was and what its maximum would
be — a fair question, and the answer exposes why it was a weak idea. It would have been a horizontal
fill bar under the Results PSD number, filling left-to-right as dose rises, with the fill tinted the
band colour. Its maximum would have had to be an arbitrary ceiling (`10000 mGy`, i.e. the red edge),
which means **every** high-dose case pins the bar at 100 % and the bar stops carrying information
exactly where the reader cares most. There is no natural maximum for peak skin dose, so there is no
honest full-scale value. Dropped.

The hue-ramp variant is rejected for its own reasons, recorded so it does not get re-proposed:

- A reader cannot recover a threshold from a hue. "Is this amber or is it yellow?" is not a question a
  dose readout should provoke, and the point of the colour is to answer "which band am I in?".
- It cannot be paired with an icon or a band name, so it loses the colour-blind fallback in §3.4.
- It is untestable in any useful way — you end up asserting interpolated hex strings.

## 6. Acceptance

1. All four PSD readouts use the same shared helper; no site hard-codes a PSD colour.
2. Before any calculation, and after every invalidation, the sidebar reads `PSD: —` in light grey —
   no `0.00`, no unit.
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
- A continuous gradient or a fill/meter bar. Decided against in §5; do not re-add without a new
  decision recorded there.
