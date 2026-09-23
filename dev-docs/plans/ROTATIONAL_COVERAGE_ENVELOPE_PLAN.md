# Rotational Coverage-Envelope Plan

Joint design (maintainer + sol review, 2026-09-22): stop silently collapsing
rotational irradiation to one static pose. Default answer is a **conditional
upper coverage envelope** — pointwise maximum full-kerma response over declared
candidate poses — with scenario analysis beside it for physical estimates.
Supersedes the assumed-arc sketch (assessment Phase 1.5, cut) and redefines
Phase 2. Status: design accepted, not yet implemented.

## Why not the alternatives

- **Static-only (today):** silent point-mass at the reported (start) pose.
  No bound on PSD in either direction (hotspot reinforcement).
- **Additive both-arcs-plus-static (rejected):** depositing K per arc plus K
  static (3K nominal) breaks kerma conservation, DAP reconciliation, and audit
  trails — yet still proves no pointwise bound (uniform spread over 150° gives
  each cell a fraction of K; concentrated true output can exceed it anywhere).
- **2×-over-360° for type-only (rejected as a guarantee):** pointwise
  domination needs m ≥ 360/L, unbounded as L→0. The envelope below needs no
  multiplier.
- **Single assumed arc (rejected as default):** direction is unmeasured in
  classic RDSR; silently picking one path is the failure to avoid.

## Core construction

For skin cell x, event envelope E(x) = K · max_{q ∈ Q} R(x,q), where R(x,q) is
dose per unit kerma at pose q and Q the declared candidate set. If truth is
poses q_i with kerma portions k_i (Σk_i = K) all inside Q, then
D_true(x) = Σk_i·R(x,q_i) ≤ K·max R ≤ E(x) — valid under **arbitrary AEC
angular modulation** and with per-subpose table/pad attenuation recomputed
inside R. Across events: sum envelope maps, take the max cell. The envelope
is not a physical dose map: unsuitable for DAP reconciliation; label it as
what it is. Kerma multiplier is always 1.0.

## Candidate domains

- **Measured endpoints:** both wrapped endpoint-consistent paths per rotating
  axis (short + long primary; all four short/long combos if secondary also
  changes — disclosed as non-exhaustive for coupled motion). Sampled at
  Δθ = 1° default (advanced setting) with exact endpoints included:
  N_arc = max(2, ⌈L/Δθ⌉ + 1). Plus the legacy static pose by default
  (harmless under max; protects legacy-construction differences).
- **Type-only (no usable endpoints):** closed 360° primary sweep about the
  reported static geometry, other geometry fixed:
  N_360 = ⌈360°/Δθ⌉ (360 distinct poses, no 0°/360° double-count). No usable
  baseline geometry → static-only + high-severity "trajectory unresolved"
  notice; no bound claimed.
- Aggregation: pointwise maximum within each event; normal summation between
  events. Original event kerma/DAP preserved untouched in records.

## Detection (prerequisite, ships with this)

Shared non-GUI classifier (`rotational_acquisition.py`), consumed by
calculation and export — never the coarse metrics mapping:
- classification `rotational` / `positioner_motion` / `static` / `unknown`;
  signals (type code/meaning, per-axis motion); confidence type-confirmed vs
  angle-inferred; treatment tag.
- Type signal: data-driven indicator set (`Rotational Acquisition`, 113613;
  extend on samples). Stepping (113612) ⇒ `positioner_motion`, honestly worded.
- Angle signal: populated end angles with circular separation > 0.5° fixed
  (not a user setting — detection integrity). Raw signed endpoints preserved
  for audit; **no span/direction inference** (90→−120 stays two hypotheses).
- Boundary tests: 0/0.49/0.50/0.51°, NaN/None, infinities, one-axis-only.
- Normalizer contract (additive): end angles through `rot_dir` convention +
  coded acquisition identity (AcquisitionPlane_CodeValue precedent), so the
  angle signal works downstream of the shared calculation path. Tabular
  adapters preserve optionals where available.

## Controls (minimal surface)

- `rotational_handling`: `coverage` (default) / `scenarios` / `static`.
  `nominal` arc selection is NOT a global mode — direction picks happen only
  via protocol-validated defaults or explicit per-event expert override,
  recorded in provenance.
- `include_static_pose`: default on (max-combined, not dose-added).
- `angular_step_deg`: default 1°, advanced.
- Per-event: `Auto` (inherits global) / `Coverage` / `Static`. No separate
  ignore control.
- Pre-calc prompt on first detection in a run writes back to the setting
  (reproducible via settings export), following the below-floor-kVp prompt
  precedent.

## Mandatory disclosures (GUI Results + rich reports)

Events treated as rotational and why; measured endpoints + concept codes;
direction known/inferred/unknown; candidate domain per event; static
inclusion; angular step and subpose counts; aggregation rule (max within,
sum between); original kerma/DAP unchanged; fixed-geometry assumptions;
static/nominal/alternative PSDs side by side when scenarios run; whether the
hotspot moves across treatments; "estimate-grade rotational modeling —
no treatment bounds PSD" stated plainly.

## Acceptance

Kerma/DAP records unchanged; envelope ≥ every single-arc realization on
synthetic fixtures (dominance tests); golden characterization tests;
convergence with decreasing Δθ; ±180° wrap tests; coupled-axis tests; cases
where static over- AND under-reads PSD; physicist review of defaults before
any protocol-specific inference becomes automatic.

## Open items (not gates)

Siemens/Philips rotational strings on samples (extend indicator set);
measured-arc subdivision when per-frame data exists; XA-header
direction/trajectory ingestion (tracked separately in TO_DO); film/array
validation; random-port/help follow-ups unaffected.
