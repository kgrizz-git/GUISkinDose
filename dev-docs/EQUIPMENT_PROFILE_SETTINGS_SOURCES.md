# Equipment-profile settings sources (contract companion)

Locks the exact `equipment_profiles` settings-block grammar, the path rules,
and the headless CLI+config composition policy. Parsing and assembly are owned
by `src/guiskindose/settings_equipment_profiles.py`; headless binding is owned
by `src/guiskindose/cli_settings.py`; the stdlib-only core in
`src/guiskindose/equipment_profiles/` is untouched.

## 1. Request grammar (exact)

```text
equipment_profiles = {
    "files": [{"path": str, "format"?: "json"|"csv"|"tsv"|"xlsx",
               "sheet"?: int|string}, ...],
    "store": {"path": str, "ids"?: [str, ...]},
}
```

- The block must be an exact builtin `dict`; only `files`/`store` keys are
  accepted (unknown keys fail `unknown_field`). Absent (`None`) returns no
  session without any I/O; an explicit empty mapping assembles an empty
  session. There is deliberately no `schema_version`: the grammar is
  code-versioned and unknown keys fail closed, so a version field would
  promise evolution this slice does not implement.
- Each file entry must be an exact builtin `dict` with only
  `path`/`format`/`sheet` keys. `path` is required and must be an exact
  NUL-free `str`. `format`, when present, must be one of the four supported
  tokens (`invalid_enum` otherwise). `sheet` must be an exact non-negative
  `int` or a non-empty exact `str` with valid Unicode and no NUL; a sheet on a non-XLSX effective format
  fails closed before any I/O.
- The store entry must be an exact builtin `dict` with only `path`/`ids`
  keys; `path` is required. `ids`, when present, must be an exact builtin
  list/tuple validated by the canonical selection rules (≤64, unique,
  pattern-checked, exact string elements) before the database opens.
- Mappings require exact builtin types with exact-string keys (subclasses and
  hostile key equality are not JSON keys); key counts gate against the
  allowlist before any iteration, so unbounded maps fail without traversal.
- Paths must be non-empty exact strings with valid unicode and no NUL; an
  empty or surrogate-carrying path fails closed before any I/O.
- File lists are bounded exactly (declared length, then bounded iteration, at
  most 64); the mixed file-plus-snapshot request total stays within
  `MAX_SOURCES` before any profile or store I/O. Inferred formats (unknown
  suffixes) and integer sheets outside `0..MAX_XLSX_SHEETS-1` fail before any
  source opens, as does a sheet on a non-XLSX effective format.
- Every failure is a value-free `EquipmentProfileError` (stable code, source
  kind, row/count only — never paths, cells, IDs, notes, or causes), so a
  CLI boundary converts it to the existing value-free user-facing error.

## 2. Path rules

File and store paths are exact strings carried transiently in the caller's
config: they are never written into runtime settings (`to_settings_dict`
receives a transient copy with the block removed in headless preparation), results,
provenance, errors, or reprs. The explicit base directory validates first
(hostile hooks, non-path types, bytes, NUL, and surrogates fail closed with
suppressed causes and no path echo); relative paths then resolve against it
with pure string operations, or against the working directory for inline
JSON/dict configs, and absolute paths ignore the base. The store opens only
through the read-only factory (never created, migrated, or written) and
composes as one frozen snapshot after the files, preserving every source,
conflict, and capability gate. A failed candidate publishes nothing.

## 3. Validated-request seam

`_parse_request` freezes the fully validated request (resolved plain file
sources plus the optional store path/selection, counts-only repr) without
profile-source I/O; `_assemble_composed` opens the stores and assembles both sides. The seam
stays internal; its dataclass constructor does not independently validate,
so callers must use the parser boundary. CLI+config composition reuses it: parse each side, validate the combined
source count, then assemble once.

## 4. CLI+config composition policy (wired headless)

Headless preparation composes CLI flags and the settings block into **one**
candidate assembled once: file requests concatenate (CLI paths first, then
config paths — order affects diagnostics only), at most one snapshot per
side, requests validated before settings construction or profile-source I/O,
assembled once and bound last. JSON settings strip the block before legacy
construction (duplicate keys in profile-bearing documents fail closed), so
the constructor never double-loads. Reading the selected settings file necessarily
precedes request validation.
Never bind or override prematurely: a pre-bound runtime session fails
closed before any mutation or read, caller-owned homes stage on an isolated
copy, and an absent-everywhere request leaves settings untouched. Duplicate
claims across sides fail the canonical conflicts — never deduped or
overridden. The legacy `ValueError` construction fallback still owns
malformed non-profile settings, but an invalid `equipment_profiles` block
fails closed first and never falls through it. Direct `PyskindoseSettings`
constructor / `initialize_settings` source support is wired (keyword-only
`settings_base_dir`); GUI authoring stays out of scope.

## 5. GUI live-session ownership (F-A slice)

The GUI holds one optional immutable `EquipmentProfileSession` on
`AppState.equipment_profile_session` (`gui/state.py`), bound only through
`bind_equipment_session` (`gui/settings_builder.py`): mistyped sessions,
in-flight operations, and loaded exams or legacy preview data all refuse
closed before any mutation (import-before-data-load); results invalidate
only on success. `build_settings` passes the home through the validated
constructor kwarg (no store/file I/O; the session arrives already assembled).

Session-active loaders request genuine receipts from their own normalizer
call, rebind each receipt to the final post-filter/post-transform frame with
the public `bind_receipt_frame` bridge, and mint one `(capture, snapshot)`
authority pair per accepted exam with `capture_from_receipt` (full bridge
validation, never a forged or foreign receipt). The snapshot is the
receipt's proven leaves on an isolated copy — the exam's genuine per-exam
baseline, retained on the exam result with `repr=False`. Publication is
candidate-based: every step runs on a bounded shallow copy and the live
state adopts wholesale only on full success, so any fault or cancellation
leaves exams, preview, raw, display, offsets, results, and session identical.
Exam/event ceilings (64 / 10,000; O(1) counts first, null-inclusive bounded
sums) refuse before copies. Calculation threads captures positionally
through the existing `equipment_capture_context(s)` APIs with the live
session stripped and private per-exam baselines (a capture-less entry with
no snapshot fails closed as inconsistent, distinct from an intentional
null); stale captures are retained and refuse loudly before dose. Captures
and session survive `reset_results`. No run-state version bump, import, or
writer rides on this slice.

## 6. Run-state staging hardening (same slice)

Pending entries validate fully at construction (finite offsets with overflow
closed, exact booleans, strict x/y/z override keys) and again before loader
reads, so forged bypass inputs fail before any I/O. Overrides store as an
immutable deepcopyable mapping with a count/token-only repr. Tabular replay
uses the `defer_capture_confirmation` registry seam (default path unchanged)
and confirms only the final transformed frame. Bounds tokens cover staged
presence (nulls included) with pre-read gates; emission/staging helpers cap
at 64 before materializing. The public writer refuses staged pending.
Already-loaded imports prove canonical capture equivalence against live
authority and refuse conflicts instead of silently keeping it.
