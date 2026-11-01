# PyInstaller spec for the portable GUISkinDose app (Phase 0 spikes).
#
# Build from the repository root (outputs go to gitignored tmp/):
#   uv sync --locked --extra gui-native --group portable
#   uv run --no-sync pyinstaller packaging/portable/guiskindose.spec --noconfirm \
#       --distpath tmp/portable/dist --workpath tmp/portable/work
#
# Onedir, windowed (no console), entry = packaging/portable/entry.py. Package data
# is an explicit include list placed under guiskindose/ inside the bundle, so
# importlib.resources and Path(__file__) lookups resolve exactly as in a wheel.
# GUISKINDOSE_PORTABLE_SHAPE picks the phantom payload (PORTABLE_APP_PLAN.md Phase 0):
#   spike (default)  every shipped STL, the original no-browser spike
#   light            only the proposed Light set (7 bases, both poses, _reduced_3000t)
#   full             every clinical STL except the legacy _reduced_1000t previews
# The spec never bundles a browser. The Full workflow job copies a pinned, sha256-
# verified Chromium into the onedir after the freeze (see PORTABLE_CHROMIUM_ARTIFACT.md).
# src/ is on pathex, so an editable install is fine.
# ruff: noqa
import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parents[1]
PKG = ROOT / "src" / "guiskindose"
ICON = PKG / "gui" / "static" / "guiskindose_icon.ico"

SHAPE = os.environ.get("GUISKINDOSE_PORTABLE_SHAPE", "spike")
# Proposed Light set: PORTABLE_APP_PLAN.md -> "Proposed Light set".
LIGHT_BASES = (
    "hudfrid",
    "adult_male",
    "adult_female",
    "ped_5y_male",
    "ped_5y_female",
    "adult_bariatric_male_1",
    "adult_bariatric_female_1",
)


def _phantom_stls() -> list[str]:
    names = sorted(path.name for path in (PKG / "phantom_data").glob("*.stl"))
    if SHAPE == "spike":
        return names
    if SHAPE == "full":
        return [name for name in names if not name.endswith("_reduced_1000t.stl")]
    if SHAPE == "light":
        wanted = {
            f"{base}{pose}{suffix}.stl"
            for base in LIGHT_BASES
            for pose in ("", "_arms_down")
            for suffix in ("", "_reduced_3000t")
        }
        missing = wanted.difference(names)
        if missing:
            raise SystemExit(f"Light set STLs missing: {sorted(missing)}")
        return sorted(wanted)
    raise SystemExit(f"unknown GUISKINDOSE_PORTABLE_SHAPE={SHAPE!r}")


# (glob under src/guiskindose, destination folder inside the bundle)
# Mirrors MANIFEST.in, except that the phantom STLs depend on SHAPE.
_PACKAGE_DATA = [(f"phantom_data/{name}", "phantom_data") for name in _phantom_stls()] + [
    ("table_data/*.csv", "table_data"),
    ("table_data/*.json", "table_data"),
    ("table_data/hvl_tables/*.csv", "table_data/hvl_tables"),
    ("gui/help/*.md", "gui/help"),
    ("gui/static/*.ico", "gui/static"),
    ("gui/static/*.svg", "gui/static"),
    ("gui/static/fonts/*", "gui/static/fonts"),
    ("gui/ui_copy.json", "gui"),
    ("settings_example.json", "."),
    ("normalization_settings.json", "."),
    ("example_data/RDSR/*.dcm", "example_data/RDSR"),
    ("example_data/tabular/*.csv", "example_data/tabular"),
    ("example_data/kerma_meter/*.csv", "example_data/kerma_meter"),
    ("example_data/kerma_meter/*.md", "example_data/kerma_meter"),
    ("example_data/equipment_profiles/*.json", "example_data/equipment_profiles"),
    ("example_data/equipment_profiles/*.csv", "example_data/equipment_profiles"),
    ("example_data/equipment_profiles/*.md", "example_data/equipment_profiles"),
]

datas = [(str(PKG / pattern), str(Path("guiskindose") / dest)) for pattern, dest in _PACKAGE_DATA]
# NiceGUI serves its own static/templates; plotly needs its package JSON/JS.
datas += collect_data_files("nicegui")
datas += collect_data_files("plotly")
datas += collect_data_files("kaleido")
# guiskindose's metadata backs __version__; the self-check fails if it is missing.
for dist in ("guiskindose", "nicegui", "plotly", "kaleido", "pydicom", "pywebview"):
    try:
        datas += copy_metadata(dist)
    except Exception as exc:
        print(f"WARNING: copy_metadata({dist!r}) failed: {type(exc).__name__}")
        if dist == "guiskindose":
            raise

# Lazy and dynamic imports inside the package (writers, tabs, adapters). The
# table_data build scripts are maintainer tools with import-time side effects.
hiddenimports = collect_submodules("guiskindose", filter=lambda name: ".table_data" not in name)
hiddenimports += ["webview", "selfcheck", "pngcheck"]
print(f"portable shape={SHAPE} phantom_stls={len(_phantom_stls())}")

excludes = [
    "pytest",
    "pytest_asyncio",
    "_pytest",
    "playwright",
    "pytest_playwright",
    "IPython",
    "jupyter",
    "jupyterlab",
    "notebook",
    "sphinx",
    "semgrep",
    "presidio_analyzer",
    "spacy",
    "tkinter",
]

a = Analysis(
    [str(Path(SPECPATH) / "entry.py")],
    pathex=[str(ROOT / "src"), str(Path(SPECPATH))],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GUISkinDose",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="GUISkinDose",
)
