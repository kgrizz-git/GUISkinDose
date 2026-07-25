# Phantom generation scripts

Implement per [`dev-docs/plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`](../../dev-docs/plans/AUTOMATED_PHANTOM_LIBRARY_PLAN.md).

**Policy:** shipped phantoms must use **true shape variety** (MPFB/MakeHuman parametric
targets via headless Blender). Global affine stretching of existing STLs is not an allowed
shipping method (affine controls are for validation only).

Working outputs go under gitignored `tmp/phantom_gen/`.

## Environment (Phase 0 — local to this repo)

Blender + MPFB are configured under **project-local** `tmp/blender_user/` via
`BLENDER_USER_RESOURCES` so host Blender preferences are not modified.

Recorded on 2026-07-21 (macOS arm64):

| Component | Version / notes |
|---|---|
| Blender | 5.2.0 LTS (`/opt/homebrew/bin/blender`) |
| MPFB | 2.0.16 (`bl_ext.blender_org.mpfb`, build info 20260613) |
| System asset pack | Not required for basemesh + macro/detail target spike |

### One-time setup

```bash
# Blender (host install; already done via brew cask on this machine)
brew install --cask blender

# Isolated Blender user dir + online access + MPFB extension
export BLENDER_USER_RESOURCES="$PWD/tmp/blender_user"
mkdir -p "$BLENDER_USER_RESOURCES" tmp/phantom_gen
blender -b --python-expr "import bpy; bpy.context.preferences.system.use_online_access=True; bpy.ops.wm.save_userpref()"
blender -b --command extension sync
blender -b --command extension install mpfb --enable
```

Optional local overrides (gitignored): `scripts/phantom_gen/env.local.json`

```json
{ "blender": "/opt/homebrew/bin/blender" }
```

## Catalog + orchestrator (Phase 1+)

Phenotype presets: `scripts/phantom_gen/catalog_v1.json` (P0/P1 rows; no affine `base_mesh`).

```bash
export BLENDER_USER_RESOURCES="$PWD/tmp/blender_user"
source .venv/bin/activate

# One entry
python scripts/phantom_gen/run_catalog.py --only pediatric_5y_male

# Reduced-preview deps (quadric decimation; do not ship triangle-subsample fallbacks)
pip install -e ".[phantom-gen]"

# All P0 (writes tmp/phantom_gen/…); reduced previews
python scripts/phantom_gen/run_catalog.py --priority P0 --out-dir tmp/phantom_gen/p0
python scripts/phantom_gen/generate_reduced.py tmp/phantom_gen/p0/*.stl --out-dir tmp/phantom_gen/p0

# Install passing STLs into phantom_data/ (privacy admission still required before commit)
python scripts/phantom_gen/run_catalog.py --priority P0 --install
```

Flags: `--only <id>`, `--priority P0|P1`, `--install`, `--skip-shape`, `--skip-phantom-load`,
`--json-report path`, `--blender /path/to/blender`.

Optional catalog `"pose": "arms_down_default_fk"` (see `poses/arms_down_default_fk.json`) adds the
MPFB default FK rig, applies the pose, and bakes it as rest before export. Used by shipped
`*_arms_down` rows; A-pose catalog rows omit the field.

Anti-balloon affine controls use gender-matched MPFB refs (`_shape_ref_adult_male` /
`_shape_ref_adult_female`), not shipped STLs. Refs are generated on demand into
`tmp/phantom_gen/` and are never installed.

### Spike (legacy single-step)

```bash
blender -b -P scripts/phantom_gen/mpfb_generate.py -- \
  --catalog scripts/phantom_gen/spike_catalog.json --catalog-id spike_adult_male
python scripts/phantom_gen/transform_to_psd_frame.py tmp/phantom_gen/spike_adult_male.obj \
  -o tmp/phantom_gen/spike_adult_male.stl --force-flip-y
python scripts/phantom_gen/validate_phantom.py tmp/phantom_gen/spike_adult_male.stl
```

MPFB/Blender OBJ exports are often near-symmetric in depth, so the default
`flip_y_if_needed` heuristic is a no-op and can leave meshes **face-down**
(face toward the table at max Y). Catalog generation (`run_catalog.py`) always
passes ``force_flip_y=True``. For one-off CLI transforms of MPFB OBJs, use
``--force-flip-y`` so the posterior lands at max Y (face-up supine).

## Fun / demo (non-clinical) phantom ingest

Demo phantoms (Cosmic Buddha, Petite Herculanaise, Ramesses II, Steamboat Willie)
are statues/cartoons ingested via `ingest_fun_mesh.py` + `fun_mesh_manifest.json`.
They are **non-clinical** and must be labeled `(demo)`. Full plan:
[`dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`](../../dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md).

**Requires** `trimesh>=4` + `fast-simplification` (+ `networkx` / `scikit-image` for hole-fill /
voxel remesh):

```bash
pip install -e ".[phantom-gen]"
```

### Download friction

Many museum / Cults / Commons pages need a browser login or an interactive
download — do **not** assume a stable unauthenticated `curl` URL. Save the
retrieved file under `tmp/fun_phantoms/raw/{id}/` (gitignored) and record the
retrieval date + exact source page in provenance. Never commit raw multi-MB
museum dumps.

### Scale / transform order (critical)

```
raw mesh
  → Euler rotate (degrees, sxyz)
  → uniform scale so the height-axis span == height_cm
  → fill/cap open boundaries (+ pre-transform fix_winding/fix_normals)
    OR --voxel-pitch remesh (solid voxel + marching cubes; e.g. Ramesses II)
  → PSD anchor: transform_to_psd_frame(obj_y_up=False,
        meters_to_cm_if_small=False, force_flip_y=<flip_y>, flip_y_if_needed=False)
  → RE-FIX winding/normals (a Y-flip reverses triangle handedness)
  → quadric decimate to the shipping budget (NO subsample)
  → RE-FIX normals again (decimation rebuilds face normals)
  → write {id}.stl → validate --require-trimesh
```

Because the mesh is already Z-up (after rotate) and already in cm, pass
`--no-obj-y-up` and `--no-unit-detect` to `transform_to_psd_frame` to avoid a
double `×100` when the span still looks "small". The `flip_y` manifest boolean
maps to the transform as: `flip_y: true` → `--force-flip-y`; `flip_y: false` →
`--no-flip-y` (also disables the asymmetric heuristic). Statue/cartoon bounding
boxes are near-symmetric, so **always** re-run `fix_winding` / `fix_normals`
after the PSD transform (and again after decimate).

When `fill_holes` cannot close open museum scans, pass `--voxel-pitch` (cm) or set
`voxel_pitch` in the manifest (needs `scikit-image`). Never ship with
`--allow-subsample`.

### Ingest CLI

```bash
source .venv/bin/activate
python scripts/phantom_gen/ingest_fun_mesh.py \
  --id cosmic_buddha \
  --input tmp/fun_phantoms/raw/cosmic_buddha/source.stl \
  --rotate-deg 90,0,0 \
  --height-cm 151 \
  --flip-y \
  --target-faces 6000 \
  --out-dir tmp/fun_phantoms/psd
```

Values omitted on the CLI fall back to the locked entry in
`fun_mesh_manifest.json` (keyed by `--id`). Use `--preview-only` during
orientation discovery to print post-transform extents / face count without
writing or validating. Never pass `--allow-subsample` to `generate_reduced` /
the decimator for shipping — subsample produces disconnected triangle soup and
is for tests/emergencies only.

Then build a reduced preview separately (default ~3000 faces; also no subsample):

```bash
python scripts/phantom_gen/generate_reduced.py tmp/fun_phantoms/psd/cosmic_buddha.stl \
  --out-dir tmp/fun_phantoms/psd
# optional legacy detail: --target-faces 1000
```

### Fun-mode validation (`--require-trimesh`)

`validate_phantom.py --require-trimesh` is stricter than the clinical validator
for shipped demo meshes:

- **hard-fails** if trimesh is missing (`watertight is None`) or the mesh is not
  watertight (clinical mode tolerates `None`);
- enforces a `1000 ≤ faces ≤ 20000` ceiling (clinical mode allows up to 40k);
- runs a **face-up** gate — in the superior `--face-up-band-frac` Z band (default
  `0.12`; use `0.20` for the headless Cosmic Buddha), requires
  `y_min_headband ≤ y_max − face_up_frac × thickness_y` (default
  `--face-up-frac 0.55`);
- runs an **outward-normal** ray gate (dependency-free Möller–Trumbore first-hit;
  no ``rtree``/embree required): a majority
  of sampled first hits must satisfy `dot(n, ray_direction) < 0`.

```bash
python scripts/phantom_gen/validate_phantom.py tmp/fun_phantoms/psd/cosmic_buddha.stl \
  --require-trimesh --face-up-band-frac 0.20
```

Run fun-mode gates on the **full** `{id}.stl` only, not `*_reduced_*t.stl` previews.

> Mesh asset licenses (CC0 / CC BY / CC BY-SA) are tracked in
> `phantom_data/NOTICE_*.txt` + `dev-docs/references/fun_phantom_provenance.md`,
> **not** in `dev-docs/THIRD_PARTY_NOTICES.md` (Python packages only).

## Tests

Unit tests (no Blender):

```bash
source .venv/bin/activate
pytest tests/unittests/test_phantom_gen_pipeline.py -q
```

Blender/MPFB smoke (skipped automatically when Blender or MPFB is missing):

```bash
export BLENDER_USER_RESOURCES="$PWD/tmp/blender_user"
pytest -m blender_mpfb tests/unittests/test_phantom_gen_blender_mpfb.py -q
```

CI runs the unit suite; `blender_mpfb` tests are for local regeneration only.
