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
`Ap1`/`Ap2` pose**. The static model concentrates dose at the reported pose
and underestimates dose elsewhere along the arc. It will often overstate the
local dose near that pose, but the direction of the global PSD error is not
guaranteed: it can under- or overestimate PSD depending on pose selection,
field overlap, phantom intersection, and geometry-dependent corrections. The
dose map shows a focal hotspot instead of an arc smear. No adapter,
normalizer, or dose-stage concept for start/end angles exists today — though
the parser already emits End Angle columns generically when vendors populate
them (verified §5.1) — and per-frame angles have no concept anywhere, so
there is still nothing modelled even where data exists.

**Recommendation:** evidence first, then detection/warning and — only where
angles exist — modelling. Gate detection and modelling independently per
input source: a validated spin fixture for each source being implemented
decides what that source supports. Vendor exports are supporting parity
evidence where available, not a universal prerequisite. Do not build
arc-subdivision for a source until that source shows where start/end or
per-frame angles actually live. Details in §5.

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
  flat columns — including `PositionerPrimaryEndAngle_deg` /
  `PositionerSecondaryEndAngle_deg` when vendors populate them (verified on
  OpenREM `RF-RDSR-Eurocolumbus.dcm`, §5.1); the normalizer reads exactly two:
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

### 1.3 `acquisition_type` is carried but never read by geometry or dose

- `IrradiationEventType` is parsed from RDSR concepts, mapped by the
  DoseTrack/Radimetrics/generic adapters (DoseTrack and Radimetrics default
  it to `"Fluoroscopy"` when absent:
  `src/guiskindose/input_adapters/dosetrack.py:314`,
  `src/guiskindose/input_adapters/radimetrics.py:210`), and stored as `acquisition_type` by the normalizer
  (`rdsr_normalizer.py:315`, contract key `constants.py:125`).
- Nothing in geometry, dose, or the GUI branches on it; the only consumer is
  rich-export reporting, which buckets it fluoroscopy/acquisition/other
  (`src/guiskindose/export/metrics.py:61`) — a `Rotational Acquisition`
  event already falls into the `acquisition` bucket via the `"acq"`
  substring. Fixture tables
  carry `"Fluoroscopy"` only
  (`tests/fixtures/tabular_inputs/normalized_events.csv:2`).
- This is the natural detection hook for Phase 1a (§5.2) — *if* Phase 0
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

- **PSD**: all of K lands on the skin cells hit at P0 instead of being
  spread over A. Local dose near P0 is usually overstated (more so with
  longer arcs and less field overlap along the arc), but the global PSD error
  direction is not guaranteed — a static pose that misses or clips the
  phantom, or less favourable pose-dependent corrections elsewhere, can flip
  the sign (see §1.4).
- **Dose map**: focal hotspot at P0 instead of an arc band. GUI Results and
  rich exports inherit the distortion as a direct consequence of the
  dose-map artifact.
- **Magnitude unknown**: no spin fixture exists in-tree, so this is a
  directional claim only. Quantification needs Phase 0 data (§5.1).

## 3. What is missing (evidence status per item)

| # | Gap | Evidence status |
|---|---|---|
| 1 | Start/end angle concepts in RDSR events | **Confirmed in standard + in the wild** — DICOM defines `Positioner Primary/Secondary End Angle` (DCM 113739/113740, conditioned on event type 113613); our parser already emits the columns; OpenREM `RF-RDSR-Eurocolumbus.dcm` populates them (equal on static events) and `RF-RDSR-Canon-Alphenix-rotational.dcm` varies them (see §5.1). Remaining unknown: per-vendor population consistency and arc semantics |
| 2 | Per-frame angle series (RDSR or image headers) | **Unknown** — same fixture dependency; image-header ingestion would additionally be out of RDSR scope (see §4) |
| 3 | Rotational `IrradiationEventType` strings per vendor | **Confirmed** — CodeMeaning `Rotational Acquisition` (DCM 113613, CID 10002; siblings 113611 Stationary / 113612 Stepping) observed in OpenREM `RF-RDSR-Canon-Alphenix-rotational.dcm` (1 of 49 events; rest `Fluoroscopy`). Remaining unknown: per-vendor emission consistency |
| 4 | Angle-range columns in DoseTrack/Radimetrics exports | **Unknown** — current column maps show single-valued angles only; needs a real spin export |
| 5 | Arc-subdivision dose model | **Not built** — angle data now confirmed obtainable upstream (see §5.1); blocked on in-tree fixture clearance and per-source arc semantics (see Phase 2) |

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

1. Start from located upstream data: OpenREM `develop`
   (`openrem/remapp/tests/test_files/`, Bitbucket `openrem/openrem`) ships
   `RF-RDSR-Canon-Alphenix-rotational.dcm` (1 `Rotational Acquisition` event:
   primary 90.0 → −120.0, i.e. a 210° sweep with secondary fixed at 0.0, plus
   48 fluoroscopy events), `RF-RDSR-Eurocolumbus.dcm` (populates End Angle
   concepts on static events), and Siemens AXIOM-Artis / Philips Allura /
   Azurion / GE RF files. **Identifier fields are populated in these files —
   nothing may be vendored without scrub + hash-pinned clearance** (see lead
   inventory below). Still missing and wanted: Siemens Artis / Philips spins
   with end angles, and any matched GE DICOM + tabular pair.
2. Record, per source: which angle concepts appear (check
   `PositionerPrimaryEndAngle_deg` / `PositionerSecondaryEndAngle_deg`
   first — the parser already emits them); the `IrradiationEventType`
   CodeMeaning (look for `Rotational Acquisition` / DCM 113613 alongside
   `Stationary Acquisition` 113611 and `Stepping Acquisition` 113612); and
   which pose the single reported angle pair corresponds to (start / mid /
   end).
3. Privacy: de-identified synthetic or properly cleared fixtures only; normal
   asset-admission rules apply (`PRIVACY_AND_SENSITIVE_ASSETS.md`).
4. Record findings as a dated follow-up section in this file (and, if a new
   angle concept or event-type string is found, a note in
   `INPUT_SCHEMA_DETECTION.md` so the finding reaches adapter readers).
   Then branch on two independent questions: (a) is there a reliable
   rotational detection signal for this source? → Phase 1a (and, without
   angles, the Phase 1.5 assumed-arc candidate); (b) are start/end
   or per-frame angles available for this source? → Phase 2. If neither,
   Phase 1b.

#### Lead inventory (surveyed + inspected 2026-09-21; nothing vendored)

- **OpenREM upstream** (Bitbucket `openrem/openrem`, `develop`,
  `openrem/remapp/tests/test_files/`; 69 files): `RF-RDSR-Canon-Alphenix-
  rotational.dcm` (Canon DFP-8000D, 49 events, 1× `Rotational Acquisition`
  with primary 90.0 → −120.0 and DoseRP 0.011 Gy), `RF-RDSR-Eurocolumbus.dcm`
  (Eurocolumbus Fly4, End Angles populated on static events),
  `RF-RDSR-Siemens-Zee.dcm` (+ `_adjusted` twin, AXIOM-Artis, 8 fluoroscopy
  events with varied poses), `RF-RDSR-Philips_Allura.dcm`,
  `RF-RDSR-Philips_Azurion.dcm` (89 events, fluoro + stationary pairs),
  `RF-RDSR-GE-OECEliteMiniView.dcm`, `RF-RDSR-GE.dcm`, plus DX/CT/MG files.
  Our `rdsr_parser` already emits End Angle columns on these files.
  **Identifier fields (`PatientName`/`PatientID`) are populated in every RF
  file inspected — treat as NOT de-identified; nothing may be copied
  in-tree without scrub + hash-pinned human clearance.** A read-only sparse
  clone lives in gitignored `tmp/openrem-upstream/` on the investigating
  machine only. Side observation (not this item): `RF-RDSR-Philips_Allura`,
  `RF-Pat-Orientation-Modifier-Missing`, and `RF-RDSR-GE.dcm` fail our
  `rdsr_parser` (missing top-level `ManufacturerModelName` / structure) —
  now tracked as the TO_DO "RDSR parser input hardening" item; not assessed here.
- **Papers as transcribed fixtures** (provenance: transcribed, not vendor
  exports): Morota et al. 2021 (Diagnostics) Table 1 — 60+ cerebral-angio
  events with LAO/RAO/CRAN per event; CVIR review 2021 Table 1 — RDSR
  excerpt with per-event geometry; Buytaert et al. 2024 — grouped RDSR
  statistics only (no event rows).
- **Shiramis/RDSR-to-Excel** (GitHub + Prog. Med. Phys. 2025): open
  extractor, Siemens/Philips/Ziehm PDF + DICOM-RDSR → Excel
  fluoroscopy/DSA event tabs. No sample inputs in the repo; the 400-file
  clinical validation set is not public.
- **Normative text** (no downloadable instances): DICOM Sup 94 (CID 10002,
  DCM 113739/113740), Sup 245 RDSR annex, PS3.17 Annex GGGG skin-dose-map
  worked example.
- **Negative results**: no public DoseTrack/Radimetrics/Qaelum sample
  exports; no fluoroscopy-RDSR datasets on Zenodo/Kaggle; OpenREM demo data
  is computer-generated with exports disabled; pydicom-data ships no RDSR.

#### Phase 0 findings (surveyed 2026-09-22; geometry columns only, no identifiers)

Provenance: read-only blobless sparse clone of Bitbucket
`openrem/openrem` (`develop` at `d168bd48` 2026-02-06), scope
`openrem/remapp/tests/test_files/` only, kept in gitignored
`tmp/openrem-upstream/` on the investigating machine — never committed,
never vendored. Parsed with our `rdsr_parser` via a gitignored scratch
script that prints geometry columns only (since deleted).

Ran our `rdsr_parser` over the RF files above (scratch script, gitignored;
no fixture vendored). Per-source results:

- **Canon Alphenix (rotational file) — the positive case.** 49 events: 48
  fluoroscopy + 1 `Rotational Acquisition` (row 48, protocol `Gastro Roll 4s
  40cm`, DoseRP 0.011131 Gy). The spin row carries start **and** end angles:
  primary 90.0 → −120.0 (210° sweep), secondary 0.0 → 0.0. Fluoro rows carry
  start angles with NaN end angles. **Reported pose = arc START**: our
  pipeline consumes `PositionerPrimaryAngle_deg`, so today the whole spin is
  modelled at its 90° start pose. The `Rotational Acquisition` CodeMeaning
  flows through the parser into `IrradiationEventType` — a working detection
  signal for this source pattern.
- **Eurocolumbus Fly4 — static with ends.** 4 fluoroscopy events; end angles
  populated and **equal** to start (6.0/183.0). Consequence: `end ≠ start`
  discriminates rotation from static on sources that populate both.
- **Siemens Zee (+`_adjusted` twin) — start only.** 8 fluoroscopy events,
  varied static poses, **no end-angle columns emitted at all**. No spin
  present, so the Siemens rotational event-type string is still unobserved.
- **Philips Azurion — start only.** 89 events (72 fluoro + 17 stationary),
  no end-angle columns. Same gap: Philips rotational string unobserved.
- **Philips Allura / GE — parse after guards (2026-09-22 update).** Both
  failed at first (`AttributeError` on absent `ManufacturerModelName`;
  `IndexError` on empty `MeasuredValueSequence`) and now parse with narrowly
  scoped fail-soft guards plus synthetic regression tests — **neither file
  contains rotational acquisitions.** Allura: 3 events (1 fluoro +
  2 stationary), static poses, no end-angle columns (but table/wedge/beam
  angle columns present). GE: 8 fluoroscopy events; the start/end angle
  *  slots* exist (113739/113740-pattern concepts) but every value sequence is
  empty, so all angle columns are None. Lesson for detection design:
  **concept-presence ≠ data-presence** — rotational signals must be
  value-based (113613 string, or end angles populated *and* unequal), never
  column-based. Boundary, stated plainly: the GE file *parses* (valueless
  angles flow as NaN through beam angulation), but full normalization still
  stops later on unrelated missing source-geometry concepts (e.g.
  `DistanceSourcetoIsocenter_mm`) — sparse-file defaults are a separate gap,
  same class as the angle-less files below. The guards also advance the
  TO_DO parser-hardening item (`RF-Pat-Orientation-Modifier-Missing`
  still open).
- **GE OEC MiniView / Canon Ultimaxi — no angle concepts at all.** 22 fluoro
  / 13 fluoro + 5 stationary; raw concept survey finds zero positioner-angle
  concepts, so no arc subdivision can ever be keyed off these files (other
  geometry components are a separate question, unexamined here).
- **Tabular side:** our `normalized` schema carries `acquisition_type`, so a
  tabular exporter *could* signal rotation — but no public DoseTrack /
  Radimetrics / Qaelum sample exists to confirm any of them do (negative
  result stands).

Branch answers (§5): (a) reliable detection signal — **yes** for
Canon-pattern sources (113613 string) and end-populating sources
(`end ≠ start`); **unknown** for Siemens/Philips spins (no spin observed),
**impossible** for angle-less files. (b) start/end angles — **yes** for
Canon only (single fixture; Phase 2 needs more). Arc-center convention
established for Canon: reported pose = START (matters for Phase 1.5/2
center choices). Still wanted: Siemens/Philips spins with end angles, any
matched GE DICOM + tabular pair, and any second measured-arc fixture.

### Phase 1a — Detection + warning (whenever Phase 0 yields a reliable rotational signal for the source, independent of angle availability)

1. Warn per affected event that its dose is modelled at one static pose: the
   local dose near that pose is usually overstated, but the global PSD error
   direction is not guaranteed (§2). Reuse/align with the existing
   `_normalize_acquisition` mapping (`src/guiskindose/export/metrics.py:61`)
   for rotational-vs-static classification rather than inventing a second
   one. Follow the `_emit_beam_miss_summary`
   dial precedent
   (`src/guiskindose/calculate_dose/calculate_irradiation_event_result.py:68`);
   reuse the GUI `state.calc_warnings` collector.
 2. Unit tests on synthetic normalized rows; docs describe the limitation in
   the Calculate-tab help and rich-export methodology note.
3. **Handling ledger (early phase, do with the first shipped handling):**
   alongside the per-event warning, surface an aggregate summary — how many
   rotational events were present out of the total, and how each was handled
   (static-pose estimate / assumed-arc / measured-arc / skipped) — in both
   the GUI warnings surface and the rich-export/report methodology section,
   so a reader of the app or the report can see the count and the treatment
   without reconstructing it event by event.

### Phase 1.5 — Assumed-arc subdivision (candidate interim approach)

If Phase 0 yields a reliable rotational detection signal but no angle data
— or the team wants a simple first stage before fixtures arrive — the event
dose may be spread over N sub-poses spanning an **assumed** arc instead of
measured angles. This is Phase 2 machinery with assumed rather than measured
arc parameters, so all of Phase 2's pipeline requirements apply unchanged
(pre-loop expansion with parent-event IDs, kerma-conserving weights,
aggregation back to one parent row, per-pose hits/field-area/`k_isq`,
per-event `k_bs`/`k_med`/HVL/`k_tab` handling, miss semantics).

Assumed-arc conventions (all explicit settings, all recorded in provenance):

1. **Single-axis sweep**: sub-poses vary `Ap1` (primary, LAO/RAO) and hold
   `Ap2` fixed, matching typical C-arm propeller rotation. Confirm per source
   in Phase 0 (per-source confirmation required); do not assume it for
   biplane or non-standard protocols.
2. **Uniform kerma split** across sub-poses by default. This is approximate:
   constant rotation speed justifies equal dwell, but AEC modulates tube
   output with angle (lateral vs AP thickness), which an assumed arc cannot
   model. State the approximation in the methodology note.
3. **Arc center**: default to the reported static pose **only if** Phase 0
   establishes what that pose represents (start / mid / end) for the source.
   Otherwise require explicit user input — a wrong center shifts the whole
   arc band.
4. **Arc span**: no silent default. Clinical spins are typically on the
   order of 180–220° arcs per source (per-source confirmation required in
   Phase 0), not full wrap-arounds; assuming a wider span than reality
   dilutes dose onto never-irradiated skin. The safe direction is uncertain
   by construction, so the span default (if any) needs physicist sign-off,
   and a full 360° wrap must never be the quiet fallback.

Safety asymmetry (why this stays estimate-grade): the current static model
typically errs **conservative** (concentrates dose; §2 notes the global PSD
direction is not guaranteed). An over-wide assumed arc errs
**non-conservative** (dilutes PSD). Phase 1a warnings therefore apply with
greater force, and GUI + exports must mark assumed-arc results as estimates,
recording center, span, N, and the uniform-split approximation.

Acceptance: Phase 2 criteria (kerma conservation, weighting, arc-band
contiguity, convergence with decreasing step, golden tests) plus one limit
check — narrowing the assumed span toward zero recovers the static-pose
result. Empirical anchor (not a fixture): the OpenREM Canon rotational event
sweeps primary 90 → −120 (210°) with secondary fixed — consistent with the
single-axis default and the 180–220° typical span, pending per-source
confirmation.

Open before building: default span value and center convention per vendor
(Phase 0); whether AEC modulation is material enough to block uniform
splitting (needs physicist input).

### Phase 1b — Documented limitation (if Phase 0 finds neither a detection signal nor angle data for the source)

If spin angles are unavailable in every supported input and no detection
signal exists: downgrade this item
to a documented limitation (help page + export methodology note stating spins
are modelled at the reported static pose), keep the TO_DO pointer, and close
the modelling question until a source format change reopens it.

### Phase 2 — Arc-subdivision model (only if Phase 0 yields angle data)

If start/end angles (or per-frame angles) are available:

1. Expand the spin event into N sub-pose rows **before** the per-row
   prerequisites in `calculate_dose()` (below-floor policy, HVL append,
   `check_new_geometry`, `k_bs` splines, `k_tab`, kerma-meter factors, and the
   event-count-sized output template:
   `src/guiskindose/calculate_dose/calculate_dose.py:144`), carrying a stable
   parent-event identifier and kerma-conserving weights (uniform split by
   default; kerma-weighted if per-frame kerma exists). Run the expanded frame
   through the existing hit-test/correction path — no new physics, just N
   evaluations. Expanding only inside the event loop would misalign the
   precomputed arrays; expanding without aggregation would leak N synthetic
   events into the GUI and exports.
2. Per sub-pose, recompute the genuinely pose-dependent quantities: hit sets,
   skin-plane field area, and `k_isq`. Reuse the parent event's per-event
   constants: HVL, the `k_bs` splines (evaluated per sub-pose through that
   sub-pose's field area), `k_med` (same field-area-dependent evaluation),
   the kerma-meter factor, and the resolved `k_tab` scalar applied via
   per-sub-pose table-hit testing. Aggregate sub-pose corrections,
   hits/misses, and provenance back into one parent event for GUI/export
   reporting (the post-policy frame is length-aligned with exports, so
   aggregation is required, not optional); record N and the arc span in the
   provenance note. Define how partial and total sub-pose misses surface,
   including the `missed_event_indices` representation.
3. Choose N by angle step with a cap: each sub-pose is a full new geometry
   evaluation, so ray-casting cost scales with N. Bound N and warn when the
   cap binds.
4. Acceptance: kerma conservation across sub-poses (weights sum to the parent
   `K_IRP`); correct weighting on a synthetic fixture; a contiguous arc band
   on the dose map; convergence of PSD and dose map with decreasing angular
   step; golden characterization tests pin the subdivision math. Assert no
   PSD inequality — a static-vs-arc comparison needs a fixture with a known
   expected result, chosen explicitly.
5. **GUI representation of subdivided events** (ship with the model, not
   after): the event-geometry view must show a rotational event as composed
   of its sub-events — e.g. the geometry slider steps through sub-poses or
   the event renders as its full arc band — rather than showing only the
   parent static pose, which would contradict the dose. On the dose map,
   give rotational sweep paths a distinct visual marker (separate color
   overlay, or an outline/border tracing the sweep band across the skin) so
   they read differently from static fields at a glance; assumed-arc bands
   additionally carry the estimate-grade marking from Phase 1.5. Keep the
   handling-ledger summary (§Phase 1a item 3) as the textual counterpart —
   marker for the eye, ledger for the record.

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
