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

`du` on `src/guiskindose/phantom_data/`: **67 MB**, 138 STL files.

| Class | Files | Size |
|-------|------:|-----:|
| Full clinical meshes | 23 | 30.1 MB |
| Arms-down twins | 23 | 30.8 MB |
| Reduced previews | 92 | 9.2 MB |
| of which `_reduced_3000t` | | 6.9 MB |
| of which `_reduced_1000t` | | 2.3 MB |

Each full mesh is about **1.3 MB** (`hudfrid.stl` is 0.68 MB). A starter of `adult_male`, `adult_female`, and `hudfrid`, both poses, both preview resolutions, is **8.6 MB**.

Other project data that a freeze must include:

| Data | Size |
|------|-----:|
| HVL / correction CSVs under `table_data/` | 6.3 MB |
| `corrections.db` | 2.5 MB |
| Example RDSR under `example_data/` | 1.2 MB |
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

Those eight are about **250 MB** before their smaller transitive dependencies and the embedded Python runtime (the local 3.14 framework is 81 MB; a freeze ships a subset). PyInstaller onedir output is larger than the sum of inputs, then a zip compresses it. **Phase 0 must publish the real onedir and zip sizes for Light and for Full separately.** Until then, use these planning ranges only:

| Build | What dominates | Planning range (compressed zip) |
|-------|----------------|----------------------------------|
| **Light** | Scientific libraries. No Chromium, no WebView2 runtime. About 22 MB of meshes. | Low hundreds of MB |
| **Full** | The same libraries, plus Chromium (often 150 MB or more) and, on Windows, the Fixed Version WebView2 runtime (Microsoft documents it as over 250 MB) | Higher than Light by those runtimes plus ~45 MB of extra meshes |

A single "low hundreds of MB" figure fits Light. It is the wrong figure for Full.

**Phantoms are the largest project asset and a small slice of the app.** 67 MB against ~250 MB of named libraries is roughly a fifth of the library payload, and less of the zipped download. Dropping the catalog to an ~9–20 MB starter saves on the order of **50 MB uncompressed**. That is worth doing. It does not turn the download into a small utility.

PNG export is a separate payload from the meshes. Kaleido 1.5 in this environment is 328 KB and does not vendor a browser. `fig.to_image()` starts a Chromium-family browser through `choreographer` (a previously downloaded browser, then Google Chrome, Chromium, Edge, Brave, or Vivaldi). Safari and Firefox are not used. The native window uses the operating-system web view, and Kaleido does not drive that window. HTML dose maps do not need a browser.

The browser that choreographer would download on its own is **Chrome for Testing**, not open-source Chromium. The pin in this environment (`choreographer` `last_known_good_chrome.json`) points at `storage.googleapis.com/chrome-for-testing-public/` build 142.0.7444.175. That is Google's Chrome build. **Full does not ship Chrome for Testing.** The bundle candidate is a Chromium binary, and Phase 0 records that binary's license text before any Full zip is built. `BROWSER_PATH` is how Kaleido is pointed at it.

## Recommendation

1. **Ship Light and Full as two GitHub Release assets per OS.** Same code, different phantom payload. Full is the air-gapped clinical download. Light is the smaller first download.
2. **Add an in-app phantom library after the freeze works**, not before. The same signed manifest installs a pack from a zip (offline) or from the matching GitHub Release (online). Hospitals that block outbound traffic still get the full catalog by choosing the Full zip.
3. **Light omits PNG export and does not bundle a browser. Full bundles Chromium, not Chrome for Testing.** Both builds still export HTML, JSON, and CSV. PDF and DOCX still generate; in Light, embedded dose-map images are omitted with the existing "image unavailable" notice. Full sets `BROWSER_PATH` to the Chromium binary inside the onedir so PNG works with no system browser and no network. If that Chromium license does not allow redistribution, stop before Phase 1 and drop the air-gapped PNG promise. Full then uses a Chromium-family browser already installed on the machine, and the release notes say PNG does not work offline.
4. **Do not vendor a second copy of the meshes inside the Python wheel and the app.** The wheel can keep today's full `phantom_data/` for `pip` users. The Light freeze uses an explicit include list. Pip behavior does not change in v1. `pip install` keeps Kaleido and still uses whatever Chromium-family browser is on the machine.

### Proposed Light set (product choice, not locked)

Enough to run a real adult case, a pediatric case, and one larger habitus, offline, with arms at the side:

- `hudfrid`, `adult_male`, `adult_female`
- `ped_5y_male`, `ped_5y_female`
- `adult_bariatric_male_1`, `adult_bariatric_female_1`
- the `_arms_down` twin of each
- `_reduced_3000t` previews only (Settings already prefers these)

The 8.6 MB figure above is only `adult_male`, `adult_female`, and `hudfrid`. This seven-base set is about **22 MB** (full meshes near 1.3 MB, both poses, plus `_reduced_3000t`). It does **not** include ectomorph, endomorph, senior, junior, preschool, or 10-year meshes. A Light user who needs one of those installs a phantom pack (Phase 2) or downloads Full.

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

- Tooling: NiceGUI `nicegui-pack` / PyInstaller. `ui.run(reload=False)`. On Windows and macOS the frozen entry calls `run_gui(native=True)`. On Linux v1 it calls `run_gui(native=False)` and opens the system browser on loopback. WebKit2GTK is a system package that needs root to install, so native Linux is not part of v1. PyInstaller's `--windowed` switch only hides the console. It is not an app flag.
- Entry: the existing `run_gui` path. The first lines of the frozen entry call `multiprocessing.freeze_support()` before argument parsing. NiceGUI starts the native window in a child process, and a late `freeze_support()` lets that child re-parse the command line. The Windows and macOS freezes include `pywebview` (pin `>=6.1`; the lock has 6.2.1). Drop test-only packages such as `pytest-asyncio` from the freeze even though they sit in the `gui` extra.
- Layout: **onedir**, zipped for download. What the user double-clicks:
  - Windows: the `.exe` PyInstaller writes in the onedir.
  - macOS: a `GUISkinDose.app` wrapper around that onedir. A bare onedir folder is not a double-clickable app.
  - Linux: the executable (browser mode) plus a `.desktop` file in the zip.
- Rebuild on each OS. Artifacts are GitHub Release assets only, after privacy and release gates. No binaries in git. Each fetched browser or runtime is pinned by version and sha256 in the CI job.
- Bundle: Python runtime, runtime dependencies, `table_data/`, `corrections.db`, packaged GUI help, `gui/static/` (fonts), `gui/ui_copy.json`, `settings_example.json`, `normalization_settings.json`, and the non-DICOM example under `example_data/kerma_meter/` (the in-app help already tells users that CSV is installed with the package). Full also bundles the Chromium binary from Phase 0. On macOS, `BROWSER_PATH` points at `Chromium.app/Contents/MacOS/Chromium`, not at the `.app` bundle.
- Omit from the freeze: dev and docs extras, Playwright, Jupyter, Semgrep, example DICOM. Light also omits the Chromium binary and the WebView2 Fixed Version runtime.
- Edition is `guiskindose/_edition.py`. The committed source file is `EDITION = "full"`, and a test asserts that. The freeze writes `light` or `full` into the build staging copy, never into the source tree. An environment variable does not override it. The GUI hides the PNG card when the edition is `light`. The same check lives in the PNG render functions (`render_dosemap_png` and the other `to_image` callers) so a Light build returns "image unavailable" without starting a browser. Windows ships Edge, and Kaleido would use it if those functions still ran.
- A windowed build has no console. Phase 0 confirms launch does not crash when `sys.stdout` is `None`, and writes a privacy-safe log under `~/.guiskindose/logs` (no filenames, no absolute paths, no identifiers). That is the file sink already sketched under Native GUI optional file logging in [TO_DO.md](../TO_DO.md).

### Phantom library

Lookup order, still confined to known roots and safe stems (the current basename allow-list stays):

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

Download URL is fixed at build time to that version's GitHub Release asset (HTTPS). The app does not accept an arbitrary URL from the user. Redirects off the release host are rejected. No identifiers, filenames, or absolute paths are logged. Failure is offline-safe: the meshes already installed keep working.

Fetching is off until the user asks. There is no background check.

### Trust and first launch

An unsigned Windows `.exe` and an unsigned macOS `.app` will be warned on by SmartScreen and Gatekeeper. A zip of an onedir is the v1 download. Phases 0–3 produce that zip. They do **not** yet produce a Windows build that a standard user can open on every PC.

What Phases 0–3 do promise: no installer, no copy into `Program Files`, and no request for administrator rights. The user unzips into a folder they can write and double-clicks the `.exe`. On Windows, Full must sit on an NTFS folder in the user profile. A USB stick formatted FAT32 or exFAT cannot store the AppContainer permissions the Fixed Version runtime needs, and that runtime does not run from a network path. Phantom packs go in the per-OS phantom directory above. Uninstall is deleting the unzipped folder plus `~/.guiskindose/` if the user also wants preferences and profiles gone.

What they do not promise, and later phases take on:

| Block | Why a standard user gets stuck | When it is handled |
|-------|--------------------------------|--------------------|
| Missing WebView2 runtime | pywebview 6.2.1 falls back to the old MSHTML engine when WebView2 is missing. NiceGUI does not run there, and the window process can fail while the server stays up. | **Phase 1** checks for WebView2 before `ui.run` and shows a message that names the Full download. No installer, no MSHTML fallback. **Phase 4** ships the Fixed Version runtime in the Full Windows zip only |
| Unknown publisher (SmartScreen, Gatekeeper) | An unsigned download shows a warning. "Run anyway" is not an admin step, but many people stop there. A brand-new certificate still warns until it gains reputation. | Phase 5 signs and notarizes |
| Antivirus heuristics | PyInstaller onedir builds, and a bundled browser, are often flagged. A packer makes that worse. | Phase 5 records a Defender scan of the signed zip. No packer, no "disable your antivirus" instruction |
| Hospital allow-lists (AppLocker, WDAC) | IT can block any publisher, signed or not. This project cannot bypass that. | Out of scope. Release notes say the site admin must allow the signed publisher |
| Mark of the Web | A browser download marks the zip. The app must not strip that mark. | Signing is the mitigation, not deleting `Zone.Identifier` |
| Network or UNC launch | Microsoft's Fixed Version runtime does not run from a network path. This applies to the Full Windows zip. | Phase 4 release notes say to copy the Full folder onto the PC first |

The frozen Windows manifest must not set `requireAdministrator`. Linux builds must not be setuid. macOS builds must not include a privileged helper.

## Phases

Each phase is a separate PR. Do not start Phase 1 until Phase 0 has measured sizes on Windows.

### Phase 0 — Spike on Windows

The failures that matter for a no-admin PC are Windows-only. Do this spike on Windows. A macOS spike can follow. It does not replace the Windows one.

- [ ] Freeze `run_gui(native=True)` with the **full** phantom payload, `table_data/`, `corrections.db`, `pywebview`, GUI help, `gui/static/`, `gui/ui_copy.json`, `normalization_settings.json`, and `example_data/kerma_meter/`.
- [ ] Call `multiprocessing.freeze_support()` before argument parsing in the frozen entry.
- [ ] Make `safe_output._git_root` survive a missing `git`. Catch `OSError`. A frozen build skips the checkout check. On Windows, the `git` spawn must not flash a console (`CREATE_NO_WINDOW`). Acceptance runs with `git` removed from `PATH` and still saves HTML. This also fixes `pip` users, so the implementation PR adds a CHANGELOG entry.
- [ ] Confirm a windowed launch does not crash when `sys.stdout` is `None`, and that the log file under `~/.guiskindose/logs` is created.
- [ ] Download a **Chromium** build, not Chrome for Testing. Record size and license. Stop the Full-bundle path if redistribution is not allowed. Record which system libraries that binary needs on Linux. If Full PNG on Linux needs packages only root can install, say so in the progress log and drop the air-gapped PNG claim for Linux.
- [ ] Record onedir size, zip size, and cold-start time twice: without that browser (Light shape) and with it (Full shape).
- [ ] Launch with the network disabled. Load a local RDSR, calculate, and export HTML, JSON, and CSV. With Chromium bundled and `BROWSER_PATH` set, export PNG with no system Chrome installed.
- [ ] Prove package data resolves inside the freeze by opening, from the frozen app, `phantom_data`, `table_data`, `gui/help`, `gui/static`, `gui/ui_copy.json`, `normalization_settings.json`, `settings_example.json`, and the kerma-meter example CSV. A list of `__file__` call sites is not the acceptance test. PyInstaller sets `__file__` for collected modules. Watch repo-root climbs such as the fun-mesh manifest path and the `ui_copy` repo-catalog fallback.
- [ ] Document the hidden imports and data files that actually worked.

**Acceptance:** a Windows zip runs calculate and HTML export with the network off and with `git` absent. Chromium's size, license, and (for Linux) library needs are written down. No release workflow yet. The Light PNG gate is Phase 1, because the edition file is not in this spike.

### Phase 1 — Light and Full payloads

- [ ] Pin `pywebview>=6.1` in `pyproject.toml`. One include list for Light and one for Full.
- [ ] The freeze staging copy gets `EDITION = "light"` or `"full"`. The committed file stays `"full"`. Light ships no Chromium and no WebView2 runtime. Full bundles Chromium only if Phase 0 cleared its license. `BROWSER_PATH` is set inside the process that calls Kaleido.
- [ ] PNG render functions return no image when the edition is `light`, before any browser lookup. A test on a machine that has Edge proves a Light rich report does not start a browser. The GUI hides the PNG card as well.
- [ ] Before `ui.run` on Windows, Light checks for an installed WebView2 runtime using the same registry locations pywebview reads. If it is missing, show a message that names the Full download. Do not fall back to MSHTML. Do not launch an installer. Acceptance is a VM without WebView2: a message, no broken window, no UAC prompt.
- [ ] Both builds run the same tests that do not need a missing mesh. A Light build test proves a starter mesh loads and a non-starter stem is reported missing. A Full test proves PNG bytes come back when the bundled browser is on `BROWSER_PATH`.
- [ ] `_reduced_1000t` is absent from both app payloads. Previews still resolve to `_reduced_3000t`.
- [ ] CI builds Windows, macOS, and Linux onedir zips. Artifacts expire. They are not committed. Fetched binaries are checked against the pinned sha256. Linux jobs launch browser mode, not native.
- [ ] Public Full Windows waits for Phase 4. A Phase 1 Full Windows zip may be kept as a size artifact and is labeled "needs WebView2 already installed." It is not the no-admin download.
- [ ] Smoke tests use a zip that was downloaded through a browser, so Mark of the Web and macOS quarantine are actually present. Release notes name the downloads, say Light has no PNG dose map, say Linux opens in the browser, and state that the app is not FDA-cleared.

**Acceptance:** public zips are Light on three OSes, Full on macOS and Linux, and no public Full Windows yet. Each launches, calculates once, and exports HTML. macOS and Linux Full also export PNG offline when the Phase 0 license check passed. Maintainer signs off the measured sizes.

### Phase 2 — User library and offline pack

- [ ] Resolve meshes from the user library, then the shipped payload, with the existing stem confinement.
- [ ] "Install phantom pack" picks a local zip, verifies the manifest, and copies only allow-listed STLs into the user library. Refuse a zip whose compressed size or uncompressed size exceeds a documented cap.
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
- [ ] Place the decompressed runtime inside the **Full** onedir only. Pass that absolute path through `app.native.settings['WEBVIEW2_RUNTIME_PATH']`. Light leaves it unset.
- [ ] On Windows 10, Fixed Version 120 and later needs AppContainer read-execute on that folder (`ALL APPLICATION PACKAGES` and `ALL RESTRICTED APPLICATION PACKAGES`). Do that from code on an NTFS folder the user owns. The acceptance run must not show a UAC prompt. A FAT or exFAT USB stick is not a supported Full location.
- [ ] Smoke Full on a Windows VM that does **not** have WebView2 installed: unzip into the user profile on NTFS, launch, calculate, export HTML. Confirm Full does not launch from a UNC path, and say that in the release notes.
- [ ] Add the runtime size to the Full Windows zip estimate only. It dominates the phantom-catalog difference on Windows.
- [ ] A later release rebuilds when that pinned runtime or the pinned Chromium has a security fix. There is no auto-updater.

**Acceptance:** Full opens on Windows 10 without a preinstalled WebView2 and without a UAC prompt, from an NTFS folder in the user profile. Light's zip does not contain the runtime. The runtime is not fetched at launch.

### Phase 5 — Signing, and not tripping the usual blocks

- [ ] Windows: Authenticode on the executable users open. macOS: Developer ID sign and notarize the `.app`.
- [ ] Document secret storage. Signing keys never enter the repo or the plan.
- [ ] Re-smoke the signed artifact. Signing can break a PyInstaller layout.
- [ ] On a clean Windows VM, scan the signed zip with Microsoft Defender and record the result. If it is blocked, fix the layout or the signature. Do not pack, obfuscate, or advise turning antivirus off.
- [ ] Release notes say a new certificate can still show SmartScreen until it has reputation, and that AppLocker or WDAC allow-lists are an IT decision. The app does not remove Mark of the Web.

**Acceptance:** the Windows binary has a valid Authenticode signature that shows the publisher. The macOS app is notarized and opens without a Gatekeeper block. A new certificate can still show SmartScreen until it has reputation. Defender does not quarantine that build. The notes state the AppLocker limit in one sentence.

## Progress log

- **2026-10-17** — Plan written from disk measurements. No freeze has been run, so compressed app size is still an estimate. The Kaleido browser binary has not been downloaded here, so its size is unmeasured.
- **2026-10-17** — Light omits PNG export and Chrome. Full bundles a Chromium for offline PNG, subject to the Phase 0 license check.
- **2026-10-17** — Review (`opencode-go/longcat-2.5-preview-free`) folded in: Chromium rather than Chrome for Testing, generated `_edition.py`, freeze path list, `pywebview`, per-OS double-click layout, separate Light/Full size ranges, and the Light mesh trade-off (~22 MB, not the 8.6 MB three-mesh starter).
- **2026-10-17** — Phases 0–3 are the zip. Phase 4 puts the WebView2 Fixed Version runtime in the Full Windows zip only. Light uses the runtime already on the PC. Phase 5 signs. AppLocker bypass, MOTW stripping, and packers are out of scope.
- **2026-10-18** — Review (Claude Opus 5.5 medium) folded in. Phase 0 is a Windows spike: missing `git` must not break export, `freeze_support` comes first, and the freeze proves data files open. Light checks for WebView2 before `ui.run` because pywebview otherwise falls back to MSHTML. Public Full Windows waits for Phase 4. Linux v1 is browser mode. PNG is gated in the render functions. Signing does not promise a SmartScreen-free first launch.

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
- **2026-10-18** — A no-admin Windows run is the Full zip after Phase 4 (Fixed Version WebView2 via `app.native.settings`, pywebview ≥ 6.1) and Phase 5 (Authenticode). Light omits that 250 MB runtime. Phase 1 already tells the user when WebView2 is missing, before the window starts. AppLocker/WDAC bypass is out of scope.

## Related docs

| Doc | Role |
|-----|------|
| [references/PORTABLE_EXECUTABLE_PACKAGING.md](../references/PORTABLE_EXECUTABLE_PACKAGING.md) | Earlier research note (tooling, Java non-goal) |
| [RELEASES_AND_DISTRIBUTION.md](../RELEASES_AND_DISTRIBUTION.md) | Where release assets are described |
| [ADDITIONAL_PHANTOMS.md](../ADDITIONAL_PHANTOMS.md) | How the clinical library is produced |
| [PRIVACY_AND_SENSITIVE_ASSETS.md](../PRIVACY_AND_SENSITIVE_ASSETS.md) | STL hashes and what may ship |
