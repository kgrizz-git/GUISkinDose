# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**Version source of truth:** the package version in `pyproject.toml` (currently `1.0.0`).
**First GUISkinDose version is `1.0.0`** — a new distribution identity, formerly
MyPySkinDose `25.2.0` / a fork of PySkinDose. Historical sections through `[25.2.0]`
remain MyPySkinDose history. Bump `pyproject.toml` when releasing.

This file records **notable** user-facing changes (features, fixes, UI updates). 
For maintainer-facing changes (CI/harness, refactors, privacy gates, tests), see [dev-docs/MAINTENANCE_LOG.md](dev-docs/MAINTENANCE_LOG.md).
That keeps SemVer and contributor history organized.

**GitHub Release notes are narrower:** summarize what end users need when upgrading; point readers here for the full user-facing list. See
[dev-docs/RELEASES_AND_DISTRIBUTION.md](dev-docs/RELEASES_AND_DISTRIBUTION.md).

## [Unreleased]

### Fixed

- **Multi-exam export paired surviving exams with the wrong input after exclusions**
  (2026-09-05) — GUI/CLI export builders indexed ``loaded_exams`` / ``inputs`` by
  position in ``MultiExamResult.exams``. When a middle exam was excluded, later
  successful exams silently received another exam's normalized frame, provenance,
  and transform metadata in the report. Matching now uses the opaque ``Exam N``
  label (original load index). Supersedes conflicted Cursor automation PR #72
  after the ``mypyskindose`` → ``guiskindose`` rename.

### Changed

- **Added docstring inventory tooling (maintainer-facing)** (2026-09-06) — new advisory
  `scripts/check_docstring_inventory.py` reports public symbols under `src/` missing
  docstrings, backing the phased documentation-assessment sweep. No end-user behavior change.
- **GitHub repository renamed to `GUISkinDose`** (2026-09-04) — the fork (still `rvbCMTS/PySkinDose` upstream)
  and the SonarCloud project (key flipped automatically) now carry the product name. Live URLs, `pyproject.toml`
  `[project.urls]`, `CITATION.cff`, community files, issue templates, the changelog footer links, and
  `sonar-project.properties` now point at `github.com/kgrizz-git/GUISkinDose` /
  `kgrizz-git_GUISkinDose`; the stale-brand gate rejects the old live URLs/keys instead of allowlisting them.
  Old GitHub links keep working via redirects. Historical `[25.x]` changelog prose and upstream links are unchanged.

## [1.0.0] - 2026-09-03

> **Identity lock:** `pyproject.toml` is `guiskindose` **`1.0.0`**. This is a new
> distribution identity, formerly MyPySkinDose `25.2.0` / a fork of PySkinDose.
> Historical sections through `[25.2.0]` below remain MyPySkinDose history.

### Added

### Fixed

- **GHSA-763m-79hh-57f2 / GHSA-23w6-3w8w-8484 / GHSA-jp53-mhqp-8xcg: bumped core `pypdf`** (2026-09-01) —
  raised the minimum to `pypdf>=6.16.1` so the lockfile no longer pins the vulnerable `6.15.0`
  (resolved `6.16.2`).
  Privacy admission uses `pypdf` to parse PDFs (`PdfReader`, text/metadata/attachments); runtime
  export PDFs still use reportlab. The pin is project-visible in `pyproject.toml` and survives
  future `uv lock --upgrade` runs.

- **GHSA-8423-8fgw-73vq / GHSA-wwv5-g3v4-889x / GHSA-mpf4-983q-p7j4: bumped transitive `tornado`**
  (2026-09-01) — added explicit `tornado>=6.5.8` to the `docs` and `notebooks` extras (pulled by
  `ipykernel` / JupyterLab, not the NiceGUI GUI server) so the lockfile no longer pins `6.5.7`.
  The pin is project-visible in `pyproject.toml` and survives future `uv lock --upgrade` runs.

- **PYSEC-2026-3726 / GHSA-vp2x-qp44-57v7: bumped transitive dev-only `nltk`** (2026-08-30) — added
  explicit `nltk>=3.10.3` minimum-version constraint to `[project.optional-dependencies].dev` so the
  lockfile no longer pins the vulnerable `3.10.0` (transitive via `safety`; `3.10.2` remains vulnerable).
  The pin is project-visible in `pyproject.toml` and survives future `uv lock --upgrade` runs.
  Superseded in this release: `safety` was removed from the dev extra on 2026-09-03, taking `nltk` and
  the pin with it (see `### Removed` below).

- **Basedpyright `corrections.py` type error** (2026-08-30) — replaced
  `min(fsl_tab, key=lambda x: abs(x - fsl_mean))` with an `np.argmin` idiom
  to eliminate a `SupportsAbs` typing friction between `numpy.floating` and
  stdlib `abs()`. Semantically identical; no behavior change.

### Changed

- **GHSA-8mgp-746c-j5xp / CVE-2026-81726: `nltk` still unpatched** (2026-09-02) —
  added `[tool.uv.audit] ignore-until-fixed` for the new model-artifact pathsec bypass
  in transitive dev-only `nltk` 3.10.3 (via `safety`). Superseded in this release: `safety` was
  dropped from the dev extra on 2026-09-03, which removed `nltk` — and both the ignore and the
  pin — entirely (see `### Removed` below).

- **Stale-brand CHANGELOG scan tightened** (2026-09-02) — `CHANGELOG.md` is no longer a
  whole-file stale-brand exemption. Unreleased is scanned (rename-prose patterns allowed);
  historical `## [25.` sections remain skipped. Sphinx `docs/source/user/install.md` now
  leads with GitHub install until PyPI exists; `PACKAGE_INSTALL.md` examples use `1.0.0`.
  Dropped leftover `pyskindose.egg-info*` from setuptools `exclude`.

- **First `guiskindose` package version is `1.0.0`** (2026-09-02) — `pyproject.toml`
  `version` and Sphinx `release` set together; `[project.scripts] guiskindose` points at
  `guiskindose.__main__:cli`. `LIVE_PACKAGE_NAME` is `guiskindose` so leftover pre-rename
  brand strings fail CI. Dual-read of `~/.mypyskindose/` and
  `MYPYSKINDOSE_SHOW_DEMO_PHANTOMS` remains. Formerly MyPySkinDose `25.2.0` / a fork of
  PySkinDose.

- **First GUISkinDose version locked at `1.0.0`** (2026-09-02) — new PyPI/import identity,
  not MyPySkinDose `26.0.0`, not a patch on `25.2.0`, and not an imitation of upstream
  PySkinDose. Package `name` was already `guiskindose`; version was `25.2.0` until the
  packaging commit in this PR set `1.0.0`. GitHub Release notes and the `[1.0.0]` changelog
  section must say this was formerly MyPySkinDose `25.2.0` / a fork of PySkinDose. Plan:
  [dev-docs/plans/archive/GUISKINDOSE_RENAME_PLAN.md](dev-docs/plans/archive/GUISKINDOSE_RENAME_PLAN.md).

- **GitHub/Sonar/URL follow-up plan** (2026-09-02) — after the in-repo package rename is on
  `main`, rename the GitHub fork to `GUISkinDose`, then SonarCloud, then live URLs/`origin`.
  Not blocked on PyPI; not part of the mechanical-rename PR. Plan:
  [dev-docs/plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md](dev-docs/plans/archive/GUISKINDOSE_GITHUB_RENAME_PLAN.md).

- **Package directory and import path are `guiskindose`** (2026-09-02) — `git mv src/mypyskindose
  src/guiskindose`; `pyproject.toml` `name` / `packages.find` follow. Version was `25.2.0`
  until the packaging commit in this PR set `1.0.0`. Legacy config reads still use
  `~/.mypyskindose/gui.json` and `.mypyskindose.local.json` when the new files are absent.
  Markdown links and backtick paths that pointed at `src/mypyskindose` now point at
  `src/guiskindose`. User-facing brand (GUI title, CLI description, export `APP_NAME`,
  launchers, Sphinx, install guide, issue templates) is **GUISkinDose** / `guiskindose`.
  Tests now import `guiskindose` so the suite can collect. The console script and
  `LIVE_PACKAGE_NAME = "guiskindose"` landed in later commits of this PR.
  Semgrep rule IDs and live GitHub/Sonar URLs are unchanged.
  Bandit pre-commit `files:` and CI bandit/compileall/coverage now scan `src/guiskindose`.
  Blocking Semgrep `paths.include` filters and `.phi-scanner.yml` HVL exclusions now
  point at `src/guiskindose` (rule IDs stay `mypyskindose-*`). `.phi-scanbaseline`
  `file_path` entries for correction CSVs were path-rewritten; hashes unchanged.

- **GUI config saves now write `~/.guiskindose/gui.json`** (2026-09-02) — `save_gui_config()`
  persists to the new home path (creating the directory as needed). Reads still fall back to
  `~/.mypyskindose/gui.json` when the new file is absent. When both exist, load–modify–save
  (onboarding dismiss, native-window prefs) updates the new file. The legacy directory is not
  deleted.

- **PySkinDoseOutput canonical lowercase API** (2026-08-05) — multi-exam and rich-export
  consumers now use lowercase object attributes (`psd`, `air_kerma`, `dose_map`, correction
  arrays, `events`) plus `patient_export()` and `sparse_hit_indices()`. The former uppercase
  object attributes have been deliberately removed to eliminate case-insensitive field
  collisions. `kerma_meter_correction` and `kerma_corrected` are now normalized to
  `list[float]` after construction; when both are omitted, the object populates unmetered
  defaults. Dict/JSON export keys, values, and schema version are unchanged.
### Fixed

- **AppSec: spreadsheet formula injection via export headers** (2026-08-03) —
  `neutralize_dataframe()` now prefixes dangerous formula characters on column
  names and index labels (not only cell values), so Data-tab CSV/XLSX/TXT exports
  cannot emit live Excel formulas from attacker-controlled tabular headers
  (CWE-1236).
- **AppSec: `human_mesh` path traversal** (2026-08-03) — string mesh stems are
  allow-listed as simple basenames and resolved with `Path.resolve()` +
  `is_relative_to(phantom_data/)`; unknown or escaping stems are rejected before
  STL load (custom meshes remain the trusted tuple form).
- **AppSec: XLSX decompression bomb bypass of upload size cap** (2026-08-03) —
  tabular Excel reads enforce uncompressed ZIP member/total budgets (declared
  sizes plus streamed inflate-byte counts) and a streamed row×column/cell budget
  before full sheet materialization, so a crafted workbook cannot OOM the process
  solely by high compression ratio or forged ZIP size metadata (CWE-409).
- **Below-floor kVp `skip` export length desync** (2026-08-02) — when
  `below_floor_kvp_policy=skip` dropped events inside `calculate_dose`, dict/JSON
  export still passed the pre-skip `data_norm` into `PySkinDoseOutput`. Single-exam
  GUI/API runs raised a Hits length `ValueError`; multi-exam runs caught that error
  and silently omitted the exam from aggregate PSD. `calculate_dose` now returns the
  post-policy event frame as a third value for `analyze_data` / `_process_exam` export
  packaging (no internal `_effective_data_norm` key on the output dict).
- **Below-floor kVp `skip` of all events** (2026-08-03) — dict/JSON export crashed in
  `EventOutput` (`zip(*[])` / event-0 setup beam) when every irradiation event was
  dropped. Empty post-skip frames now export as zero-event results (PSD / air kerma
  0) instead of raising.
- **Multi-exam calculation failure warnings** (2026-08-03) — when one exam raises during
  a multi-exam run, warnings now state that the exam was excluded from the aggregate
  PSD (with exception class), no-output exclusions use distinct wording, Calculate
  reports `N of M` successes, and the Results tab surfaces the run-warning list.
  `MultiExamResult` exposes `exams_attempted` / `exams_excluded` so GUI/export do not
  recompute those counts from warning text. Import / per-exam warnings for excluded
  exams are preserved on the run warning list (they previously dropped because no
  `ExamResult` was created).

### Removed

- **`safety` development dependency removed** (2026-09-03) — dropping unused `safety` from the
  `dev` extra also removes its unpatched transitive `nltk` exposure
  (`GHSA-8mgp-746c-j5xp` / CVE-2026-81726 and the earlier `nltk` pin for PYSEC-2026-3726).
  Dependency auditing continues via `uv audit` and `pip-audit`.

### Changed

- **CLI `--help` corrected** (2026-07-27) — `prog` was still `"PySkinDose"` (upstream name) and
  the description said "Python version 3.8"; now reads `mypyskindose` and "Python 3.11+" with an
  expanded description that lists accepted input types (RDSR, JSON, tabular). Pure user-facing text;
  no behaviour change.

- **Fail-fast CLI export** (2026-07-27) — `run_cli_export` now validates the destination
  (exists / directory / tracked / ignored) via `validate_output_path` *before* the dose
  calculation and report render, so an existing-file/`--force` error returns immediately instead
  of after a full compute. `write_report` still re-validates atomically.
- **PHI-filename name list expanded** (2026-07-27) — grew `phi_filename.name_tokens` from ~132 to
  269 curated given/surname tokens (modern SSA names + distinct US/international surnames), deliberately
  excluding the worst English/code collisions to limit false positives on a blocking gate; the latest
  batch folded in common UK/Indian surnames (e.g. `davies`, `hughes`, `kumar`, `sharma`); verified zero
  collisions across the current tree.
- **PHI-filename accession floor tightened** (2026-07-27) — split the accession structural pattern
  so the abbreviation `acc` requires a 5-digit run (avoids year-tag false positives like `acc-2024`),
  while the unambiguous full word `accession` keeps a 1-digit floor. Documented the deliberate
  decision to scan name tokens over the full path (directory components included) for maximal PHI
  recall in a medical-imaging repo, with `allowlist_patterns` as the org-directory escape hatch.
  Verified still zero hits across the tree.

### Fixed

- **PHI-filename allowlist case-insensitivity** (2026-07-27) — `phi_filename_findings` now matches
  `allowlist_patterns` with `fnmatch.fnmatchcase` over lowercased path and pattern, so exemptions
  are deterministically case-insensitive on every OS (`fnmatch.fnmatch` applied `os.path.normcase`,
  which is case-sensitive on Linux). Reported by CodeRabbit on PR #37.

### Added

- **Kerma-meter correction factors** (2026-07-26) — optional per-(equipment × tube)
  calibration `CF = (real measured dose) / (unit reported dose)` applied to reported
  `K_IRP` before physics corrections. Lookup via CSV/TSV/XLSX/JSON or GUI prompt;
  fail-soft to `default_factor` (1.0). Reported `air_kerma` / `OUTPUT_KEY_KERMA` stay
  backward-compatible; corrected values are additive (`air_kerma_corrected`,
  `kerma_corrected`, `k_meter`). CLI: `--kerma-meter-correction`,
  `--kerma-meter-correction-file`, `--kerma-meter-correction-mode`,
  `--kerma-meter-explicit-label`. When CF is enabled, kerma-weighted export correction
  stats use corrected K_IRP (see footnote in Rich Export corrections section).
- **Fork maintainer community baseline** (2026-07-26) — `CONTRIBUTING.md`,
  `SECURITY.md`, `SUPPORT.md`, `CODE_OF_CONDUCT.md`, `GOVERNANCE.md`,
  `CITATION.cff`, privacy-aware GitHub issue forms, and a PR template. README
  states research/education/QA intended use, **not FDA-cleared**, and that
  physicists/physicians remain responsible for reviewing results and patient-care
  decisions. Issues and Discussions enabled; ideas and submissions welcome there
  (prefer those channels over cold PRs). Private intake for security, privacy
  incidents, and CoC reports is GitHub private vulnerability reporting. See
  `dev-docs/FORK_MAINTAINER_GUIDE.md`.
### Changed

### Security

### Fixed

- **Export kerma-array validation** (2026-07-26) — `PySkinDoseOutput` uses `len(data_norm)` as
  the event count, rejects hits/kerma length mismatches, and requires
  `kerma_meter_correction` / `kerma_corrected` to be both provided or both omitted.
### Added

- **`_reduced_3000t` phantom preview companions** (2026-07-24) — ~3k-face reduced STLs for all
  shipped clinical human meshes (alongside existing `_reduced_1000t`). Settings preview and
  `plot_procedure` prefer `_reduced_3000t` when present; dose still uses the full STL.
  `generate_reduced` default target is 3000 faces. SemVer: **patch** on release (preview assets).

### Changed

- **Settings phantom preview caption** (2026-07-24) — Notes that the panel uses a reduced mesh for
  display speed while dose calculation and Geometry setup/event plots use the full mesh.

### Removed

- **Demo / non-clinical phantoms unshipped** (2026-07-24) — `demo_cosmic_buddha`,
  `demo_ramesses_ii`, and `demo_steamboat_willie` (and reduced companions / NOTICE sidecars)
  removed from `phantom_data/`. Local recovery stash (gitignored) with attribution notes:
  `tmp/phantom_data_demo_stash/README.md`. SemVer: **minor** on release (library surface shrinks).

### Changed

- **Demo phantoms enable sources** (2026-07-23) — `show_demo_phantoms_enabled()` now checks, in
  order: process env / repo `.env` (`MYPYSKINDOSE_SHOW_DEMO_PHANTOMS`), gitignored
  `.mypyskindose.local.json`, then `~/.mypyskindose/gui.json`. Default remains off.

- **Pediatric 5y male reinstalled face-up** (2026-07-22) — Replaced a drifted shipped STL with a
  fresh catalog regenerate; head now rests near the table like the female peer. `run_catalog`
  enforces a clinical `face_up_ok` gate after transform. See
  `dev-docs/assessments/PEDIATRIC_5Y_MALE_ORIENTATION_FIX_2026-07-22.md`.

- **Steamboat Willie face-up correction** (2026-07-23) — Locked `rotate_deg=[0,0,-90]` with
  `flip_y=true` after visual anterior review (prior Rz +90 left the character face-down; ears can
  fool the headband face-up gate). Inventory hashes updated.

- **Steamboat Willie re-oriented supine** (2026-07-22) — Re-ingest with `rotate_deg=[0,0,90]`
  (Rz +90) so the figure is not right-side-lying. Fun validate adds a `not_side_lying` headband
  gate. Inventory hashes updated.

- **Demo phantoms gated behind local prefs** (2026-07-22) — Settings mesh dropdown lists
  clinical phantoms only by default. Opt in with `"show_demo_phantoms": true` in
  `~/.mypyskindose/gui.json` to append a **Demo** section (Cosmic Buddha headless + Steamboat
  Willie). `ramesses_ii` stays on disk but is never listed in the GUI. Separator key is
  non-selectable.

- **Demo phantoms v1 plan archived** (2026-07-22) — Moved
  `dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md` after shipping Cosmic Buddha,
  Ramesses II, and Steamboat Willie. Petite Herculanaise remains blocked; Venus/David and Phase 2
  cartoons stay on `FUN_DEMO_PHANTOMS_PLAN.md`. SemVer: **minor** on release (new demo meshes).

### Added

- **Phantom mesh naming convention** (2026-07-23) — Canonical stems `ped_*`, `adult_ecto/endo_*`,
  `adult_bariatric_{sex}_{1,2,3}`, `demo_*`; legacy aliases resolve in Phantom / preview / Settings.
  Kept `adult_male` / `junior_*` / `hudfrid`. SemVer: **minor** on release.

- **Pediatric preschool meshes + stature relabel** (2026-07-23) — Option-2 keep-all
  relabel: former short 5y (~74–78 cm) kept as `ped_preschool_*`; former 10y (~101–108 cm)
  promoted to `ped_5y_*`; new `ped_10y_*` near CDC median (~137–139 cm). SemVer: **minor**
  on release.

- **Bariatric series `_1/_2/_3`** (2026-07-23) — `adult_bariatric_{sex}_1` (abdomen), `_2`
  (thick extremities), `_3` (extra-thick). SemVer: **minor** on release.

- **Pediatric stature review** (2026-07-23) — Documented short pediatric SI heights; addressed by
  preschool relabel + new 10y regenerate. See
  `dev-docs/assessments/PEDIATRIC_PHANTOM_STATURE_REVIEW_2026-07-23.md`.

- **Louvre Cults / Scan the World license review** (2026-07-23) — Documented local
  `tmp/STL-downloads-and-links/` candidates (Socrates, Mattei Athena, Childebert, Draped Woman):
  Cults labels are **CULTS PU** or **CC BY-SA**, while Zenodo Scan the World mirrors are
  **CC BY-NC-SA 4.0**. None are shippable under current redistributable (non-NC) policy; recorded in
  `dev-docs/references/fun_phantom_provenance.md` and the character/mesh sources survey.

- **TO_DO: phantom mesh naming convention** (2026-07-23) — Decisions locked: keep
  `adult_male` / `junior_*` / `hudfrid`; rename MPFB pediatrics to `ped_*`; ecto/endo to
  `adult_ecto_*` / `adult_endo_*`; bariatrics to `adult_bariatric_{sex}_{1,2,3}`; demos to
  `demo_*`. Migrate later with aliases. See
  `dev-docs/plans/archive/PHANTOM_MESH_NAMING_CONVENTION_PLAN.md`.

- **Arms-down clinical variants** (2026-07-23) — Additive `*_arms_down` meshes for all clinical
  stems (23 twins), including MPFB stature approximations of legacy `junior_*` / `adult_male|female` /
  `senior_*` / `hudfrid`. A-pose originals unchanged. Pose: `scripts/phantom_gen/poses/arms_down_default_fk.json`.
  SemVer: **minor** on release. See `dev-docs/plans/archive/ARMS_DOWN_PHANTOM_VARIANTS_PLAN.md`.

- **Arms-down spike** (2026-07-23) — `ped_5y_male_arms_down` generated in tmp via catalog
  `"pose": "arms_down_default_fk"`; waist/chest lateral width collapses toward torso. Superseded by
  the full clinical wave above.

- **TO_DO: user-imported custom meshes** (2026-07-23) — Backlog item to consider a GUI/CLI pipeline
  for users to import their own STL (or similar) phantoms (local cache; validate/orient; not bundled).

- **Bariatric thick-extremities variants** (2026-07-22) — Keeps abdomen-dominant
  `bariatric_class2_{male,female}` and adds `bariatric_class2_{male,female}_thick_extremities`
  with additive MPFB arm/leg/neck/head detail targets. Catalog skips abdomen-vs-affine shape
  compare for the thick rows (limb bulk confounds that metric). SemVer: **minor** on release.

- **Demo phantom GUI labels + docs** (2026-07-22) — Task 6 of
  `dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`. Settings mesh selector uses NiceGUI
  `{stem: label}` options via `get_human_mesh_options()` with `(demo)` suffixes for shipped
  `cosmic_buddha`, `ramesses_ii`, `steamboat_willie`. Optional fun-manifest torso overrides wired into
  habitus baselines. Help + AGENTS / FEATURE_INVENTORY / ADDITIONAL / `demo_phantoms` feature matrix
  row. Petite Herculanaise remains blocked (not listed as shipped).

- **Steamboat Willie (demo) phantom** (2026-07-22) — Task 5 of
  `dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`. Ships `steamboat_willie` (Wikimedia
  Commons, Adrian Cojocaru, **CC BY 4.0**) with `NOTICE_steamboat_willie.txt`, locked transform
  (`rotate_deg=[0,0,0]`, `height_cm=120`, `flip_y=true`, `voxel_pitch=4.5`), ~5.7k-face full STL +
  `_reduced_1000t`. Trademark-safe labeling only (`steamboat_willie`). Fun-mode validate + anterior-beam
  smoke pass. Provenance + dual inventory hashes. **Minor** SemVer bump on release when demos ship.

- **Ramesses II (demo) phantom** (2026-07-22) — Task 4 of
  `dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`. Ships `ramesses_ii` (Wikimedia Commons,
  Dejp3, **CC BY 4.0**) with `NOTICE_ramesses_ii.txt`, locked transform (`rotate_deg=[90,0,0]`,
  `height_cm=185`, `flip_y=false`, `voxel_pitch=5.5`), ~5.6k-face full STL + `_reduced_1000t`. Raw scan
  was not watertight; ingest remeshes via solid voxel + marching cubes (`scikit-image` /
  `networkx` added to `.[phantom-gen]`). Fun-mode validate + anterior-beam smoke pass (entrance −Y).
  Provenance + dual inventory hashes. **Minor** SemVer bump on release when demos ship.

- **Cosmic Buddha (demo) phantom** (2026-07-22) — Task 2 of
  `dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`. First shipped demo / non-clinical
  phantom: `cosmic_buddha` (Smithsonian Institution, Freer Gallery of Art; **CC0**). Ingested from the
  ~150k-face Wikimedia Commons mirror via `ingest_fun_mesh.py` with a locked transform
  (`rotate_deg=[0,0,0]`, `height_axis=z`, `height_cm=151`, `flip_y=false`, headless face-up band
  `face_up_band_frac=0.20`), shipping `cosmic_buddha.stl` (6000 faces) + `cosmic_buddha_reduced_1000t.stl`.
  Full-mesh fun-mode validation passes (watertight `True`, ≤20k faces, face-up + outward-normal gates);
  anterior-beam smoke on `example_data/RDSR/siemens_axiom_example_procedure.dcm` confirms entrance on the
  anterior (−Y) side (PSD ≈ 16.3 mGy). The statue is **missing its head and hands** — expect odd habitus
  labels and a weaker face cue. Discoverable via `get_human_mesh_names()`; GUI `(demo)` labels land in
  Task 6. Provenance in `dev-docs/references/fun_phantom_provenance.md`; both STLs hash-pinned in
  `dev-docs/approved_asset_inventory.json`. CC0 → no `NOTICE_*.txt` sidecar and no
  `THIRD_PARTY_NOTICES.md` change. Shipping a new asset → **minor** SemVer bump on release.

- **Fun / demo phantom ingest scaffolding** (2026-07-22) — Task 1 of
  `dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`. New
  `scripts/phantom_gen/fun_mesh_manifest.json` (locked source URLs, licenses, placeholder
  `rotate_deg`/`flip_y`, heights, optional `face_up_frac`/torso overrides for the four demo IDs) and
  `scripts/phantom_gen/ingest_fun_mesh.py` CLI (Euler rotate → uniform scale → fill/cap → PSD anchor
  with `obj_y_up=False` + explicit flip → re-fix winding/normals → quadric decimate → validate).
  `validate_phantom.py` gains a `--require-trimesh` fun mode (hard watertight gate, ≤20k face ceiling,
  face-up band gate, dependency-free outward-normal ray gate). No demo STLs shipped yet
  (developer tooling only; no runtime or public API change).

- **Settings phantom preview** (2026-07-22) — live Plotly human-mesh preview on Settings (no RDSR).
  Prefers `_reduced_1000t` when present; dose still uses the full STL. Reflects habitus scales,
  patient orientation, and patient offsets (active exam in multi-exam mode). Debounced refresh via
  `ctx.refresh_phantom_preview` with stale-request guarding; `uirevision` preserves camera orbit
  across scale updates. Help: `docs/source/gui_help/phantom_preview.md`.

### Fixed

- **MPFB catalog reduced previews (Settings scatter)** (2026-07-22) — Settings uses
  ``*_reduced_1000t`` while Geometry uses the full STL. The 10 catalog reduced meshes had been
  regenerated without ``trimesh``/``fast-simplification``, so ``generate_reduced`` silently
  triangle-subsampled (~2700 unique verts / 1000 faces → disconnected beige fragments). Regenerated
  with quadric decimation (~502 unique verts); ``generate_reduced`` now requires real decimation by
  default (``--allow-subsample`` for tests only). Optional extra: ``pip install -e ".[phantom-gen]"``.

- **MPFB catalog phantoms face-up** (2026-07-22) — the 10 shipped parametric meshes
  (`pediatric_*`, `adult_ecto/endomorph_*`, `bariatric_class2_*`) were face-down on the table
  because `transform_to_psd_frame`’s Y-flip heuristic is a no-op on near-symmetric MPFB depth.
  Reoriented all 10 (Y-flip + winding fix), regenerated `_reduced_1000t`, refreshed inventory hashes.
  `run_catalog.py` now uses ``force_flip_y=True``; CLI adds ``--force-flip-y``.

### Added

- **Clothed + Steamboat demo phantoms plan** (2026-07-22) —
  `dev-docs/plans/archive/DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md` to ship Cosmic Buddha (**CC0**), Petite
  Herculanaise (**CC BY-SA**), Ramesses II (**CC BY 4.0**), and Steamboat Willie (**CC BY 4.0**) with
  scale/rotate ingest, watertight validate, NOTICE sidecars, and GUI `(demo)` labels. Linked from
  `TO_DO.md`, `index.md`, and `ADDITIONAL_PHANTOMS.md`. Broader fun-demo survey / Venus–David D1 backlog
  remains in `FUN_DEMO_PHANTOMS_PLAN.md`. Independent-review fold-in: NiceGUI `{stem: label}` options
  (not label→stem), re-fix normals after Y-flip, fun-mode `--require-trimesh` + ≤20k faces, tunable
  `face_up_frac`, `demo_phantoms` feature_doc_matrix row, validate full STL only; plus prior items
  (dual inventory, scale/`--no-unit-detect`, torso overrides, smoke on
  `example_data/RDSR/siemens_axiom_example_procedure.dcm`, NOTICE ≠ `THIRD_PARTY_NOTICES.md`).

- **Settings phantom preview plan** (2026-07-22) — `dev-docs/plans/SETTINGS_PHANTOM_PREVIEW_PLAN.md` for a
  live Plotly preview of the selected human mesh on Settings (no RDSR; prefer `_reduced_1000t`; **live
  habitus `scale_lat/ap/lon` + patient offsets**; orientation via `position_patient_phantom_on_table`).
  Revised after subagent review and assessments: async debounce + stale-id;
  `ctx.refresh_phantom_preview`; Plotly `uirevision`; lightweight hover text; `COLOR_*` styling;
  cylinder/plane preview deferred; **`PreviewSnapshot`** (no live `state` on worker); multi-exam
  **active-exam** offsets; cross-tab refresh call sites + mount-time paint; reuse
  `GEOMETRY_DEBOUNCE_SEC`; preview controller extraction; `copy_text` / `feature_doc_matrix`.

- **Fun demo phantoms plan** (2026-07-21) — `dev-docs/plans/FUN_DEMO_PHANTOMS_PLAN.md` to ship Venus de Milo
  (SMK **CC0**), Michelangelo’s David (Scan the World **CC BY-SA 4.0**), and Steamboat Willie (Commons **CC BY
  4.0**) as labeled non-clinical phantoms; linked from `TO_DO.md`, `index.md`, and phantom source docs. Updated
  after review: transform `--no-obj-y-up` contract, watertight/GUI/NOTICE fixes, nude-sculpture decision gate,
  Steamboat Willie alternates, **clothed full-body try trio** (Cosmic Buddha **CC0**, Petite Herculanaise
  **CC BY-SA**, Ramesses II **CC BY 4.0**; Lincoln bust fallback), and Phase 2 PD cartoons (Popeye, book Pooh).
  **2026-07-22:** v1 clothed+Steamboat execution split to `DEMO_PHANTOMS_CLOTHED_AND_STEAMBOAT_PLAN.md`
  (later archived under `plans/archive/`).

### Changed

- **Fun / public-domain phantom mesh survey** (2026-07-21) — added
  `dev-docs/references/CHARACTER_AND_PUBLIC_DOMAIN_MESH_SOURCES.md` (stylized CC0 characters, MakeHuman,
  classical sculpture scans, Smithsonian Open Access clothed full-body and busts, Mixamo/Daz shipping caveats)
  and a short summary section in `ADDITIONAL_PHANTOMS.md`; registered in `dev-docs/index.md`. Updated with
  Steamboat Willie / Mickey caveats, convertible format notes (`.obj`/`.ply`/… → STL), concrete **Venus de Milo**
  (SMK **CC0**) / **David** (Scan the World **CC BY-SA 4.0**) guidance, and **clothed full-body** statue leads
  (Cosmic Buddha, Petite Herculanaise; NC toga traps).

- **`ADDITIONAL_PHANTOMS.md` consolidated** (2026-07-21) — rewrote the layered review appendices into one reference:
  shipped mesh inventory, preferred MPFB path, external sources (with corrected XCAT/Mesh50 license notes),
  bariatric options, and a single integration checklist; registered in `dev-docs/index.md`.

- **Automated phantom library plan** (2026-07-21) — replaced the MakeHuman GUI generation master/sub-plans with
  `dev-docs/plans/archive/AUTOMATED_PHANTOM_LIBRARY_PLAN.md`: full-body **true shape variety** via headless MPFB/Blender
  parametric targets (affine stretch of existing STLs is out of scope for shipped meshes). MakeHuman GUI phase
  docs archived under `dev-docs/plans/archive/`. Phases 0–4 complete (spike, catalog, P0/P1 generation, install).

### Removed

## [25.2.0] - 2026-07-21

### Added

- **Parametric human phantom library (MPFB)** — ten new full-body meshes with male/female pairs:
  `pediatric_5y_*`, `pediatric_10y_*`, `adult_ectomorph_*`, `adult_endomorph_*`, `bariatric_class2_*`
  (plus `*_reduced_1000t` previews). Generated via headless Blender/MPFB true-shape targets
  (`scripts/phantom_gen/`), not affine stretch of existing STLs. Provenance: MakeHuman/MPFB core
  assets CC0; see `ADDITIONAL_PHANTOMS.md` and assessments `P0_PHANTOM_GENERATION_2026-07-21.md` /
  `P1_BARIATRIC_PHANTOM_GENERATION_2026-07-21.md`.

### Fixed

- **Worktree-aware commit message git hook** (2026-07-21) — updated `scripts/check_commit_message.py`'s `resolve_commit_message_path()` to inspect `--git-dir` and `--git-common-dir`, allowing git commits from linked worktrees to resolve `.git/worktrees/<name>/COMMIT_EDITMSG` without triggering false path containment errors. Reused test fixtures in `tests/unittests/test_gui_figures.py` and added `text` language tags to code blocks in `HTML_EXPORT_BACKGROUND_TASK_ERROR_20260719T123241.md`.

### Changed

- **Lean CI matrix and current Python support** (2026-07-20) — raised the supported Python minimum from 3.10 to
  3.11, added Python 3.14 coverage, and set Basedpyright's target accordingly. Pull requests now receive a fast
  Ubuntu/Python 3.14 check; `main` tests Python 3.11–3.14 on Ubuntu; the macOS/Windows oldest/newest compatibility
  matrix runs weekly only after a new `main` commit since the prior scheduled/manual compatibility sweep, or on
  manual dispatch. The latest-dependencies probe also uses Python 3.14. Presidio remains a weekly, value-suppressed
  secondary privacy review with manual dispatch instead of running on every text-only PR.

- **More diagnostic (still value-free) error logging** (2026-07-19) — `privacy.safe_error_event` now appends
  the value-free code location where an exception was raised (`path:lineno in func`) to its one-line summary,
  and — when DEBUG is enabled — emits a value-free traceback that walks the exception's `cause`/`context`
  chain (frame locations + exception class names only). Exception messages, source-line text, local values,
  and absolute paths are still never logged. This turns otherwise-opaque failures (e.g. a bare
  `multi_exam_analysis failed (error_type=RuntimeError)`) into something diagnosable without exposing clinical
  data. Successful HTML/PNG dose-map exports also now log a byte-count-only breadcrumb (previously silent).
- **Corrected misleading geometry-plot debug log** (2026-07-19) — `create_plot_and_save_to_file` logged
  "savint to file `<mode>.html`" although it never writes a file (it calls `Figure.show`, which the GUI
  intercepts to embed the figure); fixed the typo and the false file-write claim.
- **Sensitive-content scanner complexity refactoring (SonarQube Phase 5)** (2026-07-18) — extracted
  format-specific readers (notebook attachment/output inspection, PDF metadata/page/attachment
  extraction, and bounded archive/office-document member iteration) from `scripts/check_sensitive_content.py`
  into a new `scripts/check_sensitive_helpers.py` module; `run_checks` was split into small policy
  helpers (path/diagnostic checks, asset-inventory status, DICOM identifier warnings, and
  extracted-text/container-flag scanning) while keeping its public signature and return value
  unchanged. Behaviour-preserving: 37 targeted tests plus the full unit suite pass, direct CLI
  output is byte-identical to the pre-refactor script, and all four baseline `S3776` findings and
  their extracted helpers are now well under the complexity budget. No new dependencies; no
  embedded content is written to disk or logged.

- **CodeRabbit follow-ups (privacy / robustness)** (2026-07-18) — validate all per-exam offsets
  before multi-exam batch output; make GUI upload/example loads transactional with temp-file cleanup;
  show opaque exam aliases instead of source filenames on Upload/Settings/drawer surfaces; suppress
  CLI input-preview identifiers even with `--include-sensitive-preview`; archive completed GUI and
  privacy-scan complexity refactor plans under `dev-docs/plans/archive/`.

- **GUI complexity refactoring (SonarQube Phase 4)** (2026-07-18) — decomposed nine high-complexity GUI components
  into controller/builder modules: `geometry_builders.py`, `results_builders.py`, `upload_builders.py`, and extracted
  settings-summary builders in `calculate.py`. Each tab now has a thin public entry point and a sibling module owning
  the controller, view references, and layout builders. All 9 `S3776` cognitive-complexity findings resolved; 663 tests
  pass; basedpyright clean (0 errors); all pre-commit and pre-push hooks pass.

### Added

- **Header-aware unit detection for tabular input** (2026-07-19) — the `radimetrics` and `dosetrack`
  adapters now read each field's physical unit from its source column header (reference-point dose,
  collimated field area, tube current, exposure, source-to-detector/isocenter distances, table
  positions) and convert to internal units, generalizing the existing DAP helper via
  `convert_field_with_header_units()` and a unit registry in `input_adapters/base.py`. Correctly- or
  unlabelled exports produce identical results; mislabelled/atypical exports now convert by their
  declared header unit, with a confident read recorded in the provenance audit trail and an import warning when
  the token is unreadable. The unit-conversion audit trail is now surfaced in the GUI import preview and
  in rich exports (`ExamSection.unit_conversions` → all four writers + dict/JSON payload). DICOM RDSR
  unit mismatches now raise a clear, unit-naming `RdsrUnitError` (surfaced in the GUI) instead of a
  generic failure. Unit handling across all three input paths is documented in
  `dev-docs/INPUT_SCHEMA_DETECTION.md` ("Unit handling").

- **Content-bound privacy admission and local SonarQube** (2026-07-16) — protected `.gitignore` rules and never-track
  roots now block unsafe staged paths; a staged/range router requires value-free, expiring receipts for applicable
  Presidio, phi-scan, HoundDog, DICOM, and image-OCR scans. Receipts and raw reports stay below Git metadata or private
  temporary directories. Added local Tesseract+Presidio rendered-asset review, a safe `dicom-phi-scan` wrapper, and an
  optional loopback-only SonarQube Community Build runner with private digest/status tracking. Codecov and Safety cloud
  execution now occurs only on `main` after repository gates pass; PyPI release publishing requires a successful main
  CI run. A machine-checked privacy-tool inventory now records direct scanner/runtime versions, roles, execution
  boundaries, and output policies; ExifTool is recorded as a candidate rather than silently enabled.

- **End-to-end privacy hardening** (2026-07-16) — default result/report serialization now omits source identifiers;
  internal exams use opaque labels; CLI/GUI exports require an explicit destination/overwrite choice and use private,
  atomic, Git-aware writes; uploads use private random-name session storage with stale cleanup; runtime diagnostics
  suppress filenames, paths, exception messages, and tracebacks; tests fail if they modify or leave artifacts in the
  checkout. Added explicit identified-export and network-binding acknowledgements, onboarding/upload/export privacy
  notices, value-safe path tokens, CI metadata scanning, and strict approved-asset enforcement.

- **Layered PHI/PII scanner cadence** (2026-07-16) — project privacy Semgrep is now blocking with synthetic rule
  tests; phi-scan runs weekly and on CSV/TSV pull requests against a reviewed expiring baseline; calibrated Presidio
  runs weekly/PR with local models and value-suppressed output; HoundDog raw reports are ephemeral and its wrapper
  distinguishes clean, findings, and not-run states. The five public DICOM fixtures and all other opaque assets are
  hash-approved with reviewer initials; copied irradiation-event UIDs were replaced by deterministic test-only UIDs.

- **PHI/PII leak SAST + agent privacy guidance** (2026-07-15) — added project-specific semgrep rules
  (`.semgrep/mypyskindose-privacy.yml`) that flag patient/study/institution/physician identifiers and source
  filenames reaching stdout/loggers, wired as a blocking `semgrep-privacy` pre-push hook and CI step. Added an
  `AGENT_PLAYBOOK.md` "Privacy and
  sensitive data" section covering when to run each scanner and that advisory findings must be triaged, not ignored.

- **HoundDog dataflow scan + PII/PHI scanner runbook** (2026-07-15) — added an advisory, local-only pre-push hook
  (`scripts/run_hounddog_advisory.py`) that runs HoundDog's source-code dataflow scan when the standalone binary is
  installed and reports `NOT RUN` otherwise; completed scans fail on risky flows and never upload or invoke cloud/AI
  features. Documented exact
  run commands for all four scanners (phi-scan, Presidio, HoundDog, dicom-phi-scan) in
  `dev-docs/references/LOCAL_PII_MODELS.md`.

- **Private IPv6 detection in the sensitive-content gate** (2026-07-15) — the blocking gate now flags unique-local
  and link-local IPv6 addresses (the fc00/7 and fe80/10 prefix ranges) in tracked text alongside the existing
  private-IPv4 rule, without echoing the matched value. MAC addresses are excluded to avoid false positives.

- **Sensitive-content and asset-admission gate** (2026-07-13) — added a blocking pre-commit/CI scanner for
  tracked PII/PHI-like text and absolute local paths, plus SHA-256 inventory enforcement for every image, DICOM,
  opaque binary, and extensionless file. Existing assets are recorded as explicitly pending a maintainer's manual
  review; new or changed assets fail immediately. Added a pinned, report-free advisory `phi-scan` workflow and a
  documented DICOM/image review policy.

- **Local Presidio advisory scan** (2026-07-14) — added an optional `privacy-scan` dependency extra and a
  tracked-text-only runner. It suppresses matched values and does not upload inputs/findings; a calibrated weekly/PR
  workflow was added on 2026-07-16.

- **Local PII/PHI evaluation reference** (2026-07-14) — documented local GLiNER, Privacy Filter, Presidio,
  HoundDog, and DICOM-pixel-scanner options, including macOS/LM Studio limits, local-only boundaries, and a
  synthetic-fixture-only evaluation protocol.

- **Sensitive asset review inventory** (2026-07-14) — added a generated Markdown inventory with links to every
  guarded asset, human-readable approval state, and DICOM checklist. Pre-commit and CI reject drift from its JSON
  source of truth.

- **Privacy admission hardening** (2026-07-14) — added a commit-message gate; private-network and DICOM/PACS
  endpoint checks; hard rejection of diagnostic artifacts; and standard-preamble detection for extensionless DICOMs.
  Notebook-embedded image/PDF outputs, PDFs, and PostScript/EPS files now require hash-pinned human clearance;
  PDFs also receive fail-closed local page-text, metadata, and readable-attachment scanning. ZIP/TAR/GZIP and
  Office/iWork containers now receive bounded embedded-text scans and an embedded file/image/DICOM review checklist.
  Native diagnostic logs are now owner-only on POSIX systems, and GUI load failures no longer expose raw traceback or
  exception content.

- **Geometry per-exam event selection** (2026-07-12) — replaced the bare event selection box with an interactive 1-based chevron stepper showing context (e.g., "Event 6 / 23") in the Geometry tab. The stepper is disabled outside of "Single event" mode to improve user focus.

### Changed

- **Body-habitus scaling controls** (2026-07-13) — reorganized each scaling control so its label and live value sit directly above its slider. Labels now consistently use left-right width, anterior-posterior thickness, and superior-inferior length. The left-right readout measures torso width below the arms while its scale factor continues to resize the full lateral mesh axis.

- **gitleaks workflow permissions** (2026-07-18) — added an explicit least-privilege `permissions:` block
  (`contents: read`, `pull-requests: write`) to `.github/workflows/gitleaks.yml`, closing open GitHub Code
  Scanning alert #3 (`actions/missing-workflow-permissions`). The `pull-requests` scope is required by
  gitleaks-action to post PR review comments. Updated `dev-docs/FORK_MAINTAINER_GUIDE.md` to note gitleaks
  now declares permissions. Commented on Dependabot PR #13 (closed) that the `mcp` 1.23.3→1.27.2 bump is
  blocked by semgrep's exact pin and remains tracked via `dev-docs/TO_DO.md` and `[tool.uv.audit]` ignores.

### Fixed

- **Latest-dependency type-check compatibility** (2026-07-20) — narrowed the human-mesh annotation to match the mesh-loading helper's contract: tuple model names are strings and unsupported top-level `Path` values are no longer advertised, resolving the scheduled `ci-latest` Basedpyright failure.

- **HTML/PNG dose-map export error reporting (Phase 1)** (2026-07-19) — `make_dosemap_html`
  and `make_dosemap_png` no longer silently return `None` on failure, which `require_io_result`
  mislabeled as a cancelled background task; both now log via `safe_error_event` and re-raise.
  The `download_html` / `download_png` export handlers distinguish a genuine NiceGUI
  cancel/shutdown from a real render failure and show an actionable, dismissible notify for the
  latter (no PHI). Root cause of the underlying render failure is not yet identified (tracked as
  Phase 2 in `dev-docs/plans/HTML_EXPORT_BACKGROUND_TASK_FIX_PLAN.md`); this phase only fixes the
  misleading error message.

- **CI dirty-checkout and SonarCloud gate** (2026-07-17) — exclude regenerable `corrections.db` artifacts
  from the pytest checkout guard; confine commit-message and Sonar scanner CLI paths; rebuild Sonar host URLs
  from allowlisted components before `subprocess.run`; write privacy-tool inventory Markdown only to a fixed
  repo path; move workflow `contents: read` permissions to job level; and replace float equality in the
  Presidio advisory fake engine with `math.isclose`.

- **Semgrep-pinned mcp audit suppressions** (2026-07-17) — added tracked `[tool.uv.audit]`
  suppressions for GHSA-jpw9-pfvf-9f58, GHSA-hvrp-rf83-w775, and GHSA-vj7q-gjh5-988w while
  semgrep continues to pin `mcp==1.23.3` (fixes require mcp >=1.27.2 / >=1.28.1). mcp is a
  semgrep-only transitive dependency and is unused by MyPySkinDose runtime code. Also added
  `pytest.importorskip("nicegui")` to `test_exam_loader_privacy.py` so core CI can collect
  without the GUI extra, and refreshed `.phi-scanbaseline` after deterministic UID
  de-identification changed fixture finding hashes (14 reviewed synthetic/numeric entries).
  Follow-up CI fixes: install `coverage` in the build job, type-ignore optional `tldextract`
  in the Presidio advisory runner, and assert value-safe logging for corrupt STL mesh reads.

- **Generalized live-preview pause** (2026-07-12) — generalized the 30-event live-preview pause guard from composite procedures to all procedure modes (single-exam, non-composite, and composite), preventing expensive reactive re-renders on large datasets. Explicitly clicking "Full procedure" now correctly renders the Plotly procedure slider once even if the procedure is paused.

- **GUI loaded-file removal** (2026-07-11) — removing a bundled example from the GUI's loaded
  exams list no longer deletes the source `.dcm` fixture from the repository; only registered
  temporary upload copies are unlinked.
- **Pre-push dependency audit** (2026-07-09) — bumped transitive dev-only `nltk` 3.9.4 → 3.10.0
  (`uv.lock`) to clear PYSEC-2026-2078 / CVE-2026-54293 and removed the now-obsolete
  `[tool.uv.audit] ignore-until-fixed` entries for the prior nltk path-traversal advisory.

### Added

- **Multi-exam per-exam dose map controls** (2026-07-11) — added inline interactive 3D dose map checkboxes per exam row inside the multi-exam Results accordion (`results.py`), capped at 5 simultaneous inline maps via a memory guard (`MAX_INLINE_MAPS = 5`). Added a visible exams subset selector card allowing users to select specific exams (`All` / `None` / per-exam checkboxes) to dynamically recompute aggregate Peak Skin Dose and update the aggregate dose map plot for the selected subset.

- **Local CI gate and reproducible CI installs** (2026-07-07) — `scripts/ci_local.py` runs the CI
  static checks plus the tests in one command before pushing; its core-test step blocks `nicegui`
  (via `scripts/check_gui_test_placement.py --run`) to reproduce the no-`gui`-extra core matrix that
  local envs otherwise hide. The `ci` workflow's `static-analysis` and `gui-smoke` jobs now install
  the exact versions pinned in `uv.lock` (`uv sync --locked`), so PR/main runs are reproducible and
  an upstream release cannot turn an unrelated PR red. A new scheduled `ci-latest` workflow installs
  the **latest** dependencies weekly (and on demand) to surface upstream breakage deliberately. CI
  runner minutes reduced: the main-push matrix drops the priciest jobs (macOS/Windows only on the
  oldest+newest Python; 12 → 8 jobs) and `gitleaks` no longer double-scans PR-branch pushes.

- **Documentation/help harness checks** (2026-07-04) — added JSON metadata and CI/pre-commit checks for GUI help
  coverage (`dev-docs/help_registry.json`, `scripts/check_help_registry.py`), high-risk UI copy and glossary
  terminology (`dev-docs/ui_copy.json`, `dev-docs/glossary.json`, `scripts/check_ui_copy.py`), feature-to-doc
  traceability (`dev-docs/feature_doc_matrix.json`, `scripts/check_feature_doc_matrix.py`), and stale prose/backtick
  path references in active docs (`scripts/check_doc_freshness.py`). Added missing Upload/Data/Results/Export GUI
  help pages and registry ids on `HelpButton` uses.
- **Total DAP and fluoro time are now reported** (2026-07-03) — tabular inputs that carry per-event
  dose-area-product and fluoro-time columns (e.g. Radimetrics `DAP (Total) Gy-cm2` and
  `Fluoro time (Total) ms`) are now summed into procedure totals and shown in the **rich report**
  dosimetric summary (previously `N/A`) and on the **Results tab** (new *Total DAP* and *Total
  Fluoro Time* cards; the multi-exam aggregate banner gains a totals line). Fluoro time is displayed
  as minutes + seconds (e.g. `5 min 30.8 s (330.8 s)`). The input-adapter pipeline
  (`input_adapters/base.attach_procedure_dose_totals`) detects the DAP column's units from its
  header, converts to internal units, and records the interpretation in the provenance
  unit-conversions. **DAP units that cannot be confirmed from the header are assumed to be Gy·cm²
  and flagged with an import warning** (surfaced in the report's alert block and the GUI) so the
  operator can verify before clinical use; fluoro time is assumed to be milliseconds. As a
  side-effect, DoseTrack DAP totals (which were also dropped during normalization) now report too.
- **DAP unit handling is now uniform across tabular adapters** (2026-07-03) — the DoseTrack adapter
  previously hard-assumed Gy·cm² (unconditional `/10000`) regardless of the column header, and did
  not flag it. All adapters (Radimetrics, DoseTrack, generic capture) now route DAP through the
  shared `input_adapters/base.convert_dap_series_to_gym2`, which reads the unit from the source
  column header (Gy·cm², mGy·cm², cGy·cm², µGy·cm², Gy·m², µGy·m²), records the interpretation in
  provenance, and only falls back to an assumed Gy·cm² **with a flagged warning** when the header
  carries no recognisable unit. Files with a `Gy·cm²` header convert exactly as before.

### Fixed

- **GUI tests are now isolated from each other (fixes flaky `gui-smoke`)** (2026-07-08) —
  the geometry-slider "no render loop" tests failed intermittently in CI (and deterministically
  under some run orders) because GUI tests shared the module-level `AppState` singleton and left
  repeating `ui.timer`s (data/settings/results refresh loops) running after their page was torn
  down; the leaked timers starved the debounce/render timing later tests assert on. Added an
  autouse fixture in `tests/gui/conftest.py` that cancels all live NiceGUI timers and resets the
  `state` singleton in place before and after every GUI test.
- **Multi-exam plot-suppression fixture no longer breaks on Python 3.10** (2026-07-08) —
  `tests/unittests/test_multi_exam.py::_suppress_plots` patched via the string
  `"mypyskindose.analyze_data.create_geometry_plot"`, but the package re-exports a function
  named `analyze_data` that shadows the submodule of the same name; whether `mock` resolved the
  target to the module or the function depended on import order and surfaced as an
  `AttributeError` on the 3.10 build matrix. It now patches the module object obtained via
  `importlib.import_module`, which is unambiguous across Python versions.
- **GUI handlers now guard NiceGUI `run.io_bound` results against `None`** (2026-07-07) —
  NiceGUI 3.14 types `run.io_bound`/`run.cpu_bound` as returning `T | None` (it returns `None`
  when a call is cancelled or the app is shutting down), which surfaced 12 strict type errors in
  the upload/calculate/export/import-preview handlers that unpacked or used the result directly.
  Added `gui.concurrency.require_io_result()` to unwrap these results (failing fast with a clear
  message on the interim `None`) and applied it at every call site. Also suppressed the optional
  gui-native `AppKit`/`webview` import diagnostics (runtime-guarded, not installed in core/CI type
  environments). Restores a green `basedpyright` static-analysis job.
- **Backup cleanup no longer deletes in-progress backups with an old mtime** (2026-07-07) —
  `scripts/cleanup_old_backups.py` `_is_stale_backup` now treats pending staged/unstaged changes
  as an absolute keep signal before the commit-age *mtime fallback*. Previously a `backups/*.bak`
  file with local changes but a filesystem mtime older than `HEAD~max_commits` could be removed,
  causing backup data loss. Added `test_cleanup_keeps_*_with_old_mtime` regression tests.
- **GUI calculation failures no longer leak tracebacks to the UI** (2026-07-07) —
  `gui/helpers.run_calculation` now logs the exception (type + traceback via the logger) and
  returns a generic "Calculation failed. See the application log for details." message instead of
  returning `traceback.format_exc()`, which could expose internal filesystem paths and exception
  details in the interface.
- **Dose calculation no longer crashes over the notebook progress bar** (2026-07-07) —
  `calculate_dose` selected `tqdm_notebook` whenever `settings.plot.notebook_mode` was set (true in
  the bundled `settings_example.json`), which raises `ImportError: IProgress not found` in headless
  CLI/export runs without `ipywidgets`. It now falls back to the plain `tqdm` bar
  (`_make_progress_bar`) when the notebook widget backend is unavailable.
- **GUI unit tests relocated so core CI passes without the `gui` extra** (2026-07-07) —
  several GUI tests imported `nicegui` (directly or via `mypyskindose.gui.*`) at load but lived under
  `tests/unittests/`, which the core build matrix runs with `--ignore=tests/gui` and no `gui` extra,
  breaking collection/execution on every platform. Moved `test_gui_helpers`,
  `test_gui_operation_guard`, `test_gui_results_refresh`, and the `TestGui*` classes from
  `test_multi_exam.py` into `tests/gui/`. Added `scripts/check_gui_test_placement.py` (wired into CI
  and the pre-push hook) which blocks `nicegui` and collects the core suite, so a misplaced GUI test
  is caught locally in seconds instead of only in full CI.
- **`test_audit_dependencies` `--frozen` assertions made CI-independent** (2026-07-07) —
  `audit_dependencies.py` emits `--locked` when `CI` is set and `--frozen` otherwise; two tests
  asserted `--frozen` without pinning `CI`, so they passed locally but failed under GitHub Actions.
  They now pin `CI` to a falsy value.
- **Spreadsheet formula injection on Data tab exports** (2026-07-07) — RDSR and tabular
  event-table exports (CSV/XLSX/TXT on the Data tab, plus rich-report XLSX cells) now
  prefix attacker-controlled strings that start with formula trigger characters (`=`, `+`,
  `-`, `@`, tab, CR) so Excel and similar tools treat them as text instead of evaluating
  formulas (CWE-1236).
- **Native "Save As" dialog for exports** (2026-07-03) — in native (pywebview) window mode, the
  export/save-path helper (`gui/io_helpers._get_save_path`) called NiceGUI's async
  `create_file_dialog` without awaiting it, so the returned coroutine was passed to `Path(...)`
  and every save crashed with `TypeError: argument should be a str ... not 'coroutine'`. The
  helper is now an awaited coroutine (and uses the non-deprecated `webview.FileDialog.SAVE`),
  restoring the ability to choose the file location and name in native mode. All callers in the
  Export and Data tabs await it.

### Changed

- **CLI `--input-schema` now defaults to `auto`** (2026-07-03) — tabular inputs (.csv/.tsv/.xlsx)
  are detected from their column headers by default, matching the GUI (which already defaults to
  `auto`). Previously the CLI fell back to the `normalized` schema, so a Radimetrics or DoseTrack
  export run without an explicit `--input-schema` failed to locate a header row. Auto-detection
  scores every real schema (normalized, generic_rdsr_like, radimetrics, dosetrack) and errors with
  a clear "pass `--input-schema` explicitly" message if two schemas are ambiguous. The
  library-level `read_and_normalize_input(input_schema=None)` default is unchanged (`normalized`).
  Detection, per-schema fingerprints, and the DAP-unit / equipment-manufacturer caveat are now
  documented in `dev-docs/INPUT_SCHEMA_DETECTION.md`, kept in sync with the code by
  `tests/unittests/test_input_schema_doc.py`.
- **GUI toasts appear at the top and linger longer** (2026-07-03) — `gui/notifications.py` patches
  `ui.notify` once at startup so notifications default to `position="top"` and an 8 s timeout
  (up from Quasar's 5 s at the bottom). Explicit per-call `position`/`timeout` still win, so
  persistent (`timeout=0`) toasts are unaffected.
- **Native window is now the default GUI mode from the launchers** (2026-07-03) — `run_gui.sh` and
  `run_gui.bat` now default to option **[2] Native Window** when the user presses Enter without a
  choice (previously defaulted to browser). Browser mode remains selectable as **[1]**.
- **Rich report export dependencies are now core** (2026-07-03) — `reportlab` (PDF) and
  `python-docx` (DOCX) moved from the optional `export` extra into the main dependency list so
  every install can produce all report formats out of the box. The `export` extra is retained as a
  no-op alias for backward compatibility. If an export backend is ever missing (e.g. a partial
  install), `export.writers.render_bytes()` now raises `MissingExportDependencyError` — with a
  copy-pasteable `pip install` hint — instead of a bare `ModuleNotFoundError`; the GUI Export tab
  surfaces this as a persistent, actionable dialog (with a Copy-command button) rather than a brief
  error toast.

### Added

- **Rich Report Export** (2026-07-02) — new `mypyskindose.export` package produces a single
  self-contained audit document (**XLSX / PDF / HTML / DOCX**) from a completed dose calculation,
  bundling dosimetric results, effective settings, input provenance (DICOM RDSR + tabular
  branches), correction-factor statistics, warnings/discarded events, and dose-map images
  (whole-body context + a view zoomed to the irradiated region). `collect_export_payload()`
  normalizes single-exam (dict) and multi-exam (`MultiExamResult`) results into one payload;
  writers under `export/writers/` consume it. GUI: Export tab **"Rich report…"** modal
  (format + optional title; native save-path vs browser download). CLI: `--export-format`,
  `--export-path`, `--export-title` on the headless path (rejects `--aggregate` /
  `--input-preview-only`). `reportlab` added as a new optional `export` extra
  (`pip install -e '.[gui,export]'`); XLSX/images reuse core `openpyxl`/`kaleido`.
  `gui/figures.py` now delegates dose-map figure construction to the GUI-free
  `export/images.py`. DOCX writer uses `python-docx` (also in the `export` extra).
  Plan: `dev-docs/plans/RICH_EXPORT_PLAN.md`.

- **Vendor X/Z coordinate clarification** (2026-06-28) — Geometry and dose-map plots now label the
  normalized frame as `X - LON / PT L-R`, `Y - VER / PT A-P`, and `Z - LAT / PT S-I`;
  Data tab and Geometry/Per-exam controls use the same frame; Geometry and Calculate help explain
  Siemens/Philips DICOM/operator naming versus GE patient-anatomy raw naming. Plan:
  `dev-docs/plans/archive/VENDOR_XZ_CLARIFICATION_PLAN.md`.
- **Lockfile-based dependency auditing** (2026-06-28) — `scripts/audit_dependencies.py` wraps
  `uv audit` on `uv.lock` (requires `uv` >= 0.11.19; `--frozen` locally, `--locked` in CI) with
  fallback to `pip-audit` on the active environment. Pre-push hook and CI `static-analysis` job now
  call the wrapper; CI installs `uv` via `astral-sh/setup-uv@v8.2.0`. Tracked suppressions live in
  `[tool.uv.audit]` (`ignore-until-fixed` for dev-only `nltk` via `safety`, GHSA-p4gq-832x-fm9v).
  Plan: `dev-docs/plans/DEPENDENCY_AUDIT_PLAN.md`.
- **One-command hook installer** (2026-06-27) — `scripts/setup-dev.sh` (macOS/Linux)
  and `scripts/setup-dev.bat` (Windows) run both `pre-commit install` and
  `pre-commit install --hook-type pre-push` in one step, ensuring all pre-push hooks
  (semgrep, pip-audit, basedpyright, check-changelog) fire automatically on `git push`.
  Added `pip-audit --desc on` as a pre-push hook in `.pre-commit-config.yaml` to match the
  existing CI gate. Expanded the CI shellcheck step to cover `scripts/setup-dev.sh`.
  `AGENTS.md` Development setup block simplified to reference the scripts. Plan:
  `dev-docs/plans/archive/ENABLE_SECURITY_HOOKS_DEFAULT_PLAN.md`.
- **Security tooling in CI and pre-push** (2026-06-27) — semgrep (OWASP Top 10 SAST) in
  the `static-analysis` CI job and as a pre-push hook, scanning `src`, `scripts`,
  `.github/workflows`, and `docs/source/conf.py`; safety dependency scan in CI (skipped when
  `SAFETY_API_KEY` is unset; `pip-audit` remains the no-key gate); shellcheck (`shellcheck-py`)
  pre-commit hook + CI step for shell scripts. Hardened `ci.yml` to avoid `${{ github.* }}`
  shell-injection by passing context through `env:` variables, and fixed latent `set -e`
  error-handling bugs in `run_gui.sh` surfaced by shellcheck. Plan:
  `dev-docs/plans/SECURITY_TOOLS_CI_PLAN.md`.
- **Body-habitus cm readouts** (2026-06-26) — Settings → Phantom body-habitus
  sliders now show the scaled human-mesh dimension in centimeters beside the
  scale factor, update on slider drag and mesh switch, and fail soft to `—` for
  unknown or unreadable STL meshes. Plan:
  `dev-docs/plans/archive/BODY_HABITUS_CM_DISPLAY_PLAN.md`.
- **First-run GUI onboarding** (2026-06-25) — first GUI page render shows a persistent onboarding
  modal explaining accepted input files, workflow steps, local-only processing, and result exports.
  Users can persist "Don't show this again" in `~/.mypyskindose/gui.json`; native window geometry
  preferences are preserved when the onboarding flag changes. Plan:
  `dev-docs/plans/archive/FIRST_RUN_ONBOARDING_PLAN.md`.
- **Native window geometry persistence** (2026-06-25) — `--native` mode restores window size,
  position, and maximized state from `~/.mypyskindose/gui.json`. First launch starts maximized
  with normal bounds at 75% of the primary screen (centered). Plan:
  `dev-docs/plans/NATIVE_WINDOW_GEOMETRY_PLAN.md`.
- **Agent guidance playbook and advisory check** (2026-06-25): added `dev-docs/AGENT_PLAYBOOK.md`,
  thin `GEMINI.md` / `QWEN.md` pointer files, and `scripts/check_agent_guidance.py` (pre-commit advisory;
  `--strict` available) to flag duplicated or drifting agent instructions, overgrown `TO_DO.md`, and
  completed-looking active execution plans.
- **Beam-miss warnings** (2026-06-24) — when an irradiation event deposits zero dose (beam does not intersect the patient phantom), a per-event `WARNING` identifies the event index, kVp, filtration, and field area. Configurable via `beam_miss_warn` setting (`"per_event"` / `"summary"` / `"off"`; CLI default `"per_event"`, GUI default `"summary"`); an all-miss sentinel always fires. Multi-exam auto-downgrades per-event to `"summary"`. GUI toast throttle at 5 messages (`_MAX_TOASTS`). Plan: `dev-docs/plans/archive/NO_PATIENT_INTERSECTION_WARNING_PLAN.md`.
- **Interactive Geometry offset sliders** (2026-06-24) — single-exam **patient offset** sliders and **table-origin override** sliders in the Geometry tab with debounced live 3D preview; read-only auto-detected table offsets in Settings and Calculate tabs; reset buttons. Plan: `dev-docs/plans/archive/INTERACTIVE_TABLE_OFFSETS_PLAN.md`.
- **Human phantom body-habitus scaling** (2026-06-25) — human STL phantoms can be directionally scaled with `phantom.scale_lat`, `phantom.scale_ap`, and `phantom.scale_lon` (defaults `1.0`, clamped to `0.5–2.0`). Scaling is applied before patient/table positioning, non-uniform scaling recomputes normals, and Settings → Phantom exposes human-only sliders that refresh Geometry preview and invalidate prior results. Plan: `dev-docs/plans/archive/PATIENT_SIZE_SCALING_PLAN.md`.

### Fixed

- **Geometry slider label placement** (2026-06-26) — Geometry tab slider value
  labels now sit adjacent to their sliders instead of wrapping to the following
  row. Plan: `dev-docs/plans/archive/SLIDER_LABEL_REPOSITION_PLAN.md`.
- **Cross-tab slider sync in GUI** (2026-06-25) — table-origin spinbox changes in Settings → Per-exam corrections now refresh Geometry sliders; switching to the Geometry tab (via the tab strip or the left nav drawer) refreshes sliders, value labels, and the live preview figure. Plan: `dev-docs/plans/archive/CROSS_TAB_SLIDER_SYNC_PLAN.md`.
- **Geometry tab render loop** (2026-06-25) — stop Plotly re-rendering on a 0.25 s timer after slider drags or external refresh; break the cycle with an `_in_render_chain` closure flag. Plan: `dev-docs/plans/archive/GEO_TAB_SPINNING_WHEEL_PLAN.md`.
- **`_CalcWarningCollector` handler leak in GUI** (2026-06-24) — multi-exam `run_calculation` branch in `gui/helpers.py` never removed the temporary log handler, causing exponentially duplicated toasts across runs. Fixed by widening the `try/finally` to wrap both single-exam and multi-exam branches. (Phase 0 of no-patient-intersection warning plan.)
- **Single-exam Geometry preview pause regression** (2026-06-24) — `live_preview_allowed` no longer pauses single-exam `plot_procedure` at >30 events; composite multi-exam pause threshold unchanged (R12).
- **GUI offset display and state leaks** (2026-06-24) — Calculate tab patient/table offset summaries now update when any axis changes; per-exam corrections global-offset label refreshes after Settings edits; patient offsets and coordinate-correction flags reset on new file load; `_remove_exam` multi→single restores globals from surviving exam meta.
- **Dose map figure exports** (2026-06-24) — restore `make_dosemap_fig` / `make_dosemap_html` / `make_dosemap_png` in `gui/figures.py` (accidentally dropped during Part II `make_geometry_fig` refactor).

### Changed

- **Agent and backlog docs** (2026-06-25): `CLAUDE.md` now imports `AGENTS.md` and points to
  `dev-docs/AGENT_PLAYBOOK.md`; `dev-docs/TO_DO.md` is trimmed to an active backlog with completed history
  redirected to `CHANGELOG.md` and archived plans.
- **GUI module split for multi-exam geometry prep** (2026-06-24) — Part I of `MULTI_EXAM_GEOMETRY_OFFSETS_PLAN`: split `gui/helpers.py` into `settings_builder`, `exam_loaders`, `exam_transforms`, and `geometry_preview` (stub); `helpers.py` is now a thin facade under the CI line cap. Loader seeds per-exam `d_*` from globals before reset (T20); Settings per-exam offset edits refresh Geometry sliders (T25).
- **Multi-exam Geometry Phase 0** (2026-06-24) — Part II: `geometry_preview.py` lifecycle/slice helpers, `EXAM_INDEX_COLUMN` for stable preview slicing, C1 banner + exam selector, `make_geometry_fig` active-exam/composite args; `reset_results` no longer clears `active_exam_index` (T2).
- **Multi-exam table-origin sliders (Geometry)** (2026-06-24) — Part III: table-origin card visible per active exam in multi-exam mode; slider limits refresh on exam switch; reset commits `meta[active]` (T3, T5a).
- **Multi-exam patient-offset sliders (Geometry)** (2026-06-24) — Part IV: patient card in multi-exam; sliders write `meta[active].d_*` only; composite preview checkbox + C3/C4 captions (T4, T5b, T29, T31).
- **Multi-exam Geometry cross-cutting (Part V)** (2026-06-24) — Calculate per-exam patient-offset summary (`lon/ver/lat`); Settings hides global Phantom spinboxes in multi-exam (C6); `per_exam_offsets_version` refresh; Settings transform → Geometry refresh + event-index clamp (N4); Upload→Geometry exam click; help/docs updated (T10).
- **Fix Geometry exam selector startup** (2026-06-24) — avoid `Invalid value: 0` when no exams are loaded (NiceGUI select requires value in options or None).
- **Fix multi-exam Results stale UI after recalc** (2026-06-24) — rebuild per-exam PSD/metrics and dose-map dialogs when `calc_run_id` changes; clear cached aggregate dose map on each run.
- **GUI decomposition (refactor plan Phase 3, 2026-06-23):** `gui/app.py` slimmed from ~1275 to 245 lines — `index()` now orchestrates layout + `PageContext` and delegates to per-tab `build(ctx)` modules (`gui/tabs/{upload,data,settings,geometry,calculate,results,export}.py`). Shared upload widgets in `gui/widgets/{import_preview,event_table}.py`; concurrency guard and upload temp-file lifecycle in `gui/concurrency.py` and `gui/upload_temp_files.py`. Below-floor kVp pre-calc prompt moved to `gui/tabs/calculate.py`. `app.py` removed from the file-size CI whitelist. Plan archived as `dev-docs/plans/archive/refactor-execution.md`.
- **Export `schema_version` (refactor plan Phase 4.3, 2026-06-23):** JSON/dict exports from `PySkinDoseOutput.to_dict()` and `MultiExamResult.to_dict()` now include top-level `schema_version` (currently `1`) so downstream consumers can detect format changes without relying on package semver.
- **Plotly layout helpers (refactor plan Phase 4.2, 2026-06-23):** `plotting/plot_layout.py` centralizes shared `go.Layout` builders for CLI/notebook geometry, procedure, and dose-map plots; `create_setup_and_event_plot`, `plot_procedure`, and `create_layout_for_dose_map_plots` delegate to it (`gui/figures.py` unchanged).
- **GUI help single source of truth** (2026-06-24): in-app help markdown now lives in `docs/source/gui_help/` and is mirrored to `src/mypyskindose/gui/help/` by `scripts/sync_gui_help.py` (enforced by pre-commit + CI). `positioning_offsets.md` merged from the prior `docs/source/user_guide/` copy and the original GUI version (Overview + 6-step workflow + Tips from the GUI; Coordinate System, Troubleshooting, and Getting More Help from the docs version; 4-row Quick Reference with `Lateral/Longitudinal/Vertical/Rotation` and a MyST footnote). `geometry_workflow.md` and `below_floor_kvp.md` relocated unchanged. New Sphinx toctree entries between `user/user_guide.md` and `getting_started/`. `scripts/check_doc_freshness.py` extended to scan the new directory. `AGENTS.md` Conventions section documents the rule. Plans archived under `dev-docs/plans/archive/`.

### Added

- **Ignored asset advisory check** (2026-06-24): `scripts/check_ignored_asset_files.py` warns (pre-commit hook; `--strict` to fail) when `.png` or `.html` files outside `PlotOutputs/` are untracked or gitignored, including tracked-but-ignored paths that can be dropped from version control while `*.png` / `*.html` remain in `.gitignore`. Restored `wiki/*.png` illustrations after accidental untracking in commit `e856ccd`.

- **User options for below-floor kVp events** (2026-06-19): events with a kVp below the 25 kV HVL table floor can now be handled by an explicit policy instead of being silently clamped. A new setting `below_floor_kvp_policy ∈ {snap (default), skip, manual, exam_average}` (+ `below_floor_kvp_manual`) is applied per exam in `geom_calc.apply_below_floor_kvp_policy()`, called at the top of `calculate_dose()` before the HVL lookup: `snap` keeps the status quo (clamp + flag), `skip` drops the events, `manual` substitutes a fixed kVp, and `exam_average` substitutes that exam's mean in-floor kVp (falls back to `snap` + warns if an exam is all below floor). `geom_calc.count_below_floor_events()` detects affected events; every policy emits a `logger.warning` → `state.calc_warnings`. GUI: a "Below-floor kVp handling" control under Physics settings (`gui/tabs/settings.py`) holds the persistent default, and a pre-calc prompt (`gui/app.py`) appears only when sub-floor events are detected, offering the policy + "don't ask again". Defaults preserve existing results (`snap`). Wired through `PyskindoseSettings`, `settings_example.json`, and `gui/helpers.build_settings`. Tests in `tests/unittests/test_geom_calc.py` (per-policy transforms, detection, all-below fallback) and `tests/unittests/test_gui_below_floor_kvp.py` (detection sum, settings propagation). Completes `dev-docs/plans/archive/hvl-interpolation-and-below-floor-kvp.md`.

- **Multi-exam Data Table exam column** (2026-06-19): in multi-exam mode the normalized event table (`state.rdsr_df`) now tags every row with a display-only `Exam` column (`"#<n> · <file>"`) so it is clear which loaded exam a row came from. Centralized in `gui/helpers.rebuild_rdsr_df()` (replaces four inline `pd.concat` sites); single-exam frames stay untagged and the tag is stripped before the single-exam calculation, so dose output is unchanged. Pinned first in the Data Table; included in normalized CSV/XLSX exports, omitted from raw exports. Unit tests in `tests/unittests/test_gui_rdsr_df.py`.

- **Recursion-to-iteration prep** (2026-06-16): golden baseline test and pinned `dose_map` fixture for `siemens_axiom_artis.dcm` (cylinder phantom); 1100-event stress test; `tests/calculate_dose_recursion_helpers.py` for synthetic normalized events; `slow` pytest marker. Plan in `dev-docs/plans/recursion-to-iteration.md`.

### Changed

- **Dependencies unified into `pyproject.toml` extras** (2026-06-19): removed the legacy `requirements.txt`, `requirements-dev.txt`, and `docs/requirements.txt`, which had drifted out of sync with the `pyproject.toml` extras (e.g. `requirements-dev.txt` installed black/isort/pydocstyle — tools the project no longer runs — while omitting the actual CI toolchain). `pyproject.toml` is now the single source of truth: new `[docs]` (Sphinx, sphinx-rtd-theme, myst-parser, nbsphinx, ipykernel, ipywidgets, pandoc) and `[notebooks]` (JupyterLab) extras hold the previously-requirements-only toolchains, and the `[dev]` extra gained `pytest` and `ruff` to be a true superset of the CI lint/type/test stack. `.readthedocs.yml` now installs `.[docs]` via `extra_requirements`; README/AGENTS install instructions point at the extras. `scripts/check_licenses.py` inventories the full declared extra set (`dev,gui,gui-native,docs,notebooks`) and `dev-docs/THIRD_PARTY_NOTICES.md` is regenerated from `uv sync --all-extras` (pinned by `uv.lock`), making the notices reproducible regardless of which extras a venv installed; the `license-notices` pre-commit hook now also triggers on `uv.lock`. Also dropped the dead `[tool.black]` and `[tool.isort]` config blocks — ruff is the sole formatter/linter.

- **HVL lookup now interpolates off-grid filtration** (2026-06-19): `geom_calc.fetch_and_append_hvl()` replaces the exact-match-with-nearest-snap lookup with **2-D bilinear interpolation over (kVp, Cu)** on the selected `(inherent, Al)` grid slice (`scipy.interpolate.RegularGridInterpolator`, cached per slice). Off-grid copper filtration (tabulated gaps at 0.5/0.7/0.8 mmCu) is now linearly interpolated instead of snapped; out-of-range queries are **clamped** to the nearest grid edge (never extrapolated). Anode angle is **selected** (first-occurrence dedup ≈ 11° where present, else 8°), not interpolated — a discrete tube property. kVp is rounded to its nearest integer node (table is 1-kV dense), so **in-grid results are unchanged** (golden PSD identical; `test_fetch_hvl_from_database` characterization preserved). Per-event `interpolated`/`clamped` warnings flow through the `mypyskindose` logger to `state.calc_warnings` (calc-tab status line + toasts). New tests in `tests/unittests/test_geom_calc.py` (interpolation betweenness, edge clamping, on-grid silence). HVL drives `k_bs` and `k_med`. Shared 2-D clamped-interpolation helper extracted to `src/mypyskindose/grid_interp.py`. First slice of `dev-docs/plans/archive/hvl-interpolation-and-below-floor-kvp.md`; below-floor-kVp user options still pending.

- **k_tab table-attenuation lookup guarded + interpolated** (2026-06-19): `corrections.calculate_k_tab()` no longer crashes on off-grid or unknown beam/device parameters. The old exact-match SQL ending in `c.fetchone()[0]` raised `TypeError` (`None[0]`) and aborted the whole calculation on any untabulated `(kVp, Cu, Al)` tuple or unknown device/plane (e.g. a non-Siemens/Philips export such as GE). Now: exact match stays the primary path (in-table results bit-for-bit unchanged — `test_fetch_correct_table_correction_*` preserved); an unknown device/plane **fails soft to `k_tab=1.0`** with a warning; off-grid copper within a known device is **interpolated over (kVp, Cu)** (per-`(model, plane, Al)` slice, all complete grids) and out-of-range queries are **clamped** to the grid edge. Per-event `no-device`/`interpolated`/`clamped` warnings surface via `state.calc_warnings`. New robustness tests in `tests/unittests/test_corrections.py`. `k_med` intentionally left as nearest-tabulated (cannot crash; documented <1% field-size dependence).

### Fixed

- **Per-event dose loop** (2026-06-16): `calculate_irradiation_event_result()` no longer recurses once per irradiation event; uses an iterative loop so procedures with >1000 events (and future multi-exam runs) do not hit Python's recursion limit. Output verified bit-identical to the prior implementation via golden baseline test.

- **Tabular input Phase 1** (2026-06-09): `src/mypyskindose/input_adapters/` package — shared loader, column mapper, registry, `normalized` schema adapter; handles CSV/TSV/XLSX with encoding fallback (UTF-8/BOM/cp1252), delimiter sniffing, decimal-comma normalization, and offset header detection. CLI flags `--input-schema`, `--sheet-name`, `--input-preview-only`. Python API `analyze_input_file()` and `preview_input_file()`. Architecture layer tests. Full unit test suite with six fixture variants.
- **Tabular input Phase 2** (2026-06-09): `generic_rdsr_like` schema adapter — maps `rdsr_parser()`-style columns to `rdsr_normalizer()` input and produces the normalized DataFrame; `--input-schema auto` with ≥0.20 margin scoring. `GENERIC_RDSR_PATTERNS` and `GENERIC_RDSR_COLUMN_NAMES` in `column_mapper.py`; `NORMALIZED_COLUMN_CANONICAL` for proper-case output matching `rdsr_normalizer()`. Test fixture `generic_rdsr_events.csv` (21-event Siemens AXIOM-Artis).
- **Tabular input Phase 3** (2026-06-10): `radimetrics` schema adapter in `input_adapters/radimetrics.py`; `RADIMETRICS_PATTERNS` and `RADIMETRICS_COLUMN_NAMES` in `column_mapper.py`; unit conversions (reference dose mGy→Gy, field area cm²→m², exposure mAs→µAs) with provenance tracking; unknown model warning (non-blocking); auto-detection support; synthetic fixture `radimetrics_events.csv` (5-event Siemens AXIOM-Artis); 8 new tests (46 total for input_adapters). GUI schema selector updated to include "Radimetrics CSV".
- **Tabular input Phase 4** (2026-06-10): `dosetrack` schema adapter in `input_adapters/dosetrack.py`; `DOSETRACK_PATTERNS` and `DOSETRACK_COLUMN_NAMES` in `column_mapper.py`; Equipment Name → Manufacturer/ModelName inference via `MODEL2MANUF` (`AXIOM-Artis`→Siemens, `Azurion`/`Allura Clarity`→Philips); `ffill()` for hierarchical DoseTrack row format; integer Plane Code → "Single Plane"/"Plane A"/"Plane B"; unit conversions (Air Kerma mGy→Gy, DAP Gy·cm²→Gy·m², Tube Current µA→mA); `CollimatedFieldArea_m2` derived from `DAP / (DoseRP * ((DSI-150)/DSD)²)` formula; Siemens filter thickness max=min; Philips semicolon-split Al;Cu filter thickness; Philips lat/lon swap warning; registered in registry with auto-detection support; synthetic fixture `dosetrack_events.csv` (5-event AXIOM-Artis); 10 new tests (56 total for input_adapters).
- **Vendor adapter stubs** (2026-06-10): `qaelum.py`, `dosemonitor.py`, `dosewatch.py` — each has empty `VENDOR_COLUMN_NAMES`/`VENDOR_PATTERNS` with `TODO` notes and an `adapt()` that raises `NotImplementedError` with step-by-step implementation instructions. Wired into registry for explicit `--input-schema` selection; excluded from auto-detection until column maps are populated. Qaelum, DoseMonitor, and DoseWatch documented as Phase 5+ placeholders in `TABULAR_RDSR_INPUT_PLAN.md` and `FEATURE_INVENTORY.md`.
- **Header-row detection fix** (2026-06-10): `detect_header_row` threshold changed from fraction-based (`matched/total_cells ≥ 0.05`) to absolute hit count (`matched_columns ≥ 5`). Fixes false-negative on exports with 100+ columns where few columns are in the known set. `_score_row` now also normalizes `known_names` before comparison so underscore-containing entries in `GENERIC_RDSR_COLUMN_NAMES` (e.g. `"distancesourcetodetector_mm"`) correctly match normalized cell values (`"distancesourcetodetector mm"`). `_score_schema` (auto-detection) is unaffected — it uses its own `.lower()`-only normalization.
- **Tabular input Phase 5** (2026-06-10): GUI upload tab now accepts `.csv`, `.tsv`, `.xlsx`, `.xlsm` in addition to `.dcm`; routes to `load_tabular()` helper; schema selector dropdown (Auto-detect / Normalized / Raw RDSR-like / Radimetrics CSV / DoseTrack XLSX/CSV); import preview panel showing schema, encoding, delimiter, header row index, column mapping table, warnings, and first 5 normalized events; **individual coordinate correction toggles** (Swap lateral ↔ longitudinal `Tx↔Tz`, Flip primary angle `Ap1×−1`, Flip secondary angle `Ap2×−1`) with tooltips, each its own inverse applied live to `state.rdsr_df`; **intelligent transform defaults** auto-set from detected manufacturer (GE Radimetrics and Philips DoseTrack auto-enable lat/lon swap) with override hint label; **XLSX sheet picker** shown only for multi-sheet files, re-parses on change without overwriting user transform choices; Calculate tab blocked on import errors; Data Table tab shows source filename and schema. Tabular provenance now preserved in JSON exports (`tabular_input` key) and HTML exports (HTML comment in `<head>`).
- **Vendor coordinate documentation**: new "Tabular input coordinate handling" section in `VENDOR_COORDINATE_SYSTEMS.md`; `TabularImportOptions` plan (Phase 3+) documented in `TABULAR_RDSR_INPUT_PLAN.md`; DoseTrack Philips lat/lon swap finding added.
- **Reference implementations saved**: `dev-docs/references/` now contains `dhen2714_radimetrics.py`, `dhen2714_dosetrack.py` (from `github.com/dhen2714/PySkinDose`), and `psdcalcrework_io_utils.py` (from private repo) with findings summary.

- Harness docs: `TO_DO.md` cleanup (pending vs open questions vs completed); `FEATURE_INVENTORY.md` §0 harness/CI shipped features; GUI doc consolidation (`GUI_PLAN.md` §0 supersedes `UI_ANALYSIS.md`); `scripts/generate_ui_values.py` for auto-generated `UI_values.md`; `dev-docs/references/` stub; Phase 6 plan lifecycle closed.
- Harness docs: `check_doc_freshness.py` now scans `CHANGELOG.md` for `FEATURE_INVENTORY` contradictions; doc-gardening cadence documented in `HARNESS_ENGINEERING.md`.
- Harness CI: **basedpyright** `typecheck` job (strict — any type error fails); optional baseline helpers in `scripts/type_baseline.sh`; `[dev]` optional dependency.
- Harness CI: **gitleaks** secret scanning workflow on push/PR.
- Harness CI: **bandit** `bandit` job (Python SAST on `src/mypyskindose` + `scripts`; medium+ severity gate).
- Harness CI: **pip-audit** `dependency-audit` job (core + `[dev]` + `[gui]` extras; fails on known CVEs).
- Harness CI: **license compliance** — `scripts/check_licenses.py` in `dependency-audit` job; policy in `dev-docs/LICENSE_COMPLIANCE.md`; inventory in `dev-docs/THIRD_PARTY_NOTICES.md`.
- Harness local hooks: **pre-commit** config (commit: ruff, gitleaks, bandit, doc-freshness; pre-push: basedpyright).
- Harness Phase 5: GUI smoke tests (`tests/gui/`) with NiceGUI user simulation; `gui-smoke` CI job; `tests/scripts/launch_gui_headless.py`.
- Harness Phase 4: package layering documented in `CODEBASE_OVERVIEW.md`; structural layer tests in `tests/unittests/test_architecture_layers.py`.
- Harness Phase 3: `python -m build` in CI (`package-build` job on Ubuntu, Python 3.12); local full checks now match CI.
- Harness Phase 2: root `CHANGELOG.md`; `python -m compileall src/mypyskindose` in CI; GitHub Actions upgraded to current majors.
- Harness Phase 1: `scripts/check_doc_freshness.py` and Ubuntu CI job for broken internal markdown links and checkable `FEATURE_INVENTORY.md` contradictions.
- Harness Phase 0: `dev-docs/index.md` documentation catalog; expanded source-of-truth map in `dev-docs/HARNESS_ENGINEERING.md`; `design.md` renamed to `DESIGN.md`.

### Changed

- **Per-exam corrections moved to Settings tab** (2026-06-19): the editable per-exam controls (patient offsets, coordinate corrections, table-origin override, "Apply global to all") now live in a new **Settings → Per-exam corrections** section (`gui/tabs/_per_exam.py`, registered via `ctx.refresh_per_exam`) instead of the Upload tab, so each exam is edited separately and apart from the global settings. The Upload tab keeps a compact loaded-files summary (badges, event count, warnings, remove button) and points to Settings for edits. Trims `gui/app.py` by ~225 lines.
- Harness docs: document master vs execution vs archive plan conventions in `HARNESS_ENGINEERING.md`; add `dev-docs/plans/archive/` (basedpyright plan); sync `TO_DO.md` with shipped tabular Phases 3–5; update `dev-docs/index.md` catalog.
- Repository hygiene: stop tracking build artifacts (`dist/`), Jupyter checkpoint notebooks, legacy `phantom_data/old/` meshes, local `debug.json`, ad-hoc `_test_gui_import.py`, and duplicate `.windsurf/` rules; expand `.gitignore` for `PlotOutputs/`, coverage output, and local agent config.
- Type checking: resolved all 147 basedpyright errors; CI now runs strict `basedpyright` (no baseline). Optional incremental baseline workflow documented in `.basedpyright/README.md` with `scripts/type_baseline.sh`.
- Pre-commit: `cleanup-old-backups` hook removes `backups/*.bak` files last touched more than 5 commits ago; `backups/` added to `.gitignore`.
- Harness Phase 2: stop tracking generated `src/mypyskindose.egg-info/`; `.gitignore` covers egg-info and standard Python build artifacts.
- Harness Phase 2: CI `flake8` limited to syntax/fatal errors (`E9,F63,F7,F82`); style overlap with `ruff` (120-column) removed from CI.
- Harness Phase 2: `.github/workflows/ci.yml` and `release.yml` use `actions/checkout@v4` and `actions/setup-python@v5`.
- CI test matrix: full 3 OS × 4 Python on pull requests and `main` pushes only; other branch pushes run a single Ubuntu + Python 3.12 `build` cell (other jobs unchanged).
- Local hooks: **basedpyright** moved to pre-push only via pre-commit (`pre-commit install --hook-type pre-push`); removed manual `scripts/pre-push.sh`.

### Fixed

- Dose calculation: `calculate_k_isq` now returns one inverse-square-law factor per hit cell for any number of hits. A `len(cells) > 3` guard previously fell back to `norm(axis=0)` for events hitting ≤3 skin cells, which crashed (`operands could not be broadcast (2,) (3,)`) for 1–2 hits and silently mis-dosed exactly-3-hit events. Affected exports whose geometry clips the phantom at only a few cells.
- Dose output template: `k_med` placeholder aligned to scalar `float`; zero-hit events now write explicit correction slots (`k_bs` empty array, `k_med` 0.0 meaning not applied, real per-event `k_tab`) instead of leaking template placeholders. New-geometry zero-hit events no longer carry stale `k_isq` / `field_area` from the prior event.
- Pre-commit backup cleanup: new untracked `backups/*.bak` files are no longer deleted just because the same path was touched in older git history.
- Pre-commit backup cleanup: a backup whose path is still tracked in `HEAD` but was recreated/force-staged (or locally modified) with new content is now protected too — commit-age deletion is skipped when the path has pending staged/unstaged changes, deferring to the mtime fallback.
- Normalization settings: `update_translation_offset` and `update_rotation_direction` now apply vendor overrides from JSON/settings (previously no-ops when values were already initialized).
- Phantom: cylinder mesh resolution assertions run after resolution is assigned (basedpyright refactor had broken cylinder phantom creation).
- Type-check fixes for unit tests (2026-06-24): resolved 10 basedpyright errors blocking the pre-push type check. `tests/unittests/test_check_doc_pruning.py` now passes a structural lambda matching the `GitAgeProvider` protocol's `relative_path` parameter (and wrapping `dict.get`) instead of binding the `dict.get` bound method directly; `tests/unittests/test_plot_layout.py` reads margin values through `to_plotly_json()` to avoid basedpyright's spurious `tuple[Unknown, ...] | None` inference for the untyped plotly `Layout.margin` property. No behavior change.

## [25.1.1] - 2025-01-01

### Added

- MyPySkinDose fork baseline: peak skin dose estimation and 3D skin dose maps from fluoroscopic RDSR data.
- NiceGUI application (`python -m mypyskindose --mode gui`).

[Unreleased]: https://github.com/kgrizz-git/GUISkinDose/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/kgrizz-git/GUISkinDose/compare/v25.1.1...v1.0.0
[25.1.1]: https://github.com/kgrizz-git/GUISkinDose/releases/tag/v25.1.1
