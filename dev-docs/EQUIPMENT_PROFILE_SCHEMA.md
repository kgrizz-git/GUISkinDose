# Equipment Profile Schema — Common and Coordinate Implementation Contract

Status: **Implementation contract for the common and coordinate domains.** This Markdown is the contract the
code implements, not prose about it: where the code and this document disagree, this document is wrong and must
be corrected. Design authority: [plans/CUSTOM_EQUIPMENT_PROFILES_SPEC.md](plans/CUSTOM_EQUIPMENT_PROFILES_SPEC.md);
execution: [plans/CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md](plans/CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md).

Implemented today: the stdlib-only core package `src/guiskindose/equipment_profiles/` — immutable canonical
models, JSON and in-memory parsing, full-v1 structural validation, canonical serialization and hashes,
across-source duplicate/conflict validation, immutable match-record types, the initial capability gate, the
CSV/TSV/XLSX adapters, and the local user profile store repository.
**No application wiring exists.** Profiles are not applied to any dose, normalization, or GUI path in this slice.

**Not in this contract (later slices, do not assume):** run-state and rich-export schema version bumps and
backward readers; transmission eligibility, grid completion, and inherited-evidence classification (Phase 4);
GUI/CLI wiring; packaging inclusion in `MANIFEST.in`. Full Phase 0 is therefore **not** complete.

## 1. Document envelope

Every source produces one canonical document. The root envelope holds **only** two keys:

| Key | Req. | Type | Rule |
|---|---|---|---|
| `schema_version` | required | integer | Exactly `1`. A JSON boolean is **not** an integer, so `true` is rejected. |
| `profiles` | required | array | Non-empty, bounded (§4), each element an object (§2). |

No other root key exists. `schema_version` is an integer and is never serialized as a float. A missing,
`null`, float, boolean, or non-`1` `schema_version` is `unsupported_schema_version`; a missing, `null`, or non-array `profiles` is `invalid_type`; an empty array is `empty_source`.

### 1.1 Parsing rules that apply at every level

- **Unknown keys are rejected at every level** — envelope, profile, coordinate block, nested axis object,
  transmission row, provenance — with `unknown_field`.
- **Duplicate JSON object keys are rejected.** A parser implementing this must use an `object_pairs_hook` that
  fails on a repeated key rather than the default last-value-wins behaviour.
- **`null` is not omission.** An optional key present with value `null` is a structural error, not an absent
  field: `invalid_type` for a typed leaf where `null` is impossible, `missing_required_field` where a required
  value is needed. Omission means the key is absent.
- **Strict UTF-8, BOM tolerated.** Text is decoded as strict UTF-8; a leading UTF-8 BOM is accepted and stripped.
  Any other encoding is `unsupported_source_encoding`. Invalid UTF-8 and overlong/ill-formed sequences are not
  silently replaced with U+FFFD.
- Nesting is bounded (§4); deeper input is `nesting_limit_exceeded`.

## 2. Profile field model

Every field not listed here is `unknown_field`. `required` means the key must be present and non-empty;
`optional` may be absent (and must then be absent, not `null`). A profile must carry **at least one non-empty
domain** (`coordinates` or `transmission`), else `empty_domain`.

| Field | Req. | Type | Notes |
|---|---|---|---|
| `profile_id` | required | string | Stable user-supplied ID, §4 |
| `manufacturer` | required | string | Non-empty identity, §3 |
| `models` | required | array of string | Non-empty canonical model keys, §3 |
| `manufacturer_aliases` | optional | array of string | §3 |
| `model_aliases` | optional | array of string **or** object | §3 |
| `provenance` | optional | object | `source`, `notes`; both optional strings |
| `coordinates` | optional | object | Six coordinate blocks, §2.1 |
| `transmission` | optional | array of object | Transmission rows, §6 |
| `promote_coordinate_wildcard` | optional | boolean | §3 |

`provenance` carries only `source` and `notes`. Bounded free text, local to the profile. It is included in the
profile hash (§7). There is **no** heuristic that tries to detect station names or serial numbers inside this
text; the guarantee is bounded length plus suppression from `repr` and error messages, not content sniffing.

### 2.1 Coordinate blocks and leaves

`coordinates` holds **six** optional blocks; the 15 leaves they contain are independently optional, so a
nested axis object may supply a subset (`{"translation_offset": {"z": -12.5}}` is valid). A block present but
empty is `empty_coordinate_block`. Unknown block or leaf names are `unknown_field`.

| Block | Type | Leaves | Values / range |
|---|---|---|---|
| `translation_offset` | object | `x`, `y`, `z` — each optional | finite number, cm, `-1000.0 … 1000.0` |
| `translation_direction` | object | `x`, `y`, `z` — each optional | `"+"` or `"-"` |
| `rotation_direction` | object | `Ap1`, `Ap2`, `Ap3`, `At1`, `At2`, `At3` — each optional | `"+"` or `"-"` |
| `swap_lateral_longitudinal` | boolean | — | `true` / `false` |
| `field_size_mode` | string | — | `"CFA"` or `"ASD"` |
| `detector_side_length` | number | — | finite, `> 0`, `≤ 200`; cm; visualization-only, never dose-affecting |

A fully specified coordinate profile supplies all 15 leaves. Numeric leaves must be finite numbers; JSON
`true`/`false` is never accepted where a number is required, and `1`/`0` are never accepted where a boolean is
required — `invalid_number` and `invalid_enum` respectively. NaN and ±Infinity (in any spelling, including
`1e999`) are `invalid_number`.

## 3. Identity, aliases, and wildcards

- Canonical identity is the **normalized** `(manufacturer, model)` pair, using the existing normalization key
  algorithms — casefold, replace every run of characters outside `[0-9a-z]` with one space, strip, and collapse
  whitespace. Profile matching reuses those algorithms and never inherits the bundled hardcoded alias sets.
- `models` is non-empty, holds at most 32 entries, is unique after normalization, and every entry is a non-empty
  string.
- The model wildcard `"*"` is preserved verbatim by the model-key algorithm. It is permitted **only** as the
  sole element of `models`, and only under an exact (non-empty, non-wildcard) `manufacturer`. Otherwise
  `wildcard_not_permitted`. There is no manufacturer wildcard.
- **Aliases.** `manufacturer_aliases` is a plain array of alternative manufacturer spellings. `model_aliases`
  has two accepted shapes:
  - **Explicit map (canonical):** a JSON object whose keys are alias strings and whose values are model
    strings. A target may be written with any spelling that normalizes to a listed model; it is resolved
    through the normalized key and stored as the **listed** spelling, so a map whose target is written with an
    equivalent normalized spelling canonicalizes to exactly the same content as the shorthand array.
  - **Single-model shorthand array:** a non-empty array of alias strings, valid **only** when `models` has
    exactly one non-wildcard element; every alias then maps to that one model.
  - A shorthand array (JSON) is **only** an array. The `|`-separated single-cell form is a *tabular* spelling
    used by CSV/TSV/XLSX adapters; it is not a JSON value form.
  - **An empty array or empty object always means "no aliases"**, for every profile shape. An explicitly empty
    list is not an ambiguity for a multi-model or wildcard profile; it normalizes to absent.
  - A **non-empty** shorthand array with more than one model in `models` is `alias_ambiguous_target`.
  - Every alias value must resolve to a model listed in `models`, else `alias_target_mismatch`.
  - Aliases are unique after normalization **within their own collection**; two aliases normalizing to one key
    are `alias_ambiguous_target`.
  - An alias whose normalized key equals a listed model's normalized key is harmless when it resolves to that
    very model; it is `alias_ambiguous_target` when it resolves to a **different** model, because the two would
    be indistinguishable on lookup.
  - Empty alias arrays and empty alias objects normalize to *absent*: they are omitted from canonical
    serialization and add nothing to the profile hash.
- Aliases never silently inherit bundled alias sets, and an alias may repeat the exact spelling of the
  manufacturer it aliases (the packaged example does this) — that is not an ambiguity.
- `promote_coordinate_wildcard` is valid only when `models` is `["*"]`.
- **Model keys.** Only the exact spelling `"*"` (surrounding whitespace tolerated, then canonicalized to `"*"`)
  is the model wildcard. A model whose normalized key is empty — `"!!!"`, `"   "`, `"-"` — is
  `invalid_model_list`. `" * "` is therefore handled *as the wildcard*, consistently with `"*"`: usable only as
  the sole element, never stored as a literal model name.

## 4. Bounds

These are ingestion sanity bounds, not physics limits. All are enforced before any profile is used.

| Bound | Value |
|---|---|
| Source file bytes (`.json`, `.csv`, `.tsv`, `.xlsx`) | 8,388,608 (8 MiB) |
| Aggregate logical rows across all sources in one load | 10,000 |
| Logical row definition | JSON/memory: `len(profiles) + total coordinate leaves + total transmission rows` |
| Profiles per document / per load | 64 |
| Models per profile | 32 |
| Coordinate leaves per profile | 15 (one per allowed leaf) |
| Transmission rows per profile | 2,000 |
| `manufacturer_aliases` / `model_aliases` entries | 16 each |
| JSON nesting depth | 16 |
| Traversal node budget (depth check) | 250,000 |
| XLSX sheets selected | 16 |
| XLSX preflight (before the aggregate ceiling) | 32 MiB per member, 64 MiB inflated total, 100,000 rows, 512 columns, 2,000,000 cells |
| `profile_id`, `manufacturer`, model keys, alias values | 64 characters each |
| `source` | 200 characters |
| `notes`, `comment` | 500 characters each |

`profile_id` must match `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` and is compared exactly (no case folding) —
`invalid_profile_id` otherwise.

### 4.1 How the bounds are applied

Bounds are applied cheapest-first so a hostile document cannot force exhaustive work before it is rejected.

1. **Bounded read.** A file is read with one read of at most `MAX_SOURCE_BYTES + 1` bytes, so an oversized
   source is rejected from the read length itself. The file is not stat-ed first, so a file that grows between
   a size check and a read cannot slip past the bound.
2. **Early count checks.** Before any structure traversal, the envelope's `profiles` list length is checked
   against `MAX_PROFILES`, and the already-known aggregate row total (profile count plus each profile object's
   coordinate-leaf and transmission-row children) is checked against `MAX_AGGREGATE_ROWS`.
3. **Bounded traversal.** The depth check runs over an explicit stack with a depth bound (`MAX_JSON_DEPTH`) and
   a node budget (`MAX_TRAVERSAL_NODES`), so a deep or very broad in-memory structure is rejected rather than
   walked. The budget is derived from the document shape: one document holds at most `MAX_AGGREGATE_ROWS`
   logical rows, each with a bounded number of keys, so any valid document is far below it.
4. **Per-document aggregate.** Every document enforces the aggregate logical-row ceiling itself, not only the
   multi-document combination, so a single oversized document is rejected where it is read.

## 5. Coordinate activation capability gate

The **canonical parser represents the full v1 schema**, including capability fields it cannot yet apply.
**Activation checks capabilities separately** and fails closed. The initial gate rejects every one of these
with `unsupported_profile_capability`:

- any manufacturer alias (list);
- any model alias (array shorthand **or** explicit map);
- any model wildcard, and `promote_coordinate_wildcard`;
- any non-empty `transmission` domain.

Enabled in the initial gate: exact `manufacturer`/`model` coordinate identity and leaf-level inheritance within
that exact match. A capability that cannot be applied is never silently dropped and never partially applied —
the check runs before any profile is recorded as active.

Promotion of a custom wildcard above a bundled exact requires `promote_coordinate_wildcard: true` **plus** GUI
acknowledgement or CLI `--allow-equipment-profile-wildcard-promotion`; missing acknowledgement is
`promotion_not_acknowledged`. Promotion never outranks a custom exact. That path is specified here but is not
reachable while the gate above rejects wildcards.

## 6. Transmission rows (key and shape only)

`device_model` must target a model listed **exactly** in `models`, else `alias_target_mismatch`. The model
wildcard is never a valid target: a row naming `"*"` is rejected even on a wildcard profile. The acquisition
plane is literal: `"Single Plane"`, `"Plane A"`, or `"Plane B"`. Every required row field must be present;
absence is `missing_required_field` with the row's own field path (never a `KeyError`). Matching key is
unchanged: **exact target model + literal plane + kVp + Cu + Al**. Manufacturer is provenance, never a join
column.

| Field | Req. | Type | Range |
|---|---|---|---|
| `device_model` | required | string | must equal a listed model |
| `acquisition_plane` | required | string | the three literals above |
| `kvp_kv` | required | number | finite, `> 0`, `≤ 200` |
| `filtration_added_mmcu` | required | number | finite, `≥ 0`, `≤ 100` |
| `filtration_added_mmal` | required | number | finite, `≥ 0`, `≤ 1000` |
| `k_patient_support` | required | number | finite, `(0, 1]` |
| `evidence_status` | required | string | `"measured"` or `"estimated"` |
| `source` | required when `measured` | string | bounded |
| `date` | required when `measured` | string | strict valid `YYYY-MM-DD` |
| `comment` | optional | string | bounded |

Filtration must be an **explicit finite non-negative number**; `0` means no added filtration. A blank
filtration cell is `blank_disallowed_cell` — it is not read as zero. Dates are strict: `2026-02-30` is
`invalid_date`, not a rounded value.

Overlay precedence, evidence ownership, grid eligibility, and fallback are **already agreed** in spec §7 and are
not redefined here.

## 6A. Flat tabular shape (CSV / TSV)

Tabular sources are one flat table holding exactly the 19 columns of the packaged example, in any order,
optionally plus `promote_coordinate_wildcard`. The authoritative field dictionary — column names, applicability,
units, and blank meaning — is the packaged `src/guiskindose/example_data/equipment_profiles/README.md`, which is
identical for every tabular format. This section restates only the rules the parser enforces, so it never
disagrees with the README. The shape is **implicit v1**: there is no version column, and an adapter emits
`schema_version: 1`.

`record_type` selects which columns a row may use (both apply to every row regardless of `record_type`):

| `record_type` | May use |
|---|---|
| `profile` | `profile_id`, `manufacturer`, `models`, `manufacturer_aliases`, `model_aliases`, `source`, `notes`, `promote_coordinate_wildcard` |
| `coordinate` | `profile_id`, `field`, `value` |
| `transmission` | `profile_id`, `source`, `device_model`, `acquisition_plane`, `kvp_kv`, `filtration_added_mmcu`, `filtration_added_mmal`, `k_patient_support`, `evidence_status`, `date`, `comment` |

A value in any other column for that row's `record_type` is `unknown_field` naming only that column.

**Header rules.** Exactly the 19 columns, optionally plus the promotion column. Duplicate column names are
`duplicate_json_key` and unknown names are `unknown_field`; **neither echoes the offending column name** — the
error carries the column index as its count. Missing columns are `missing_required_field`. Column order is free.

**Row rules.** Every row must have exactly `len(header)` cells, else `malformed_tabular`. Unknown `record_type`
values are `unknown_field` and never echo the value.

**Blank semantics.** A blank cell means *omitted* for an optional field. A blank cell in a column required by the
row's `record_type` is `blank_required_cell`. Filtration is the explicit exception: a blank
`filtration_added_mmcu` or `filtration_added_mmal` is `blank_disallowed_cell` — use an explicit `0`. A blank
`source`, `notes`, or `comment` is omitted text, so a `measured` row with a blank `source` is
`missing_required_field` rather than a blank-cell error.

**Shared `source` column.** On a `profile` row it is `provenance.source`; on a `transmission` row it is that
row's evidence `source`. They are different fields with the same column name.

**Cell lexical forms.** Numeric cells must parse to a finite double: `NaN`, `Infinity`, `1e999`, and underscored
forms such as `8_0` are `invalid_number`, and a boolean is never a number. Boolean cells accept only the exact
forms `true` and `false`. Sign cells accept only `+` and `-`. A null-like string (`null`, `None`) is literal
text, not omission. List cells use `|` as the separator; a `model_aliases` cell whose first non-space character
is `{` must be a properly quoted JSON object, rejected as `malformed_tabular` if it does not parse and
`duplicate_json_key` if it repeats a key. Pipes never appear inside a JSON map cell.

**Grouping.** Rows are grouped by `profile_id`; rows may appear in any order, so a group's `profile` row may
follow its `coordinate` and `transmission` rows. A group with no `profile` row at all is an orphan and fails
`missing_required_field`. Repeated `profile` rows for one `profile_id` may agree; disagreement is
`conflicting_profile_metadata`. A repeated coordinate leaf fails `duplicate_json_key` even when identical —
there is no last-write-wins. A repeated transmission key fails through the canonical cross-profile check, even
when identical.

**Source equivalence.** A tabular document is assembled into the same canonical document mapping the JSON
adapter produces, so a filled CSV/TSV and the equivalent JSON have identical profile hashes, leaf values, and
transmission values, while their raw source hashes differ. The source kind on every adapter failure is `csv` or
`tsv`, never `json`.

**Bounds.** Bounded read of `MAX_SOURCE_BYTES + 1` bytes in one call (no stat-then-read race); strict UTF-8 with
an optional BOM and no unpaired surrogates; SHA-256 over the exact bytes read, before decoding. The aggregate
logical-row ceiling (a tabular row is exactly one logical row) is enforced **while accumulating rows, before any
profile object is built**, and the profile-count ceiling is enforced when a new group appears.

Adapters use only the standard library for JSON, CSV, and TSV — no third-party reader and no DataFrame
materialization — and read the decoded byte snapshot once. The XLSX adapter is the sole exception, and it
confines its spreadsheet dependency to itself; see §6B.

## 6B. XLSX (OOXML) adapter

XLSX is the same flat table on one sheet. All §6A rules apply unchanged, and the canonical document is
assembled by the same seam, so a workbook and the equivalent CSV have identical profile hashes, leaf values,
and transmission values while their raw source hashes differ. This section covers only what differs.

**Dependency containment.** openpyxl is imported *inside* the functions that need it, so a caller that parses
only JSON, CSV, or TSV never imports the spreadsheet stack. The workbook is opened with `read_only=True`,
`data_only=False`, `keep_links=False`, and nothing is ever extracted to the filesystem.

**Sheet selection.**

| Workbooks | Selection |
|---|---|
| exactly 1 | sheet `0` is the default; an explicit `sheet=0` is also accepted |
| 2 or more | `sheet=None` selects the first worksheet; an explicit index or exact title selects another |
| out of range, negative, non-integer, unknown or ambiguous title | `unknown_sheet` |

More than 16 worksheets is `sheet_limit_exceeded`: standard worksheet-part
counts are bounded before the reader opens, and the actual reader catalog is bounded
before title traversal or worksheet row iteration. Sheet **titles resolve against the opened
workbook's own catalog on the same bounded bytes used for hashing and parsing**
— exact match only; a title held by more than one worksheet fails closed as
ambiguous. Titles are transient and never retained: only the resolved zero-based
index flows on, and no title ever appears in an error.

**Typed cell policy.**

| Cell | Rule |
|---|---|
| number | preserved as a number; an unquoted `true`/`false` is *not* read as the boolean `TRUE` |
| boolean | accepted only where the schema expects a boolean, normalized once to the exact lexical forms `true`/`false`; a boolean is **never** coerced into `1` for a numeric column |
| date / datetime | valid **only** in the `date` column; must be exactly midnight of one day, and renders as strict ISO `YYYY-MM-DD`. A date object in any other column is `invalid_date_object`, not a silently stringified value; a time or offset makes it `invalid_date_object` |
| formula (`data_type='f'`) | `unsafe_formula` — never read as its cached value, and no formula is evaluated |
| spreadsheet error (`data_type='e'`) | `spreadsheet_error` |
| string | bounded text, preserved intact; a formula-*looking* string is legitimate text and is not evaluated |
| blank / `None` | an omitted cell; blank filtration is still `blank_disallowed_cell` |

A number or a boolean is accepted **only** in a column whose schema type is that type: `kvp_kv`,
`filtration_added_mmcu`, `filtration_added_mmal`, `k_patient_support` (and a coordinate `value` whose leaf is
numeric), and `promote_coordinate_wildcard` plus the `swap_lateral_longitudinal` coordinate leaf. A number or a
boolean in an identity or free-text column is a `invalid_type` (an `invalid_number` in a numeric column for a
boolean) and is never coerced into a string or into `1`. The `value` column's type comes from the row's
`field` and is resolved per leaf, so a number, boolean, and date are each accepted or rejected by the leaf they
address. Header cell names must be strings.

A null-like string (`null`, `None`) is literal text, never omission.

**Header rules.** Header cell names must be strings. openpyxl's read-only parser pads every row to the widest
row, so trailing blank header cells are padding, not column names, and are dropped; a blank header cell
*inside* the header is kept and rejected as an unknown column name.

**Bounds, applied cheap-first.**

| Bound | Value |
|---|---|
| Compressed source bytes | 8,388,608 (8 MiB) |
| Any single decompressed ZIP member | 33,554,432 (32 MiB) |
| Sum of all decompressed members | 67,108,864 (64 MiB) |
| Worksheets offered | 16 |
| Worksheet preflight rows / columns / cells | 100,000 / 512 / 2,000,000 |
| Aggregate logical rows of actual profile data | 10,000 |
| Archive entries accepted at all | 80 |

The archive is opened from the in-memory byte snapshot and preflighted **before** any worksheet is read.
Declared central-directory sizes are used only as a cheap early reject; every member is then inflated by
*streaming real decompressed bytes* in chunks and counting them, so a forged `file_size` cannot smuggle a zip
bomb. Worksheets offered is bounded against the workbook's own catalog.

**Archive hygiene.** Duplicate entry names and directory-spoofing names are `malformed_container`; the entry
list is bounded. Non-ZIP bytes, corrupt members, and any structural failure are `malformed_container` with the
raw cause suppressed.

**Bounds are validated before materialization, and no silent truncation is possible.** Every worksheet part
is parsed with a bounded streaming XML parser that never builds a tree. It ignores the declared `<dimension>`
for sizing and enforces the row, column, and cell budgets on the coordinates actually present, rejecting
out-of-range, repeated, and malformed coordinates as `malformed_container`. Declared sizes, DTDs, entity
declarations, and external entity references are refused, and any parse failure fails closed with a value-free
error and a suppressed cause. Because the actual bounds are known before the reader runs, the adapter discards
the reader's own dimension (`reset_dimensions()`) and iterates the real rows: a workbook that **understates**
its content is read in full, and a workbook that **overstates** it can never allocate padding it does not
hold. The budgets are then re-enforced on the reader's real iteration before any row is converted. Sheet
counts come from the workbook's own worksheet catalog, bounded by the sheet ceiling, and never from archive
part filenames, so nonstandard part naming cannot desynchronize a sheet index.

**Closed error catalog for this adapter.** `malformed_container`, `inflation_limit_exceeded`,
`unsafe_formula`, `spreadsheet_error`, `invalid_date_object`, `sheet_required`, `unknown_sheet`,
`sheet_limit_exceeded` — plus the shared codes. Every one carries source kind `xlsx`; none carries a sheet
name, a path, a cell value, or a library message.

**Outstanding.** A packaged XLSX example and template are **not** shipped. A tracked `.xlsx` binary needs
hash-pinned human clearance in `dev-docs/approved_asset_inventory.json` before it may be committed, and no such
clearance has been added. The CSV and JSON examples remain the reference starting material, and the TSV variant
remains ungenerated.

## 7. Canonical serialization and hashes

Canonical form is UTF-8 JSON with recursively sorted keys, compact separators, and no insignificant whitespace.

- **Numeric normalization.** Numeric *value* fields (`translation_offset.*`, `detector_side_length`, `kvp_kv`,
  `filtration_added_*`, `k_patient_support`) are normalized to IEEE-754 doubles and serialized as floats, so
  `40`, `40.0`, and `4.0e1` all canonicalize to `40.0` and a tabular `40` and a JSON `40` hash identically.
  Negative zero normalizes to `+0.0`. `schema_version` stays an integer. Any value that does not fit a finite
  double — a JSON integer with hundreds of digits — is `invalid_number`, not an `OverflowError`.
- **Omission.** Empty optional texts, empty alias arrays/objects, empty coordinate blocks, an empty
  `transmission` array, and `promote_coordinate_wildcard: false` are all **omitted** from canonical
  serialization. They add nothing to a hash.
- **Model-alias map form.** The canonical `model_aliases` form is a **JSON object** `{alias: target_model}`,
  the same shape the parser accepts for an explicit map, so canonical output round-trips through the parser
  to an identical profile hash. The target is always the listed model spelling, so a map and the shorthand
  array for the same alias produce identical canonical content.
- **Profile hash.** SHA-256 over the canonical JSON bytes of the wrapper `{"schema_version": 1, "profile": …}`.
- **Active-set hash.** SHA-256 over the canonical JSON bytes of the wrapper
  `{"schema_version": 1, "profiles": […]}`, profiles ordered by exact `profile_id`.
- **Source hashes.** A file source contributes a SHA-256 of the exact bytes read, before decoding. An
  in-memory or GUI entry has no source bytes and contributes none.
- **Provenance vs source context.** The profile hash covers profile *content*, including `provenance`. It never
  covers source context — source kind, file, source hash, store revision — or any per-leaf provenance. The same
  profile loaded from a JSON file and built in memory has the same profile hash and different source context.
- **Stored selected-revision-set hash (locked).** The revision-set hash is SHA-256 over the canonical bytes of
  `{"schema_version": 1, "store_schema_version": 1, "store_id": …, "records": [{profile_id, revision,
  profile_hash} …]}` with records ordered by exact `profile_id` (§12). It covers the store schema version, the
  opaque store ID, and the selected records — never filenames, paths, timestamps, or enablement.

## 8. Cross-profile conflicts

- Two **logical profiles** (distinct profile objects, from any sources, even with byte-identical content) that
  share a `profile_id` → `duplicate_profile_id`.
- Two enabled profiles claiming the **same normalized coordinate identity** → `duplicate_coordinate_claim`,
  even when the claimed content is identical. The user disables one claimant; v1 has no conflict-override
  syntax.
  - Only a profile with **non-empty coordinate content** claims a coordinate slot. A transmission-only profile
    claims no coordinate slot, so it may share an identity with a coordinate-only profile safely.
  - A claim spans every canonical and alias spelling of both axes: the canonical manufacturer **plus every
    manufacturer alias**, and every listed model **plus every mapped model alias**.
  - An alias key that resolves to a *different* model than a listed model with the same normalized key is
    already rejected at validation (§3), so it can never become a claim here.
- Two transmission rows with the **same key** → `duplicate_transmission_key`, **within a single profile and
  across profiles**, independent of manufacturer. The model component of the key is the *normalized* model
  key, so duplicates are detected regardless of case or punctuation.
- Repeated profile metadata for one `profile_id` inside a single **tabular grouping** may agree; a tabular
  grouping that disagrees with itself is `conflicting_profile_metadata`. That rule is a tabular-adapter rule
  and does not license the JSON duplicates above.
- File order never breaks ties. Input order may affect only deterministic diagnostics and serialization.

## 9. Match records (immutable, per exam)

Per-exam match records are immutable snapshots, never mutable `NormalizationSettings` fields. Coordinate domain:

```json
{
  "domain": "coordinate",
  "profile_id": "demo-partial",
  "source": "custom",
  "level": "exact",
  "source_kind": "json",
  "revision": null,
  "profile_hash": "<sha256>",
  "matched_input_key": { "manufacturer": "acme imaging", "model": "demoscope 2000" },
  "affected_event_count": 12,
  "fields": [
    {
      "field": "translation_offset.x",
      "value": 0.0,
      "source": "custom",
      "level": "exact",
      "profile_id": "demo-partial",
      "source_kind": "json",
      "revision": null,
      "profile_hash": "<sha256>",
      "inherited": false
    },
    {
      "field": "rotation_direction.Ap2",
      "value": "+",
      "source": "bundled",
      "level": "exact",
      "profile_id": "bundled-siemens-axiom-artis",
      "source_kind": "json",
      "revision": null,
      "profile_hash": "<sha256>",
      "inherited": true
    }
  ]
}
```

- `source` is `custom` / `bundled` / `default`; `level` is `exact` / `wildcard` / `default`.
- `source_kind` is `json`, `memory`, `csv`, `tsv`, `xlsx`, `gui`, or `store`. All but `gui` are
  implemented; `gui` is reserved for its adapter.
- `inherited` is `true` for any leaf whose value comes from a candidate other than the selected **custom
  coordinate profile** — including a lower-priority custom wildcard. It is `false` only for leaves the selected
  custom exact profile supplied itself.
- The illustrative ID above is a partially supplied profile. A complete example cannot legitimately claim a
  bundled inherited leaf, so a fully supplied profile has `inherited: false` on every leaf and no partial
  notice.
- Every leaf present in the effective profile appears exactly once in `fields`. `matched_input_key` uses
  canonical normalized keys, never raw user spellings. A fully specified profile yields `complete match`.

## 10. Errors

Errors are bounded and value-free. An error carries a stable `code`, a `source_kind`, an optional row/sheet
index, a **field path built only from allowlisted names**, and an optional count. **No raw user value, unknown
user key, file path, note, station name, or serial number appears in an error, and an unknown key is never
echoed back** — a field path names the closest allowlisted parent (for example `coordinates.translation_offset`),
not the offending key. Raw exception causes are suppressed (`raise ... from None`) so no library text leaks. The
error object's `repr` is value-free.

Codes: `unsupported_source_suffix`, `unsupported_source_encoding`, `unreadable_source`, `empty_source`,
`oversized_source`, `row_limit_exceeded`, `profile_limit_exceeded`, `model_limit_exceeded`, `alias_limit_exceeded`,
`nesting_limit_exceeded`, `malformed_json`, `malformed_tabular`,
`malformed_container`, `inflation_limit_exceeded`, `unsafe_formula`, `spreadsheet_error`,
`invalid_date_object`, `unknown_sheet`, `sheet_limit_exceeded`,
`unsupported_schema_version`, `unknown_field`, `duplicate_json_key`, `invalid_type`, `missing_required_field`,
`blank_required_cell`, `blank_disallowed_cell`, `empty_domain`, `empty_coordinate_block`, `invalid_profile_id`,
`invalid_manufacturer`, `invalid_model_list`, `alias_ambiguous_target`, `alias_target_mismatch`,
`wildcard_not_permitted`, `promotion_not_acknowledged`, `invalid_number`, `invalid_enum`, `invalid_date`,
`value_out_of_range`, `duplicate_profile_id`, `duplicate_coordinate_claim`, `duplicate_transmission_key`,
`conflicting_profile_metadata`, `conflicting_profile_claim`, `unsupported_profile_capability`,
`store_conflict`, `store_corruption`, `unsupported_store_version`, `store_not_found`, `store_unavailable`,
`store_limit_exceeded`.

`unreadable_source` covers a file that cannot be read at all (missing, a directory, or any I/O failure). A path
is never included in the error, so the failure is indistinguishable by path and only distinguishable by code.

`unreadable_source` covers a file that cannot be read at all (missing, a directory, or any I/O failure). A path
is never included in the error, so the failure is indistinguishable by path and only distinguishable by code.

Strings must be encodable as strict UTF-8; escaped unpaired surrogates are rejected with
`unsupported_source_encoding`. Measured source text must contain non-whitespace content. Traversal bounds
limit both visited nodes and queued children, so a broad in-memory container cannot grow an unbounded stack.
`unknown_sheet` and `sheet_limit_exceeded` belong to the XLSX adapter (§6B) and never name a
sheet; `malformed_container`, `inflation_limit_exceeded`, `unsafe_formula`, `spreadsheet_error`, and
`invalid_date_object` likewise carry only a source kind, an allowlisted column or `record_type`, an index, and
a count.

Four further codes are **reserved for later slices and must not be reported as implemented**:
`sheet_required` (future interfaces that require an explicit sheet selection; the file adapter never raises
it), `existing_model_out_of_extent` (transmission bounds), and `explicit_sqlite_collision`
(explicit `corrections_db_path` coexistence). `store_corruption` was reserved for the user store and is now
raised by the store repository (§12).

## 11. Packaged examples

The packaged example is **verified against the real adapters**: the CSV reads to the same profile hashes as the
JSON, and an in-memory workbook built from that CSV reads to the same hashes again. Three profiles, 16
coordinate leaves, and 5 transmission rows in every format; the two alias fields on `demo-scope-2000` are
accepted shorthand arrays (JSON) or `|`-separated shorthand (tabular), `demo-scope-wildcard` supplies one
nested leaf, and `demo-scope-biplane-rows` supplies two transmission rows.

The packaged README is the **authoritative field dictionary** for the flat formats: column names, applicability,
units, and blank meaning. Outstanding for later slices: the packaged TSV and XLSX variants (an XLSX binary needs
hash-pinned human clearance in `dev-docs/approved_asset_inventory.json` before it may be committed, and no such
clearance has been added), `MANIFEST.in` inclusion, and the wheel proof.

Worksheet XML preflight resolves namespaces and declared worksheet parts from OOXML content types; every
reader-selected part must have passed preflight. Row coordinates must increase and stay within the row budget;
cell coordinates must increase within, and belong to, their containing row. Reader-emitted padding also counts
toward row/column/cell budgets. Text numeric and boolean cells use the same lexical rules as CSV/TSV; spreadsheet
number and boolean objects remain restricted to their respective field types. Non-empty whitespace beyond the
header is an unknown column value, not blank padding.

The first-sheet default follows spec §4. `sheet_required` is reserved for future interfaces that require
an explicit selection; the file adapter does not raise it.

## 12. Local user profile store

The store is a **separate, user-owned SQLite database** (spec decisions 5 and 17): never `corrections_db_path`,
never bundled package data, never a migration target for anything else. Implemented by the stdlib-`sqlite3`
`src/guiskindose/equipment_profiles/profile_store.py` repository with `store_reads.py`/`store_writes.py`
operation modules, the `store_schema.py` schema contract, and the `store_types.py` immutable types. No
application, GUI, CLI, normalization, or dose-path wiring reads it in this slice.

**Identity and location.** The default path is computed purely as
`Path.home() / ".guiskindose" / "equipment_profiles.sqlite3"` — the same configuration area as
`gui/window_prefs.py` — with no `mkdir`, no read, and no platform branch; computing it never touches the
filesystem. Initialization and access are explicit, and tests use `tmp_path` only.

**Schema and versions.** `store_schema_version` is `1`, written to both `PRAGMA user_version` and
`store_meta.store_schema_version`; the canonical profile schema stays `1`. Tables (verified exactly —
names, column names and types, primary keys, the revision foreign key, and the absence of triggers and
views): `store_meta(key, value)`, `profile_records(profile_id, enabled, current_revision, generation,
updated_utc)`, `profile_revisions(profile_id, revision, payload_json, profile_hash, logical_rows,
created_utc)`, and `profile_tombstones(profile_id, generation, next_revision)`. Only a fresh empty database
is created, at version 1. An unknown nonempty unversioned database, a future version, or a corrupt schema is
rejected with a value-free error **without mutating the file**. Future versions need a real migration later;
none is pretended here.

**Revisions and metadata.** `store_id` is a random opaque 32-hex identifier recorded once at initialization.
Revisions are immutable: each stores the canonical profile JSON payload, its content `profile_hash`, a
positive integer revision, a stored row count, and a UTC timestamp, with a per-record current-revision
pointer, a monotonically bumped `generation` token, and an enabled flag. Timestamps and enablement are audit
data, never hashed. No origin filename, path, station name, or serial number is stored. Bounded
`provenance.source`/`notes` are retained privately inside the payload but are never logged, errored, or
exported by default.

**API and transactions.** Explicit `initialize()`; `save_new_revision` (strictly type-checked and round-trip
validated, so no hand-built `Profile` is trusted; a brand-new record starts disabled); `read_revision`
(current by default); bounded `list_records`; `set_enabled`/`delete_record` with optimistic revision *and*
generation expectations; and `selected_snapshot`, which loads in **one** read transaction before any mutable
data escapes. Every write runs in `BEGIN IMMEDIATE` and rolls back on *any* failure — including unexpected
ones, which additionally close the handle safely — while reads use a plain `BEGIN` so they never take the
writer lock. A nested or leaked transaction is refused rather than stacked onto. Schema, foreign keys, and
growth caps are re-verified inside every transaction, so external tampering after initialization fails closed
on the next operation.

**Explicit revision-CAS contract.** Creating a record expects absence (a supplied expectation conflicts);
updating an existing record **requires** `expected_current_revision`, so an accidental omission cannot
overwrite newer content. Enable and delete honor an optional content-revision expectation **and** an optional
`expected_generation` — an omitted expectation is unconditional caller-controlled behaviour, and GUI layers
must always pass one. Content CAS alone cannot see metadata-only races, so every mutation also bumps
`generation`, a deleted ID leaves a tombstone continuing both generation and revision numbering, and
recreating an ID can never silently reuse a revision number (no ABA reuse). The total tracked identities
(live records plus tombstones) are bounded at 1024; creating past it fails closed while deleting never does.
`generation` is exposed on every record for a future metadata compare-and-swap; the current contract does
not claim enable-race protection beyond content CAS.

**Conflicts.** Saving a candidate with unsupported capabilities persists it but never activates or applies
it. Enabling runs the canonical conflict check across the would-be enabled set atomically (bounded to 64
profiles and 10,000 stored rows before any payload loads), so no ambiguous enabled custom claim can result.
An empty enabled store yields a valid empty snapshot (the empty-document parser is never misused for this).

**Source hash (locked).** The revision-set hash is SHA-256 over the canonical bytes of
`{"schema_version": 1, "store_schema_version": 1, "store_id": …, "records": [{profile_id, revision,
profile_hash} …]}` with records ordered by exact `profile_id`. The content `profile_hash` excludes the store
ID, revision, timestamps, and enablement. A snapshot exposes `source_kind: "store"`, that source hash, and the
selected revisions for later activation — never a filename or path.

**Bounds, checked before querying or materializing.** At most 64 unique selected IDs (duplicates rejected, IDs
pattern-checked); at most 10,000 aggregate logical rows (summed from stored per-revision counts before
payloads are read, rechecked after parsing); 8 MiB per revision payload (length and storage type queried
before the text is fetched); 256 records and 64 revisions per profile; listing capped at 64 with validated
offsets; caller integers range-checked to SQLite's 64-bit limits before binding; global growth caps
re-verified on reads. All SQL is parameterized. Every `sqlite3` failure collapses to a stable value-free
`store_*` code (`store_conflict`, `store_corruption`, `unsupported_store_version`, `store_not_found`,
`store_unavailable`, `store_limit_exceeded`) with the raw cause suppressed and `source_kind: "store"` on
every failure.

**Read-only factory lock.** `ProfileStore.open_read_only(path)` opens an explicit existing database
without creating the main database, schema, parent directories, journals, or migrations: the path escapes into a `mode=ro`
URI (spaces, unicode, `#`, `?` cannot break parsing), the connection sets `query_only = ON` as a
second safeguard, and empty/unversioned/foreign/corrupt/future databases fail closed (missing or
unopenable is `store_unavailable`; empty or unversioned content is `store_corruption`; future versions
stay `unsupported_store_version`). A read-only handle refuses `initialize()` before any filesystem
access and refuses writes before any statement runs, so no write lock is ever attempted; the
read-only flag survives `close()`. Version and schema validate through the existing verify path
before any payload, with per-transaction re-verification unchanged; every mutation attempt through
the handle fails coded and the handle closes on all failure paths. Committed content — including
WAL-committed rows — reads normally (`immutable=1` is deliberately unused: it would ignore the
WAL and read stale content). Auxiliary effects such as `-shm`/`-wal` handling follow SQLite and
platform behavior and are not claimed absent. No schema redesign or version bump in this
slice.

## 13. Compiled lookup indexes

Indexes are compiled once from validated profiles and answer per-event lookups without scanning profiles.
They perform no matching precedence, inheritance, interpolation, overlay, or evidence eligibility, and they
change nothing about the initial activation gate (§5).

**Inputs.** Each entry carries a `Profile` plus its source context: `source_kind`, an optional store
`revision`, and the claimed canonical `profile_hash`. Nothing is trusted on construction. The input must be a
real sequence: strings, bytes, and one-shot iterables fail `invalid_type`, a declared length above
`MAX_PROFILES` (64) fails `profile_limit_exceeded` before anything is copied, and materialization re-checks
the cap item by item so a lying length cannot force unbounded work.

**Entry context is strictly checked.** `source_kind` must be exactly `str` and a member of the §9 vocabulary
— a subclass, or any object with a permissive equality, fails `invalid_enum`. `revision` must be exactly
`int` (booleans rejected) in `1..2**63-1`, or `value_out_of_range`. `profile_hash` must be 64 lowercase hex
characters, or `invalid_type`.

**Hand-built profiles are re-validated through the existing boundary.** Nested fields must be the exact
immutable types (tuples, never lists; exact `bool`, never `1`), numbers must be finite non-boolean values
that survive `float()` (a huge integer fails `invalid_number` in the pre-check, never raw text from the
serializer), and the canonical mapping is then run through the full document validator — so an unresolvable
alias target, a bad enum, or an out-of-range value fails with its usual code. The recompiled canonical hash
must equal the claimed `profile_hash`, or compilation fails `conflicting_profile_metadata`. Re-parsing is
compile-time validation only; nothing is activated. The aggregate logical-row ceiling (`MAX_AGGREGATE_ROWS`)
is enforced on the recompiled profiles before any claim is expanded. Global conflicts then run through the
canonical §8 check *before* anything is published — profiles are ordered by exact `profile_id` first — so
duplicate IDs, coordinate claims (including alias and wildcard collisions), and transmission keys all fail
closed with their stable codes.

**Coordinates.** Compiled by canonical manufacturer/model key. Every claim the schema allows is stored —
exact slots, explicit alias spellings (marked `via_alias`, except an alias spelling identical to its
canonical target), and manufacturer-scoped `"*"` model wildcards (marked `is_wildcard`) — with the declared
`promote_coordinate_wildcard` flag recorded but never applied. No built-in vendor aliases are consulted for
user claims. Retrieval normalizes keys on entry and bisects the sorted slot table, so cost is logarithmic
in slots, never linear in profiles. A transmission-only profile claims no slot and coexists disjointly.

**Transmission.** Compiled by canonical model key plus the *literal* acquisition plane (never normalized),
with each plane's nodes ordered by their original `(kVp, Cu, Al)` numeric key. Retrieval normalizes the
model on entry, compares the plane exactly, and returns the node group (possibly empty) without scanning.

**Invariants.** Storage is tuples only — no mutable mappings are exposed. Successful compilation is
identical for every source order (full compiled equality holds for all permutations); only a conflict
diagnostic's `source_kind` follows the lead (first) entry, per the existing conflict semantics. Retrieval
bisects the sorted key tables, so a per-event lookup resolves with no profiles attached. All failures are
value-free, and every public repr shows only counts, source-kind tokens, flags, and content hashes — never
identifiers, model text, provenance, or row content.

## 14. Custom-exact coordinate resolution (initial slice)

Resolution answers one homogeneous exam with all 15 coordinate leaves over the ladder custom exact →
bundled exact → bundled manufacturer-scoped wildcard → Default. Later slices extend the ladder with
custom wildcards, promotion, and transmission; this slice resolves custom exact matches with
inheritance. Nothing here applies a profile to a calculation.

**Inputs.** An exam identity (raw maker/model spellings plus the fixed per-exam event count), a
compiled custom index, and a compiled bundled set (exact/wildcard index plus the separate Default
entry). Both compiled inputs are validated once up front — entry context (exact types, hash shape),
structural shape (exact immutable containers, canonical leaf value types), recomputed content hashes
(`conflicting_profile_metadata` on mismatch), and claim tables (parallel tuple keys/claims, every
claim referencing a prepared entry, otherwise `invalid_type`) — so hand-built or corrupted inputs
fail closed instead of raising raw errors at lookup time; nothing is re-checked per leaf. Malformed
identities and inputs fail `invalid_type`; a negative event count fails `value_out_of_range`. Blank,
`None`, and `"nan"`/`"nat"`/`"none"` identity artifacts of any case all mean missing identity (shared
stdlib convention in `keys.clean_identity_text`) and yield empty keys — a custom profile literally
named `"none"` or `"nan"` stays unreachable.

**Gate first.** Every custom profile runs through the initial capability gate with its own source
kind before anything resolves: alias-, wildcard-, promotion-, and transmission-bearing custom
profiles fail `unsupported_profile_capability` with the capability token — never silently ignored,
never partially applied. Bundled entries are not gated: built-in vendor aliases and the wildcard
ladder belong to the bundled layer, attached only as explicit per-profile `manufacturer_aliases`
from the shared allowlist.

**Per-leaf walk.** Each leaf walks the full ladder independently and takes the first supplied
value; `None` never counts as supplied, so explicit `False` and `0.0` survive. Missing maker
identity bypasses custom exact and both bundled steps for the legacy Default path. A leaf no
candidate supplies fails `missing_required_field` with the allowlisted block/leaf path — never a
previous mutable setting. The selected candidate is the highest rung with a claim (custom exact >
bundled exact > bundled wildcard > Default); `inherited` is `false` only for leaves the selected
candidate supplied itself, generalizing §9 beyond custom-selected resolutions.

**Records and notices.** The record reuses the §9 shape: all 15 leaves in canonical order,
`matched_input_key` with canonical keys (empty when missing, never `"none"`/`"nan"`),
`affected_event_count` fixed per exam, and the selected entry's source kind, revision, and content
hash on the record and every leaf. The notice is `complete` when every leaf came from the selected
candidate, else `partial` with one entry per inherited leaf (field, source, level, profile ID, and
display label — the profile ID for custom profiles, the listed model for bundled ones). Notice text
names permitted labels only (fields, closed-vocabulary sources/levels, maker/model/profile labels),
never notes, source paths, or raw source text. New public reprs show counts and closed-vocabulary
kinds only — never keys, IDs, labels, or rendered text.

**Bundled conversion.** At most `MAX_PROFILES` entries (Default included) are materialized before
any conversion, with bounded iteration against inaccurate lengths; each model list is capped before
its profile ID is derived. Legacy settings entries convert to canonical profiles with deterministic
IDs (`bundled-<maker>-<model>` from canonically sorted model keys, so reordered lists compile
identically; wildcard models as `wildcard`), validated through the existing
boundary with `source_kind: "json"`; non-Default entries compile into the conflict-checked index
while `Default` stays separate as the unconditional fallback (a second `Default` fails
`duplicate_profile_id`). Omitted `swap_lateral_longitudinal` materializes as `False` on every
bundled entry, preserving the runtime default — which applies it to each chosen entry — with honest
provenance, so shipped exact entries are complete and never inherit a wildcard's `True`.

Resolver preparation reuses the canonical compiler to revalidate payloads and hashes, reject global conflicts,
and compare every supplied coordinate claim against the keys and metadata compiled from its profiles.

## 15. Multi-source session assembly (import-before-load preparation)

A session freezes validated custom profiles from file byte snapshots (`json`/`csv`/`tsv`/`xlsx`),
in-memory documents, and store snapshots into one immutable, conflict-checked, capability-gated
custom set with a compiled index prepared once for per-exam resolution. Nothing here applies a
profile to a calculation.

**Requests.** A file request names a path, an optional adapter format (else the file suffix
routes), and an optional zero-based XLSX sheet index (`None` reads the first sheet; a sheet on
another format fails). Relative paths resolve against the working directory, or against an
explicit caller settings base directory; the process directory never changes. Paths coerce
behind a closed boundary (hostile pathlikes, bytes, and NUL collapse value-free), and adapters
always receive plain strings. Request collections are bounded before copying (declared lengths
first, bounded iteration, at most 64 sources including empty snapshots). Malformed requests fail
`invalid_type`/`invalid_enum` (`sheet` misuse fails closed); unknown suffixes fail
`unsupported_source_suffix`.

**Assembly order.** Profile/row ceilings (64 profiles, 10,000 rows) accrue incrementally while
loading and stop before the next source once exceeded; canonical conflicts run across all kinds;
the capability gate runs before the session becomes usable; then the custom index compiles once,
the active-set hash covers the combined profiles, and the resolver context prepares once. Any
failure publishes nothing, so a prior session object is unaffected. An explicitly empty selection
yields a valid empty custom session resolving bundled/Default.

**Snapshots.** Tuple shapes and the source bound gate traversal; store identity, the locked
wrapper hash, per-profile hashes, revisions, and the row counter all re-verify against content
(disagreements report conflicting metadata, like stale compile-time claims). Session payloads use
the compiler's canonical output — never caller-owned objects.

**Outputs.** Profiles frozen in exact profile-ID order; the prepared custom index; the active-set
hash; and default-safe provenance per source (`file`/`memory`/`store` kind, adapter format, exact
file-bytes or locked store-set hash, profile IDs, store revisions, counters — never paths, notes,
raw text, station, or serial) plus session totals, with source records canonically ordered by
kind, format, hash, and IDs. Input order affects diagnostics only: reordered inputs assemble
equal sessions. Per-exam resolution reuses the prepared custom side with no recompiling,
revalidating, re-reading, or shared mutable caches; a bundled set may arrive compiled or
prepared. Prepared contexts validate fully at construction (entries, claim tables, lead kind,
gate), so forged instances fail closed before any exam. New public reprs show counts and kinds
only — never keys, IDs, labels, or rendered text.

## 16. Run-state and rich-export contract (locked companion)

The run-state/rich-export versioning, privacy, backward-reader, representation,
and reproducibility contract is locked in
[EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md](EQUIPMENT_PROFILE_RUNSTATE_EXPORT_CONTRACT.md)
(Phase 0, docs only): run-state 1→2, rich-report 3→4, dict/JSON export stays 3
while additive, default-safe maker/model keys vs gated station/serial, old-document
readers, coordinates-only captures, and the exact open implementation list. That
companion is normative for the listed slices; no run-state or export
implementation is complete.
