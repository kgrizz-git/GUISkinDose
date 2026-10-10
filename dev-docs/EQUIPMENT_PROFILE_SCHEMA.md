# Equipment Profile Schema — Common and Coordinate Implementation Contract

Status: **Implementation contract for the common and coordinate domains.** This Markdown is the contract the
code implements, not prose about it: where the code and this document disagree, this document is wrong and must
be corrected. Design authority: [plans/CUSTOM_EQUIPMENT_PROFILES_SPEC.md](plans/CUSTOM_EQUIPMENT_PROFILES_SPEC.md);
execution: [plans/CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md](plans/CUSTOM_EQUIPMENT_PROFILES_EXECUTION.md).

Implemented today: the stdlib-only core package `src/guiskindose/equipment_profiles/` — immutable canonical
models, JSON and in-memory parsing, full-v1 structural validation, canonical serialization and hashes,
across-source duplicate/conflict validation, immutable match-record types, and the initial capability gate.
**No application wiring exists.** Profiles are not applied to any dose, normalization, or GUI path in this slice.

**Not in this contract (later slices, do not assume):** the user-store schema and migration policy; run-state and
rich-export schema version bumps and backward readers; CSV/TSV/XLSX adapters and their fixtures plus
approved-asset inventory evidence; transmission eligibility, grid completion, and inherited-evidence
classification (Phase 4); GUI/store/CLI wiring; packaging inclusion in `MANIFEST.in`. Full Phase 0 is
therefore **not** complete.

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
- **Not yet locked:** the stored selected-revision-set hash. It is specified only as "a hash over the selected
  revisions", and is deliberately not marked complete anywhere until the store schema lands.

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
      "profile_id": "AXIOM-Artis",
      "source_kind": "json",
      "revision": null,
      "profile_hash": "<sha256>",
      "inherited": true
    }
  ]
}
```

- `source` is `custom` / `bundled` / `default`; `level` is `exact` / `wildcard` / `default`.
- `source_kind` is `json`, `memory`, `csv`, `tsv`, `xlsx`, `gui`, or `store`. Only `json` and `memory` are
  implemented in this slice; the rest are reserved for their adapters.
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
`unsupported_schema_version`, `unknown_field`, `duplicate_json_key`, `invalid_type`, `missing_required_field`,
`blank_required_cell`, `blank_disallowed_cell`, `empty_domain`, `empty_coordinate_block`, `invalid_profile_id`,
`invalid_manufacturer`, `invalid_model_list`, `alias_ambiguous_target`, `alias_target_mismatch`,
`wildcard_not_permitted`, `promotion_not_acknowledged`, `invalid_number`, `invalid_enum`, `invalid_date`,
`value_out_of_range`, `duplicate_profile_id`, `duplicate_coordinate_claim`, `duplicate_transmission_key`,
`conflicting_profile_metadata`, `conflicting_profile_claim`, `unsupported_profile_capability`.

`unreadable_source` covers a file that cannot be read at all (missing, a directory, or any I/O failure). A path
is never included in the error, so the failure is indistinguishable by path and only distinguishable by code.

Four further codes are **reserved for later slices and must not be reported as implemented**:
`sheet_limit_exceeded` (XLSX adapter), `store_corruption` (user store),
`existing_model_out_of_extent` (transmission bounds), and `explicit_sqlite_collision`
(explicit `corrections_db_path` coexistence).

## 11. Packaged examples

The packaged `example_data/equipment_profiles/` JSON parses under this contract unchanged: 3 profiles, 16
coordinate leaves, and 5 transmission rows. The two alias fields on `demo-scope-2000` are accepted shorthand
arrays (JSON), `demo-scope-wildcard` supplies one nested leaf, `demo-scope-biplane-rows` supplies two
transmission rows. They remain **unverified against a real loader** until Phase 1, and TSV/XLSX variants and
`MANIFEST.in` inclusion remain outstanding.

Strings must be encodable as strict UTF-8; escaped unpaired surrogates are rejected with
`unsupported_source_encoding`. Measured source text must contain non-whitespace content. Traversal bounds
limit both visited nodes and queued children, so a broad in-memory container cannot grow an unbounded stack.
