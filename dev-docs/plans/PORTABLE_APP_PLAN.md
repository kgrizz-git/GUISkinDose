# Portable desktop app — GUISkinDose

_Status: plan only — not started._
_Created: 2026-10-17._
_Parent hub: [RELEASES_AND_DISTRIBUTION.md](../RELEASES_AND_DISTRIBUTION.md)._
_Feasibility note: [references/PORTABLE_EXECUTABLE_PACKAGING.md](../references/PORTABLE_EXECUTABLE_PACKAGING.md)._

## Goal

Ship a double-clickable desktop app for people who do not install Python: unzip (or open) a per-OS build, get the existing NiceGUI window, load an RDSR, calculate, and export. Processing stays on the machine. No exam data leaves the computer.

Two downloadable builds, same program:

| Build | Who it is for | Phantom payload | PNG / browser | Windows window |
|-------|----------------|-----------------|----------------|-----------------|
| **Light** | First download, quick trials, smaller transfer | A small clinical starter set, installed and usable offline | No bundled browser. PNG dose-map export is not offered, including inside PDF and DOCX | Uses the WebView2 runtime already on the PC. If it is missing, a message names the Full download. Does not ship the 250 MB Fixed Version runtime |
| **Full** | Clinical library, air-gapped workstations | Every shipped clinical STL, including arms-down twins and the preferred preview | Bundled Chromium so Kaleido PNG export works offline | Ships the Fixed Version WebView2 runtime so the window opens with no admin install |

A later phase lets a Light install add the rest from a phantom pack: download when the network is allowed, or install a pack zip with no network. The pack is data, not a second application.

## What exists today

The GUI already runs as `python -m guiskindose --mode gui`, with `--native` opening a pywebview window. Source checkouts also have double-click launchers with the app icon ([DESKTOP_LAUNCHERS_PLAN.md](DESKTOP_LAUNCHERS_PLAN.md)); they still need Python. There is no freeze pipeline, no installer, and no PyPI publish yet. Mesh lookup is confined to the package directory `src/guiskindose/phantom_data/` (`resolve_human_mesh_stl_path`). A frozen bundle is often read-only and signed, so extra phantoms cannot be dropped into that directory. They need a separate user library.

## Measured sizes (2026-10-17, this tree)

`du` on `src/guiskindose/phantom_data/`: **67 MB**, 138 STL files. The class rows below are byte sums, which add to 70.1 MB.

| Class | Files | Size |
|-------|------:|-----:|
| Full clinical meshes | 23 | 30.1 MB |
| Arms-down twins | 23 | 30.8 MB |
| Reduced previews | 92 | 9.2 MB |
| of which `_reduced_3000t` | | 6.9 MB |
| of which `_reduced_1000t` | | 2.3 MB |

Each full mesh is about **1.3 MB** (`hudfrid.stl` is 0.68 MB). A starter of `adult_male`, `adult_female`, and `hudfrid`, both poses, both preview resolutions, is **8.6 MB**.

Other project data that a freeze must include. `corrections.db` is not on this list: the runtime reads the packaged CSVs and ignores a `corrections.db` in the working directory (`correction_data.resolve_corrections_source`).

| Data | Size |
|------|-----:|
| HVL / correction CSVs under `table_data/` | 6.3 MB |
| Example RDSR and tabular files under `example_data/` | 1.2 MB |
| GUI help | 72 KB |

The development virtualenv is about 1.1 GB and is the wrong number to quote. Most of it is tools that must not ship (Playwright and its Node wheel alone are about 336 MB, plus basedpyright, Jupyter, Sphinx, spaCy). Libraries the app actually imports, measured in that same environment:

| Package | Size |
|---------|-----:|
| scipy | 76.5 MB |
| pandas | 47.9 MB |
| plotly | 44.8 MB |
| nicegui | 27.1 MB |
| numpy | 23.2 MB |
| Pillow | 14.0 MB |
| pydicom | 10.6 MB |
| reportlab | 6.3 MB |

Those eight are about **250 MB** before their smaller transitive dependencies and the embedded Python runtime (the local 3.14 framework is 81 MB; a freeze ships a subset). PyInstaller onedir output is larger than the sum of inputs, then a zip compresses it. **Phase 0 must publish the real onedir and zip sizes for the Light shape and the Chromium-Full shape.** Phase 4 adds the WebView2 runtime delta for Full Windows. Until then, use these planning ranges only:

| Build | What dominates | Planning range (compressed zip) |
|-------|----------------|----------------------------------|
| **Light** | Scientific libraries. No Chromium, no WebView2 runtime. About 20 MB of meshes. | Low hundreds of MB |
| **Full** | The same libraries, plus Chromium (often 150 MB or more) and, on Windows, the Fixed Version WebView2 runtime (Microsoft documents it as over 250 MB) | Higher than Light by those runtimes plus ~45 MB of extra meshes |

A single "low hundreds of MB" figure fits Light. It is the wrong figure for Full.

**Phantoms are the largest project asset and a small slice of the app.** 67 MB against ~250 MB of named libraries is roughly a fifth of the library payload, and less of the zipped download. Dropping the catalog to an ~9–20 MB starter saves on the order of **50 MB uncompressed**. That is worth doing. It does not turn the download into a small utility.

PNG export is a separate payload from the meshes. Kaleido 1.5 in this environment is 328 KB and does not vendor a browser. `fig.to_image()` starts a Chromium-family browser through `choreographer` (a previously downloaded browser, then Google Chrome, Chromium, Edge, Brave, or Vivaldi). Safari and Firefox are not used. The native window uses the operating-system web view, and Kaleido does not drive that window. HTML dose maps do not need a browser.

The browser that choreographer would download on its own is **Chrome for Testing**, not open-source Chromium. The pin in this environment (`choreographer` `last_known_good_chrome.json`) points at `storage.googleapis.com/chrome-for-testing-public/` build 142.0.7444.175. That is Google's Chrome build. **Full does not ship Chrome for Testing.** The bundle candidate is a Chromium build, and Phase 0 records its license text and third-party notices before any Full zip is built. The candidate is a whole distribution directory, not one binary. On macOS it is a nested app bundle with helper apps. `chrome-headless-shell` is also a candidate, because it has no macOS app bundle; it must support new headless mode, since Kaleido 1.5 runs headless.

choreographer 1.4.0 looks for a browser in this order: a browser it downloaded earlier, then `BROWSER_PATH`, then typical install paths. So `BROWSER_PATH` loses to a Chrome for Testing that `kaleido_get_chrome` once downloaded on that machine. Full must pass the bundled path explicitly instead, for example with `kaleido.start_sync_server(path=...)` in the process that renders. Kaleido also starts Chromium with `--no-sandbox` by default (`enable_sandbox=False`). Full records whether it turns the sandbox on.

## Recommendation

1. **Ship Light and Full as two GitHub Release assets per OS.** Same code, different phantom payload. Full is the air-gapped clinical download. Light is the smaller first download.
2. **Add an in-app phantom library after the freeze works**, not before. The same signed manifest installs a pack from a zip (offline) or from the matching GitHub Release (online). Hospitals that block outbound traffic still get the full catalog by choosing the Full zip.
3. **Light omits PNG export and does not bundle a browser. Full bundles Chromium, not Chrome for Testing.** Both builds still export HTML, JSON, and CSV. PDF and DOCX still generate; in Light, embedded dose-map images are omitted with the existing "image unavailable" notice. Full passes the bundled Chromium path to Kaleido explicitly so PNG works with no system browser and no network. If that Chromium license does not allow redistribution, stop before Phase 1 and drop the air-gapped PNG promise. Full then uses a Chromium-family browser already installed on the machine, and the release notes say PNG does not work offline.
4. **Do not vendor a second copy of the meshes inside the Python wheel and the app.** The wheel can keep today's full `phantom_data/` for `pip` users. The Light freeze uses an explicit include list. Pip behavior does not change in v1. `pip install` keeps Kaleido and still uses whatever Chromium-family browser is on the machine.

### Proposed Light set (product choice, not locked)

Enough to run a real adult case, a pediatric case, and one larger habitus, offline, with arms at the side:

- `hudfrid`, `adult_male`, `adult_female`
- `ped_5y_male`, `ped_5y_female`
- `adult_bariatric_male_1`, `adult_bariatric_female_1`
- the `_arms_down` twin of each
- `_reduced_3000t` previews only (Settings already prefers these)

The 8.6 MB figure above is only `adult_male`, `adult_female`, and `hudfrid`. This seven-base set is about **20 MB** (byte sum) (full meshes near 1.3 MB, both poses, plus `_reduced_3000t`). It does **not** include ectomorph, endomorph, senior, junior, preschool, or 10-year meshes. A Light user who needs one of those installs a phantom pack (Phase 2) or downloads Full.

The Full build keeps the current 23 + 23 clinical meshes and their `_reduced_3000t` previews. Both app builds drop `_reduced_1000t` (2.3 MB). The pip wheel keeps those legacy previews until a separate cleanup, so a wheel and an app zip are not the same phantom tree. That divergence is intentional for v1 and is a follow-up, not part of the freeze.

Plane and cylinder phantoms are generated in code. They are in every build and are not part of the catalog.

## Non-goals

- One binary that runs on Windows, macOS, and Linux.
- Committing built executables, or putting PHI fixtures in a release zip.
- A Java / JVM wrap of the stack.
- An auto-updater, an update check, or crash reporting. Nothing phones home with usage, hostnames, or exam metadata. A new version is a new download. Uninstall is deleting the unzipped app. The user phantom library is outside that folder and stays until the user deletes it.
- Replacing `pip install` or the CLI. The frozen app is an extra channel.
- macOS App Store or Microsoft Store distribution.
- Defeating AppLocker, WDAC, or other site allow-lists. Signing makes the publisher identifiable. It does not force a hospital policy to allow it.
- Stripping Mark of the Web, packing or obfuscating the executable, or asking the user to turn antivirus off.
- Trimming scipy/pandas to shrink the download. That is a different project, and it risks the dose path.

## Design

### Freeze

- Tooling: plain PyInstaller at a pinned version, unless Phase 0b's decision-log entry switches macOS to Briefcase. `nicegui-pack` is an optional wrapper; it does not produce a macOS `.app`. `ui.run(reload=False)`. On Windows and macOS the frozen entry calls `run_gui(native=True)`. On Linux v1 it calls `run_gui(native=False)` and opens the system browser on loopback. WebKit2GTK is a system package that needs root to install, so native Linux is not part of v1. On Windows, PyInstaller's `--windowed` switch only hides the console. On macOS it is the switch that produces the `.app` bundle.
- Entry: a dedicated frozen entry script, not `guiskindose.__main__:cli`. Its first statement is `multiprocessing.freeze_support()`, before any project import. NiceGUI spawns the native window in a child process that re-executes the entry. Without `freeze_support()` first, that child runs `get_argument_parser` on its `--multiprocessing-fork` arguments and exits, and it also pays the import cost of nicegui and pandas. The entry then calls `run_gui` with no CLI parsing. The Windows and macOS freezes include `pywebview` (pin `>=6.1`; the lock has 6.2.1). Drop test-only packages such as `pytest-asyncio` from the freeze even though they sit in the `gui` extra.
- Layout: **onedir**, zipped for download. What the user double-clicks:
  - Windows: the `.exe` PyInstaller writes in the onedir.
  - macOS: the `GUISkinDose.app` that PyInstaller's onedir `--windowed` build writes (`Contents/MacOS`, `Contents/Frameworks`), with `--osx-bundle-identifier`. Do not hand-roll a wrapper. Archives are made with `ditto -c -k --keepParent`, because `zip -r` breaks the framework symlinks.
  - Linux: the executable (browser mode) plus a `.desktop` file in the zip.
- Architectures: Windows x64. macOS arm64 and x86_64 as separate builds on matching runners, unless Phase 0b shows a universal2 build is practical. Linux x86_64. PyInstaller does not cross-compile.
- Rebuild on each OS. Artifacts are GitHub Release assets only, after privacy and release gates. No binaries in git. Each fetched browser or runtime is pinned by version and sha256 in the CI job.
- Bundle: Python runtime, runtime dependencies, `table_data/` (collected as package data so `importlib.resources` resolves it), packaged GUI help, `gui/static/` (fonts), `gui/ui_copy.json`, `settings_example.json`, `normalization_settings.json`, the kerma-meter example under `example_data/kerma_meter/` (the in-app help already tells users that CSV is installed with the package), and the bundled examples the Upload tab lists: the synthetic RDSR files under `example_data/RDSR/` and the tabular CSVs under `example_data/tabular/`. Each shipped DICOM already carries an approved-inventory hash. Full also bundles the Chromium build from Phase 0 and passes its executable path to Kaleido explicitly. On macOS that path is inside the bundle, such as `Chromium.app/Contents/MacOS/Chromium`.
- Omit from the freeze: dev and docs extras, Playwright, Jupyter, Semgrep, `corrections.db`. Light also omits the Chromium binary and the WebView2 Fixed Version runtime.
- Edition is `guiskindose/_edition.py`. The committed source file is `EDITION = "full"`, and a test asserts that. The freeze runs from a gitignored staging copy of the source (under `tmp/`) with the rewritten module, never from the source tree. `--add-data` cannot shadow a collected module. A packaged-build test asserts the frozen edition. An environment variable does not override it. The GUI hides the PNG card when the edition is `light`. The same check lives in every `to_image` caller: `export/images.py`, `gui/figures.py`, `gui/tabs/export.py`, and `plotting/create_dose_map_plot.py`. They must fail the same way; today `render_dosemap_png` returns `None` while `gui/figures.make_dosemap_png` raises. The HTML report embeds these images too, so a Light build returns "image unavailable" without starting a browser. Windows ships Edge, and Kaleido would use it if those functions still ran.
- A windowed build has no console, so `sys.stdout` and `sys.stderr` can be `None` and `print()` fails. The frozen entry routes startup messages to the log sink, never to stdout. That sink is the Native GUI optional file logging item in [TO_DO.md](../TO_DO.md): a temp-path file with rotation, session purge, `0o600` permissions, and an opt-out for shared machines. It is not built yet, so it is an explicit Phase 0 task. A persistent log location is a privacy decision; if the freeze needs one, amend the TO_DO design and `PRIVACY_AND_SENSITIVE_ASSETS.md` in the same PR. The log has no filenames, no absolute paths, and no identifiers.

### Phantom library

Today the mesh list comes from globbing the package directory, and at least four places compute that directory from `__file__` (`gui/helpers.py`, `gui/phantom_preview.py`, `package_phantom_data_dir`, and the package `__init__`). `resolve_human_mesh_stl_path` checks a safe-stem pattern and file existence. It is not an allow-list. The GUI selector also falls back to the first clinical mesh or `hudfrid` when a stem is not selectable (`canonicalize_human_mesh_selection`). Phase 2 replaces all of that with a canonical catalog constant and one resolution entry point, used by `Phantom`, the preview, mesh measurement, and the selector. It removes the silent fallback. A user mesh whose stem matches a shipped mesh is refused.

Lookup order, confined to known roots and safe stems:

1. User library (writable, outside the bundle).
2. Shipped payload inside the bundle (`phantom_data/` or the frozen equivalent).

The user library for extra phantoms lives outside the bundle. Window geometry and the equipment-profile store already use `~/.guiskindose/` (`gui.json`, the profile store). Keep that directory. Do not invent a second scheme for those files. Uninstall notes name both `~/.guiskindose/` and the phantom directory.

| OS | Extra phantoms |
|----|----------------|
| macOS | `~/Library/Application Support/GUISkinDose/phantoms` |
| Windows | `%LOCALAPPDATA%\GUISkinDose\phantoms` |
| Linux | `$XDG_DATA_HOME/guiskindose/phantoms`, or `~/.local/share/guiskindose/phantoms` when `XDG_DATA_HOME` is unset |

Resolution must keep rejecting `..`, separators, and stems outside the safe pattern.

A **phantom pack** is a zip of `.stl` files plus a manifest. The manifest lists stem, byte size, sha256, pack version, and the app versions it is allowed to serve. Install verifies the hash against the manifest, and the manifest hash against a value shipped in the app (or a release asset the app was built to expect). Unknown stems, extra archive members, and path traversal fail closed. The pack contains meshes only.

Settings lists the whole clinical catalog. Installed meshes are selectable. Missing meshes are visible as not installed, with two actions: install from a pack zip, and download this mesh or the full catalog when a network fetch is enabled. Dose calculation refuses a missing mesh with that same explanation. It does not silently fall back to another body.

Pack version follows the app version. A pack from 1.2 is not assumed to fit a 1.3 geometry frame. The manifest says which app versions it matches.

### Network

Download URL is fixed at build time to that version's GitHub Release asset (HTTPS). The app does not accept an arbitrary URL from the user. GitHub release downloads redirect to its asset CDN (`release-assets.githubusercontent.com`), so that host is allowed explicitly. Any other redirect is rejected. The sha256 pin is the real trust anchor. No identifiers, filenames, or absolute paths are logged. Failure is offline-safe: the meshes already installed keep working.

Fetching is off until the user asks. There is no background check.

### Trust and first launch

An unsigned Windows `.exe` gets a SmartScreen warning. An unsigned, quarantined macOS `.app` is blocked outright; since macOS 15 the user must go to System Settings → Privacy & Security to allow it. So public macOS zips are signed and notarized from Phase 1 on. A zip of an onedir is the v1 download. Phases 0–3 do **not** yet produce a Windows build that a standard user can open on every PC.

What Phases 0–3 do promise: no installer, no copy into `Program Files`, and no request for administrator rights. The user unzips into a folder they can write and double-clicks the `.exe`. On Windows, Full must sit on an NTFS folder in the user profile. A USB stick formatted FAT32 or exFAT cannot store the AppContainer permissions the Fixed Version runtime needs, and that runtime does not run from a network path. Phantom packs go in the per-OS phantom directory above. Uninstall is deleting the unzipped folder, plus `~/.guiskindose/` and the per-OS phantom directory if the user also wants preferences, profiles, and extra meshes gone.

What they do not promise, and later phases take on:

| Block | Why a standard user gets stuck | When it is handled |
|-------|--------------------------------|--------------------|
| Missing WebView2 runtime | pywebview 6.2.1 falls back to the old MSHTML engine when WebView2 is missing. NiceGUI does not run there, and the window process can fail while the server stays up. | **Phase 1** checks for WebView2 before `ui.run`, in every edition, and shows a message. No installer, no MSHTML fallback. **Phase 4** ships the Fixed Version runtime in the Full Windows zip only |
| Unknown publisher (SmartScreen, Gatekeeper) | Windows shows a warning. "Run anyway" is not an admin step, but many people stop there. A brand-new certificate still warns until it gains reputation. macOS blocks an unsigned download. | macOS: Phase 1 signs and notarizes. Windows: Phase 5 adds Authenticode |
| Antivirus heuristics | PyInstaller onedir builds, and a bundled browser, are often flagged. A packer makes that worse. | Phase 5 records a Defender scan of the signed zip. No packer, no "disable your antivirus" instruction |
| Hospital allow-lists (AppLocker, WDAC) | IT can block any publisher, signed or not. This project cannot bypass that. | Out of scope. Release notes say the site admin must allow the signed publisher |
| Mark of the Web | A browser download marks the zip. The app must not strip that mark. | Signing is the mitigation, not deleting `Zone.Identifier` |
| Network or UNC launch | Microsoft's Fixed Version runtime does not run from a network path. This applies to the Full Windows zip. | Phase 4 release notes say to copy the Full folder onto the PC first |

The frozen Windows manifest must not set `requireAdministrator`. Linux builds must not be setuid. macOS builds must not include a privileged helper. The macOS `Info.plist` sets `NSAppTransportSecurity` → `NSAllowsLocalNetworking`, because the native window loads `http://127.0.0.1` and App Transport Security can block that from macOS 14.

## Phases

Each phase is a separate PR. Do not start Phase 1 until Phase 0 has measured sizes on Windows.

### Phase 0 — Spike on Windows

The failures that matter for a no-admin PC are Windows-only. Do this spike on Windows. Phase 0b is a macOS spike that runs alongside it. Linux checks belong to the Phase 1 Linux CI job.

- [ ] Freeze `run_gui(native=True)` with the **full** phantom payload, `table_data/`, the Upload examples, `pywebview`, GUI help, `gui/static/`, `gui/ui_copy.json`, `normalization_settings.json`, and `example_data/kerma_meter/`.
- [ ] Write the dedicated frozen entry. Its first statement is `multiprocessing.freeze_support()`, before any project import. Confirm the native window child starts.
- [ ] Verify export with `git` absent. `safe_output` already catches `OSError`, uses `CREATE_NO_WINDOW`, and skips the checkout check when frozen (shipped 2026-10-18). Acceptance runs with `git` removed from `PATH` and still saves HTML.
- [ ] Build the log sink from the TO_DO design. Confirm a windowed launch does not crash when `sys.stdout` is `None`, and that the log file is created.
- [ ] Pick the exact Chromium artifact to fetch (a Chromium build or `chrome-headless-shell`), not Chrome for Testing. Record its provider, size, license, and the notices it must ship with. Stop the Full-bundle path if redistribution is not allowed.
- [ ] Record onedir size, zip size, and cold-start time twice: without that browser (Light shape) and with it (Full shape).
- [ ] Launch with the network disabled. Load a local RDSR, calculate, and export HTML, JSON, and CSV. With Chromium bundled and its path passed explicitly, export PNG with no system Chrome installed, and record which binary launched.
- [ ] Prove package data resolves inside the freeze by opening, from the frozen app, `phantom_data`, `table_data`, `gui/help`, `gui/static`, `gui/ui_copy.json`, `normalization_settings.json`, `settings_example.json`, and the kerma-meter example CSV. A list of `__file__` call sites is not the acceptance test. PyInstaller sets `__file__` for collected modules. Watch repo-root climbs such as the fun-mesh manifest path and the `ui_copy` repo-catalog fallback.
- [ ] Document the hidden imports and data files that actually worked.

**Acceptance:** a Windows zip runs calculate and HTML export with the network off and with `git` absent. The Chromium artifact's size and license are written down. No release workflow yet. The Light PNG gate is Phase 1, because the edition file is not in this spike.

### Phase 0b — macOS spike: sign, notarize, and compare Briefcase

Run this alongside Phase 0. The maintainer now has an Apple Developer account, so the macOS signing risk can be tested early instead of waiting for Phase 5. Signing and notarization often break a frozen layout, and that is cheaper to learn now.

- [ ] Create a **Developer ID Application** certificate and an App Store Connect API key for `notarytool`. Keep both out of the repository. CI later reads them from GitHub secrets.
- [ ] Freeze a Light-shape `GUISkinDose.app` with PyInstaller on an arm64 runner, and record whether an x86_64 or universal2 build is practical. Use the same payload and frozen entry as Phase 0, with the app icon converted to `.icns` and the ATS key in `Info.plist`.
- [ ] Sign every nested Mach-O file (dylibs, `.so` extensions, the Python framework) inside-out with the hardened runtime and a timestamp. Do not use `codesign --deep`. Record the entitlements that were actually needed, such as `allow-unsigned-executable-memory` or `disable-library-validation`, and keep the list minimal.
- [ ] Notarize in this order: `ditto -c -k --keepParent GUISkinDose.app` → `xcrun notarytool submit --wait` → `xcrun stapler staple GUISkinDose.app` → re-zip the stapled app with `ditto` for download. `notarytool` takes a zip, not a bare `.app`, and a zip cannot be stapled. Record any rejected files from the notary log.
- [ ] Verify with `codesign --verify --deep --strict`, `spctl -a -t exec -vv`, and `xcrun stapler validate`.
- [ ] Confirm the windowed `.app` does not crash when `sys.stdout` is `None`, and that the native window actually renders the page from `127.0.0.1`.
- [ ] Sign and notarize a Full-shape app that contains the chosen Chromium artifact. Sign it inside-out (binary, framework, helper apps) with the same identity, the hardened runtime, and a timestamp. Record the entitlements Chromium needs. If this cannot be notarized, drop offline PNG from Full macOS.
- [ ] On a second Mac or a clean user account, download the zip through a browser so it gets the quarantine flag. Confirm Gatekeeper opens it with no warning, including with the network off, which proves the ticket is stapled. Then load a local RDSR, calculate, and export HTML with the network off.
- [ ] Build the same Light app with **Briefcase** (`briefcase create`, `build`, `package macOS -p zip --identity ...`). Briefcase ships a standalone Python and installs the dependency wheels instead of freezing, and it signs and notarizes as part of `package`. Record build time, bundle size, cold-start time, and every workaround each tool needed.
- [ ] Compare Briefcase against the plan constraints: pywebview's native child process, package data resolving through `importlib.resources`, and the Python version Briefcase can use against the 3.14 target. Briefcase's Windows output is an MSI and its Linux outputs are AppImage or Flatpak, so a Windows zip and browser-mode Linux are recorded as gaps, not checked.

**Acceptance:** a notarized, stapled Light `.app` opens with no Gatekeeper prompt on a clean Mac, then calculates and exports HTML offline. `codesign`, `spctl`, and `stapler validate` pass. The progress log records the entitlements (Light and Full), architectures, sizes, and a PyInstaller-versus-Briefcase recommendation. The Freeze design switches tools only through a decision-log entry.

### Phase 1 — Light and Full payloads

- [ ] Pin `pywebview>=6.1` in `pyproject.toml`. One include list for Light and one for Full.
- [ ] The freeze staging copy gets `EDITION = "light"` or `"full"`. The committed file stays `"full"`. Light ships no Chromium and no WebView2 runtime. Full bundles Chromium only if Phase 0 cleared its license. The bundled browser path is passed to Kaleido explicitly inside the process that renders.
- [ ] PNG render functions return no image when the edition is `light`, before any browser lookup. A test on a machine that has Edge proves a Light rich report does not start a browser. The GUI hides the PNG card as well.
- [ ] Before `ui.run` on Windows, every edition checks for a usable WebView2 runtime the way pywebview's `_is_chromium()` does: the registry locations and .NET Framework 4.6.2 or later. When a bundled runtime path is set, the check confirms that folder exists, because pywebview trusts the setting without checking it. If no runtime is usable, show a message. Until Phase 4 publishes Full Windows, it names Microsoft's Evergreen runtime; after that, it names the Full download. Do not fall back to MSHTML. Do not launch an installer. Acceptance is a VM without WebView2: a message, no broken window, no UAC prompt.
- [ ] Both builds run the same tests that do not need a missing mesh. A Light build test proves a starter mesh loads and a non-starter stem is reported missing. A Full test proves PNG bytes come back and proves which binary launched, for example from the browser child's command line, on a machine that also has a downloaded Chrome for Testing.
- [ ] `_reduced_1000t` is absent from both app payloads. Previews still resolve to `_reduced_3000t`.
- [ ] macOS release zips are signed, notarized, and stapled with the Phase 0b recipe. Signing secrets are GitHub secrets read only by the release job.
- [ ] CI builds Windows, macOS, and Linux onedir zips. Artifacts expire. They are not committed. Fetched binaries are checked against the pinned sha256. Linux jobs launch browser mode, not native. The Linux job records which system libraries the bundled Chromium needs. If Full PNG on Linux needs packages only root can install, drop the air-gapped PNG claim for Linux.
- [ ] Public Full Windows waits for Phase 4. A Phase 1 Full Windows zip may be kept as a size artifact and is labeled "needs WebView2 already installed." It is not the no-admin download.
- [ ] Smoke tests use a zip that was downloaded through a browser, so Mark of the Web and macOS quarantine are actually present. Release notes name the downloads, say Light has no PNG dose map, say Linux opens in the browser, and state that the app is not FDA-cleared.

**Acceptance:** public zips are Light on three OSes, Full on macOS and Linux, and no public Full Windows yet. macOS zips are notarized. Each launches, calculates once, and exports HTML. macOS and Linux Full also export PNG offline when the Phase 0 license check passed. Maintainer signs off the measured sizes.

### Phase 2 — User library and offline pack

- [ ] Add the canonical catalog and one resolution entry point (user library, then shipped payload, with stem confinement). Move `Phantom`, the preview, mesh measurement, and the selector onto it. Remove the selector's silent fallback.
- [ ] "Install phantom pack" picks a local zip, verifies the manifest, and copies only allow-listed STLs into the user library. Extract entry by entry into a temp directory with a running decompressed-byte cap, because central-directory sizes can lie. Reject symlinks, hardlinks, directories, and names that collide after case folding. Move only allow-listed `.stl` files into place.
- [ ] Settings shows installed and not-installed catalog rows.
- [ ] A missing mesh blocks calculation with an install hint.
- [ ] Unit tests use a temp library and a tiny synthetic STL. They do not download anything.
- [ ] Help text states that packs are optional data and that Full already contains the catalog.

**Acceptance:** a Light app plus a pack zip gains a mesh that was not in the Light payload, survives restart, and is used for a calculation. A tampered STL is rejected. An oversized zip is rejected before extraction finishes.

### Phase 3 — Download from the matching release

- [ ] Download action fetches the pack (or one stem, if the release layout allows) from the build's pinned release URL.
- [ ] Hash check is the same as Phase 2. Partial files are not treated as installed.
- [ ] Cancel, retry, and offline failure leave the library unchanged.
- [ ] No request carries exam data, file names, or machine identifiers beyond what HTTPS already sends.

**Acceptance:** on a machine with network, Light can grow to the full catalog without a second app download. With network disabled, installed meshes and the local zip path still work.

### Phase 4 — Full Windows runtime without an admin install

Light's missing-runtime message is Phase 1. This phase only adds the runtime to Full. NiceGUI applies native settings in the child process, so the path goes in `app.native.settings` as an absolute path under the `.exe` folder. Setting `webview.settings` in the parent process does not reach that child. This runtime is separate from the Chromium browser Full uses for PNG.

- [ ] Download Microsoft's **Fixed Version** WebView2 runtime for the build arch, not the Evergreen machine-wide installer. Pin the version and sha256. Record its size (Microsoft documents it as over 250 MB) and the redistribution terms in the progress log.
- [ ] Place the decompressed runtime inside the **Full** onedir only. Pass that absolute path through `app.native.settings['WEBVIEW2_RUNTIME_PATH']`. Light leaves it unset. `webview.settings` rejects unknown keys, and NiceGUI applies these settings in the window child, so a misspelled key kills the window.
- [ ] On Windows 10, Fixed Version 120 and later needs AppContainer read-execute on that folder (`ALL APPLICATION PACKAGES` and `ALL RESTRICTED APPLICATION PACKAGES`). A zip stores no NTFS ACLs, so the app grants them after extraction, on the runtime folder only. The grant is idempotent, runs without a console flash, and fails loudly with a message. The acceptance run must not show a UAC prompt. A FAT or exFAT USB stick is not a supported Full location.
- [ ] Smoke Full on a Windows VM that does **not** have WebView2 installed: unzip into the user profile on NTFS, launch, calculate, export HTML. Confirm Full does not launch from a UNC path, and say that in the release notes.
- [ ] Add the runtime size to the Full Windows zip estimate only. It dominates the phantom-catalog difference on Windows.
- [ ] A later release rebuilds when that pinned runtime or the pinned Chromium has a security fix. There is no auto-updater.

**Acceptance:** Full opens on Windows 10 without a preinstalled WebView2 and without a UAC prompt, from an NTFS folder in the user profile. Light's zip does not contain the runtime. The runtime is not fetched at launch.

### Phase 5 — Signing, and not tripping the usual blocks

- [ ] Windows: Authenticode on the executable users open. Since June 2023, code-signing keys must live on FIPS 140-2 hardware, so a `.pfx` in GitHub secrets is not allowed. Use a cloud signing service such as Azure Trusted Signing, DigiCert KeyLocker, or SSL.com eSigner, and record its cost and setup. macOS signing already runs from Phase 1; re-verify it here.
- [ ] Document secret storage. Signing keys never enter the repo or the plan.
- [ ] Re-smoke the signed artifact. Signing can break a PyInstaller layout.
- [ ] On a clean Windows VM, scan the signed zip with Microsoft Defender and record the result. If it is blocked, fix the layout or the signature. Do not pack, obfuscate, or advise turning antivirus off.
- [ ] Release notes say a new certificate can still show SmartScreen until it has reputation, and that AppLocker or WDAC allow-lists are an IT decision. The app does not remove Mark of the Web.

**Acceptance:** the Windows binary has a valid Authenticode signature that shows the publisher. The macOS app is still notarized and opens without a Gatekeeper block. A new certificate can still show SmartScreen until it has reputation. Defender does not quarantine that build. The notes state the AppLocker limit in one sentence.

## Progress log

- **2026-10-17** — Plan written from disk measurements. No freeze has been run, so compressed app size is still an estimate. The Kaleido browser binary has not been downloaded here, so its size is unmeasured.
- **2026-10-17** — Light omits PNG export and Chrome. Full bundles a Chromium for offline PNG, subject to the Phase 0 license check.
- **2026-10-17** — Review (`opencode-go/longcat-2.5-preview-free`) folded in: Chromium rather than Chrome for Testing, generated `_edition.py`, freeze path list, `pywebview`, per-OS double-click layout, separate Light/Full size ranges, and the Light mesh trade-off (~22 MB, not the 8.6 MB three-mesh starter).
- **2026-10-17** — Phases 0–3 are the zip. Phase 4 puts the WebView2 Fixed Version runtime in the Full Windows zip only. Light uses the runtime already on the PC. Phase 5 signs. AppLocker bypass, MOTW stripping, and packers are out of scope.
- **2026-10-18** — Review (Claude Opus 5.5 medium) folded in. Phase 0 is a Windows spike: missing `git` must not break export, `freeze_support` comes first, and the freeze proves data files open. Light checks for WebView2 before `ui.run` because pywebview otherwise falls back to MSHTML. Public Full Windows waits for Phase 4. Linux v1 is browser mode. PNG is gated in the render functions. Signing does not promise a SmartScreen-free first launch.
- **2026-10-19** — Added Phase 0b, a macOS spike that signs and notarizes a Light build early and compares Briefcase with PyInstaller.
- **2026-10-19** — Reviews (`opencode/deepseek-v4.1-flash-free`, `opencode-go/minimax-m3.1-flash-free`) folded in. The macOS notarize order uses `ditto` and staples before the final zip. Full macOS signs its Chromium. Kaleido gets the browser path explicitly, because `BROWSER_PATH` loses to a downloaded Chrome. The frozen entry is a dedicated script. `corrections.db` leaves the freeze. Upload examples ship. The git item is already shipped. The log sink follows the TO_DO design. Architectures, ATS, Windows cloud signing, the GitHub asset CDN redirect, zip extraction rules, and the phantom-resolution refactor are now explicit. Mesh sizes use byte sums.

## Decision log

- **2026-10-17** — Light + Full zips are the v1 product. In-app download is Phase 3 because many target machines are offline.
- **2026-10-17** — Pip wheels keep the full phantom tree. Only the frozen Light build is reduced.
- **2026-10-17** — PNG export needs a Chromium-family browser (Kaleido 1.5 / choreographer), not the native GUI window. Light does not offer PNG and does not ship a browser. HTML export stays in both.
- **2026-10-17** — Full's bundled browser is Chromium. Chrome for Testing, which choreographer downloads from `chrome-for-testing-public`, is not a ship candidate. If Chromium cannot be redistributed, the air-gapped PNG claim is dropped before Phase 1.
- **2026-10-17** — Edition is `guiskindose/_edition.py`. The committed default is `full`. The freeze overwrites the staging copy only. Users cannot flip it with an environment variable. Light returns no PNG from the render functions, so a machine with Edge does not become a Light PNG host.
- **2026-10-18** — Linux v1 opens in the system browser. Native Linux needs WebKit2GTK, which is a root install.
- **2026-10-18** — Extra phantoms use the per-OS application-support directory. Window prefs and equipment profiles stay in `~/.guiskindose/`.
- **2026-10-18** — Full Windows is an NTFS folder in the user profile. The WebView2 path is set on `app.native.settings` with an absolute path. A new Authenticode certificate can still show SmartScreen.
- **2026-10-17** — No update check and no crash reporting. The user phantom library survives deleting the app folder.
- **2026-10-19** — macOS signing and notarization move into Phase 1, because an unsigned quarantined `.app` is blocked, not just warned. Phase 5 is Windows Authenticode plus re-verification.
- **2026-10-19** — The WebView2 pre-check runs in every edition, not only Light.
- **2026-10-18** — A no-admin Windows run is the Full zip after Phase 4 (Fixed Version WebView2 via `app.native.settings`, pywebview ≥ 6.1) and Phase 5 (Authenticode). Light omits that 250 MB runtime. Phase 1 already tells the user when WebView2 is missing, before the window starts. AppLocker/WDAC bypass is out of scope.

## Related docs

| Doc | Role |
|-----|------|
| [references/PORTABLE_EXECUTABLE_PACKAGING.md](../references/PORTABLE_EXECUTABLE_PACKAGING.md) | Earlier research note (tooling, Java non-goal) |
| [RELEASES_AND_DISTRIBUTION.md](../RELEASES_AND_DISTRIBUTION.md) | Where release assets are described |
| [ADDITIONAL_PHANTOMS.md](../ADDITIONAL_PHANTOMS.md) | How the clinical library is produced |
| [PRIVACY_AND_SENSITIVE_ASSETS.md](../PRIVACY_AND_SENSITIVE_ASSETS.md) | STL hashes and what may ship |
