# macOS and Linux portable builds in CI

_Status: in progress — chunks 1–3 are in the tree on branch `portable/mac-linux-ci-builds`; chunk 4 (archive wrapper plan) waits on green Full macOS arm64 and Linux runs. Frozen Full `--png-check` stays unchecked until a completed Actions run id is recorded._
_Parent: [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md) Phase 0b "Export PNG offline" and Phase 1 "CI builds Windows, macOS, and Linux onedir zips"._
_Closes the frozen-proof gap in [PORTABLE_BROWSER_WRAPPER_PLAN.md](PORTABLE_BROWSER_WRAPPER_PLAN.md). The wrapper code is already on main (PR #218). This plan adds the builds that run it, and it changes the macOS browser path the wrapper plan left undecided._

Extend `.github/workflows/portable-spike.yml` with macOS arm64 and Linux x86_64 jobs. Each job builds Light and Full. Full bundles a pinned ungoogled-chromium and runs the frozen `--png-check`. Release Developer ID signing and notarization stay in the parent plan. The macOS job does ad-hoc re-sign the outer bundle after the browser copy, then runs `codesign --verify --deep --strict`. That is a layout check. It is not a notarized release signature.

The Windows job's steps stay as they are. The shared `on:` block gains `main` and a path filter, so a docs-only push no longer rebuilds Windows either. Update the workflow's opening comment so it names the unix jobs and the ad-hoc layout check.

## Decisions

| Topic | Decision |
|-------|----------|
| Workflow | New jobs in `portable-spike.yml`. One trigger list and one concurrency group. |
| macOS arch in the default matrix | arm64 on `macos-15`. The job checks `uname -m` and stops unless it prints `arm64`. |
| macOS Intel | `macos-15-intel`, Full only, and only when a `workflow_dispatch` input asks for it. The wrapper closeout does not wait for it. |
| Linux arch | x86_64 on `ubuntu-24.04`. |
| macOS Chromium.app | `GUISkinDose.app/Contents/Helpers/Chromium.app`, copied with `ditto` after the freeze. |
| macOS notices | `GUISkinDose.app/Contents/Resources/chromium/`. License files and `CREDITS.html` stay out of `Contents/MacOS`, `Contents/Helpers`, and `Contents/Frameworks`. |
| Ad-hoc signing | PyInstaller already ad-hoc signs the bundle. The `ditto` copy breaks that seal. After `--png-check` against the upstream nested signature, CI re-signs inside-out with identity `-` and no hardened runtime, then `codesign --verify --deep --strict`. |
| Linux browser | Launch `chromium/chrome` directly. Prepend that directory to `LD_LIBRARY_PATH`. The binary has no `DT_RUNPATH`. A green runner `ldd` is not a self-contained bundle. |
| Trigger | `workflow_dispatch`, plus push to `portable/**`, `spike/portable-*`, and `main`, filtered by paths that include `src/guiskindose/**`. No `pull_request` trigger. |
| Artifact retention | 7 days. The zips are CI artifacts. They are not Release assets and they are not committed. |

## Where the macOS browser goes

Checked on this Mac with a toy bundle, signed the way `packaging/portable/macos_sign_notarize.sh` signs: every Mach-O, then each nested `.app` deepest first, then the outer app, identity `-`, no `--options runtime`. Verify was `codesign --verify --deep --strict`, the same command the script runs after its walk (script line 242). `--deep` is only on the verify. The sign walk does not pass `--deep`.

| Layout | Result |
|--------|--------|
| `Contents/MacOS/chromium/Chromium.app` plus `LICENSE.chromium.txt` in that `chromium` directory | Sign fails: `code object is not signed at all`, subcomponent the license file. |
| `Contents/Helpers/LICENSE.chromium.txt` beside `Chromium.app` | Same failure. A loose file in a code directory is rejected. |
| `Contents/MacOS/chromium/Chromium.app` with no loose file | Verify passes on this OS today. |
| `Contents/Helpers/Chromium.app` and notices under `Contents/Resources/chromium/` | Verify passes. |
| `Contents/Frameworks/Chromium.app` and the same Resources notices | Verify passes. |
| `Contents/Helpers/chromium/Chromium.app` and Resources notices | Verify passes. |
| Outer app signed, then `ditto` of a nested app into `Contents/Helpers` | Verify fails: `a sealed resource is missing or invalid`. Re-signing inside-out makes verify pass again. |

Apple TN2206 says code locations (`Contents/MacOS`, `Contents/Helpers`, `Contents/Frameworks`) are expected to contain only code, and that a directory of nested code inside a code location is not officially supported. The loose license file is the failure this bundle would hit, because `pngcheck` currently wants those files in the `chromium` directory. The extra `chromium` directory under `MacOS` is the pattern TN2206 does not support, even though today's `codesign` accepted the toy with no loose file. This plan does not ship that pattern.

`Contents/Helpers/Chromium.app` is the location. TN2206 lists helper apps under `Contents/Helpers` and under `Contents/MacOS`, and lists frameworks and dylibs under `Contents/Frameworks`. Both Helpers and Frameworks passed the toy verify. Frameworks is already where PyInstaller puts `Python.framework` and the extension modules. Helpers is empty in that bundle and is the helper-app row in the TN2206 table. The app is placed directly in Helpers, not in `Helpers/chromium/`, so there is no extra directory of nested code.

Notices go in `Contents/Resources/chromium/`: `LICENSE.chromium.txt`, the platform ungoogled-chromium license, and `CREDITS.html`. Resources is where TN2206 says data files are sealed, in `Contents/_CodeSignature/CodeResources`, rather than in extended attributes. The macOS zip stays `ditto -c -k --keepParent` so framework symlinks survive.

The pinned arm64 disk image `156.0.8078.79-1.1` hashes to `4ff3b084c49d2391aecdd3924ebd1bd7417fb1dd88e3da45891bee73f8e5c173` (hashed from the GitHub asset on 2026-11-06). Its root holds `Chromium.app`. The Mach-O is `Chromium.app/Contents/MacOS/Chromium`. Helper apps already live inside that bundle, under its own `Contents/Frameworks/Chromium Framework.framework/.../Helpers/`. `ditto` of the whole `.app` carries them. Nothing else is copied into `GUISkinDose.app/Contents/Frameworks`.

### Code that has to follow the move

Today three lookups join `chromium` onto the directory of the frozen executable, which on this bundle is `Contents/MacOS`:

- `bundled_browser()` in `src/guiskindose/export/png_browser.py` returns `<exe dir>/chromium/Chromium.app/Contents/MacOS/Chromium` on darwin.
- The wrapper confinement in `packaging/portable/entry.py` allows a target only under `<exe dir>/chromium`.
- `selfcheck._bundled_browser_present` is true when `<exe dir>/chromium` exists.
- `pngcheck._chromium_notice_dir` is `<exe dir>/chromium`, and `pngcheck.app_dir` is the root `_inside` uses for `launched_from_onedir`.

On darwin those have to move together. `Contents/Helpers` is a sibling of `Contents/MacOS`, so a browser there is outside today's `app_dir()` and `--png-check` would report `launched_outside_onedir` even for the bundled Mach-O.

| Piece | darwin rule | Linux and Windows |
|-------|-------------|-------------------|
| Executable directory | `Contents/MacOS` | the onedir |
| Browser | `Contents/Helpers/Chromium.app/Contents/MacOS/Chromium` | `<onedir>/chromium/chrome` or `chrome.exe` |
| Wrapper root | `Contents/Helpers` (the Mach-O and the helpers inside `Chromium.app` are inside; a binary under `Contents/MacOS/chromium` is refused) | `<onedir>/chromium` |
| Notice directory | `Contents/Resources/chromium` | `<onedir>/chromium` |
| Containment root for `_inside` | `Contents` | the onedir |
| Browser present | `Contents/Helpers/Chromium.app` is a directory | `<onedir>/chromium` is a directory |

`bundled_browser(base)` keeps treating `base` as the executable directory. On darwin, `base.name` is `MacOS`, and the browser is `base.parent / "Helpers" / "Chromium.app" / "Contents" / "MacOS" / "Chromium"`. The relative report path from `Contents` is `Helpers/Chromium.app/Contents/MacOS/Chromium`.

Tests that encode the old path have to change in the same chunk: `tests/unittests/test_png_browser.py` (`bundled_browser(tmp_path)` on darwin), `tests/unittests/test_portable_pngcheck.py` (the macOS `launched_from_onedir` string and both notice-directory tests), and a new darwin case in `tests/unittests/test_portable_entry.py`. The existing entry fixture forces the linux override and still uses `<exe dir>/chromium/chrome`. Leave that fixture on linux. Add a darwin override whose allowed browser is under `Contents/Helpers` and whose `Contents/MacOS/chromium` target exits 1 before `dup2`.

## Ad-hoc signing

PyInstaller 6.22.3 `BUNDLE` calls `sign_binary(..., deep=True)` at the end of the build (`PyInstaller/building/osx.py`). `sign_binary` (`PyInstaller/utils/osx.py`) uses identity `-` when no identity is set, and it adds `--options=runtime` only when an identity string is set. The spec does not set an identity, so the freeze is an ad-hoc signature without the hardened runtime.

Copying `Chromium.app` in after that sign changes a sealed bundle. The toy reproduced the failure: `a sealed resource is missing or invalid`. A later `codesign --verify --deep --strict` on the outer app fails until the outer app is signed again. Leaving the outer app unsigned does not avoid that. The seal is already there, and the copy breaks it.

The nested `Chromium.app` from the disk image is a separate signature. `codesign -dv` on the mounted app reports `Developer ID Application: Qian Qian (B9A88FL5XJ)`, Team ID `B9A88FL5XJ`, a stapled ticket, and flags `kill,restrict,library-validation,runtime`. An ad-hoc re-sign of that nested app replaces the Team ID. Phase 0b recorded that an ad-hoc signature has no Team ID, so the hardened runtime's library validation then needs `disable-library-validation`. `packaging/portable/macos_entitlements.plist` is an empty dictionary, and this job does not add that key. `sign_binary` itself withholds `--options=runtime` for identity `-`.

CI order for Full:

1. Freeze. Delete `tmp/portable/work`.
2. `ditto --norsrc --noextattr --noacl` `Chromium.app` into `Contents/Helpers/Chromium.app`, then run `xattr -cr` on that copy only. Clearing only `com.apple.quarantine` is not enough, because `codesign --verify --strict` rejects the other extended attributes the disk image carries. Clearing them is a CI step. It is not applied to a user download, and it is not `spctl --master-disable`.
3. `codesign --verify --strict` on the nested `Chromium.app` alone. This checks that `ditto` and the attribute clear left the upstream seal intact. A failure stops the job.
4. Write notices under `Contents/Resources/chromium/`, including `CREDITS.html` from `dump_chromium_credits.py` against the Mach-O. Run the first `--png-check`. The outer seal is already invalid. A non-quarantined executable still runs, which is what this step is measuring: the pipe wrapper and Kaleido, against the upstream nested binary.
5. Re-sign inside-out with `codesign --force --sign -` and no `--options runtime`, no `--timestamp`, and no `--deep`: every Mach-O under `Contents`, then each nested `.app` and `.framework` deepest first, then `GUISkinDose.app`. This matches the release script's walk with identity `-`.
6. `codesign --verify --deep --strict` on `GUISkinDose.app`. A failure fails the job. This is the command the release script will run later. It checks the seal. It does not check dyld library validation.
7. Run `--png-check` again on the unzipped artifact (expanded tree from the zip that was built after step 6). If the pre-resign run passed and this one fails, the summary says `adhoc_resign_broke_launch` and the job fails. The wrapper evidence is the first run. The post-resign run is the one that matches what a user expands from the artifact.

Light has no `ditto` of a nested app. After the freeze, run `codesign --verify --deep --strict` once. Do not re-sign Light when that verify already passes.

`macos_sign_notarize.sh` stays out of this job. It requires a Developer ID, it turns on the hardened runtime, and it notarizes. The later release PR re-signs this same Helpers layout with that script and reads the notary log. The empty entitlements file stays empty.

A passing first `--png-check` means the bootloader handed Chromium pipe fds through child-side `preexec_fn` remap even when the frozen parent already holds fd 3 (`base_library.zip`). The summary says `wrapper_fds=child_remap` when that run passes. The signing script's use of fd 3 is the shell reading a notary env file. This job does not run that script.

## Runners, memory, and disk

GitHub's hosted-runner table lists `macos-15`, `macos-26`, and `macos-latest` as arm64, 3-core M1, 7 GB RAM, 14 GB disk. Pin `macos-15`. `macos-latest` currently tracks the macOS 26 image. `macos-15-intel` is Intel, 4-core, 14 GB RAM.

Public `ubuntu-24.04` is x64, 4-core, 16 GB RAM, 14 GB disk. Pin that label. Record the glibc banner from `ldd --version` in the summary.

`kgrizz-git/GUISkinDose` is public. Standard hosted runners are free there. The scarce resource is the macOS queue and the 7 GB RAM ceiling. If the repository is made private, the published rates are macOS `$0.062` per minute and Linux `$0.006`. A 40-minute Full macOS job is about `$2.50` at that rate, before Light.

Delete `tmp/portable/work` after a successful freeze, and delete the disk image or tarball after the copy, before `--png-check`. If the freeze dies with no Python traceback, treat that as the 7 GB ceiling and record it here. The escape hatch, after that OOM is recorded, is `macos-15-intel` (14 GB) for the Full freeze, or a larger runner the organization already pays for. This plan does not subscribe to larger runners and does not start on Intel.

Timeouts: 90 minutes for each macOS job, 75 minutes for each Linux job. `fail-fast` is false on each matrix.

## Pinned Chromium

Windows stays on `156.0.8078.73-1.1`. This plan does not bump it. Both unix pins are Chromium `156.0.8078.79`.

| OS | Asset | sha256 | Checked |
|----|-------|--------|---------|
| macOS arm64 | `ungoogled-chromium_156.0.8078.79-1.1_arm64-macos.dmg` from `ungoogled-software/ungoogled-chromium-macos` tag `156.0.8078.79-1.1` | `4ff3b084c49d2391aecdd3924ebd1bd7417fb1dd88e3da45891bee73f8e5c173` | Hashed from the GitHub asset on 2026-11-06. |
| macOS x86_64 | `ungoogled-chromium_156.0.8078.79-1.1_x86_64-macos.dmg`, same tag | `152f0d67ab9301a2e6fa4d38b25e1382c0c74c72772d533ce7c4390e599a1db4` | Release-notes digest only. The Intel job fails closed on a mismatch. |
| Linux x86_64 | `ungoogled-chromium-156.0.8078.79-1-x86_64_linux.tar.xz` from `ungoogled-software/ungoogled-chromium-portablelinux` tag `156.0.8078.79-1` (157,697,672 bytes) | `d35a9064068274af1a2efa8bcb9b42306e590f9b5c929789f2e0e51a35880499` | Hashed from the GitHub asset on 2026-11-06. One top-level directory, 675 members. `chrome` sits in that directory. |

The Linux job uses the `.tar.xz`. The AppImage on the same release is the wrong artifact. Copy the directory contents into `chromium/` so the binary is `chromium/chrome`. Copying only the `chrome` file drops the libraries that sit beside it.

Download with a fail-closed sha256 check. Print the expected digest and the actual digest on mismatch. Each pin lives in the job env and in `dev-docs/references/PORTABLE_CHROMIUM_ARTIFACT.md`. No browser binary is committed.

### What the Linux binary links

The `chrome` ELF from that tarball has no `DT_RPATH` and no `DT_RUNPATH`. It has 32 `DT_NEEDED` entries, including `libnss3.so`, `libnspr4.so`, `libnssutil3.so`, `libsmime3.so`, `libX11.so.6`, `libXext.so.6`, `libcairo.so.2`, `libpango-1.0.so.0`, `libgbm.so.1`, `libasound.so.2`, `libcups.so.2`, `libatk-1.0.so.0`, `libgtk` is not in the list, and the glib/gio/dbus family is. The files beside `chrome` (`libEGL.so`, `libvulkan.so.1`, `libvk_swiftshader.so`, `libqt5_shim.so`) are not those `DT_NEEDED` names. A direct exec uses the system linker path. `ubuntu-24.04` already provides those sonames, so `ldd` can print no `not found` line while every one of them was resolved outside `chromium/`.

`chrome-wrapper` in the same tarball exports `LD_LIBRARY_PATH` to `$HERE`, `$HERE/lib`, and `$HERE/lib.target`, then execs `chrome`. When `ldd` reports them missing, the script symlinks host copies of `libnss3.so`, `libnspr4.so`, and the related NSS sonames from `/lib64`, `/lib`, `/usr/lib64`, and `/usr/lib` into the tree. The portable tarball is not a closed set of libraries. The wrapper says so.

The frozen app launches `chromium/chrome`, not `chrome-wrapper`. The wrapper also writes an XDG desktop file under the user data directory. This plan does not exec it.

On Linux, the frozen entry prepends the `chromium` directory to `LD_LIBRARY_PATH` before any child starts, so a bundled soname wins over a system one and the child inherits the path. That is the `$HERE` half of the wrapper. It does not vendor the 32 `DT_NEEDED` sonames, and it does not make PNG work on a machine that lacks them.

The Linux job runs `ldd` on `chromium/chrome` with that `LD_LIBRARY_PATH`. The summary lists two soname sets and no resolved paths: sonames resolved inside `chromium/`, and sonames resolved outside it, plus any `not found`. A green `--png-check` with a non-empty outside set still passes the wrapper proof. The summary says the air-gapped Linux claim is open. The parent plan drops that claim when PNG needs packages only root can install. This job must not apt-install those packages to empty the outside list. Do not read a zero `not found` count as a self-contained bundle.

### License files

`pngcheck.NOTICE_FILES` at `packaging/portable/pngcheck.py` line 48 is `LICENSE.chromium.txt`, `LICENSE.ungoogled-chromium-windows.txt`, and `CREDITS.html`. `_check_bundle` requires every name. A macOS or Linux Full run fails `browser_notices_missing` until the name follows the host. `_write_chromium_notices` in `tests/unittests/test_portable_pngcheck.py` iterates that tuple (the helper at line 109), so a darwin test currently writes the Windows license file and would still pass for the wrong reason.

Replace the tuple with `required_notice_names()`: always `LICENSE.chromium.txt` and `CREDITS.html` (at least 100 kB), plus one packaging license.

| Host | Extra file | Directory |
|------|------------|-----------|
| `win32` | `LICENSE.ungoogled-chromium-windows.txt` | `<onedir>/chromium` |
| `darwin` | `LICENSE.ungoogled-chromium-macos.txt` | `Contents/Resources/chromium` |
| anything else | `LICENSE.ungoogled-chromium-portablelinux.txt` | `<onedir>/chromium` |

Commit the two new texts from each repo's `LICENSE` at the pinned tag. Diff the Chromium source `LICENSE` at `156.0.8078.79` against the committed `LICENSE.chromium.txt` (from `156.0.8078.73`). Identical text means every bundle copies that one file. A difference means the workflow copies the text that matches that binary, and the artifact note records both. The credits dump still fails on a placeholder page.

The darwin success test writes the three files under `Contents/Resources/chromium` and reads them from there. Notices beside the Mach-O, or only the Windows license file, still fail. The Windows ancestor test stays on `chromium/chrome.exe`.

### Process names in the PNG report

`_describe_launch` keeps a descendant when `"chrom"` is in the file name (`pngcheck.py` around the browser filter). That already counts `chrome`, `chrome.exe`, `Chromium`, and `Chromium Helper`, and the macOS unit test expects `chromium/Chromium.app/Contents/MacOS/Chromium`. That string changes to `Helpers/Chromium.app/Contents/MacOS/Chromium` when the containment root becomes `Contents`. The bootloader name `GUISkinDose` stays excluded.

`system_chrome_processes_running` is the narrower counter. It counts a process whose file name is exactly `chrome.exe` and whose path is outside the root. A system `chrome`, `google-chrome`, or `Google Chrome` on macOS or Linux adds nothing to that field. Extend the name set to those file names, case-insensitive, still outside the containment root. Add a unit test that an outside `chrome` and an outside `Google Chrome` increment the counter, and keep the existing `chrome.exe` assertion. The CI gate remains `launched_outside_onedir == 0`, which uses the descendant filter, plus the required relative path.

## What each job runs

Shared setup, matching Windows: checkout, setup-python, and setup-uv at the SHAs already pinned in `portable-spike.yml`, Python 3.14, uv `0.11.25`, then `uv sync --locked --extra gui-native --group portable`. `permissions` stay `contents: read`. No signing secrets and no GitHub environment.

Unfrozen reference, then the freeze:

```bash
uv run --no-sync python packaging/portable/entry.py --self-check "$RUNNER_TEMP/selfcheck-unfrozen"
uv run --no-sync pyinstaller packaging/portable/guiskindose.spec --noconfirm \
  --distpath tmp/portable/dist --workpath tmp/portable/work
```

The spec stages Light or Full from `GUISKINDOSE_PORTABLE_EDITION`. Record `BUILD_SECONDS` and the PyInstaller version. Then the browser and signing steps above. Light must not contain `Contents/Helpers/Chromium.app` on macOS, and must not contain a `chromium` directory on Linux.

Zip after the signature step that the artifact should carry. macOS: `ditto -c -k --keepParent` of the re-signed `GUISkinDose.app`. Linux: zip the onedir. The parent plan's `.desktop` file is not in the tree. This Linux zip is the onedir alone.

Expand that archive and run the self-check from the expanded tree. The macOS binary is `GUISkinDose.app/Contents/MacOS/GUISkinDose`. The Linux binary is `GUISkinDose/GUISkinDose`. On macOS, the pre-resign `--png-check` runs on the build tree before the zip; the post-resign run happens on the expanded artifact. Linux runs `--png-check` once, from the expanded tree, with `LD_LIBRARY_PATH` already set by the frozen entry.

Strip `git` from `PATH`: drop every entry whose directory contains an executable named `git`, then fail if `git` is still visible. `git_on_path` in the report must be false.

Self-check, twice. Same edition assertions as Windows, with these host differences:

- `report.frozen` is true, and the PSD equals the unfrozen reference from this runner.
- `reduced_1000t_stl` is 0, the preview stem is `adult_male_reduced_3000t`, and the starter mesh loads.
- Light: PNG export off, bundled browser absent, `to_image` count 0, non-starter mesh `not_installed`.
- Full: PNG export on, bundled browser layout present, non-starter mesh `loads`.
- `webview2.applicable` is false.

Full `--png-check` sets `BROWSER_PATH` to a path that is not on disk. Copy `pngcheck_report.json` into `out/` before the assertions. Require exit 0, `page.http_script_refs == 0`, `render.launched_outside_onedir == 0`, `render.png_images >= 2` and equal to `render.images`, `render.png_bytes_total > 0`, and every `launched_from_onedir` entry relative. macOS includes `Helpers/Chromium.app/Contents/MacOS/Chromium`. Linux includes `chromium/chrome`. Other entries must stay under `Helpers/Chromium.app/` or `chromium/`. An empty process list is `browser_not_seen`, which fails the job.

`pngcheck._require_bundled_launch` only requires a watched browser under `app_dir()` (``Contents`` on macOS, the onedir elsewhere). It does not check the Mach-O path string. CI's `macos_frozen_png_check.sh` sets `BROWSER_REL` and `png_assert` requires that exact relative path in `launched_from_onedir`; Linux and Windows workflows assert `chromium/chrome` or `chromium/chrome.exe` inline the same way.

If the browser file exists and the report is `browser_not_seen`, the follow-up is a long-lived sampler on that OS. Unix already polls `ps` every 0.1 s. Build a long-lived sampler only after that red report. Do not move Chromium again in response to it.

### macOS launch smoke

Start the Mach-O after the re-sign, wait up to 120 s for `127.0.0.1:8765`, then stop the process. Record whether the server listened. Do not require a second GUI process. Read the native log only to test for the startup line and the NiceGUI ready line. Do not print the log.

### Linux launch and display

This job does not launch the GUI. Linux v1 calls `run_gui(native=False)`, and a headless `xdg-open` can hang the step. `--self-check` imports the GUI stack. The summary records `native=false`.

Do not start Xvfb first. If png-check fails with a display error and the `not found` soname list is empty, rerun that step under `xvfb-run -a` and record `display=xvfb`. Do not tee Chromium's stderr into the log.

### Network

The required proof is the decoy `BROWSER_PATH` plus `launched_outside_onedir == 0`. On Linux, try `unshare --net` around `--network-probe` and, when that probe shows the outbound call blocked, around `--png-check`. If `unshare` is refused, record `network_namespace=unavailable` and run png-check in the normal namespace. That refusal does not fail the job. On macOS, skip `pf`. The summary records `network_block=skipped`.

## Artifacts and the job summary

| Edition | OS | Zip name | Artifact name |
|---------|----|----------|---------------|
| light, full | macOS arm64 | `GUISkinDose-<edition>-macos-arm64.zip` | `guiskindose-<edition>-macos-arm64` |
| full | macOS x86_64, dispatch only | `GUISkinDose-full-macos-x64.zip` | `guiskindose-full-macos-x64` |
| light, full | Linux x64 | `GUISkinDose-<edition>-linux-x64.zip` | `guiskindose-<edition>-linux-x64` |

`actions/upload-artifact` at the SHA the Windows job already uses, `retention-days: 7`, `if: always()`, `if-no-files-found: warn`.

The summary step is `if: always()`. Fields: edition, arch, build seconds, onedir size, zip size, Chromium version, credits product count, png wall seconds, png image count, the required relative browser path, nested upstream verify, outer `--verify --deep --strict`, second png-check, Linux bundled-soname count, Linux system-soname count, display helper, network result. Numbers and relative names only.

## Triggers and cost

```yaml
on:
  workflow_dispatch:
    inputs:
      macos_intel:
        description: Also build Full on macos-15-intel
        type: boolean
        default: false
  push:
    branches: ['spike/portable-*', 'portable/**', 'main']
    paths:
      - '.github/workflows/portable-spike.yml'
      - 'packaging/portable/**'
      - 'src/guiskindose/**'
      - 'pyproject.toml'
      - 'uv.lock'
```

`src/guiskindose/**` is the whole frozen package: dose code, GUI, phantoms, tables, and `png_browser.py`. A filter that names only `edition.py`, `_edition.py`, `png_browser.py`, and `webview2.py` would leave a `main` push of `gui/app.py` or `calculate_dose/` on the old artifact. `packaging/portable/**` already covers `entry.py`, `pngcheck.py`, and the spec. Test-only pushes stay off this workflow. `workflow_dispatch` ignores `paths`. The Intel job's `if` is `github.event_name == 'workflow_dispatch' && inputs.macos_intel`.

The path filter applies to the Windows job too, because there is one `on.push`. A docs-only push rebuilds nothing. A package change rebuilds Windows, macOS, and Linux.

There is no `pull_request` trigger. The proof runs on the `portable/**` branch push and again on `main` when a matching path changes. Fork pull requests are the wrong place to download and execute a browser.

Concurrency stays `portable-spike-${{ github.ref }}` with `cancel-in-progress: true`. A cancelled job is a superseded run. Quote a completed run id in the progress log.

## How a failure shows up

The job name is `macos-<edition>` or `linux-<edition>` (and `macos-intel-full` for the dispatch leg). The red step is the failing one: hash, freeze, nested verify, credits dump, first png-check, ad-hoc re-sign, outer verify, or second png-check. The summary still prints. The artifact uploads when `out/` has files. Seven days later it expires, so the progress log cites the run id before that.

`continue-on-error` is not set on those steps. The Xvfb retry and the `unshare` fallback are the only second attempts besides the deliberate second macOS png-check.

## Tests and docs

```bash
uv run --extra dev --extra gui --locked python -m pytest \
  tests/unittests/test_portable_pngcheck.py \
  tests/unittests/test_portable_entry.py \
  tests/unittests/test_png_browser.py \
  tests/unittests/test_portable_selfcheck.py -q
uv run --extra dev --extra gui --locked python scripts/check_complexity.py
```

New helpers stay at Ruff C901 ≤ 10. `packaging/` is outside the complexity scanner. Keep the limit anyway. Do not weaken an assertion to make a test pass.

| File | Edit |
|------|------|
| `dev-docs/index.md` | Add a row for this plan next to the wrapper-plan row. This authoring change is the plan file alone, so the implementation PR adds the index row before `check_doc_freshness.py`. |
| `dev-docs/TO_DO.md` | Point the existing portable bullets at this plan. Extend those bullets. Do not add a section. |
| `dev-docs/plans/PORTABLE_APP_PLAN.md` | Link this plan from the Phase 1 CI checkbox. Record the Helpers and Resources decision on the Phase 0b browser bullet so it no longer says the path is only recorded. After the four default legs are green, tick Windows plus those legs, and leave macOS x86_64 open. Tick "Export PNG offline" with the run id and the relative path `Helpers/Chromium.app/Contents/MacOS/Chromium`. Leave "Sign and notarize a Full-shape app" open. The Linux air-gapped sentence stays open while the summary's system-soname count is non-zero. |
| `dev-docs/plans/PORTABLE_BROWSER_WRAPPER_PLAN.md` | Archive after both Full png-checks are cited. The archive note says the macOS path is `Contents/Helpers/Chromium.app`, which this plan decided. Intel is not required for that archive. |
| `dev-docs/references/PORTABLE_CHROMIUM_ARTIFACT.md` | Add the pins, the Helpers and Resources layout, the Linux `DT_NEEDED` fact, and the license filenames. Leave the Windows pin as it is. |
| `dev-docs/references/PORTABLE_EXECUTABLE_PACKAGING.md` | Say what the four unix legs prove, including that Linux `--png-check` uses the runner's system libraries. |
| `dev-docs/MAINTENANCE_LOG.md` | Unreleased entry for the CI jobs, the macOS path move, and the Linux library path. |
| `CHANGELOG.md` | Unreleased line. The path move and the tests touch `src/` and `tests/`, so the changelog hook requires an entry. Say the macOS and Linux zips are CI artifacts, release signing is still open, and Linux PNG on this runner uses system libraries. |

```bash
uv run --extra dev --extra gui --locked python scripts/check_file_sizes.py
uv run --extra dev --extra gui --locked python scripts/check_doc_freshness.py
```

## Chunks

Chunk 1 before chunk 2. A workflow that runs `--png-check` before the path and notice changes fails closed: missing notices, or `launched_outside_onedir` because Helpers is outside `Contents/MacOS`. Chunk 4 waits for a completed run id. Do not tick parent checkboxes in the commit that only adds the jobs.

### Chunk 1 — Paths, notices, process names, library path

**Files:** `src/guiskindose/export/png_browser.py`, `packaging/portable/entry.py`, `packaging/portable/pngcheck.py`, `packaging/portable/selfcheck.py`, the two new license texts under `packaging/portable/chromium/`, `tests/unittests/test_png_browser.py`, `tests/unittests/test_portable_pngcheck.py`, `tests/unittests/test_portable_entry.py`, `tests/unittests/test_portable_selfcheck.py` if the presence check is asserted there.

**Steps:**

1. Darwin browser, wrapper root, notice directory, containment root, and presence check, as in the table above. Linux and Windows paths stay `<onedir>/chromium/<binary>`.
2. `required_notice_names()`, and point `_write_chromium_notices` at it. Darwin notices live under `Contents/Resources/chromium`.
3. Extend `system_chrome_processes_running` beyond `chrome.exe`, with the new unit test. Update the macOS `launched_from_onedir` expectation to the Helpers relative path.
4. On Linux, prepend the `chromium` directory to `LD_LIBRARY_PATH` in the frozen entry before a child starts. Do not log the value.
5. Commit the two packaging licenses. Diff the Chromium `LICENSE` texts so chunk 2 copies the right file.
6. Add the darwin wrapper test: a target under `Contents/Helpers/Chromium.app` is allowed, and a target under `Contents/MacOS/chromium` exits 1 before `dup2`.

**Verify:** the pytest command above.

### Chunk 2 — Workflow jobs

**Files:** `.github/workflows/portable-spike.yml`.

**Steps:**

1. Add the path filter, including `src/guiskindose/**`, and the `main` branch.
2. Add `macos-edition` (`macos-15`, Light and Full), `linux-edition` (`ubuntu-24.04`, Light and Full), and the dispatch-only Intel Full job.
3. Full macOS follows the seven-step signing order, including both png-checks and `codesign --verify --deep --strict` after the ad-hoc re-sign. Light macOS only verifies the PyInstaller seal.
4. Linux records bundled sonames, system sonames, and `not found` sonames. It does not apt-install to clear the system set.
5. Leave the existing `windows-edition` steps in place.
6. Push the branch. `portable/**` runs this workflow when a filtered path changes. Fix a red step from its report.

**Verify:** a completed run. Full macOS summaries show both png-checks at `launched_outside_onedir` 0 with the Helpers relative path, and the outer verify passing. Full Linux summaries show `chromium/chrome` and a system-soname count. Light summaries show edition `light` and no png-check.

### Chunk 3 — Docs while the run is still fresh

**Files:** the doc table above, except the archive move.

**Steps:** write the run id, sizes, and seconds into the parent progress log and the maintenance log before the 7-day expiry. Tick only the checkboxes whose runs are green. Leave Developer ID signing, Intel, the Linux `.desktop` file, the manual window check, and the Linux air-gapped claim open.

### Chunk 4 — Archive the wrapper plan

**Depends on chunk 2's Full macOS arm64 run and Full Linux run.**

Move `PORTABLE_BROWSER_WRAPPER_PLAN.md` to `dev-docs/plans/archive/`, update `dev-docs/index.md`, and add the archive line to the parent plan. Archive this plan in that same commit only when chunks 1–3 are done and Intel is either green or left open on the parent checklist. An open Intel bullet can ship with that archive. An unticked Phase 0b PNG checkbox cannot.

## Out of scope

- Developer ID signing, notarization, stapling, and `macos_sign_notarize.sh`. The empty entitlements file stays empty. The ad-hoc re-sign in CI does not turn on the hardened runtime and does not add `disable-library-validation`.
- Authenticode, the Windows pin, and the Windows job's steps.
- A universal2 binary, and Linux arm64.
- Vendoring the 32 Linux `DT_NEEDED` libraries, or exec of `chrome-wrapper`.
- A `.desktop` file, a browser-mode GUI launch on Linux, and the manual macOS window check.
- `pull_request` builds and larger runners.
- Quarantine and Mark of the Web smokes. The CI quarantine-attribute clear is not that smoke.

## Acceptance

A green `macos-light`, `macos-full`, `linux-light`, and `linux-full` run on a filtered `portable/**` or `main` push. Full macOS reports include `Helpers/Chromium.app/Contents/MacOS/Chromium`, with `launched_outside_onedir` 0 and at least two PNGs, both before and after the ad-hoc re-sign. The outer app passes `codesign --verify --deep --strict` after that re-sign. The nested app passed `codesign --verify --strict` with the upstream Team ID before the re-sign. Full Linux reports include `chromium/chrome` and list the system sonames `ldd` resolved outside `chromium/`. Light reports edition `light` and a zero `to_image` count. The parent Phase 0b export checkbox cites the run id. The sign-and-notarize checkbox and the Linux air-gapped claim stay open. Artifacts expire after 7 days and are absent from git.

## Review notes

| Finding | Result |
|---------|--------|
| `Contents/MacOS/chromium` plus notices breaks `codesign` | Accepted. Reproduced: `code object is not signed at all` on the license file. The app moves to `Contents/Helpers/Chromium.app`. Notices move to `Contents/Resources/chromium`. Both Helpers and Frameworks passed a toy `--verify --deep --strict`. Helpers is the TN2206 helper-app location and is not PyInstaller's framework directory. The same toy also passed `Contents/MacOS/chromium/Chromium.app` with no loose file, so the unsigned notice is the failure that this bundle would hit. The extra directory stays unused because TN2206 does not support it. |
| `ditto` after the freeze invalidates the outer ad-hoc signature | Accepted. PyInstaller calls `sign_binary` with identity `-`. The toy then failed verify with `a sealed resource is missing or invalid` until an inside-out re-sign. CI re-signs without the hardened runtime, then runs `--verify --deep --strict`. The first png-check still uses the upstream nested binary, so a bad re-sign is not mistaken for a wrapper failure. |
| Path filter misses `src/guiskindose/**` | Accepted. The filter is `src/guiskindose/**` plus the packaging, workflow, and lockfile paths. |
| Linux tarball is not self-contained | Accepted. `chrome` has no `DT_RUNPATH`. `chrome-wrapper` sets `LD_LIBRARY_PATH` and symlinks host NSS libraries. CI records sonames resolved outside `chromium/` and does not treat a green `ldd` as an air-gapped proof. |
| `NOTICE_FILES` and `chrome.exe` | Accepted for the notice tuple and the test helper that iterates it. The descendant filter already matches any file name containing `chrom`, including `Chromium`. The `chrome.exe`-only logic is `system_chrome_processes_running`, and chunk 1 extends that counter. |
