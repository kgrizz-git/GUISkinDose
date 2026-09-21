> **NEEDS REVIEW** — This assessment has not yet been reviewed by a domain expert
> (medical physicist). Code-path claims are verified against the tree; DICOM
> encoding claims are marked where fixture evidence is still missing.

# Rotational-Acquisition Handling Assessment

Investigated: 2026-09-21

For `TO_DO.md` item *"Review rotational-acquisition handling"* (Next Up):
determine whether spin/rotational acquisitions need dose spread across
per-frame or start/end angles.

## Summary

Every irradiation event is modelled at **one static C-arm pose**. A
rotational (spin) acquisition — one RDSR event whose gantry sweeps through a
large arc — therefore deposits its **entire event kerma at a single
`Ap1`/`Ap2` pose**. The expected effect is a **PSD overestimate at that pose**
and an **underestimate along the rest of the arc**, with the dose map showing
a focal hotspot instead of an arc smear. No parser, adapter, normalizer, or
dose-stage concept for start/end angles or per-frame angles exists today, so
there is currently nothing to spread even if we wanted to.

**Recommendation:** evidence first, then warn, then model — in that order.
Do not build arc-subdivision until a real spin RDSR (plus its vendor export
counterpart) shows where start/end or per-frame angles actually live. Details
in §5.

---

## 1. What exists today

### 1.1 One static geometry per event

- `Beam.__init__` (`src/guiskindose/beam_class.py:63`) reads a single
  `Ap1[event]`, `Ap2[event]`, `Ap3[event]` and builds one static beam +
  detector. The full event kerma is deposited through that geometry.
- `calculate_irradiation_event_result`
  (`src/guiskindose/calculate_dose/calculate_irradiation_event_result.py:92`)
  loops over events; each event contributes through its own single geometry.
- The geometry-reuse cache keys on the full pose
  (`Tx/Ty/Tz`, `FS_lat/FS_long`, `Ap1–3`, `At1–3`) — see
  `FEATURE_INVENTORY.md:224` and `PSD_CALCULATION_ALGORITHM.md:147`. A spin
  recorded as one event gets exactly one cache entry and one hit-test.
- Canonical algorithm reference: `PSD_CALCULATION_ALGORITHM.md:73`
  (per-event loop over static geometry rows).

### 1.2 Only one angle pair per event exists in the pipeline

- `rdsr_parser.py` extracts whatever angle concepts the RDSR carries into
  flat columns; the normalizer reads exactly two:
  `PositionerPrimaryAngle_deg → Ap1`, `PositionerSecondaryAngle_deg → Ap2`
  (`src/guiskindose/rdsr_normalizer.py:522`; units pinned to `deg` at
  `src/guiskindose/rdsr_normalizer.py:122`).
- `Ap3` is hardcoded to zero (`rdsr_normalizer.py:525`, `# temp set to zero`)
  — an orthogonal gap, noted in §4 but out of scope here.
- All four tabular adapters (`normalized`, `generic_rdsr_like`,
  `radimetrics`, `dosetrack`) map only single-valued angle columns
  (`src/guiskindose/input_adapters/dosetrack.py:62`,
  `src/guiskindose/input_adapters/radimetrics.py:76`,
  `src/guiskindose/input_adapters/generic_rdsr.py:119`). No adapter accepts an angle range, start/end
  pair, or per-frame series.

### 1.3 `acquisition_type` is carried but never read

- `IrradiationEventType` is parsed from RDSR concepts, mapped by the
  DoseTrack/Radimetrics/generic adapters (DoseTrack and Radimetrics default
  it to `"Fluoroscopy"` when absent:
  `src/guiskindose/input_adapters/dosetrack.py:314`,
  `src/guiskindose/input_adapters/radimetrics.py:210`), and stored as `acquisition_type` by the normalizer
  (`rdsr_normalizer.py:315`, contract key `constants.py:125`).
- Nothing in geometry, dose, GUI, or export branches on it. Fixture tables
  carry `"Fluoroscopy"` only
  (`tests/fixtures/tabular_inputs/normalized_events.csv:2`).
- This is the natural detection hook for Phase 1 (§5.2) — *if* Phase 0
  confirms vendors actually emit a distinct rotational event-type string.

### 1.4 Already-known downstream symptom

`plans/NO_PATIENT_INTERSECTION_WARNING_PLAN.md:37` lists "a rotational
acquisition modelled as a single static `Ap1` / `Ap2`" as a cause of
beam-miss warnings: depending on which pose the single angle pair represents
(start, mid, end), the static beam may miss the phantom entirely or clip it,
producing a zero-dose event that is really a modelling artifact.

## 2. Expected dose impact (unquantified)

For a spin recorded as one event with total air kerma K at pose P0 over arc
A:

- **PSD**: all of K lands on the skin cells hit at P0. True PSD is spread
  over A; reported PSD is biased high at P0 (and low elsewhere). The bias
  grows with arc length and shrinks with field overlap along the arc.
- **Dose map**: focal hotspot at P0 instead of an arc band. GUI Results and
  rich exports inherit the distortion as a direct consequence of the
  dose-map artifact.
- **Magnitude unknown**: no spin fixture exists in-tree, so this is a
  directional claim only. Quantification needs Phase 0 data (§5.1).

## 3. What is missing (evidence status per item)

| # | Gap | Evidence status |
|---|---|---|
| 1 | Start/end angle concepts in RDSR events | **Unknown** — parser has no such columns; needs a real spin RDSR to check whether the concepts exist but are dropped, or are absent entirely |
| 2 | Per-frame angle series (RDSR or image headers) | **Unknown** — same fixture dependency; image-header ingestion would additionally be out of RDSR scope (see §4) |
| 3 | Rotational `IrradiationEventType` strings per vendor | **Unknown** — adapters pass the value through; no observed spin value in fixtures |
| 4 | Angle-range columns in DoseTrack/Radimetrics exports | **Unknown** — current column maps show single-valued angles only; needs a real spin export |
| 5 | Arc-subdivision dose model | **Not built** — correctly blocked on 1–4 |

## 4. Explicit non-goals and adjacent gaps

- **Per-frame image-header ingestion** (e.g. reading XA multi-frame
  functional groups for per-frame positioner angles) is out of scope: the
  pipeline consumes RDSR + tabular event tables, not image objects. If Phase 0
  shows angles live *only* in image headers, that finding alone decides
  whether this item stays feasible.
- **`Ap3` hardcoded zero** (`rdsr_normalizer.py:525`) is a separate gap
  affecting detector-rotation modelling for all events, not just spins.
  Tracked here for visibility; do not bundle the fixes.
- **Table motion** is not part of this item: spins are normally table-static,
  so only `Ap` varies across the arc. The `check_new_geometry` cache key
  already includes `Ap1–3`, so arc sub-poses would slot into the existing
  reuse machinery without key changes.

## 5. Recommendations (phased, evidence-gated)

### Phase 0 — Evidence gathering (no behavior change)

1. Obtain a de-identified spin RDSR (ideally Siemens Artis + Philips Allura/
   Azurion spins, matching the validated normalization profiles) **plus** the
   same case's DoseTrack/Radimetrics export where available.
2. Record, per source: which angle concepts appear (start/end? per-frame?
   `NumberOfFrames`? rotation direction?), the `IrradiationEventType` string
   for the spin event, and which pose the single reported angle pair
   corresponds to (start / mid / end — determines the miss-warning behavior
   in §1.4).
3. Privacy: de-identified synthetic or properly cleared fixtures only; normal
   asset-admission rules apply (`PRIVACY_AND_SENSITIVE_ASSETS.md`).
4. Record findings as a dated follow-up section in this file. **Stop here if
   the angles are nowhere to be found** — re-scope toward a documented
   limitation + warning (Phase 1b below) instead of modelling.

### Phase 1a — Detection + warning (only if Phase 0 yields a type signal)

If a distinct rotational event-type string (or a reliable heuristic, e.g.
`K_IRP`-large single event with arc-scale neighbor deltas) emerges:

1. Warn per affected event that its dose is modelled at one static pose and
   PSD may be overstated at that pose. Follow the `_emit_beam_miss_summary`
   dial precedent
   (`src/guiskindose/calculate_dose/calculate_irradiation_event_result.py:68`);
   reuse the GUI `state.calc_warnings` collector.
2. Unit tests on synthetic normalized rows; docs describe the limitation in
   the Calculate-tab help and rich-export methodology note.

### Phase 1b — Documented limitation (if Phase 0 finds no angle data)

If spin angles are unavailable in every supported input: downgrade this item
to a documented limitation (help page + export methodology note stating spins
are modelled at the reported static pose), keep the TO_DO pointer, and close
the modelling question until a source format change reopens it.

### Phase 2 — Arc-subdivision model (only if Phase 0 yields angle data)

If start/end angles (or per-frame angles) are available:

1. Subdivide the event's kerma across N sub-poses spanning the arc
   (uniform split by default; kerma-weighted if per-frame kerma exists).
   Each sub-pose is a synthetic geometry row reusing the existing
   hit-test/correction path — no new physics, just N evaluations.
2. Recompute geometry-dependent corrections (`k_isq`, `k_bs`, `k_tab`) per
   sub-pose; keep the event as one row in GUI/exports with a provenance note
   recording N and the arc span.
3. Choose N by angle step with a cap: each sub-pose is a full new geometry
   evaluation, so ray-casting cost scales with N. Bound N and warn when the
   cap binds.
4. Acceptance: synthetic spin fixture (constant-kerma arc) shows PSD at/below
   the static-pose value and a contiguous arc band on the dose map; golden
   characterization tests pin the subdivision math.

### Suggested sequencing note

Phase 0 is small, user-invisible, and unblocks the whole item — it fits as a
first slice whenever this Next Up item is pulled. Phases 1–2 are separate
PRs behind Phase 0's findings.

---

## Files examined

- `src/guiskindose/rdsr_parser.py`
- `src/guiskindose/rdsr_normalizer.py` (esp. lines 114-149, 315, 516-542)
- `src/guiskindose/beam_class.py` (esp. lines 34-70)
- `src/guiskindose/calculate_dose/calculate_irradiation_event_result.py` (esp. lines 80-116)
- `src/guiskindose/helpers/calculate_rotation_matrices.py`
- `src/guiskindose/input_adapters/dosetrack.py` (esp. lines 52-93, 314-316)
- `src/guiskindose/input_adapters/radimetrics.py`, `generic_rdsr.py`, `normalized.py`
- `src/guiskindose/constants.py:125`
- `dev-docs/PSD_CALCULATION_ALGORITHM.md`, `dev-docs/VENDOR_COORDINATE_SYSTEMS.md`
- `dev-docs/plans/NO_PATIENT_INTERSECTION_WARNING_PLAN.md:37`
- `tests/fixtures/tabular_inputs/normalized_events.csv`
