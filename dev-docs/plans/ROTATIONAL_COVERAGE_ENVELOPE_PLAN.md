# Rotational Coverage-Envelope Plan

Joint design (maintainer/medical physicist + sol review, 2026-09-22): stop
silently collapsing rotational irradiation to one static pose. The default
answer is a **conditional, numerically sampled upper coverage envelope** — the
pointwise maximum full-event-kerma response over declared candidate poses —
with separate scenario results available for physically realizable estimates.

This plan supersedes the assumed-arc default in the rotational-acquisition
assessment Phase 1.5 and redefines Phase 2. The assessment remains the evidence
and current-code record; this plan is the implementation source of truth.
Status: initial envelope implementation complete (classifier, normalizer contract, dose loop, prompt, exports, badge); scenarios/nominal UI deferred (see Open follow-ups).

The clinical goal is useful improvement with honest limitations, not exact
trajectory reconstruction from data that classic RDSR does not contain. A
second vendor fixture or film/array validation may improve the model later but
is not a gate to the first implementation.

## Why not the alternatives

- **Static-only (today):** silent point-mass at the reported start pose. It
  does not bound PSD in either direction.
- **Additive both-arcs-plus-static (rejected):** depositing K per arc plus K
  static (3K nominal) breaks kerma conservation, DAP reconciliation, and event
  audit semantics, yet still proves no pointwise bound. Concentrated true
  output can exceed a uniformly spread candidate at a skin cell.
- **2x-over-360 degrees for type-only (rejected as a guarantee):** for a
  uniform true arc of length L, pointwise angular-density domination requires
  m >= 360/L; this is unbounded as L approaches zero. Nonuniform AEC output
  removes even that finite guarantee. The envelope needs no multiplier.
- **Single assumed arc (rejected as the default):** direction is absent from
  classic RDSR. Silently selecting one path repeats the problem being fixed.

## Core construction and semantics

For skin cell x, event envelope

`E(x) = K * max(q in Q) R(x, q)`,

where K is the parent event/acquisition's **full effective `K_IRP`** entering
the dose response (the full reported `K_IRP`, adjusted once by any configured
kerma-meter calibration), R(x, q) is dose per unit effective `K_IRP` at pose q,
and Q is the declared candidate set. If the real event comprises poses q_i in
Q with nonnegative kerma portions k_i whose sum is K, then

`D_true(x) = sum(k_i * R(x, q_i)) <= K * max(R(x, q_i)) <= E(x)`.

This permits arbitrary AEC angular modulation and recomputes pose-dependent
skin hits, inverse-square response, field area, and table/pad attenuation
inside R. Corrections that are truly parent-event constants remain constants.

Implementation must evaluate every candidate with the **full parent K**, take
the cellwise maximum across candidate maps, and discard the candidate maps.
It must never sum those full-K maps or expand them as N kerma-bearing events.
It does not divide K by N. The rotational-envelope multiplier is always `1.0`;
configured meter calibration is an existing measurement correction, not an
envelope multiplier. Preserve the original reported `K_IRP` separately for
audit.

Across parent events, sum their event maps cellwise and then take the maximum
cell for PSD. A rotational envelope event contributes its cellwise envelope;
a scenario or static event contributes its ordinary physical event map. Do not
max between different parent events.

The envelope is not a physical dose distribution and has no meaningful
map-integrated kerma or DAP. Source K/DAP values remain unchanged and remain
the only values used in dose/kerma audits. The conditional claim requires:

1. the true poses to be represented by the declared pose domain;
2. event output to be representable as nonnegative portions summing to K;
3. the pose response to be sufficiently sampled at the selected angular step;
4. unreported field, spectrum, table, and secondary-motion assumptions to be
   adequate for the case.

Reports must therefore use **conditional coverage envelope**, not simply
"conservative dose" or "upper-bound dose".

## Classifier and normalizer contract

Classification is shared non-GUI code (`rotational_acquisition.py`) consumed
by calculation, GUI, CLI, and export. Export metrics must consume its result;
they must not independently classify by substring.

### Additive normalized fields

Keep current `Ap1`, `Ap2`, and `acquisition_type` meanings unchanged and add:

| Field | Meaning |
|---|---|
| `Ap1_end` | normalized primary end angle in degrees, using the same `rot_dir.Ap1` sign transform as `Ap1`; null when absent/nonfinite |
| `Ap2_end` | normalized secondary end angle in degrees, using the same `rot_dir.Ap2` sign transform as `Ap2`; null when absent/nonfinite |
| `acquisition_type_code` | raw code value as a string, e.g. `113613`; null when unavailable |
| `acquisition_type_coding_scheme` | raw coding scheme, e.g. `DCM`; null when unavailable |
| `acquisition_type_meaning` | raw code meaning/string without heuristic rewriting; preserves current `acquisition_type` compatibility |

The RDSR parser must preserve code value, coding scheme, and meaning using the
existing `AcquisitionPlane_*` pattern. Raw DICOM columns remain
`PositionerPrimaryEndAngle_deg` and `PositionerSecondaryEndAngle_deg`; the new
raw identity columns are `IrradiationEventType_CodeValue` and
`IrradiationEventType_CodingSchemeDesignator`, alongside the existing
`IrradiationEventType` meaning column.
Tabular adapters pass optional equivalents when present and otherwise set the
new fields to null; their absence is not an import error.

### Classification result and reason codes

Each parent row produces:

- `classification`: `rotational`, `positioner_motion`, `static`, or `unknown`;
- `reason_codes`: one or more stable tokens below;
- `confidence`: `coded`, `meaning`, `text_alias`, `angle_motion`, or `none`;
- `usable_endpoints`: boolean;
- `usable_baseline_geometry`: boolean;
- per-axis circular separations for audit, never interpreted as direction.

Stable reason codes for the first implementation:

| Reason code | Trigger |
|---|---|
| `type_code_rotational` | DCM `113613` |
| `type_meaning_rotational` | exact normalized meaning `Rotational Acquisition` when a code is unavailable |
| `type_code_stepping` | DCM `113612` |
| `type_meaning_stepping` | exact normalized meaning `Stepping Acquisition` when a code is unavailable |
| `type_code_stationary` | DCM `113611` |
| `type_meaning_stationary` | exact normalized meaning `Stationary Acquisition` when a code is unavailable |
| `contradictory_static` | explicit stationary identity is present together with primary or secondary endpoint motion |
| `text_alias_rotational` | case-insensitive whole token/phrase `DynaCT`, `spin`, or `roll` in acquisition type or protocol text |
| `primary_endpoint_motion` | finite primary endpoints separated by at least 2.0 degrees circularly |
| `secondary_endpoint_motion` | finite secondary endpoints separated by at least 2.0 degrees circularly |
| `equal_endpoints` | populated endpoints are separated by less than the fixed 2.0-degree threshold |
| `missing_or_invalid_endpoints` | required endpoint value absent, NaN, or infinite |
| `missing_baseline_geometry` | existing beam/phantom geometry prerequisites are not finite/evaluable |
| `unrecognized_type` | nonempty acquisition identity is not in the data-driven indicator set |
| `trajectory_unresolved` | effective handling fell back to static because the requested candidate domain could not be constructed |

The fixed `>= 2.0 degrees` threshold suppresses rounding/readout jitter; it is
a detection rule, not a claim that smaller physical motion is impossible and
not a user setting. Test 0/1.99/2.00/2.01 degrees, wrap boundaries, nulls, NaN,
infinities, and one-axis-only motion. Preserve signed endpoints for audit.
Never infer a span or direction from their signed difference: 90 to -120
remains two hypotheses.
The 2.0-degree threshold was deliberately chosen over the earlier 0.5-degree
draft as extra margin against encoder rounding and calibration wobble.

`DynaCT`, `spin`, and `roll` are practical general rotational-handling
triggers. Match them case-insensitively as whole normalized tokens/phrases so
unrelated substrings do not trigger. They may classify and prompt, but they
never choose direction, span, or a nominal arc. Record the alias reason and
lower `text_alias` confidence; do not export raw protocol text.

Classification precedence is deterministic: an exact stepping identity wins
`positioner_motion`. An explicit stationary identity together with endpoint
motion yields `unknown` plus `contradictory_static`; neither declaration nor
angles silently override the other. It raises a high-severity pre-calculation
notice and requires an explicit per-event `Coverage` or `Static` selection
(`Auto` cannot proceed). Otherwise an exact rotational identity, a rotational
text alias, or either endpoint-motion reason yields `rotational`; an exact
stationary identity or populated equal endpoints yields `static`; all remaining
rows are `unknown`. Other unknown rows retain today's static calculation
without a rotational prompt or bound claim.

`usable_endpoints` means at least one axis has finite start/end values and a
motion reason. An axis without motion needs a finite start value but does not
need an end value; it is held fixed. Thus primary motion with an absent
secondary end value remains usable when the secondary start is finite.

### Direction evidence boundary

Classic RDSR TID 10003C supplies start/end angles but no direction, increment,
trajectory, or speed concept. Defensive parsing may retain unknown/private SR
extensions and report that they were present, but no private value controls
geometry until a documented mapping is enabled. Direction/increment fields in
referenced XA or X-Ray 3D image objects (`0018,1520/1521` and
`0018,9514/9515/9518/9519`) belong to the separately tracked image-ingestion
work; they are not searched for as if they were classic-RDSR event content.

`positioner_motion` is not automatically treated as a primary rotational
sweep. It remains static with a warning unless the event is explicitly
overridden, because stepping and coupled motions need a declared domain.

## Candidate-domain rules

### Shared wrapped-path generator

Generate candidates in normalized GUISkinDose angle coordinates, after
`rot_dir` signs have been applied. For each changing circular axis with start
`s_raw` and end `e_raw`:

1. Canonicalize `s = s_raw mod 360` and `e = e_raw mod 360` into `[0, 360)`.
2. Compute the positive wrapped displacement
   `delta_pos = (e - s) mod 360`, in `[0, 360)`.
3. Invoke this generator only for an axis carrying an endpoint-motion reason.
   If separation is zero or below the motion threshold, emit no measured paths
   and do not compute a negative path. Otherwise compute
   `delta_neg = delta_pos - 360`.
4. The two path hypotheses are the signed displacements `delta_pos` and
   `delta_neg`. Label the smaller absolute displacement short and the other
   long. At exactly 180 degrees retain explicit positive-180 and negative-180
   paths rather than assigning an arbitrary unique short path.

For a signed path displacement `delta`, let `L = abs(delta)` and

`N_path = max(2, ceil(L / angular_step_deg) + 1)`.

For `j = 0 .. N_path - 1`, set `t_j = j / (N_path - 1)` and generate
`angle_j = (s + t_j * delta) mod 360`. Set the first and last candidates from
the canonical start/end explicitly so floating-point interpolation cannot move
an endpoint. Raw signed endpoints remain in the ledger even though candidate
angles are canonicalized.

Candidate `q` is a complete normalized geometry pose, not just an angle:
copy the parent event's geometry fields used by the existing geometry-cache
key (`Tx/Ty/Tz`, field sizes, `Ap1-Ap3`, `At1-At3`, distances, and other
required beam fields), replacing only the angle or angles varied by the
declared path. This keeps candidate generation separate from dose physics.
`N` is a numerical angular-resolution choice, not an estimate of projection
count. Do not derive it from exposure or total time because classic RDSR does
not provide the speed/trajectory needed for that inference.

Deduplicate only after all requested paths and the optional legacy static pose
have been generated. Compare the complete geometry pose; compare circular
angles modulo 360 with absolute tolerance `1e-9` degrees. Preserve requested
path IDs/counts in the ledger even when endpoints collapse to one unique pose.
Dedup runs in two stages: the generator deduplicates angle pairs (its only
pose knowledge), and the dose loop re-deduplicates over complete geometry
poses before evaluating, since a legacy static candidate may share angles
while differing elsewhere.

### Measured endpoints

An event uses the measured-endpoint envelope when it classifies `rotational`,
either endpoint-motion reason is present, and the existing baseline geometry
is usable. Acquisition type may corroborate this but is not required. A
`positioner_motion` event needs an explicit Coverage override before these
endpoint rules are applied.

- One changing axis: generate both wrapped paths between start and end (short
  and long). Their union samples the full circle, but retaining path identity
  makes the unknown-direction disclosure explicit.
- Both primary and secondary changing: generate the four combinations of
  short/long primary and short/long secondary. For each combination, couple
  both axes by normalized path fraction `t` from 0 to 1. This is practical,
  not exhaustive of arbitrary non-monotonic or independently timed two-axis
  motion, and must be disclosed.
- An unchanged axis is held at its reported start value. Other event geometry
  is held fixed unless a later measured source explicitly supplies it.
- Add the legacy static pose to Q when `include_static_pose` is true. It is
  max-combined and usually duplicates an endpoint; it is never dose-added.

For one-axis open arc length L and configured step d, the shared generator
therefore gives:

`N_arc = max(2, ceil(L / d) + 1)`.

Use exact endpoints and an actual uniform step `L / (N_arc - 1) <= d`. For a
coupled path, use `L = max(L_primary, L_secondary)` so neither changing axis
advances by more than d per sample: calculate one `N_path` from that maximum,
use the same `t_j` for both signed displacements, and create the paired
`(Ap1_j, Ap2_j)` pose. Deduplicate identical endpoint/static poses before
calculation, but report both requested path counts and the final unique
candidate count.

At exactly 180 degrees, short and long have equal length but opposite signed
directions; retain both paths and deduplicate only identical poses, not path
identities in the ledger.

### Type-only rotation with no usable endpoints

A quiet 360-degree coverage fallback is allowed **only** when:

1. classification is `rotational` because of `type_code_rotational`, exact
   `type_meaning_rotational`, `text_alias_rotational`, or an explicit per-event
   expert override; and
2. the reported static geometry is sufficient for the existing beam/phantom
   calculation, including finite starting primary and secondary angles.

Generate a closed primary-angle circle about that reported static geometry;
hold secondary angle, table position, field, spectrum, and distances fixed.

`N_360 = ceil(360 / d)`

with N distinct poses, actual step `360 / N <= d`, and no duplicated 0/360
endpoint. At the default 1 degree, N is 360. The reported static pose is
already a member. Specifically, for `j = 0 .. N - 1`, generate
`Ap1_j = (Ap1_start + j * 360 / N) mod 360`, copy all other parent geometry,
then add/deduplicate the optional legacy static candidate.

If either gate fails, use static handling and emit high-severity reason
`trajectory_unresolved`; do not claim a coverage bound. Angle-less files with
no rotational type signal do not silently receive a 360-degree envelope.

This rule intentionally supersedes the assessment Phase 1.5 prohibition on a
quiet full-360 **kerma-spreading scenario**. Full-360 remains prohibited as a
silent physical scenario; it is permitted here only as a clearly labeled
max-envelope candidate domain.

### Static events

Use the existing one-pose physical calculation: N = 1 and multiplier = 1.0.
Do not apply envelope wording or rotational inflation.

### Pipeline integration and parent-event outputs

Do not expand the shared normalized DataFrame for envelope handling. That
would misalign event-sized correction arrays and would invite synthetic rows
to leak into GUI/export event counts. Instead, the parent-event calculation
builds candidate poses and calls a reusable single-pose response evaluator.
Stream each returned cell-dose vector into a running cellwise maximum so N
full maps do not remain resident in memory. Then add that one envelope vector
to the procedure accumulator and emit one parent-event result/ledger row.

For hit/miss reporting, an envelope event is a total miss only when every
candidate misses the phantom. Record candidate hit and miss counts; partial
candidate misses are an envelope limitation notice, not N missed events.

Do not invent one physical correction-factor row for an envelope. Preserve
parent constants, report ranges for pose-dependent corrections, and identify
the candidate controlling the final envelope PSD cell. Scenario mode retains
its ordinary kerma-weighted physical correction summary. Existing public
dict/JSON output adds the structured `rotational_handling` object and advances
its schema version; rich-report payload changes advance that schema separately.

### Sampling bounds

`angular_step_deg` defaults to `1.0` and accepts `0.25` through `10.0`
degrees. Invalid API/CLI values fail validation; the GUI constrains entry.
These bounds keep the maximum four-path, two-axis candidate set finite without
a silent cap. The first release makes a numerical coverage claim only at the
reported step; convergence tests characterize, rather than promise away,
continuous-angle sampling error.

## Scenario mode is separate

`scenarios` produces physical, kerma-conserving alternatives. It does not
reuse or relabel the envelope map:

- `static`: all K at the reported static pose;
- `nominal_arc`: one explicitly selected endpoint path, with nonnegative
  subpose weights summing to 1.0;
- `alternative_arc`: the other endpoint path when available, also with its
  own weights summing to 1.0.

Each scenario is calculated and reported separately; scenarios are never
added together and are never max-combined and called a physical dose map.
Uniform subpose weights are the initial approximation unless measured
per-frame output becomes available.

At procedure level, the first release emits these non-combinatorial results:

1. `all_static`: every rotational event uses its reported static pose;
2. `nominal`: every rotational event uses its explicitly selected nominal
   path; unresolved events remain static and are flagged;
3. one-at-a-time alternatives: change one event to one alternative path while
   all other events remain nominal.

For a one-axis event there is one alternative path. For a coupled two-axis
event, the three unselected short/long combinations are separate alternatives.
Do not silently form the Cartesian product of alternatives across events.
Every result names the event/path changed, and no generic "alternative PSD"
is shown without that identity.

`nominal_arc` requires either an explicit per-event expert selection or a
documented site/protocol profile enabled by the user. Protocol-name heuristics
may suggest a choice but cannot silently select it. No vendor dataset is a
universal shipping gate; an automatic profile needs documented local evidence
and physicist approval for that profile.

For type-only events, scenario mode does not invent a 360-degree physical
arc. Without explicit center/span/direction inputs or an enabled profile, it
falls back to static with `trajectory_unresolved`. The old assumed-arc design
is therefore optional expert input, not a default.

## Controls and prompt behavior

Minimal persisted/global settings:

- `rotational_handling`: `coverage` (default), `scenarios`, or `static`;
- `include_static_pose`: boolean, default true;
- `angular_step_deg`: float, default 1.0.

Per rotational/positioner-motion event: `Auto`, `Coverage`, or `Static`.
`Auto` inherits the global setting. The first release has no per-event Ignore
and no per-event Nominal button; scenario path selection belongs in the
scenario details control and requires explicit confirmation.

Deferred to a later slice (not in the first release): per-event override
controls in the GUI, their persistence across recalculation, provenance
export of overrides, and reset-on-new-dataset for overrides. Likewise,
`scenarios` handling and nominal-arc selection UI are API/CLI-only until
that slice; the pre-calc prompt offers `coverage` vs `static` only.

`include_static_pose=false` means "do not add the separate legacy static
candidate." It cannot remove a reported start pose that is inherently an arc
endpoint or a member of the type-only 360-degree domain. The GUI tooltip and
ledger must say this so "no static" is not mistaken for excluding that angle.

In the GUI, before calculation, show one prompt per loaded dataset when any
event classifies as rotational or positioner motion, unless suppressed for
the session. It shows counts by classification, the default handling, any
type-only unresolved events, and a link/expander for event details. `Run`
writes the selected global handling to GUI state; `Cancel` aborts calculation;
`Don't ask again this session` suppresses repeats only for that session.
Per-event overrides survive recalculation for the loaded dataset and are
included in settings/provenance export. Loading a new dataset clears them and
the prompt suppression. CLI/API never prompt: they use settings, emit the
summary warning, and default to coverage when the setting is absent.

## Handling ledger and disclosure placement

Calculation returns one privacy-safe ledger row per detected rotational or
positioner-motion parent event. Do not include source filenames, UIDs, patient
identifiers, or raw protocol names. Each row contains:

- `event_index` (calculation-local integer) and exam label/index already used
  by the result model;
- `classification`, `reason_codes`, `confidence`;
- `requested_handling`, `effective_handling`, and any fallback reason;
- normalized start/end angles and per-axis circular separations;
- `candidate_domain`, requested path counts, unique candidate count,
  `angular_step_deg`, and static-pose inclusion;
- direction source (`unknown`, `expert`, `profile`, or future `measured`);
- source K/DAP values unchanged, multiplier `1.0`, and aggregation rule;
- fixed-geometry assumptions and coded notices.

The aggregate ledger records total events, detected counts by classification,
counts by effective handling, and whether any event fell back to static.

Disclosures appear in all relevant surfaces:

1. **Calculate:** pre-run prompt and post-run coded warning summary.
2. **Results:** persistent envelope/scenario/static badge, headline PSD method,
   unresolved-event warning, and expandable event ledger.
3. **Rich DOCX/XLSX reports:** methodology statement near the PSD result plus
   the per-event ledger in the event/method appendix.
4. **Dict/JSON exports:** structured `rotational_handling` object containing
   mode, aggregate counts, assumptions, and event rows.
5. **CLI:** value-safe stderr summary; JSON/dict carries the full ledger.

Every envelope disclosure states: event detection reason; measured endpoints
and their DCM concept codes (`112011`, `112012`, `113739`, `113740`) when
applicable; direction status; candidate domain;
static inclusion; angular step and counts; max-within/sum-between aggregation;
unchanged source kerma/DAP; fixed-geometry assumptions; and that this is an
estimate-grade conditional envelope, not a physical trajectory or guaranteed
bound for unrepresented motion. Scenario reports place static, nominal, and
alternative PSDs side by side and say which path/weights produced each.

## Acceptance bar

Required for the first practical release:

- source kerma/DAP and parent-event count remain unchanged;
- multiplier is asserted as 1.0 and full-K candidate maps are maxed, not added;
- on synthetic candidate grids, the event envelope is cellwise greater than
  or equal to every tested kerma-conserving trajectory/weight realization;
- measured one-axis, coupled-axis, wrap, type-only, unresolved, and static
  classifications have boundary tests;
- N formulas, exact endpoints, deduplication, and 0/360 handling are pinned;
- arbitrary AEC-weight synthetic tests preserve dominance;
- per-subpose hit/field/inverse-square/table-pad behavior is exercised;
- decreasing-step characterization detects material numerical instability;
- GUI/CLI/API settings and per-event overrides produce identical handling;
- ledger schemas and required disclosure locations have tests;
- static over-read and under-read examples remain characterized;
- a physicist reviews user-facing defaults and warnings.

The observed Canon characteristics may be represented with synthetic rows;
identifier-bearing upstream DICOM need not be vendored. Siemens/Philips/GE
rotational fixtures, film/array comparison, and per-frame validation are
valuable iterative improvements, not first-release blockers.

## Required implementation tests and documentation

These are part of delivery, not optional follow-up. Tests may be split across
implementation PRs, but each behavior ships with its tests and affected docs.

### Tests

- Classifier unit tests: coded meanings, `DynaCT`/`spin`/`roll` whole-token
  aliases, false-positive substrings, precedence, 1.99/2.00/2.01-degree
  boundaries, wrap boundaries, invalid values, and one-axis motion.
- Candidate-generator unit tests: positive/negative paths, exact 180 degrees,
  start/end preservation, `N_path`/`N_360`, maximum step, coupled-axis shared
  `t`, full-pose copying, deduplication, and static-candidate semantics.
- Envelope math tests: full parent `K_IRP` at each candidate, no K/N split,
  max-within/sum-between aggregation, arbitrary nonnegative AEC weights, and
  proof-by-fixture that candidate maps are never added.
- Dose-pipeline integration tests: pose-dependent hits, inverse square, field
  area, table/pad attenuation, all/partial misses, correction ranges, parent
  event count, and unchanged reported K/DAP.
- Type-only tests: exact/coded and text-alias triggers, usable-geometry gate,
  unresolved static fallback, 360-degree generation, and no fallback for an
  unclassified angle-less event.
- Scenario tests: weights sum to one per physical scenario, explicit nominal
  gating, one-at-a-time alternatives, and no cross-event Cartesian explosion.
- GUI tests: prompt Run/Cancel/session suppression, loading a new dataset,
  global/per-event controls, Results badge, unresolved warning, and ledger.
- CLI/API/export tests: no prompt, default handling, structured ledger, schema
  versions, value-safe warnings, and DOCX/XLSX disclosure sections.
- Documentation contract tests: update any machine-checked algorithm/schema
  assertions, including `test_psd_algorithm_doc.py` where its execution-order
  anchors change.

### Documentation and registries

- Update `PSD_CALCULATION_ALGORITHM.md`, `FEATURE_INVENTORY.md`, and
  `CODEBASE_OVERVIEW.md` with the shipped calculation and output semantics.
- Update `INPUT_FIELD_REFERENCE.md`, `INPUT_DATA_FLOW_AND_OFFSETS.md`, and
  `INPUT_SCHEMA_DETECTION.md` for end-angle/type-code normalized fields and
  adapter availability.
- Update `GUI_PLAN.md`, Settings/Calculate/Results/Export help under
  `docs/source/gui_help/`, then run `scripts/sync_gui_help.py`.
- Update `settings_example.json` and public API/CLI documentation for the new
  settings and defaults.
- Update `help_registry.json`, `ui_copy.json`, `glossary.json`, and
  `feature_doc_matrix.json` when their covered UI copy/features are added;
  then run their repository checks and `scripts/sync_ui_copy.py`.
- Add the user-visible behavior to `CHANGELOG.md`, update `TO_DO.md`, and keep
  this plan plus `dev-docs/index.md` current. Archive the plan only after all
  accepted slices are shipped or explicitly moved to follow-up work.

## Open follow-ups (not gates)

- GUI controls for `angular_step_deg`/`include_static_pose` plus the
  tooltip/ledger semantics for the static flag (currently accepted in
  settings but geometrically inert whenever the reported static pose
  coincides with an arc endpoint, which the pipeline always passes).
- Value-safe warning-content tests, AEC-weight dominance characterization,
  and decreasing-step convergence characterization beyond the N-invariance
  pin already in `test_rotational_envelope_dose.py`.
- Extend exact rotational type indicators as real inputs become available.
- Ingest measured direction/per-frame trajectory from matched XA/Enhanced XA
  objects as a separate future input source.
- Add measured per-frame output weights to scenario mode.
- Revisit continuous-angle error and adaptive sampling if convergence results
  show 1 degree is inadequate for clinically relevant meshes/fields.
- Add protocol-profile import/export after the explicit expert workflow is
  stable.
