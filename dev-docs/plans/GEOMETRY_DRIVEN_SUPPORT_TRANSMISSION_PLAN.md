# Geometry-Driven Patient-Support Transmission Plan

Status: Research and validation required — separate future branch/PR
Created: 2026-09-08
Parent roadmap:
[CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md](CORRECTION_DATA_AND_SUPPORT_TRANSMISSION_PLAN.md)
Dependencies:
[CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md](CORRECTION_SAFETY_AND_TUBE_IDENTITY_PLAN.md) and
[CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md](CORRECTION_DATA_PACKAGING_AND_PROVENANCE_PLAN.md)

## Objective

Determine patient-support intersection from the actual positioned table and pad
volumes, independently of manufacturer/tube labels, and establish a scientifically
validated route to path-length-aware transmission.

This plan must not infer material attenuation from geometry alone. Intersection and
path length are geometry outputs; converting path length into transmission requires
measured or defensible material/effective attenuation data.

## Verified Current State

- The table and pad phantoms are separate cuboids with user-configurable dimensions.
- `check_table_hits()` tests source-to-skin rays against two triangles from one table
  face and returns a boolean per irradiated skin cell.
- The positioned pad is not tested.
- A source-side dot-product shortcut bypasses the intersection test for one side of
  the table plane.
- Intersected cells receive one event-level combined table+pad transmission `k_tab`.
- No entry/exit points, table path length, pad path length, or angle-dependent
  transmission are calculated.
- Tube A/B/single identity does not position the source. Beam angles, distances, and
  table coordinates determine geometry.
- Plane B zero transmission is handled by the immediate safety plan; this geometry
  plan must not rely on plane-specific zero rows to represent lateral beams.

## Phase 0 — Characterize Existing Geometry

- [ ] Build synthetic, vendor-neutral fixtures for AP, PA, exact lateral,
  near-lateral, oblique, partial-field, translated table, shifted patient, and
  biplane-labeled events with identical physical geometry.
- [ ] Pin which table face is currently tested and how table orientation affects it.
- [ ] Characterize the dot-product shortcut on both sides of the face and around its
  zero boundary. Treat numerical fragility as a hypothesis until tests demonstrate
  it.
- [ ] Verify that changing only `acquisition_plane` does not change beam geometry.
- [ ] Verify current per-cell behavior when some rays intersect and others do not.
- [ ] Record current pad omission and combined-factor behavior.
- [ ] Record the interim safety invariant: warned-neutral `1.0` for an invalid
  transmission on a genuinely table-intersecting lateral event is conservative on
  the PSD side but may overestimate dose by omitting support attenuation. Preserve
  its warning/export status until validated geometry and attenuation data replace it.

Deliverable: a maintainer assessment with diagrams, characterization tests, known
limitations, and explicit invariants for the replacement.

## Phase 1 — Closed-Volume Intersection

- [ ] Define a reusable segment-versus-closed-cuboid intersection result containing:
  support object, hit/miss, entry point, exit point, and in-volume path length.
- [ ] Apply it independently to the positioned table and pad for every irradiated
  skin-cell segment.
- [ ] Handle parallel rays, face/edge/corner contact, source-inside, cell-inside,
  zero-length segments, floating-point tolerance, and rotated/translated cuboids.
- [ ] Remove the old dot-product shortcut only when replacement tests show correct
  source-side behavior without it.
- [ ] Keep plotting and calculation coordinate conventions aligned.
- [ ] Preserve the legacy boolean/combined transmission mode while recording richer
  path metadata.

Acceptance:

1. Physical geometry, not manufacturer or tube label, determines table/pad crossing.
2. Table and pad intersections are independently auditable.
3. Exact/near-lateral and boundary behavior is deterministic and tested.
4. Legacy valid AP/PA dose remains unchanged while legacy combined mode is active,
   unless a separately reviewed bug is demonstrated.

## Phase 2 — Attenuation Model Requirements

- [ ] Inventory available measurements: combined table+pad transmission, separate
  table transmission, separate pad transmission, material composition, thickness,
  beam quality, and measurement angle.
- [ ] Do not derive separate table/pad coefficients from one combined measurement;
  that problem is underdetermined.
- [ ] Select one model only after review:
  - measured transmission grid by beam quality and angle;
  - separate effective linear attenuation coefficients;
  - a clearly labeled effective combined model with constrained assumptions.
- [ ] Define uncertainty, interpolation/clamping, valid angle/path ranges, and
  fallback behavior.
- [ ] Require literature, empirical dosimetry, or Monte Carlo evidence appropriate
  to the selected model.
- [ ] Establish reference cases and acceptance tolerances before implementation.

## Phase 3 — Path-Length-Aware Transmission

- [ ] Implement the approved model as a separate strategy; do not silently replace
  legacy behavior.
- [ ] Calculate per-cell transmission from actual table and pad path lengths and
  beam quality.
- [ ] Use neutral transmission `1.0` for supports the closed-volume geometry proves
  are not intersected.
- [ ] Do not key geometric crossing on Plane A/B/Single or manufacturer.
- [ ] Retain explicit measured-profile identity where material/support data are
  equipment-specific.
- [ ] Export per-cell/event summaries sufficient to audit intersection, path length,
  model, source, and applied transmission.
- [ ] Add a controlled migration option and comparison report before any default
  change.

## Validation

- Analytic segment/cuboid tests and property tests for rigid transformations.
- Characterization and golden-dose comparisons.
- Independent reference implementation or geometry cross-check.
- Empirical phantom or Monte Carlo benchmarks for the attenuation model.
- Performance benchmarks on realistic event/cell counts.
- GUI Geometry and Results smoke tests plus export audit checks.
- Type, lint, privacy, documentation, and full regression suite.

## Risks and Non-Goals

- More geometric detail does not by itself improve attenuation accuracy.
- Table and pad meshes/dimensions may not represent every clinical support.
- Applying normal-incidence transmission at oblique angles without validation can
  be less accurate than the current model.
- This plan does not alter inherited Plane B data; immediate invalid-value safety is
  owned by the correction-safety plan.
- This plan does not create the custom equipment-profile ingestion surface.

## Delivery

Keep characterization, closed-volume geometry, and attenuation-model changes in
separate commits or PRs where practical. Do not change the default dose model until
scientific acceptance criteria are met and the SemVer/release impact is approved.
