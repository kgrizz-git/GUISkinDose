"""Unit tests for phantom_gen transform/validate/catalog (no Blender required)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from stl import mesh as stl_mesh

from scripts.phantom_gen.affine_control import build_affine_control
from scripts.phantom_gen.run_catalog import check_expect_ranges, load_catalog, select_ids
from scripts.phantom_gen.transform_to_psd_frame import transform_to_psd_frame
from scripts.phantom_gen.validate_phantom import abdomen_bulk, extents, head_ratio, validate

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_V1 = REPO_ROOT / "scripts" / "phantom_gen" / "catalog_v1.json"
ADULT_MALE = REPO_ROOT / "src" / "mypyskindose" / "phantom_data" / "adult_male.stl"


def _write_box_stl(path: Path, *, x: float, y: float, z: float, origin=(0.0, 0.0, 0.0)) -> None:
    """Axis-aligned box as 12 triangles (open topology ok for metric unit tests)."""
    ox, oy, oz = origin
    # 8 corners
    corners = np.array(
        [
            [ox, oy, oz],
            [ox + x, oy, oz],
            [ox + x, oy + y, oz],
            [ox, oy + y, oz],
            [ox, oy, oz + z],
            [ox + x, oy, oz + z],
            [ox + x, oy + y, oz + z],
            [ox, oy + y, oz + z],
        ],
        dtype=float,
    )
    faces = [
        (0, 1, 2),
        (0, 2, 3),
        (4, 6, 5),
        (4, 7, 6),
        (0, 4, 5),
        (0, 5, 1),
        (1, 5, 6),
        (1, 6, 2),
        (2, 6, 7),
        (2, 7, 3),
        (3, 7, 4),
        (3, 4, 0),
    ]
    stl = stl_mesh.Mesh(np.zeros(len(faces), dtype=stl_mesh.Mesh.dtype))
    for i, (a, b, c) in enumerate(faces):
        stl.vectors[i][0] = corners[a]
        stl.vectors[i][1] = corners[b]
        stl.vectors[i][2] = corners[c]
    path.parent.mkdir(parents=True, exist_ok=True)
    stl.save(str(path))


def test_catalog_v1_loads_and_forbids_affine_shipping_fields():
    catalog = load_catalog(CATALOG_V1)
    # 10 shippable + 2 MPFB shape-reference adults
    assert len(catalog["entries"]) == 12
    assert "pediatric_5y_male" in catalog["entries"]
    assert "bariatric_class2_female" in catalog["entries"]
    assert "_shape_ref_adult_male" in catalog["entries"]
    assert "_shape_ref_adult_female" in catalog["entries"]
    assert catalog["entries"]["_shape_ref_adult_male"].get("ship") is False
    assert catalog["entries"]["_shape_ref_adult_female"].get("ship") is False
    for entry in catalog["entries"].values():
        assert "base_mesh" not in entry
        assert "scale" not in entry
        assert entry["license"] == "mpfb-makehuman-assets"
        assert "macros" in entry
        assert "expect" in entry
        assert "detail_targets" in entry
    base = catalog["affine_control_base"]
    assert base["method"] == "mpfb_catalog_id"
    assert base["id"] == "_shape_ref_adult_male"
    assert base["id_female"] == "_shape_ref_adult_female"


def test_catalog_rejects_base_mesh_entry(tmp_path: Path):
    bad = {
        "entries": {
            "bad": {
                "license": "mpfb-makehuman-assets",
                "macros": {"age": 0.5},
                "expect": {},
                "base_mesh": "adult_male",
            }
        }
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    with pytest.raises(ValueError, match="base_mesh"):
        load_catalog(path)


def test_select_ids_only_and_priority():
    catalog = load_catalog(CATALOG_V1)
    assert select_ids(catalog, only="pediatric_5y_male", priority=None) == ["pediatric_5y_male"]
    # REF entries excluded from default / priority sweeps
    all_ids = select_ids(catalog, only=None, priority=None)
    assert "_shape_ref_adult_male" not in all_ids
    assert len(all_ids) == 10
    p0 = select_ids(catalog, only=None, priority="P0")
    assert len(p0) == 8
    assert all(catalog["entries"][i]["priority"] == "P0" for i in p0)
    p1 = select_ids(catalog, only=None, priority="P1")
    assert len(p1) == 2


def test_transform_to_psd_frame_anchors_obj_y_up_meters():
    # Standing Y-up human in meters: height along +Y, depth along +Z, lateral X.
    # Shape: x in [-0.2, 0.2], y in [0, 1.7], z in [-0.15, 0.15]
    rng = np.random.default_rng(0)
    n = 200
    vertices = np.column_stack(
        [
            rng.uniform(-0.2, 0.2, n),
            rng.uniform(0.0, 1.7, n),
            rng.uniform(-0.15, 0.15, n),
        ]
    )
    out = transform_to_psd_frame(vertices, obj_y_up=True)
    ext = extents(out)
    assert abs(ext["x_mid"]) < 1e-6
    assert abs(ext["y_max"]) < 1e-6
    assert abs(ext["z_max"]) < 1e-6
    assert 160.0 < ext["height_z"] < 180.0  # 1.7 m → 170 cm


def test_head_ratio_higher_for_large_head_bulk():
    # Build synthetic point clouds: adult-like vs big-head pediatric-like.
    rng = np.random.default_rng(1)

    def body(head_r: float, torso_r: float, height: float = 100.0) -> np.ndarray:
        # Head band: top 0–12%; torso: 25–45% from head.
        head_pts = []
        torso_pts = []
        for _ in range(80):
            z = height * (1.0 - rng.uniform(0.0, 0.12))
            ang = rng.uniform(0, 2 * np.pi)
            head_pts.append([head_r * np.cos(ang), -abs(head_r * np.sin(ang)), z])
        for _ in range(120):
            z = height * (1.0 - rng.uniform(0.25, 0.45))
            ang = rng.uniform(0, 2 * np.pi)
            torso_pts.append([torso_r * np.cos(ang), -abs(torso_r * np.sin(ang)), z])
        # Fill rest of height so extents are valid
        filler = np.column_stack(
            [
                rng.uniform(-torso_r, torso_r, 40),
                rng.uniform(-torso_r, 0, 40),
                rng.uniform(0, height, 40),
            ]
        )
        return np.vstack([np.array(head_pts), np.array(torso_pts), filler])

    pediatric = body(head_r=12.0, torso_r=10.0)
    adult = body(head_r=8.0, torso_r=18.0)
    assert head_ratio(pediatric) > head_ratio(adult)


def test_abdomen_bulk_increases_with_mid_torso_radius():
    rng = np.random.default_rng(2)
    height = 170.0

    def cloud(torso_r: float) -> np.ndarray:
        pts = []
        for _ in range(200):
            z = height * (1.0 - rng.uniform(0.15, 0.45))
            ang = rng.uniform(0, 2 * np.pi)
            pts.append([torso_r * np.cos(ang), -abs(torso_r * np.sin(ang)), z])
        filler = np.column_stack(
            [
                rng.uniform(-5, 5, 30),
                rng.uniform(-10, 0, 30),
                rng.uniform(0, height, 30),
            ]
        )
        return np.vstack([np.array(pts), filler])

    slim = cloud(12.0)
    heavy = cloud(25.0)
    assert abdomen_bulk(heavy) > abdomen_bulk(slim)


def test_check_expect_ranges():
    ext = {"height_z": 80.0, "width_x": 50.0, "thickness_y": 20.0}
    expect = {"height_z": [70.0, 110.0], "width_x": [40.0, 60.0], "thickness_y": [15.0, 30.0]}
    assert check_expect_ranges(ext, expect) == []
    failures = check_expect_ranges({**ext, "height_z": 50.0}, expect)
    assert failures and "height_z" in failures[0]


def test_affine_control_uniform_height_preserves_ratios(tmp_path: Path):
    if not ADULT_MALE.is_file():
        pytest.skip("adult_male.stl not present")
    match = tmp_path / "match.stl"
    # Short box "candidate" at ~80 cm height in PSD frame (y<=0, z<=0).
    _write_box_stl(match, x=40.0, y=20.0, z=80.0, origin=(-20.0, -20.0, -80.0))
    control = tmp_path / "control.stl"
    info = build_affine_control(ADULT_MALE, match, control, mode="uniform_height")
    assert info["mode"] == "uniform_height"
    # Uniform scale: all three scale components equal
    s = info["scale"]
    assert s[0] == pytest.approx(s[1])
    assert s[1] == pytest.approx(s[2])


def test_generate_reduced_writes_1000_face_preview(tmp_path: Path):
    from stl import mesh as stl_mesh

    from scripts.phantom_gen.generate_reduced import generate_reduced

    src = tmp_path / "box.stl"
    _write_box_stl(src, x=10.0, y=5.0, z=20.0, origin=(-5.0, -5.0, -20.0))
    base = stl_mesh.Mesh.from_file(str(src))
    big = stl_mesh.Mesh(np.zeros(1500, dtype=stl_mesh.Mesh.dtype))
    for i in range(1500):
        big.vectors[i] = base.vectors[i % len(base.vectors)]
    big_path = tmp_path / "big.stl"
    big.save(str(big_path))

    out = generate_reduced(big_path, target_faces=1000)
    assert out.name.endswith("_reduced_1000t.stl")
    assert len(stl_mesh.Mesh.from_file(str(out)).vectors) == 1000


def test_validate_basic_anchors_on_shipped_mesh():
    if not ADULT_MALE.is_file():
        pytest.skip("adult_male.stl not present")
    result = validate(ADULT_MALE, skip_phantom_load=False)
    assert result["checks"]["anchors_ok"]
    assert result["checks"]["scale_ok"]
    assert result["passed"]
