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
# On macOS the build also writes GUISkinDose.app (BUNDLE). Its .icns is generated at
# build time from the committed SVG icon into tmp/portable/icon (AppKit via osascript,
# sips, iconutil), so no binary icon is committed. Sign and notarize the .app afterwards with
# packaging/portable/macos_sign_notarize.sh.
# ruff: noqa
import os
import shutil
import subprocess
import sys
from importlib.metadata import version as _dist_version
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve().parents[1]
PKG = ROOT / "src" / "guiskindose"
ICON = PKG / "gui" / "static" / "guiskindose_icon.ico"
SVG_ICON = PKG / "gui" / "static" / "guiskindose_icon.svg"
IS_MACOS = sys.platform == "darwin"
BUNDLE_ID = "io.github.kgrizz-git.guiskindose"


# AppKit renders the SVG into a 1024 px RGBA bitmap with a clear background. The art is
# scaled to 824 px and centered, and clipped to a rounded rect (radius 185 px), which
# follows Apple's macOS icon grid. Quick Look thumbnails were not used, because they
# flatten the SVG onto white and leave square white corners.
_RENDER_ICON_JXA = r"""
ObjC.import('AppKit');
function run(argv) {
  const size = 1024, art = 824, pad = (size - art) / 2, radius = 185;
  const image = $.NSImage.alloc.initWithContentsOfFile(argv[0]);
  if (image.isNil()) { throw new Error('cannot load SVG'); }
  const rep = $.NSBitmapImageRep.alloc
    .initWithBitmapDataPlanesPixelsWidePixelsHighBitsPerSampleSamplesPerPixelHasAlphaIsPlanarColorSpaceNameBytesPerRowBitsPerPixel(
      null, size, size, 8, 4, true, false, 'NSDeviceRGBColorSpace', 0, 0);
  rep.size = $.NSMakeSize(size, size);
  const ctx = $.NSGraphicsContext.graphicsContextWithBitmapImageRep(rep);
  $.NSGraphicsContext.saveGraphicsState;
  $.NSGraphicsContext.setCurrentContext(ctx);
  $.NSColor.clearColor.set;
  $.NSRectFillUsingOperation($.NSMakeRect(0, 0, size, size), 1);
  const rect = $.NSMakeRect(pad, pad, art, art);
  $.NSBezierPath.bezierPathWithRoundedRectXRadiusYRadius(rect, radius, radius).addClip;
  image.drawInRectFromRectOperationFractionRespectFlippedHints(rect, $.NSZeroRect, 2, 1.0, true, $());
  ctx.flushGraphics;
  $.NSGraphicsContext.restoreGraphicsState;
  const png = rep.representationUsingTypeProperties(4, $({}));
  if (!png.writeToFileAtomically(argv[1], true)) { throw new Error('cannot write PNG'); }
}
"""


def _macos_icns() -> str:
    """Render the SVG icon to tmp/portable/icon/GUISkinDose.icns (macOS tools only)."""
    out = ROOT / "tmp" / "portable" / "icon"
    iconset = out / "GUISkinDose.iconset"
    shutil.rmtree(out, ignore_errors=True)
    iconset.mkdir(parents=True)
    master = out / "master_1024.png"
    subprocess.run(["osascript", "-l", "JavaScript", "-e", _RENDER_ICON_JXA, str(SVG_ICON), str(master)],
                   check=True, stdout=subprocess.DEVNULL)
    has_alpha = subprocess.run(["sips", "-g", "hasAlpha", str(master)], check=True,
                               capture_output=True, text=True).stdout
    if "hasAlpha: yes" not in has_alpha:
        raise SystemExit("icon master PNG has no alpha channel")
    # sips scales the master to each iconset size.
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = size * scale
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            subprocess.run(["sips", "-z", str(px), str(px), str(master), "--out", str(iconset / name)],
                           check=True, stdout=subprocess.DEVNULL)
    icns = out / "GUISkinDose.icns"
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)], check=True)
    return str(icns)


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
    icon=None if IS_MACOS else str(ICON),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="GUISkinDose",
)

if IS_MACOS:
    _version = _dist_version("guiskindose")
    app = BUNDLE(
        coll,
        name="GUISkinDose.app",
        icon=_macos_icns(),
        bundle_identifier=BUNDLE_ID,
        version=_version,
        info_plist={
            "CFBundleName": "GUISkinDose",
            "CFBundleDisplayName": "GUISkinDose",
            "CFBundleShortVersionString": _version,
            "CFBundleVersion": _version,
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            # The native window only loads the local NiceGUI server on 127.0.0.1.
            "NSAppTransportSecurity": {
                "NSAllowsArbitraryLoads": False,
                "NSAllowsLocalNetworking": True,
            },
        },
    )
