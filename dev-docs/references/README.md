# External library references

_Index of authoritative documentation for major MyPySkinDose dependencies. Expand before the next major dependency review._

| Library | Role in MyPySkinDose | Documentation |
|---------|----------------------|---------------|
| [pydicom](https://pypi.org/project/pydicom/) | DICOM RDSR parsing | [User guide](https://pydicom.github.io/pydicom/stable/) · [Tag dictionary](https://dicom.innolitics.com/) |
| [NiceGUI](https://pypi.org/project/nicegui/) | Web/desktop GUI (`[gui]` extra) | [Documentation](https://nicegui.io/documentation) · [User simulation testing](https://nicegui.io/documentation/section_testing) |
| [Plotly](https://pypi.org/project/plotly/) | 3D geometry and dose-map plots | [Python API](https://plotly.com/python/) · [Mesh3d](https://plotly.com/python/3d-mesh/) |
| [pandas](https://pypi.org/project/pandas/) | Normalized event DataFrame contract | [User guide](https://pandas.pydata.org/docs/user_guide/index.html) |
| [numpy-stl](https://pypi.org/project/numpy-stl/) | Human phantom meshes | [API](https://numpy-stl.readthedocs.io/) |

**Phantom mesh sources (candidates):** [`CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md`](CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md) — stylized/game characters, MakeHuman, classical sculpture scans, Smithsonian Open Access; summarized from [`ADDITIONAL_PHANTOMS.md`](../ADDITIONAL_PHANTOMS.md).

**Portable GUI executables (research):** [`PORTABLE_EXECUTABLE_PACKAGING.md`](PORTABLE_EXECUTABLE_PACKAGING.md) — NiceGUI/`nicegui-pack` feasibility; parent hub [`../RELEASES_AND_DISTRIBUTION.md`](../RELEASES_AND_DISTRIBUTION.md); deferred in `TO_DO.md`.

**Harness note:** Optional `LLMS.txt` or per-library cheat sheets can live in this directory when a dependency upgrade needs focused agent context. Until then, link here from `AGENTS.md` only when adding new integration surfaces.

---

## Reference implementations — tabular input adapters

Saved copies of adapter implementations from related projects. Used as reference for Phase 3–4 work (Radimetrics, DoseTrack adapters). **These are read-only references, not production code** — do not import or use directly.

| File | Source | What it shows |
|------|--------|---------------|
| [`dhen2714_radimetrics.py`](dhen2714_radimetrics.py) | `github.com/dhen2714/PySkinDose` (public fork) | `RADIMETRICS2PSD` column map; unit conversions (mGy→Gy, cm²→m², mAs→µAs); calls `rdsr_normalizer()` (raw DICOM frame path) |
| [`dhen2714_dosetrack.py`](dhen2714_dosetrack.py) | `github.com/dhen2714/PySkinDose` (public fork) | `DOSETRACK2PSD` column map; Siemens and Philips paths; Philips **swaps TableLateralPosition ↔ TableLongitudinalPosition**; derives CollimatedFieldArea from DAP/dose formula; `ffill()` for forward-filling geometry rows |
| [`psdcalcrework_io_utils.py`](psdcalcrework_io_utils.py) | `github.com/kgrizz-git/PSDCalcReworkTemp` (private) | `_ALIASES` column normalization dict; heuristic header detection; per-manufacturer lat/lon swap defaults (GE → swap=True); sheet picker; structured `load_rdsr()` return format |

### Key findings from these references

1. **Coordinate frame confirmed (for dhen2714 exports)**: Both adapters call `rdsr_normalizer()` after column rename — raw DICOM frame is the correct assumption for those specific Radimetrics CSV and DoseTrack XLSX templates.
2. **DoseTrack Philips lat/lon swap**: `parse_philips()` in `dosetrack.py` explicitly swaps `TableLateralPosition_mm ↔ TableLongitudinalPosition_mm`. This is a DoseTrack-specific issue for Philips exports, separate from the GE DICOM RDSR issue.
3. **CollimatedFieldArea missing in DoseTrack**: Both Siemens and Philips DoseTrack paths derive `CollimatedFieldArea_m2` from `DAP_Gym2 / (DoseRP_Gy × geometry_factor²)`. The column is not present directly in DoseTrack exports.
4. **DoseTrack uses ffill()**: Some rows carry position data from the previous event. Forward-fill before processing.
5. **Manufacturer not in DoseTrack**: Inferred from `Equipment Name` column via a `MODEL2MANUF` dict.
6. **Private repo example data**: `ExampleDataClean/Example RDSR+Data Cleaned/` contains real RDSR+Data XLSX files that could serve as Phase 3/4 test fixtures.

These findings are captured in `TO_DO.md` and `VENDOR_COORDINATE_SYSTEMS.md`.
