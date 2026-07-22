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
from scripts.phantom_gen.validate_phantom import (
    abdomen_bulk,
    extents,
    face_up_ok,
    head_ratio,
    validate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOG_V1 = REPO_ROOT / "scripts" / "phantom_gen" / "catalog_v1.json"
FUN_MANIFEST = REPO_ROOT / "scripts" / "phantom_gen" / "fun_mesh_manifest.json"
ADULT_MALE = REPO_ROOT / "src" / "mypyskindose" / "phantom_data" / "adult_male.stl"
FUN_MESH_IDS = ("cosmic_buddha", "petite_herculanaise", "ramesses_ii", "steamboat_willie")


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


def test_transform_force_flip_y_mirrors_near_symmetric_depth():
    """MPFB-like near-symmetric depth: force_flip_y puts the nose toward −Y (face-up)."""
    rng = np.random.default_rng(2)
    n = 300
    # Y-up meters; depth (Z) nearly symmetric so the heuristic is a no-op.
    vertices = np.column_stack(
        [
            rng.uniform(-0.2, 0.2, n),
            rng.uniform(0.0, 1.7, n),
            rng.uniform(-0.2, 0.2, n),
        ]
    )
    # Mark a "nose" at +Z (Blender depth) mid-face so after remap it lands on +Y without force.
    nose = np.array([[0.0, 1.55, 0.25], [0.0, 1.54, 0.24], [0.0, 1.56, 0.24]])
    vertices = np.vstack([vertices, nose])
    no_force = transform_to_psd_frame(vertices, obj_y_up=True, force_flip_y=False)
    forced = transform_to_psd_frame(vertices, obj_y_up=True, force_flip_y=True)

    def mid_sag_head_tips(arr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        zmax = float(arr[:, 2].max())
        head = arr[arr[:, 2] > zmax - 20.0]
        strip = head[np.abs(head[:, 0]) < 3.0]
        return strip[strip[:, 1].argmin()], strip[strip[:, 1].argmax()]

    tn_f, tp_f = mid_sag_head_tips(forced)
    tn_n, tp_n = mid_sag_head_tips(no_force)
    # Face-up (forced): more inferior tip (nose) at ymin (−Y).
    assert tn_f[2] < tp_f[2] - 1.0
    # Face-down (no force): more inferior tip at ymax (toward table).
    assert tp_n[2] < tn_n[2] - 1.0


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

    # Unit-test mesh is degenerate duplicated faces; allow subsample so CI does
    # not require trimesh/fast-simplification. Shipping uses quadric decimation.
    out = generate_reduced(big_path, target_faces=1000, allow_subsample=True)
    assert out.name.endswith("_reduced_1000t.stl")
    assert len(stl_mesh.Mesh.from_file(str(out)).vectors) == 1000


def test_validate_basic_anchors_on_shipped_mesh():
    if not ADULT_MALE.is_file():
        pytest.skip("adult_male.stl not present")
    result = validate(ADULT_MALE, skip_phantom_load=False)
    assert result["checks"]["anchors_ok"]
    assert result["checks"]["scale_ok"]
    assert result["passed"]


# --- Fun / demo (non-clinical) ingest scaffolding tests -----------------------


def test_fun_mesh_manifest_has_all_four_ids():
    manifest = json.loads(FUN_MANIFEST.read_text(encoding="utf-8"))
    meshes = manifest["meshes"]
    for mesh_id in FUN_MESH_IDS:
        assert mesh_id in meshes, mesh_id
        entry = meshes[mesh_id]
        # Required scaffolding fields per the plan schema.
        for key in ("id", "source_url", "license", "attribution", "height_cm", "flip_y", "rotate_deg"):
            assert key in entry, f"{mesh_id} missing {key}"
        assert entry["id"] == mesh_id
        assert len(entry["rotate_deg"]) == 3
    # Cosmic Buddha uses the headless superior-20% face-up band.
    assert meshes["cosmic_buddha"]["face_up_band_frac"] == pytest.approx(0.20)
    # Steamboat records a fallback source note.
    assert "fallback_notes" in meshes["steamboat_willie"]


def test_manifest_entry_merges_defaults():
    from scripts.phantom_gen.ingest_fun_mesh import load_manifest, manifest_entry

    manifest = load_manifest(FUN_MANIFEST)
    entry = manifest_entry(manifest, "petite_herculanaise")
    # Inherits default target_faces unless overridden; petite overrides it to 6000.
    assert entry["target_faces"] == 6000
    assert entry["license"] == "CC BY-SA"
    with pytest.raises(KeyError):
        manifest_entry(manifest, "does_not_exist")


def test_face_up_gate_passes_for_face_up_body():
    """A body spanning the full Y thickness in the head band is face-up."""
    rng = np.random.default_rng(3)
    n = 500
    # PSD frame: y in [-20, 0], z in [-170, 0]; full Y span everywhere incl. head band.
    verts = np.column_stack(
        [
            rng.uniform(-15.0, 15.0, n),
            rng.uniform(-20.0, 0.0, n),
            rng.uniform(-170.0, 0.0, n),
        ]
    )
    passed, detail = face_up_ok(verts, face_up_frac=0.55, band_frac=0.12)
    assert passed, detail


def test_face_up_gate_fails_for_face_down_body():
    """Head band hugging the posterior (near y_max) is face-down and must fail."""
    rng = np.random.default_rng(4)
    torso = np.column_stack(
        [
            rng.uniform(-15.0, 15.0, 400),
            rng.uniform(-20.0, 0.0, 400),
            rng.uniform(-170.0, -25.0, 400),  # below head band
        ]
    )
    # Head band (top ~12% of a 170 cm body -> z >= -20.4) hugging the table (y near 0).
    head = np.column_stack(
        [
            rng.uniform(-10.0, 10.0, 120),
            rng.uniform(-2.0, 0.0, 120),
            rng.uniform(-18.0, 0.0, 120),
        ]
    )
    verts = np.vstack([torso, head])
    passed, _ = face_up_ok(verts, face_up_frac=0.55, band_frac=0.12)
    assert not passed


def _make_icosphere_stl(path: Path, *, radius: float, subdivisions: int = 3):
    """Write a watertight icosphere translated into the PSD frame (anchors ~0)."""
    import trimesh

    sphere = trimesh.creation.icosphere(subdivisions=subdivisions, radius=radius)
    # Anchor: x_mid=0, y_max=0, z_max=0 (sphere centered at origin -> shift by -radius).
    sphere.apply_translation([0.0, -radius, -radius])
    sphere.export(str(path), file_type="stl")
    return sphere


def test_outward_normals_gate_detects_inverted_normals(tmp_path: Path):
    trimesh = pytest.importorskip("trimesh")
    from scripts.phantom_gen.validate_phantom import outward_normals_ok

    good = tmp_path / "sphere_out.stl"
    _make_icosphere_stl(good, radius=40.0)
    passed_good, detail_good = outward_normals_ok(good)
    assert passed_good, detail_good

    # Invert the mesh -> normals point inward -> gate must fail.
    mesh = trimesh.load(str(good), force="mesh")
    mesh.invert()
    bad = tmp_path / "sphere_in.stl"
    mesh.export(str(bad), file_type="stl")
    passed_bad, _ = outward_normals_ok(bad)
    assert not passed_bad


def test_validate_fun_mode_passes_on_watertight_sphere(tmp_path: Path):
    pytest.importorskip("trimesh")
    stl = tmp_path / "sphere.stl"
    _make_icosphere_stl(stl, radius=40.0, subdivisions=3)  # ~1280 faces, height 80 cm
    result = validate(stl, require_trimesh=True, skip_phantom_load=True)
    assert result["checks"]["watertight_ok"], result["checks"]["watertight"]
    assert result["checks"]["face_count_ok"], result["checks"]["face_count"]
    assert result["checks"]["face_count_ceiling"] == 20000
    assert result["checks"]["anchors_ok"], result["checks"]["extents"]
    assert result["checks"]["face_up_ok"], result["checks"]["face_up"]
    assert result["checks"]["outward_normals_ok"], result["checks"]["outward_normals"]
    assert result["passed"]


def test_ingest_fun_mesh_preview_anchors(tmp_path: Path):
    pytest.importorskip("trimesh")
    from scripts.phantom_gen.ingest_fun_mesh import ingest_fun_mesh

    # A simple upright box as the "raw" mesh; ingest must anchor y_max/z_max/x_mid ~0.
    raw = tmp_path / "raw.stl"
    _write_box_stl(raw, x=30.0, y=20.0, z=60.0, origin=(-15.0, -10.0, 0.0))
    report = ingest_fun_mesh(
        mesh_id="unit_box",
        input_path=raw,
        rotate_deg=(0.0, 0.0, 0.0),
        height_cm=170.0,
        height_axis="z",
        target_faces=6000,
        flip_y=False,
        out_dir=tmp_path / "psd",
        preview_only=True,
    )
    ext = report["post_transform_extents"]
    assert abs(ext["y_max"]) < 1.0
    assert abs(ext["z_max"]) < 1.0
    assert abs(ext["x_mid"]) < 1.0
    # Height axis (z span 60) uniformly scaled to 170 cm.
    assert ext["height_z"] == pytest.approx(170.0, abs=1.0)


def test_ingest_fun_mesh_writes_and_validates_sphere(tmp_path: Path):
    pytest.importorskip("trimesh")
    from scripts.phantom_gen.ingest_fun_mesh import ingest_fun_mesh

    # Watertight raw sphere (radius 25 -> height 50) scaled up to 170 cm by ingest.
    raw = tmp_path / "raw_sphere.stl"
    _make_icosphere_stl(raw, radius=25.0, subdivisions=3)
    report = ingest_fun_mesh(
        mesh_id="unit_sphere",
        input_path=raw,
        rotate_deg=(0.0, 0.0, 0.0),
        height_cm=170.0,
        height_axis="z",
        target_faces=2000,
        flip_y=False,
        out_dir=tmp_path / "psd",
        preview_only=False,
    )
    out = Path(report["written"])
    assert out.is_file()
    assert out.name == "unit_sphere.stl"
    assert report["validation_passed"], report["validation"]["checks"]
