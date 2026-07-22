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

# All P0 (writes tmp/phantom_gen/…); reduced previews
python scripts/phantom_gen/run_catalog.py --priority P0 --out-dir tmp/phantom_gen/p0
python scripts/phantom_gen/generate_reduced.py tmp/phantom_gen/p0/*.stl --out-dir tmp/phantom_gen/p0

# Install passing STLs into phantom_data/ (privacy admission still required before commit)
python scripts/phantom_gen/run_catalog.py --priority P0 --install
```

Flags: `--only <id>`, `--priority P0|P1`, `--install`, `--skip-shape`, `--skip-phantom-load`,
`--json-report path`, `--blender /path/to/blender`.

Anti-balloon affine controls use gender-matched MPFB refs (`_shape_ref_adult_male` /
`_shape_ref_adult_female`), not shipped STLs. Refs are generated on demand into
`tmp/phantom_gen/` and are never installed.

### Spike (legacy single-step)

```bash
blender -b -P scripts/phantom_gen/mpfb_generate.py -- \
  --catalog scripts/phantom_gen/spike_catalog.json --catalog-id spike_adult_male
python scripts/phantom_gen/transform_to_psd_frame.py tmp/phantom_gen/spike_adult_male.obj \
  -o tmp/phantom_gen/spike_adult_male.stl
python scripts/phantom_gen/validate_phantom.py tmp/phantom_gen/spike_adult_male.stl
```

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
