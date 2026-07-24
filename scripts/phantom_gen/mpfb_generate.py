#!/usr/bin/env python3
"""Generate a full-body human mesh via MPFB inside Blender (headless).

Run only under Blender::

    export BLENDER_USER_RESOURCES=/path/to/tmp/blender_user
    blender -b -P scripts/phantom_gen/mpfb_generate.py -- --catalog-id spike_adult_male

Writes OBJ (and companion MTL if any) under ``tmp/phantom_gen/{id}.obj``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _repo_root_from_script() -> Path:
    # scripts/phantom_gen/mpfb_generate.py -> repo root
    return Path(__file__).resolve().parents[2]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    # Blender passes args after ``--``.
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser(description="MPFB headless human generator")
    parser.add_argument("--catalog-id", required=True, help="Entry id in spike/catalog JSON")
    parser.add_argument(
        "--catalog",
        default=str(_repo_root_from_script() / "scripts/phantom_gen/catalog_v1.json"),
        help="Path to catalog JSON (default: catalog_v1.json)",
    )
    parser.add_argument(
        "--out-dir",
        default=str(_repo_root_from_script() / "tmp/phantom_gen"),
        help="Output directory for OBJ",
    )
    return parser.parse_args(argv)


def _enable_mpfb(module_name: str) -> None:
    import addon_utils

    addon_utils.enable(module_name, default_set=True, persistent=True)


def _import_mpfb_services(module_name: str):
    # Extension package layout: bl_ext.blender_org.mpfb.services...
    base = module_name
    humanservice = __import__(f"{base}.services.humanservice", fromlist=["HumanService"])
    targetservice = __import__(f"{base}.services.targetservice", fromlist=["TargetService"])
    exportservice = __import__(f"{base}.services.exportservice", fromlist=["ExportService"])
    objectservice = __import__(f"{base}.services.objectservice", fromlist=["ObjectService"])
    rigservice = __import__(f"{base}.services.rigservice", fromlist=["RigService"])
    return (
        humanservice.HumanService,
        targetservice.TargetService,
        exportservice.ExportService,
        objectservice.ObjectService,
        rigservice.RigService,
    )


def _resolve_pose_path(repo_root: Path, entry: dict) -> Path | None:
    """Return pose JSON path from catalog ``pose`` or ``pose_file``, else None."""
    pose_file = entry.get("pose_file")
    pose_name = entry.get("pose")
    if pose_file:
        path = Path(pose_file)
        if not path.is_absolute():
            path = repo_root / "scripts" / "phantom_gen" / path
        return path
    if pose_name:
        return repo_root / "scripts" / "phantom_gen" / "poses" / f"{pose_name}.json"
    return None


def _apply_catalog_pose(
    basemesh,
    entry: dict,
    *,
    HumanService,
    ObjectService,
    RigService,
    repo_root: Path,
) -> None:
    """Optionally add default FK rig, apply pose dict, bake as rest pose."""
    pose_path = _resolve_pose_path(repo_root, entry)
    if pose_path is None:
        return
    if not pose_path.is_file():
        raise FileNotFoundError(f"Catalog pose file not found: {pose_path}")

    import bpy

    pose = json.loads(pose_path.read_text(encoding="utf-8"))
    armature = HumanService.add_builtin_rig(basemesh, "default", import_weights=True)
    ObjectService.deselect_and_deactivate_all()
    ObjectService.activate_blender_object(armature)
    bpy.ops.object.mode_set(mode="POSE", toggle=False)
    RigService.set_pose_from_dict(armature, pose, from_rest_pose=True)
    bpy.ops.object.mode_set(mode="OBJECT", toggle=False)
    RigService.apply_pose_as_rest_pose(armature)
    print(f"MPFB_POSE_OK file={pose_path.name} armature={armature.name}")


def _find_target_file(mpfb_root: Path, target_name: str) -> Path:
    """Locate ``{target_name}.target`` or ``.target.gz`` under MPFB data/targets."""
    targets_root = mpfb_root / "data" / "targets"
    matches = list(targets_root.rglob(f"{target_name}.target.gz")) + list(
        targets_root.rglob(f"{target_name}.target")
    )
    if not matches:
        raise FileNotFoundError(f"Detail target not found: {target_name} under {targets_root}")
    return matches[0]


def _bake_shape_keys_to_mesh(basemesh) -> None:
    """Collapse shape keys into the active mesh (Blender 4+/5)."""
    import bpy

    bpy.context.view_layer.objects.active = basemesh
    basemesh.select_set(True)
    if basemesh.data.shape_keys is not None:
        # convert applies evaluated geometry including shape keys
        bpy.ops.object.convert(target="MESH")


def main() -> int:
    import bpy

    args = _parse_args(sys.argv)
    catalog_path = Path(args.catalog)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    if args.catalog_id not in catalog["entries"]:
        print(f"ERROR: unknown catalog id {args.catalog_id!r}", file=sys.stderr)
        return 2

    entry = catalog["entries"][args.catalog_id]
    module_name = catalog.get("mpfb_module", "bl_ext.blender_org.mpfb")
    scale = float(catalog.get("scale", 0.1))

    _enable_mpfb(module_name)
    HumanService, TargetService, ExportService, ObjectService, RigService = _import_mpfb_services(
        module_name
    )

    macro = TargetService.get_default_macro_info_dict()
    macro.update(entry["macros"])

    # Clear default cube / startup objects
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    basemesh = HumanService.create_human(
        mask_helpers=True,
        detailed_helpers=True,
        extra_vertex_groups=True,
        feet_on_ground=True,
        scale=scale,
        macro_detail_dict=macro,
    )

    # Resolve MPFB extension root for detail targets
    mpfb_mod = __import__(module_name, fromlist=["*"])
    mpfb_root = Path(mpfb_mod.__file__).resolve().parent

    for detail in entry.get("detail_targets") or []:
        name = detail["name"]
        value = float(detail["value"])
        target_path = _find_target_file(mpfb_root, name)
        TargetService.load_target(basemesh, str(target_path), weight=value, name=name)
        TargetService.set_target_value(basemesh, name, value)

    _apply_catalog_pose(
        basemesh,
        entry,
        HumanService=HumanService,
        ObjectService=ObjectService,
        RigService=RigService,
        repo_root=_repo_root_from_script(),
    )

    bpy.context.view_layer.objects.active = basemesh
    basemesh.select_set(True)
    ExportService.bake_modifiers_remove_helpers(
        basemesh,
        bake_masks=True,
        bake_subdiv=False,
        remove_helpers=True,
        also_proxy=False,
    )
    _bake_shape_keys_to_mesh(basemesh)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_obj = out_dir / f"{args.catalog_id}.obj"

    bpy.ops.object.select_all(action="DESELECT")
    basemesh.select_set(True)
    bpy.context.view_layer.objects.active = basemesh
    bpy.ops.wm.obj_export(
        filepath=str(out_obj),
        export_selected_objects=True,
        export_materials=False,
        export_triangulated_mesh=True,
    )

    nverts = len(basemesh.data.vertices)
    npolys = len(basemesh.data.polygons)
    print(f"MPFB_GENERATE_OK id={args.catalog_id} verts={nverts} faces={npolys} out={out_obj}")
    if npolys < 1000:
        print("ERROR: face count too low", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
