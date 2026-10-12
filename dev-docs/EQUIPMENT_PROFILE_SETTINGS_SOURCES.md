# Equipment-profile settings sources (contract companion)

Locks the exact `equipment_profiles` settings-block grammar, the path rules,
and the future CLI+config composition policy. Implemented (inert, no wiring)
by `src/guiskindose/settings_equipment_profiles.py`; the stdlib-only core in
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
  future CLI boundary reuses its existing converter unchanged.

## 2. Path rules

File and store paths are exact strings carried transiently in the caller's
config: they are never written into runtime settings (`to_settings_dict`
drops the block today since the constructor ignores unknown keys), results,
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
any I/O; `_assemble_request` opens the store and assembles it. The seam
stays internal; its dataclass constructor does not independently validate,
so callers must use the parser boundary. Later CLI+config composition
reuses it: parse each side, merge the
frozen requests, assemble once.

## 4. Future CLI+config composition policy

When wiring lands, compose CLI flags and the settings block into **one**
candidate assembled once: concatenate file requests (CLI paths first, then
config paths — order affects diagnostics only), attach at most one snapshot
per side, validate everything before any I/O, and bind exactly once at the
end. Never bind or override prematurely: a pre-bound runtime session fails
closed before any mutation or read, and an absent-everywhere request leaves
settings untouched. A later integration slice must validate the settings
block explicitly and fail closed — it must **not** depend on the
`ValueError`-swallowing fallback in `parse_settings_to_settings_class`,
which today would silently fall back to example settings instead of
reporting an invalid block.
