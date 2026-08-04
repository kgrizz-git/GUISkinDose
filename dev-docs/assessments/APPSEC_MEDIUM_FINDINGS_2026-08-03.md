# AppSec remediation — medium findings (eeef294 review)

_Date: 2026-08-03_

Validated remediations for three medium findings from the AppSec review of
`eeef294`. Prior network-bind / upload-size / PyPI-pin issues were already
addressed upstream of this note.

## 1. Spreadsheet formula injection via column headers (CWE-1236)

- **Was:** `neutralize_dataframe()` sanitized string *cell values* only.
  Attacker-controlled tabular column names (and index labels) survived into
  Data-tab CSV/XLSX/TXT exports and could become live Excel formulas
  (`data_type='f'`).
- **Now:** `mypyskindose.spreadsheet_safety.neutralize_dataframe()` also
  neutralizes column names and index labels (including MultiIndex parts and
  column-/index-axis `name`/`names`) with the same dangerous-prefix rules
  (`=`, `+`, `-`, `@`, tab, CR).
- **Tests:** `tests/unittests/test_spreadsheet_safety.py` (header + index +
  column-axis name cases; openpyxl asserts header `data_type == "s"`).

## 2. `human_mesh` path traversal outside `phantom_data/`

- **Was:** `Phantom._load_human_mesh` joined a settings stem into
  `phantom_data/{stem}.stl` without rejecting `../` or verifying confinement,
  so a compromised settings value could load an STL outside the package tree.
- **Now:** `phantom_mesh_names.assert_safe_human_mesh_stem` /
  `resolve_human_mesh_stl_path` allow-list simple basenames, resolve aliases,
  require `Path.resolve().is_relative_to(phantom_data/)`, and require an
  existing `.stl`. Custom meshes remain the intentional trusted **tuple** form.
- **Tests:** `tests/unittests/test_human_mesh_path_safety.py`.

## 3. XLSX decompression bomb bypasses upload size cap (CWE-409)

- **Was:** GUI/CLI accepted up to 64 MiB *compressed* `.xlsx`/`.xlsm`;
  `pd.read_excel` / openpyxl inflated without a post-decompress size or cell
  budget.
- **Now:** `input_adapters.tabular_loader` checks ZIP central-directory
  uncompressed sizes, then stream-inflates each member to count actual bytes
  (so forged `ZipInfo.file_size` cannot bypass the cap), then streams the selected
  sheet in openpyxl `read_only` mode under row / column / cell caps before building
  the DataFrame. Formula cells keep `data_only=False` (prior `pd.read_excel`
  behavior; uncached formulas would otherwise become empty).
- **Tests:** `tests/unittests/test_xlsx_size_guards.py` (monkeypatched budgets,
  underreported inflate).

## SemVer impact

Patch-level security hardening under `[Unreleased]`; no intentional public API
break for valid stems or normal clinical workbooks. Invalid traversal stems and
oversized workbooks now raise `ValueError` instead of loading.
