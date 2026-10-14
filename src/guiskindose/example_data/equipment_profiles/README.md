# Example equipment profiles

These files are starting points for your own profiles. Every equipment name, number, and date in them is
**fictional** — nothing here describes a real scanner or a real measurement. Copy a file and replace the values
with your own data.

- `equipment_profile_example.json` / `.csv` — the same three profiles in both supported shapes, filled in.
- `equipment_profile_template.json` / `.csv` — blank starting points (header/skeleton only).

The CSV is the same content as the JSON, in a different shape: **JSON is nested** (`provenance` is an object,
each coordinate field is a key, `transmission` is a list of row objects), while **tabular is one flat table**
where each row is one record selected by `record_type` (see *Tabular shape* below). A filled CSV and a filled
JSON describe identical profiles.

## What the example demonstrates

| `profile_id` | Shape | What it shows |
|---|---|---|
| `demo-scope-2000` | Coordinates complete, transmission sparse | All 15 coordinate leaves are supplied, so the coordinates need no inheritance. Only three transmission rows are present (80, 100 and 120 kVp on `Single Plane`), so transmission is partially covered. |
| `demo-scope-wildcard` | Coordinates only, partial | A manufacturer-scoped model wildcard (`models: ["*"]`) that supplies only `translation_offset.z`. The remaining coordinate leaves are inherited from the next candidate in the ladder and named in the **partial match** notice before calculation; for a manufacturer with no bundled entry that next candidate is Default. |
| `demo-biplane-rows` | Transmission only, partial | Two transmission rows (Plane A and Plane B at 80 kVp). For this fictional model there is no original lookup table: use custom exact rows, and uncovered queries retain the existing unknown-model handling for the selected transmission mode. |

Partial profiles are intentional: supply what you measured, and the rest is resolved from the next candidate
that supplies it, with a notice naming which fields came from where. A fully supplied custom exact profile
(the `demo-scope-2000` coordinates) needs no inheritance at all, fictional manufacturer and model included —
it does not fall through to Default. Transmission rows for a new model are valid without an original lookup
table. Isolated rows provide exact coverage; interpolation requires a complete usable grid within custom
coverage. Missing custom coverage keeps the original lookup and its mode-dependent fallback. Sparse additions
never create holes in otherwise usable original interpolation. Invalid custom values or out-of-original-extent
rows for an existing model/plane fail validation; uncovered event queries fall back and notify.

## JSON shape

```json
{
  "schema_version": 1,
  "profiles": [
    {
      "profile_id": "demo-scope-2000",
      "manufacturer": "Acme Imaging",
      "models": ["DemoScope 2000"],
      "manufacturer_aliases": ["AcmeImaging"],
      "model_aliases": ["DemoScope2000", "DS2000"],
      "provenance": { "source": "...", "notes": "..." },
      "coordinates": {
        "translation_offset": { "x": 0.0, "y": 0.0, "z": 0.0 },
        "translation_direction": { "x": "+", "y": "+", "z": "+" },
        "rotation_direction": { "Ap1": "+", "Ap2": "+", "Ap3": "+", "At1": "+", "At2": "+", "At3": "+" },
        "swap_lateral_longitudinal": false,
        "field_size_mode": "CFA",
        "detector_side_length": 40
      },
      "transmission": [
        {
          "device_model": "DemoScope 2000",
          "acquisition_plane": "Single Plane",
          "kvp_kv": 80,
          "filtration_added_mmcu": 0.0,
          "filtration_added_mmal": 0,
          "k_patient_support": 0.71,
          "evidence_status": "estimated",
          "source": "...",
          "date": "1901-01-01",
          "comment": ""
        }
      ]
    }
  ]
}
```

`coordinates` and `transmission` are independently optional; a profile needs at least one. Any coordinate field
may be omitted — an omitted leaf is inherited from the next candidate that supplies it (see the ladder in the
plan); a fully supplied profile omits nothing. Unknown fields are rejected.

## Tabular shape

CSV, TSV, and XLSX use **one** flat table (the same rows and columns in every tabular format; XLSX reads the
same table from one sheet, chosen by 0-based index or exact sheet title). Each row is one record, selected by `record_type`:

- `profile` — one row per profile: identity (`manufacturer`, `models`, aliases) and provenance. List values use
  `|` as the separator (`DemoScope2000|DS2000`); an empty list is an empty cell.
- `coordinate` — one row per coordinate leaf, with `field` (dotted path, e.g. `translation_offset.z`,
  `rotation_direction.Ap2`, `swap_lateral_longitudinal`, `field_size_mode`, `detector_side_length`) and `value`.
- `transmission` — one row per transmission row: `device_model`, `acquisition_plane` (`Single Plane` / `Plane A` /
  `Plane B`), `kvp_kv`, `filtration_added_mmcu`, `filtration_added_mmal`, `k_patient_support` (in `(0, 1]`),
  `evidence_status` (`measured` / `estimated`), `source`, `date`, `comment`.

Cells that do not apply to a row's `record_type` are left empty. The same `profile_id` may appear on as many
`coordinate` and `transmission` rows as it has fields and rows — that is how partial profiles are expressed.

### Column dictionary (19 columns)

`record_type` selects which other columns a row reads; every other column is blank on the rows where it does
not apply. Coordinate lengths and sizes are **cm**; `kvp_kv` is **kV**; filtration is **mm Cu** (`mmcu`) or
**mm Al** (`mmal`); `k_patient_support` is dimensionless.

| # | Column | Used by | Maps to | Units / values | Blank means |
|---|---|---|---|---|---|
| 1 | `record_type` | all | — | `profile`, `coordinate`, `transmission` | never blank |
| 2 | `profile_id` | all | `profile_id` | stable identifier, repeated on that profile's rows | never blank |
| 3 | `manufacturer` | `profile` | `manufacturer` | canonical manufacturer string | never blank on a `profile` row |
| 4 | `models` | `profile` | `models` | canonical model keys, `\|`-separated; `*` is the only wildcard and only under an exact manufacturer | never blank on a `profile` row |
| 5 | `manufacturer_aliases` | `profile` | `manufacturer_aliases` | `\|`-separated explicit list; never inherits bundled aliases | no aliases |
| 6 | `model_aliases` | `profile` | `model_aliases` | `\|`-separated shorthand for one exact model; quoted JSON alias-to-model map for multiple models | no aliases |
| 7 | `source` | `profile`, `transmission` | `provenance.source` on a `profile` row; `transmission[].source` on a `transmission` row | bounded free text | missing evidence text (required for `measured`) |
| 8 | `notes` | `profile` | `provenance.notes` | bounded free text, no station/serial/path | no notes |
| 9 | `field` | `coordinate` | dotted coordinate leaf, e.g. `translation_offset.z`, `rotation_direction.Ap2`, `swap_lateral_longitudinal`, `field_size_mode`, `detector_side_length` | one leaf path per row | never blank on a `coordinate` row |
| 10 | `value` | `coordinate` | that leaf's value | cm for `translation_offset.*` and `detector_side_length`; `+`/`-` for direction leaves; `true`/`false` for `swap_lateral_longitudinal`; `CFA` or `ASD` for `field_size_mode` | never blank on a `coordinate` row |
| 11 | `device_model` | `transmission` | `transmission[].device_model` | explicit model name this row applies to | never blank on a `transmission` row |
| 12 | `acquisition_plane` | `transmission` | `transmission[].acquisition_plane` | `Single Plane`, `Plane A`, `Plane B` | never blank on a `transmission` row |
| 13 | `kvp_kv` | `transmission` | `transmission[].kvp_kv` | kV | never blank on a `transmission` row |
| 14 | `filtration_added_mmcu` | `transmission` | `transmission[].filtration_added_mmcu` | mm Cu; use explicit `0` for none | never blank on a `transmission` row |
| 15 | `filtration_added_mmal` | `transmission` | `transmission[].filtration_added_mmal` | mm Al; use explicit `0` for none | never blank on a `transmission` row |
| 16 | `k_patient_support` | `transmission` | `transmission[].k_patient_support` | dimensionless, `(0, 1]` | never blank on a `transmission` row |
| 17 | `evidence_status` | `transmission` | `transmission[].evidence_status` | `measured` or `estimated` | never blank on a `transmission` row |
| 18 | `date` | `transmission` | `transmission[].date` | ISO date `YYYY-MM-DD` | required for `measured` |
| 19 | `comment` | `transmission` | `transmission[].comment` | bounded free text, no station/serial/path | no comment |

The shared `source` column is the one easy mistake: on a `profile` row it is the profile's provenance
(`provenance.source`), on a `transmission` row it is that transmission row's evidence source
(`transmission[].source`). They are different fields with the same column name.

The 19-column examples use the implicit v1 tabular shape. An optional profile-row column
`promote_coordinate_wildcard` accepts `true`/`false` (blank/absent means false). Wildcard
promotion requires explicit acknowledgement through a supporting interface; the current
CLI file flow offers none, so wildcard profiles fail closed there. Promotion never resolves
conflicting custom claimants. Disable one conflicting profile. JSON aliases can be an explicit
alias-to-model object; the existing single-model list remains valid shorthand. Numeric limits,
errors, and canonical hashes are specified in `dev-docs/EQUIPMENT_PROFILE_SCHEMA.md`.

### Blank templates are not loadable

`equipment_profile_template.csv` / `.json` contain the header/skeleton only. They are **invalid until
filled**: an empty `profile_id`, `manufacturer`, `models`, a profile with both domains empty, or a
`transmission` row missing `kvp_kv`/`k_patient_support`/`evidence_status` fails validation with a stable
error naming the row and field. Fill in at least one domain before loading.

## Loading a profile

Coordinate-only files load today; transmission content is rejected wholesale by the
initial coordinate-only capability gate (see below). Available entry points:

- **Python API:** `assemble_session(documents=[...])` / `assemble_session(files=[FileSource(...)])`
  from `guiskindose.equipment_profiles`, bound as `PyskindoseSettings(...,
  equipment_profile_session=session)` before loading raw input.
- **CLI:** `guiskindose --equipment-profile my_profile.json` (repeatable; JSON, CSV, TSV, and
  XLSX accepted; relative paths resolve against the working directory), with optional global
  `--equipment-profile-sheet` (sheet name or 0-based index) for XLSX workbooks. An explicit
  existing store database composes via `--equipment-profile-store` (read-only, never created)
  with optional repeatable `--equipment-profile-id` (current revisions regardless of the enable
  flag; without IDs, all enabled current records apply). Assembly
  failures exit non-zero with a value-free error before any exam input is read. Refused in
  `--mode gui`. A settings file may carry its own sources under an `equipment_profiles`
  block (`files` with `path`/`format`/`sheet`, `store` with `path`/`ids`); relative paths
  resolve against the settings file's directory, and CLI flags compose with the block
  into one candidate assembled once. Save/enable/delete commands, store management, and
  direct constructor wiring are not available from the CLI.
- **Still planned and unimplemented:** GUI import/activation/download and profile-store management commands. See
  [dev-docs/plans/CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md](../../../../dev-docs/plans/CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md)
  for status.

The three filled examples above are each rejected **wholesale** under the initial
coordinate-only gate — no subset is applied from a rejected file. Transmission rows,
model wildcards without promotion acknowledgement, and manufacturer aliases are
all beyond the current activation; write exact, coordinate-only, alias-free files
to load today.
Blank templates remain invalid until filled (see above).

Privacy split: manufacturer and model names are ordinary audit data and may appear in reports and logs.
Station names and serial numbers are site-identifying: they are **never written to logs or diagnostics under any
setting** (counts and event indices only), and they reach output solely as gated fields in per-event exports
through the existing `include_identifiers` opt-in.

The field set above follows the locked schema, resolution, and fallback rules in
`dev-docs/EQUIPMENT_PROFILE_SCHEMA.md` and the run-state contract.

Also note: the JSON, CSV, and XLSX shapes are verified to produce identical profile hashes through the
parser (a workbook built from the CSV parses to the same profiles as the JSON). TSV and XLSX packaged
variants are still outstanding (a tracked `.xlsx` needs hash-pinned human clearance first), and packaging
of this folder into the wheel is not done.
