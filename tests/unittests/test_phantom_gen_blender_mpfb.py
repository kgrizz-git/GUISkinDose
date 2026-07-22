"""Optional Blender/MPFB smoke tests (skipped when environment unavailable).

Run locally after Phase 0 setup::

    export BLENDER_USER_RESOURCES="$PWD/tmp/blender_user"
    source .venv/bin/activate
    pytest -m blender_mpfb tests/unittests/test_phantom_gen_blender_mpfb.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.phantom_gen.run_catalog import blender_mpfb_available, load_catalog, process_entry

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_V1 = REPO_ROOT / "scripts" / "phantom_gen" / "catalog_v1.json"

pytestmark = pytest.mark.blender_mpfb


def test_blender_mpfb_probe_or_skip():
    ok, detail = blender_mpfb_available()
    if not ok:
        pytest.skip(f"Blender/MPFB unavailable: {detail}")
    assert ok


def test_generate_one_catalog_entry_smoke(tmp_path: Path):
    ok, detail = blender_mpfb_available()
    if not ok:
        pytest.skip(f"Blender/MPFB unavailable: {detail}")

    catalog = load_catalog(CATALOG_V1)
    # Use smallest pediatric entry for a relatively quick smoke.
    report = process_entry(
        "pediatric_5y_male",
        catalog,
        catalog_path=CATALOG_V1,
        out_dir=tmp_path,
        blender=detail,
        skip_phantom_load=False,
        skip_shape=False,
    )
    assert report["passed"], report
    assert (tmp_path / "pediatric_5y_male.stl").is_file()
