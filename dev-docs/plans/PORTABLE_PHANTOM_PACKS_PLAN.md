# Portable phantom packs — Phase 2

_Status: in progress (Steps 0–3 implemented on branch). Execution plan for Phase 2 of [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md) (User library and offline pack)._
_Created: 2026-11-07._
_Parent: [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md) lines 136–159 and 321–330. Phase 3 download and pack signing stay in the parent plan._

This file is the checklist. Do the steps in order. Each step is one reviewable PR, or a smaller PR that finishes every box in that step. Do not start the next step with the previous step's tests red.

SemVer: this is a minor feature. Leave `pyproject.toml` at `1.1.1` until a release. Put the user-facing change under `[Unreleased]` → Added in `CHANGELOG.md`. Put test-only and harness notes in `dev-docs/MAINTENANCE_LOG.md`.

## Goal

A Light install can add clinical meshes from a local pack zip. The zip is data. It is not a second application. Full already contains the clinical catalog, so a Full user does not need a pack. Calculation uses the mesh the user selected. It does not switch to another body when that file is missing.

## What the code does today

Mesh lookup reads only the package directory. These places each derive that directory from `__file__`:

- `package_phantom_data_dir()` in `src/guiskindose/phantom_mesh_names.py`
- `_PHANTOM_DATA_DIR` in `src/guiskindose/gui/helpers.py` (about line 89), used by `get_human_mesh_names()` and `_cache_mesh_baseline_measurements()`
- `_PHANTOM_DATA_DIR` in `src/guiskindose/gui/phantom_preview.py`, used by `resolve_preview_mesh()` and `make_phantom_preview_fig()`
- `print_available_human_phantoms()` in `src/guiskindose/__init__.py`

`resolve_human_mesh_stl_path()` checks the safe-stem pattern and that the file exists. It is not an allow-list beyond `is_clinical_catalog_stem()`. A clinical stem with no STL raises `HumanMeshNotInstalledError`. Any other missing stem raises `ValueError` (`Unknown human mesh stem.`).

The clinical allow-list already exists as `_CLINICAL_SORT_ORDER` and `_CLINICAL_DISPLAY_LABELS` in `phantom_mesh_names.py`. Legacy names in `HUMAN_MESH_ALIASES` resolve before that check. `edition.py` is the freeze include list (Light is 28 STL names). It is not the runtime catalog. Plane and cylinder phantoms are generated in code and are not catalog rows.

Settings builds a `ui.select` from files on disk (`get_human_mesh_options()`). `canonicalize_human_mesh_selection()` then rewrites a missing stem to `hudfrid`, or to the first clinical option. `_select_installed_mesh()` in `gui/tabs/settings.py` explains that rewrite. `tests/gui/test_light_edition_gui.py` locks the rewrite. Calculate calls `human_mesh_not_installed_message()` and notifies. That message looks only at the package directory. The CLI excepthook prints a `UserFacingInputError` verbatim and hides every other exception behind a generic code (`privacy.install_value_safe_excepthook`). `HumanMeshNotInstalledError` is a bare `ValueError` today, so a headless run does not show the mesh sentence.

There is no user phantom directory, no pack manifest, and no zip installer. Window prefs and equipment profiles stay in `~/.guiskindose/`. Extra phantoms must not go there. The parent plan names a separate per-OS directory.

`gui/helpers.py` is about 723 lines. New pack code does not belong in that file. `phantom_mesh_names.py` stays the stem, alias, label, and sort module.

## Rules for every step

- One lookup function: `resolve_human_mesh_stl_path`. Callers stop joining a stem onto a directory they computed themselves. The order is the Resolution rule below, and that section is the only place the order is defined.
- The clinical catalog is the allow-list for packs and for the user library. A pack cannot add a new stem, a legacy alias, a demo stem, or a `_reduced_1000t` file.
- A pack member whose stem is already a shipped file is skipped and counted. The rest of that zip may still install. A non-catalog stem, an alias, a demo stem, or an unsafe path rejects the whole archive.
- Logs, notifications, and CLI text name the display label and the canonical stem. They do not contain an absolute path, a zip name, a home directory, or a source filename.
- Hash is SHA-256. Do not accept MD5 or SHA-1. Signing is a function seam for Phase 3. Phase 2 does not treat a signature as trust.
- New functions stay at Ruff C901 ≤ 10. New and edited Markdown and Python files stay under 800 lines. Split modules instead of growing `helpers.py` or `settings.py`.
- `src/` uses `pathlib.Path`. Atomic publish uses `Path.replace()`, not `os.rename`. Platform path rules live in one function that takes the platform name, the environment, and the home path, so tests cover Windows, macOS, and Linux on any runner.
- GUI tests go under `tests/gui/`. Zip and path tests go under `tests/unittests/`. Tests use a temp library and a tiny synthetic STL. They do not download and they do not read the real home phantom directory.
- Edit help under `docs/source/gui_help/`. Run `python scripts/sync_gui_help.py`. Do not hand-edit `src/guiskindose/gui/help/`.
- Update tests when this plan changes their locked behavior. Say so in the PR. Do not weaken an assertion to keep a rewrite that this plan removes.

## Resolution rule

Shipped data first, then the user library. A shipped file cannot be shadowed.

After `resolve_human_mesh_stem()` and `assert_safe_human_mesh_stem()`:

1. If the shipped root has `{stem}.stl` as a regular file inside that root, return it. Do not read a user-library file of the same stem.
2. Otherwise, if the stem is a clinical catalog stem and the user library has that regular file inside the library root, return it.
3. Otherwise, if the stem is in `DEMO_HUMAN_MESHES` or `GUI_HIDDEN_HUMAN_MESHES`, do not look in the user library. A `DEMO_HUMAN_MESHES` stem resolves only from the shipped root, and only when `show_demo_phantoms_enabled()` is true. `GUI_HIDDEN_HUMAN_MESHES` stay off the Settings list. When the demo flag is off, a demo stem raises `ValueError` and is not loaded.
4. Otherwise a clinical catalog stem raises `HumanMeshNotInstalledError` with the install hint. Any other stem raises `ValueError` (`Unknown human mesh stem.`) and is not looked up on disk.

`prefer_reduced_preview_stem()` uses this same order. It still prefers `_reduced_3000t`, then a legacy `_reduced_1000t` if that file is already in the shipped tree. A pack must not contain `_reduced_1000t`. Dose calculation loads the full stem. The Settings preview may use the reduced companion. If the companion is absent, the preview uses the full STL when that file exists.

## User library

| OS | Directory |
|----|-----------|
| macOS (`darwin`) | `~/Library/Application Support/GUISkinDose/phantoms` |
| Windows (`win32`) | `%LOCALAPPDATA%\GUISkinDose\phantoms` |
| Linux and other | `$XDG_DATA_HOME/guiskindose/phantoms`, or `~/.local/share/guiskindose/phantoms` when `XDG_DATA_HOME` is unset |

`~/.guiskindose/` stays the home of `gui.json` and the equipment-profile store. Uninstall text names both that directory and the phantom directory. Deleting the app folder does not delete either one.

If `LOCALAPPDATA` is unset on Windows, install and lookup fail with a fixed sentence. They do not invent a path and they do not echo the environment. Lookup does not create the directory. Install creates it, mode `0o700`, before it stages any file. Write STL files mode `0o600`. If `chmod` is unavailable, keep going and do not log the path. Refuse to install when the library path is a symlink. If this install created the directory and the install then fails, remove that empty directory so the machine matches the pre-install state.

## Pack manifest

The zip root contains `manifest.json` and the listed `.stl` files. Nothing else. The manifest is UTF-8 JSON, at most 256 KiB, with no duplicate keys.

```json
{
  "format": 1,
  "pack_version": "1.1.1",
  "app_versions": ["1.1.1"],
  "files": [
    {"stem": "senior_male", "bytes": 128, "sha256": "<64 lowercase hex chars>"}
  ]
}
```

- `format` must be `1`.
- `pack_version` is the pack's own version string, at most 32 characters, and it must match one entry in `app_versions`.
- `app_versions` is a list of exact application versions. The running `guiskindose.__version__` must be in the list. A `0.0.0+unknown` tree fails closed unless the caller passes an expected version in tests.
- Each `stem` is the canonical stem, not a legacy alias. It must be a clinical full mesh, an `_arms_down` twin, or a `_reduced_3000t` companion. Reject `_reduced_1000t`, demo stems, and hidden demo stems.
- `bytes` must equal the decompressed size. `sha256` must equal the SHA-256 of those bytes.
- Unknown keys fail closed, except that the key `signature` is reserved. Phase 2 rejects a present `signature` with a fixed sentence. The function `verify_pack_signature()` is the Phase 3 seam. Its Phase 2 body only checks that the key is absent. Trust is the SHA-256 pin below.
- No extra archive member, no missing member, no duplicate stem.

The installer also hashes the canonical manifest bytes (UTF-8, keys sorted, no insignificant whitespace) and compares them to `EXPECTED_PHANTOM_PACK_SHA256` in a new `src/guiskindose/phantom_pack_pin.py`. Tests pass an explicit expected hash so they do not need the production pin. An empty production pin refuses every real install. Fill the pin in the same PR that adds `scripts/build_phantom_pack.py`, which builds a zip from the repo's clinical STLs that are outside `light_phantom_stl_names()` and checks the pin with `--check`. Do not commit the zip. Publishing it is Phase 3.

## Zip limits

Reject the archive before any library file is replaced when any check fails.

| Check | Limit |
|-------|-------|
| Members, including the manifest | 128 |
| Compressed zip size | 80 MiB |
| Declared size of one member | 8 MiB |
| Actual bytes read from one member | 8 MiB |
| Running total of decompressed bytes | 80 MiB |
| Declared uncompressed / compressed ratio | 100 |

Also reject the whole archive for: directories, absolute paths, drive prefixes, backslashes, `.` and `..` parts, empty names, names other than `manifest.json` or `{stem}.stl` at the zip root, case-fold collisions, encrypted members, symlinks (Unix mode `0o120000`), and any other non-regular Unix file mode when the mode is non-zero. A Windows-written zip often stores mode 0. Accept mode 0 only after the name and size checks. A non-catalog stem, a legacy alias, or a demo stem also rejects the whole archive. A member whose canonical stem is already a file in the shipped root is skipped and counted. It is not a reason to reject the other members. Do not use `extract()` or `extractall()`. Read each member in 64 KiB chunks and count the bytes, because the central-directory size can lie. Stop reading when the cap is crossed.

Create the library directory, mode `0o700`, before staging. Stage inside that directory (a child such as `library/.incoming-<token>/`) so `Path.replace()` stays on one volume. Publish one stem at a time: move the existing `library / f"{stem}.stl"` aside to a backup name, then `Path.replace()` the staged file onto the destination. On any failure, including `PermissionError` when Windows has the destination open, put every backup back, delete any file this install added, and delete the stage directory. The library then matches the pre-install bytes. On success, delete the backups and the stage directory. Do not report paths. A failure is `PhantomPackError`, defined in the next section.

## Errors

`UserFacingInputError` in `src/guiskindose/privacy.py` is the existing type whose message the CLI excepthook prints verbatim. Its text must be fixed code-owned sentences and counts, never a path or a filename.

Add `PhantomPackError` in `src/guiskindose/phantom_pack.py`, subclassing `UserFacingInputError`. Use it for manifest, pin, zip, and install failures. Catch `OSError` (including `PermissionError`), `zipfile.BadZipFile`, and `KeyError` at the install boundary and raise `PhantomPackError` with a fixed sentence. Log the original exception through `safe_error_event`. Do not put `str(exc)` in the user message, because those types often include a path. `HumanMeshNotInstalledError` stays a separate subclass of `UserFacingInputError` for a missing catalog mesh.

## Step 0 — Register the plan

- [x] Add a row for this file under Master plans in `dev-docs/index.md`.
- [x] Add a short pointer in `dev-docs/TO_DO.md` that links here. Remove that pointer in the PR that finishes the acceptance list.
- [x] Do not tick the Phase 2 boxes in `PORTABLE_APP_PLAN.md` until the matching step here is done.

## Step 1 — One catalog lookup

Files:

- `src/guiskindose/phantom_library.py` (new). Roots, installed-stem query, and the two-root file check.
- `src/guiskindose/phantom_mesh_names.py`. Keep stems, aliases, labels, and sort. Make `resolve_human_mesh_stl_path()` and `prefer_reduced_preview_stem()` call the library. Extend `human_mesh_not_installed_message()` so a missing catalog stem names the pack install. Keep the Light sentence about the Full download, and the Full sentence about reinstall, as the second sentence.
- `src/guiskindose/privacy.py` consumers only. Change `HumanMeshNotInstalledError` so it subclasses `UserFacingInputError`. The message stays label, stem, and fixed sentences.

The shipped root remains `package_phantom_data_dir()`. The optional `phantom_data_dir=` argument stays for tests and means the shipped root only. Add `user_library_dir=` the same way. Both default to the real roots. Tests pass temp paths and must not touch the real home library.

`get_human_mesh_names()` returns installed full-resolution clinical stems from the lookup, not from a raw glob. `get_human_mesh_options()` still appends a shipped `DEMO_HUMAN_MESHES` stem when `show_demo_phantoms_enabled()` is true. That stem is not a clinical name and is not read from the user library. `print_available_human_phantoms()` calls `get_human_mesh_names()` and prints stems only.

Point these callers at the lookup, and delete their private joins:

- `Phantom._load_human_mesh` already calls `resolve_human_mesh_stl_path`. Leave the tuple form as the trusted in-memory path.
- `gui/helpers.py` measurement (`_cache_mesh_baseline_measurements`).
- `gui/phantom_preview.py` (`resolve_preview_mesh`, `make_phantom_preview_fig`).
- `plotting/create_geometry_plot.py` already calls `prefer_reduced_preview_stem`. Confirm it does not grow a third root.

Do not add pack parsing in this step.

Tests (`tests/unittests/test_phantom_library.py`, new, plus updates to `test_human_mesh_path_safety.py` and `test_edition.py`):

- [x] A catalog stem in the temp user library resolves there when the shipped temp dir lacks it.
- [x] The same stem in the shipped temp dir wins when both dirs have a file. The user bytes are not the bytes returned.
- [x] `../`, separators, NUL, and an unknown stem still raise `ValueError`, and the unknown stem is not `HumanMeshNotInstalledError`.
- [x] A resolved path is always `is_relative_to` the root that supplied it.
- [x] The missing-mesh message contains the label and the stem, the words for a pack install, and neither the temp path nor a slash-form of that path.
- [x] Legacy alias `pediatric_5y_male` still resolves to `ped_5y_male.stl`.
- [x] Preview still prefers `_reduced_3000t` from either root. The shipped root is tried first.
- [x] With `show_demo_phantoms_enabled()` true, a demo stem resolves from the shipped temp dir and does not resolve from the user library. With the flag false, that stem raises `ValueError`. A pack path is not part of this step.

`test_edition.py` currently expects the Light missing text to say `Full download` and the Full missing text to say `Reinstall`. Keep those sentences. Add the pack sentence. Update the assertions in the same PR and say that the message gained an install hint.

## Step 2 — Manifest, pin, and signature seam

Files:

- `src/guiskindose/phantom_pack.py` (new). Parse and validate the manifest. Hash files. Call `verify_pack_signature()`. Define `PhantomPackError` here.
- `src/guiskindose/phantom_pack_pin.py` (new). The expected manifest hash constant only.
- `scripts/build_phantom_pack.py` (new). Maintainer build and `--check`. The script stays under C901 10 by splitting list, hash, and write.

- [x] Raise `PhantomPackError` for a bad `format`, a version that is not running, an alias stem, a demo stem, a `_reduced_1000t` stem, a stem outside the catalog, a byte mismatch, and a SHA-256 mismatch. Each of those rejects the whole archive. A stem that is already shipped is valid in the manifest. Install skips it later.
- [x] Reject duplicate JSON keys and any unknown key.
- [x] `verify_pack_signature()` raises a fixed error when `signature` is present and returns when it is absent.
- [x] `scripts/build_phantom_pack.py --check` fails if `EXPECTED_PHANTOM_PACK_SHA256` does not match a pack built from the non-Light clinical STLs. The zip is written only under `tmp/` and is not committed.
- [x] Unit tests in `tests/unittests/test_phantom_pack_manifest.py` use a synthetic STL and an injected hash. They do not rebuild the 64-file catalog pack.

## Step 3 — Safe zip install

Files:

- `src/guiskindose/phantom_pack_install.py` (new). Classify a member, read with a cap, stage inside the library, back up, and `Path.replace`. Each of those is its own function. `OSError`, `zipfile.BadZipFile`, and `KeyError` become `PhantomPackError` here.
- The public function is `install_phantom_pack(source, *, user_library_dir, shipped_dir, expected_manifest_sha256, app_version) -> InstallResult`. `source` is a binary file object, not a `bytes` blob. `InstallResult` holds counts only: installed and skipped because shipped. It holds no paths. A rejected archive raises `PhantomPackError` instead of returning a rejected count.

- [x] A synthetic zip installs `senior_male.stl` into the temp library and leaves the shipped temp dir unchanged.
- [x] First run, when the library path does not exist yet: the install creates it before staging. On POSIX, `stat().st_mode & 0o777` is `0o700`. On Windows, the directory exists and is not a symlink. The test does not require Unix mode bits on Windows.
- [x] A second run with the same bytes replaces the library file and still leaves no stage directory and no backup file.
- [x] A tampered STL byte fails the hash, raises `PhantomPackError`, and leaves the previous library file in place.
- [x] Reject the whole archive for a symlink member, an absolute member name, a `..` member, a directory member, two names that case-fold together, a non-catalog stem, an alias stem, a demo stem, a 129th member, a member whose actual bytes exceed 8 MiB, and a member whose tiny header hides a stream past the running cap. Nothing from that zip is left in the library.
- [x] A zip that mixes one already-shipped stem with one missing clinical stem skips the shipped stem, counts that skip, installs the missing stem, and does not change the shipped file.
- [x] Full edition: when the shipped dir already contains every stem in the zip, the result counts those stems as skipped, and the user library does not gain them. When the Full shipped dir is missing one catalog stem, that stem installs into the user library.
- [x] Mid-replace rollback: monkeypatch `Path.replace` so the second file raises `PermissionError`. After `PhantomPackError`, every destination matches its pre-install bytes, backups are gone, and the stage directory is gone. Include a file that existed before the install and a stem this install would have added.
- [ ] A failure before the first `Path.replace` leaves an existing library byte-for-byte as it started. If the install created the directory, that directory is removed.
- [x] Log capture for every failure case contains none of: the zip path, the library path, `tmp_path` text. The `PhantomPackError` message has no path.
- [x] Tests live in `tests/unittests/test_phantom_pack_install.py`.

## Step 4 — CLI

The settings field `phantom.human_mesh` stays the selector. Do not add a second mesh flag.

- [x] A headless calculate or plot whose human mesh is a missing catalog stem prints the `HumanMeshNotInstalledError` sentence to stderr and exits 1. The excepthook must not replace it with the generic operation code.
- [x] The same run for plane or cylinder does not consult the mesh library.
- [x] Add `--install-phantom-pack PATH` on the headless parser in `cli_args.py`. It installs and exits. It does not require `--file-path`. It prints counts and a fixed success or failure sentence. It does not print `PATH`.
- [x] `--mode gui` plus `--install-phantom-pack` exits 1 with a fixed sentence, the same shape as the equipment-profile GUI refusal in `__main__.py`.
- [x] A bad zip exits 1 with the `PhantomPackError` sentence and does not create a library file. `BadZipFile` and `OSError` from the installer are not what the process prints.
- [x] Tests in `tests/unittests/test_phantom_pack_cli.py` use the temp library and monkeypatch the pin and the version. They do not launch the GUI.
- [x] One test runs `--install-phantom-pack` with no `--file-path`. It exits 0, prints the installed count, and does not start a calculation.

## Step 5 — Settings rows and install action

Files:

- `src/guiskindose/gui/tabs/_phantom_catalog.py` (new). Build the catalog rows and the install handler. Keep `settings.py` under 800 lines.
- `src/guiskindose/gui/phantom_preview_controller.py`. When the preview figure is missing because the selected human mesh is not installed, set the status label to the install hint. `settings.phantom_preview.unavailable` stays the text for a corrupt or unreadable file.
- `src/guiskindose/gui/io_helpers.py`. Add an open dialog for a `.zip` next to the existing save dialog. Native mode uses pywebview's open dialog and passes the opened file object to `install_phantom_pack`. Neither path is logged. Follow `safe_error_event` on dialog failure.
- `src/guiskindose/gui/tabs/settings.py`. Stop calling the Hudfrid rewrite for a catalog stem. Browser mode uses one `ui.upload`.
- `src/guiskindose/gui/tabs/_run_config.py`. The run-state import path calls `_select_installed_mesh()`. It must keep a saved catalog stem that is not installed.

NiceGUI 3.18 (`nicegui/elements/upload.py` and `upload_files.py` in the locked tree) does not give the handler a `SpooledTemporaryFile`. `UploadEventArguments.file.read()` returns the whole body as `bytes`. `file.iterate()` yields chunks. A body larger than Starlette `MultiPartParser.spool_max_size` (1 MiB) is already a `LargeFileUpload` temp file. The handler must not call `read()`. Stream `iterate()` into a `tempfile.SpooledTemporaryFile` with `max_size` at most 1 MiB, seek to the start, and pass that object as `source`. Delete the spool when the install returns. `ui.upload` sets `max_file_size` to 80 MiB and `accept=".zip"` (the same `.props('accept=...')` pattern as the run-configuration uploader). `max_file_size` is enforced in the browser. The stream loop still stops at 80 MiB so a bypassed client cannot fill memory.

Rows follow `_CLINICAL_SORT_ORDER`. Each row shows the display label and either Installed or Not installed. Arms-down twins are their own rows. Demo rows stay behind `show_demo_phantoms_enabled()` and are never pack targets or user-library files. When that flag is on, a demo stem that exists in the shipped dir still loads. Plane and cylinder hide the human catalog, as the mesh select hides today.

The select options are the full clinical catalog, so a missing current value still binds. A missing stem's label uses a `ui_copy` suffix `(not installed)`. Choosing a missing stem sets `state.human_mesh` to that stem and does not rewrite it. One button, `Install phantom pack`, starts the zip flow. There is no download button. A caption says a later version can fetch the pack. That caption is the Phase 3 placeholder.

After a successful install, rebuild the options from a fresh `get_human_mesh_options()` call. Do not use the import-time `HUMAN_MESHES` snapshot in `gui/constants.py`. On failure, show the fixed sentence and leave the previous selection in place.

`tests/gui/test_light_edition_gui.py` expects a saved `senior_male` to become `hudfrid`. Change that expectation to: the stem stays `senior_male`, and the note is the install hint. State that in the PR.

GUI tests in `tests/gui/test_phantom_pack_settings.py`:

- [x] With a temp shipped set that has `adult_male` and a temp library that has `senior_male`, the senior row is Installed and the adult row is Installed.
- [x] A catalog stem in neither root is Not installed, remains the selected value, and is not replaced by `hudfrid`.
- [x] The install control accepts a synthetic zip and the row flips to Installed without a process restart. The test reads the temp library file. It does not assert a real home path.
- [ ] A tampered zip leaves the row Not installed.
- [ ] The preview status for a missing human mesh shows the install hint and does not draw a different body.

## Step 6 — Block calculation

Files:

- `src/guiskindose/gui/tabs/calculate.py`. `_human_mesh_is_installed()` already notifies and returns before dose work. Point it at the two-root message.
- `src/guiskindose/gui/figures.py`. `make_geometry_fig()` builds a `Phantom`. Catch `HumanMeshNotInstalledError` and return no figure instead of a substituted body. Do not log the exception text.
- `src/guiskindose/gui/tabs/geometry_controller.py`. When `make_geometry_fig()` returns no figure for a missing human mesh, `ui.notify` the install hint. That file already calls `ui.notify` for other blocked actions. Do not add a new status widget. Leave the plot empty. A plane or cylinder preview is unchanged.

These three paths exist today. `calculate.py` gates `do_calculate`. `figures.py` owns `make_geometry_fig`. `geometry_controller.py` calls that function around the `run.io_bound` site.

- [x] Human model plus a missing catalog stem notifies with the install hint, does not call the dose runner, and does not change `state.human_mesh`.
- [x] The same stem becomes calculable after the Step 5 install, using a synthetic STL that `Phantom` can load or a stub of the runner if the STL is too small to mesh. Prefer a tiny valid STL if the test suite already has a builder. Otherwise stub `Phantom` only in the GUI test and keep a real `Phantom` load in the unit test from Step 1.
- [x] Plane and cylinder still calculate without a mesh file.
- [x] Geometry preview of a missing human mesh shows the hint and does not substitute `hudfrid`.
- [x] GUI coverage goes in `tests/gui/test_phantom_pack_settings.py` or `tests/gui/test_calculate_tab_coverage.py`. Do not put this NiceGUI test under `tests/unittests/`.

## Step 7 — Docs, help, and registries

- [x] Add `docs/source/gui_help/phantom_packs.md`. State that a pack is optional data, that Full already contains the catalog, that Light gains the other clinical meshes from a pack zip or the Full download, and that removing extra meshes means deleting the per-OS phantom directory. Name `~/.guiskindose/` as the prefs and profile directory, not as the mesh directory. Do not write an absolute path from this machine.
- [x] Register it in `dev-docs/help_registry.json` with a new help id, and add a `HelpButton` on the catalog section.
- [x] Adjust `docs/source/gui_help/phantom_preview.md` so it no longer says the mesh list is only what `phantom_data/` happens to contain.
- [x] Run `python scripts/sync_gui_help.py` and commit the mirrored help.
- [x] Add `ui_copy` keys for the not-installed suffix, the install button, the success count sentence, the failure sentence, the Phase 3 caption, and the CLI GUI-mode refusal. Owners are the modules that call `copy_text()`.
- [x] Add a glossary entry `phantom pack` in `dev-docs/glossary.json`.
- [x] Add a `phantom_packs` feature to `dev-docs/feature_doc_matrix.json` with the new modules, the new tests, this plan, `ADDITIONAL_PHANTOMS.md`, and the help page.
- [x] Update `AGENTS.md` (phantom paragraph), `dev-docs/ADDITIONAL_PHANTOMS.md`, and `dev-docs/FEATURE_INVENTORY.md` so they describe the catalog lookup and the user library.
- [x] Run `python scripts/check_help_registry.py`, `python scripts/check_ui_copy.py`, `python scripts/check_feature_doc_matrix.py`, and `python scripts/sync_gui_help.py --check`.
- [x] Tick the matching Phase 2 boxes in `PORTABLE_APP_PLAN.md` only for behavior that has landed. Leave the parent acceptance box open until the acceptance section below is done.
- [x] Changelog Added bullet. Maintenance log bullet for the pin script and the tests.

## Acceptance

- [ ] A Light settings tree whose shipped dir has only the starter meshes, plus a pack zip of one missing clinical stem, resolves that stem after install, still resolves it after a new process reads the same library, and uses it for a human-phantom calculation. The automated form of this is the unit test plus the GUI test. The parent plan's Light-app sentence also needs one manual smoke on a Light zip. Record that smoke on the parent plan. Do not tick the parent acceptance from unit tests alone.
- [ ] A zip with one flipped STL byte is rejected and the previous library file is unchanged.
- [ ] A zip whose decompressed stream exceeds the running cap is rejected before that stream is written into the library.
- [ ] A shipped stem is skipped and counted. The shipped file is unchanged, and the user library does not gain a copy. On the Full edition the same skip applies to every stem the payload already has.
- [ ] A mid-replace `PermissionError` rolls the library back to its pre-install bytes.
- [ ] Selecting a missing catalog mesh blocks calculation and shows the install hint. It does not load `hudfrid`.
- [ ] CLI stderr and captured logs for these cases contain no absolute path.
- [ ] `python scripts/check_file_sizes.py` and `python scripts/check_complexity.py` pass for the new modules.
- [ ] `uv run --extra dev --extra gui --locked pytest tests/unittests/test_phantom_library.py tests/unittests/test_phantom_pack_manifest.py tests/unittests/test_phantom_pack_install.py tests/unittests/test_phantom_pack_cli.py tests/unittests/test_human_mesh_path_safety.py tests/unittests/test_edition.py tests/gui/test_phantom_pack_settings.py tests/gui/test_light_edition_gui.py` passes.

## Out of scope

- Phase 3 network download, redirect allow-list, cancel, and retry. The signature function and the Settings caption are the only seams this phase leaves.
- Building or signing a release zip of the pack. The builder script writes `tmp/` or checks the pin.
- Per-stem download, custom user STLs outside the clinical catalog, and writing into `phantom_data/` inside the bundle.
- Changing Light or Full freeze include lists. `edition.py` stays the payload list.
- Moving `gui.json` or equipment profiles out of `~/.guiskindose/`.
