# Coordinate Transform Comparison

Compares how MyPySkinDose, dhen2714/PySkinDose (public fork), and kgrizz-git/PSDCalcReworkTemp
(private rework) handle geometry, coordinate axes, and preprocessing.

## Axis conventions

| Repo | X | Y | Z |
|------|---|---|---|
| MyPySkinDose | Lateral | Longitudinal | Vertical | 
| dhen2714/PySkinDose | Lateral | Longitudinal | Vertical (same — identical normalizer) |
| PSDCalcReworkTemp | `focal_x` = lateral | `focal_y` = height | `focal_z` = longitudinal |

**Note**: In the DICOM RDSR tags, `TableLongitudinalPosition_mm` maps to the X (lateral) axis
and `TableLateralPosition_mm` maps to the Z (longitudinal) axis in MyPySkinDose / dhen2714.
This naming inversion is inherited from the original PySkinDose source.

---

## `rdsr_normalizer()` — MyPySkinDose vs dhen2714/PySkinDose

These two repos share **byte-for-byte identical** normalizer logic. Both compute:

```python
Tx = offset.x + dir.x * data_parsed.TableLongitudinalPosition_mm / 10
Ty = offset.y + dir.y * data_parsed.TableHeightPosition_mm / 10
Tz = offset.z + dir.z * data_parsed.TableLateralPosition_mm / 10
```

Differences are limited to package name and import paths. No algorithmic divergence.

---

## Per-vendor normalization offsets

**MyPySkinDose**: offset vectors and axis direction signs are loaded from
`normalization_settings.json` — one entry per manufacturer/model combination.

| Manufacturer | Y offset | Z offset | Y dir | Notes |
|---|---|---|---|---|
| Siemens | 0 | 0 | +1 | All offsets zero; lat/lon swap not needed for DICOM RDSR |
| Philips | ~105 cm | ~173 cm | −1 | Large physical offsets; must **not** apply twice |
| GE | 0 | 0 | +1 | DICOM tags have lat/lon swapped vs physical reality |

**dhen2714/PySkinDose**: Same `normalization_settings.json` structure (fork source); identical
offset values.

**PSDCalcReworkTemp**: No `normalization_settings.json` equivalent. Geometry is fully
recomputed inside `intercept_ell()` using the raw table position columns.

---

## Lateral/longitudinal axis swap

Some vendor exports (and some DICOM RDSRs) have `TableLateralPosition_mm` and
`TableLongitudinalPosition_mm` physically swapped relative to what `rdsr_normalizer()` expects.

| Vendor / export format | Repo | How the swap is applied |
|---|---|---|
| GE DICOM RDSR | PSDCalcReworkTemp | `_should_swap_by_default("ge") → True`; swaps `Table_Lateral_Position ↔ Table_Longitudinal_Position` before passing to calculation |
| DoseTrack Philips XLSX | dhen2714/PySkinDose | `parse_philips()` renames `TableLateralPosition_mm ↔ TableLongitudinalPosition_mm` before calling `rdsr_normalizer()` |
| Any tabular import | MyPySkinDose GUI | User-selectable toggle ("Swap lateral/longitudinal axes") swaps `Tx ↔ Tz` **after** normalization |

**Risk — double correction**: applying the swap on a file that has already been correctly
exported (e.g., Siemens DICOM RDSR) gives wrong positions. Philips offsets (~105/173 cm) make
errors obvious; GE (zero offsets) produces silent geometry errors.

---

## Phantom and dose accumulation model

| Repo | Phantom | Geometry |
|---|---|---|
| MyPySkinDose | STL mesh (human/cylinder/plane) | Per-event beam-skin intersection; per-event physics corrections (BSF, field-size, back-scatter, table transmission) |
| dhen2714/PySkinDose | Same as MyPySkinDose (fork) | Identical |
| PSDCalcReworkTemp | Parametric ellipsoid | Ray–ellipsoid intersection (`intercept_ell()`); **global** correction factors applied once after accumulation |

### PSDCalcReworkTemp focal-point transform (distinct from others)

```python
# Inside intercept_ell():
Pf = [-focal_x / 10, focal_y / 10, -focal_z / 10]   # x and z are negated; /10 cm→mm
phi = -phi / 180 * pi                                  # phi sign is inverted
theta = theta / 180 * pi                               # theta sign unchanged
# Rotation order: Rz @ Rx (not Ry @ Rx as in MyPySkinDose)
```

This produces a **mirrored** X/Z space relative to MyPySkinDose. Results are not
directly comparable without re-deriving the sign conventions.

### Global vs per-event corrections

PSDCalcReworkTemp hardcodes three scalars applied to the summed dose map:
```python
F_FACTOR = 1.06          # field size / backscatter combined
TABLE_TRANSMISSION = 0.8
BACKSCATTER_FACTOR = 1.3
```

MyPySkinDose / dhen2714 apply physically derived correction factors per event from a
SQLite database (`corrections.db`), varying with kVp, field size, filter thickness, etc.

---

## Tabular input preprocessing (MyPySkinDose vs dhen2714)

### Radimetrics CSV (dhen2714 reference)

`parse_axiom_artis()` in `dhen2714_radimetrics.py`:
- Renames columns via `RADIMETRICS2PSD` dict (key = Radimetrics header, value = DICOM-style name)
- `DoseRP_Gy /= 1000` (mGy → Gy)
- `CollimatedFieldArea_m2 /= 10000` (cm² → m²)
- `Exposure_mAs *= 1000` (s → ms)
- Then calls `rdsr_normalizer()` directly — treats the result as a raw DICOM-frame DataFrame

MyPySkinDose's shipped `radimetrics` adapter (Phase 3, 2026-06-10) follows this column
mapping and unit conversion before handing off to `rdsr_normalizer()`.

### DoseTrack XLSX (dhen2714 reference)

`parse_philips()` + `parse_axiom_artis()` in `dhen2714_dosetrack.py`:
- `DOSETRACK2PSD` dict maps DoseTrack headers to DICOM-style names
- `DoseRP_Gy /= 1000`
- `CollimatedFieldArea_m2` is **derived**: `DAP / (DoseRP * (SID/SDD)²)` (not a direct column)
- Manufacturer inferred from model name via `MODEL2MANUF` dict (`{"Azurion": "Philips", ...}`)
- `parse_philips()` explicitly swaps `TableLateralPosition_mm ↔ TableLongitudinalPosition_mm`
- Forward-fills (`ffill()`) missing rows
- Then calls `rdsr_normalizer()`

### PSDCalcReworkTemp (private, different architecture)

`_normalize_header()` strips non-alphanumeric and lowercases before matching — more
tolerant of spacing/punctuation variants than our current column mapper. Our
`GENERIC_RDSR_PATTERNS` use regex; tolerance is comparable but implementation differs.

GE swap is manufacturer-keyed (`_should_swap_by_default()`); ours is a user toggle.
Automating the swap from `Manufacturer` column is a potential Phase 3/4 improvement.

---

## Full comparison summary

The table below covers every axis of comparison across the three repos.
"Identical" means the code or logic is the same; "diverges" means meaningfully different behavior.

| Aspect | MyPySkinDose | dhen2714/PySkinDose | PSDCalcReworkTemp |
|---|---|---|---|
| **Phantom geometry** | STL mesh (human / cylinder / plane) | STL mesh — identical to MyPySkinDose | Parametric ellipsoid (`intercept_ell()`) |
| **`rdsr_normalizer()` logic** | Reference implementation | Byte-for-byte identical fork | Not used |
| **Axis convention** | X=lateral, Y=longitudinal, Z=vertical | Identical | focal_x=lateral, focal_y=height, focal_z=longitudinal |
| **X / Z sign convention** | +X right, +Z up (DICOM-derived) | Identical | −focal_x, −focal_z (mirrored) |
| **Phi angle sign** | Standard | Identical | Negated (`phi = −phi`) |
| **Rotation order** | Ry @ Rx | Identical | Rz @ Rx |
| **Vendor offsets** | `normalization_settings.json` per model | Same JSON structure and values | No equivalent — raw positions used |
| **Correction factors** | Per-event, from SQLite (`corrections.db`) | Per-event, DB-driven — identical | Three global scalars applied after accumulation (F=1.06, T=0.8, BSF=1.3) |
| **Lat/lon axis swap — GE** | User toggle in GUI | Not explicitly handled for GE DICOM | Auto-detected from `Manufacturer` column |
| **Lat/lon axis swap — DoseTrack Philips** | User toggle in GUI | Hardcoded in `parse_philips()` (pre-normalizer) | Not applicable (different architecture) |
| **Philips double-correction risk** | Documented; user warned at import | Avoided by handling in `parse_philips()` | N/A |
| **Tabular input architecture** | Layered `input_adapters/` package (L2) | Ad-hoc `parse_*()` functions mixed with analysis | Standalone `io_utils.py` |
| **Column matching tolerance** | Regex patterns (`GENERIC_RDSR_PATTERNS`) | Exact string rename dict | `_normalize_header()` strips punctuation/spaces |
| **Radimetrics CSV support** | Shipped — Phase 3 | Implemented (`parse_axiom_artis()`) | Not applicable |
| **DoseTrack XLSX support** | Shipped — Phase 4 | Implemented (`parse_philips()`) | Implemented (XLSX reader) |
| **Field area (CFA) source** | Direct RDSR column | Direct RDSR column (Radimetrics); derived from DAP formula (DoseTrack) | Not tracked separately |
| **Forward-fill for missing rows** | Not yet implemented | Used in `parse_philips()` | `ffill()` in XLSX reader |

### What this means for future work

- **Shipped Phases 3–4 adapters**: dhen2714's column maps (`RADIMETRICS2PSD`, `DOSETRACK2PSD`) and
  unit conversions remain the ground-truth reference for future fixture validation. The
  `CollimatedFieldArea_m2` derivation for DoseTrack is the trickiest part (no direct column; must
  be computed from DAP, DoseRP, and geometry).
- **Lat/lon swap automation**: PSDCalcReworkTemp shows that auto-detecting the swap from a
  `Manufacturer` column is feasible. Phase 5+ could auto-set the toggle when `Manufacturer`
  contains "GE" and schema is `generic_rdsr_like`.
- **Correction factor approach**: PSDCalcReworkTemp's global scalars are simpler but less accurate.
  MyPySkinDose's per-event DB approach is physically correct and should be preserved.
- **Sign convention (PSDCalcReworkTemp)**: Results from that repo are **not directly comparable**
  to MyPySkinDose due to the mirrored X/Z axes and negated phi. Any cross-validation must account
  for these differences.
