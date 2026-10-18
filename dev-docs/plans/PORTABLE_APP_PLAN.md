# Portable desktop app — GUISkinDose

_Status: plan only — not started._
_Created: 2026-10-17._
_Parent hub: [RELEASES_AND_DISTRIBUTION.md](../RELEASES_AND_DISTRIBUTION.md)._
_Feasibility note: [references/PORTABLE_EXECUTABLE_PACKAGING.md](../references/PORTABLE_EXECUTABLE_PACKAGING.md)._

## Goal

Ship a double-clickable desktop app for people who do not install Python: unzip (or open) a per-OS build, get the existing NiceGUI window, load an RDSR, calculate, and export. Processing stays on the machine. No exam data leaves the computer.

Two downloadable builds, same program:

| Build | Who it is for | Phantom payload | PNG / browser |
|-------|----------------|-----------------|----------------|
| **Light** | First download, quick trials, smaller transfer | A small clinical starter set, installed and usable offline | No bundled browser. PNG dose-map export is not offered |
| **Full** | Clinical library, air-gapped workstations | Every shipped clinical STL, including arms-down twins and the preferred preview | Bundled Chromium so Kaleido PNG export works offline |

A later phase lets a Light install add the rest from a phantom pack: download when the network is allowed, or install a pack zip with no network. The pack is data, not a second application.

## What exists today

The GUI already runs as `python -m guiskindose --mode gui`, with `--native` opening a pywebview window. There is no freeze pipeline, no installer, and no PyPI publish yet. Mesh lookup is confined to the package directory `src/guiskindose/phantom_data/` (`resolve_human_mesh_stl_path`). A frozen bundle is often read-only and signed, so extra phantoms cannot be dropped into that directory. They need a separate user library.

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
| **Light** | Scientific libraries. No browser. About 22 MB of meshes. | Low hundreds of MB |
| **Full** | The same libraries, plus a browser binary that is expected to outweigh the 67 MB mesh tree (often on the order of 150 MB or more before it is zipped with everything else) | Higher than Light by roughly the browser plus ~45 MB of extra meshes |

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

- Tooling: NiceGUI `nicegui-pack` / PyInstaller. `ui.run(reload=False)`. The frozen entry calls `run_gui(native=True)` (the app's `--native` flag). PyInstaller's `--windowed` switch only hides the console. It is not an app flag.
- Entry: the existing `run_gui` path, not a second toy script. The freeze includes `pywebview` (the `gui-native` extra). Without it, native mode cannot open a window.
- Layout: **onedir**, zipped for download. Faster start and easier diagnosis than onefile. What the user double-clicks:
  - Windows: the `.exe` PyInstaller writes in the onedir.
  - macOS: a `GUISkinDose.app` wrapper around that onedir. A bare onedir folder is not a double-clickable app.
  - Linux: the executable plus a `.desktop` file in the zip.
- Rebuild on each OS. Artifacts are GitHub Release assets only, after privacy and release gates. No binaries in git.
- Bundle: Python runtime, runtime dependencies including `pywebview`, `table_data/`, `corrections.db`, packaged GUI help, `settings_example.json`, and the selected phantom payload. Full also bundles the Chromium binary from Phase 0.
- Omit from the freeze: dev and docs extras, Playwright, Jupyter, Semgrep, example DICOM (users bring their own files; examples stay in the source tree and the wheel). Light also omits the Chromium binary.
- Edition is a generated module, `guiskindose/_edition.py`, written at freeze time with `EDITION = "light"` or `EDITION = "full"`. The source tree ships `EDITION = "full"` so `pip install` keeps today's behavior: PNG is offered and Kaleido looks for a browser on the machine. The GUI imports `EDITION` and hides the PNG dose-map card when it is `"light"`. An environment variable does not override it. Rich-report image rendering already treats a failed PNG as "image unavailable"; Light relies on that for PDF and DOCX.

### Phantom library

Lookup order, still confined to known roots and safe stems (the current basename allow-list stays):

1. User library (writable, outside the bundle).
2. Shipped payload inside the bundle (`phantom_data/` or the frozen equivalent).

The user library lives outside the bundle, not inside a signed app:

| OS | Directory |
|----|-----------|
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

What Phases 0–3 do promise: no installer, no copy into `Program Files`, and no request for administrator rights. The user unzips into a folder they can write (their profile or a USB drive) and double-clicks the `.exe`. Phantom packs go in `%LOCALAPPDATA%`. Uninstall is deleting the unzipped folder.

What they do not promise, and later phases take on:

| Block | Why a standard user gets stuck | When it is handled |
|-------|--------------------------------|--------------------|
| Missing WebView2 runtime | The native window uses pywebview's Edge backend. Windows 11 usually has the runtime. Some Windows 10 PCs do not. The machine-wide installer needs admin. | Phase 4 bundles Microsoft's Fixed Version runtime beside the `.exe` |
| Unknown publisher (SmartScreen, Gatekeeper) | An unsigned download shows a warning. "Run anyway" is not an admin step, but many people stop there. A brand-new certificate still warns until it gains reputation. | Phase 5 signs and notarizes |
| Antivirus heuristics | PyInstaller onedir builds, and a bundled browser, are often flagged. A packer makes that worse. | Phase 5 records a Defender scan of the signed zip. No packer, no "disable your antivirus" instruction |
| Hospital allow-lists (AppLocker, WDAC) | IT can block any publisher, signed or not. This project cannot bypass that. | Out of scope. Release notes say the site admin must allow the signed publisher |
| Mark of the Web | A browser download marks the zip. The app must not strip that mark. | Signing is the mitigation, not deleting `Zone.Identifier` |
| Network or UNC launch | Microsoft's Fixed Version runtime does not run from a network path. | Phase 4 release notes say to copy the folder onto the PC first |

The frozen Windows manifest must not set `requireAdministrator`. Linux builds must not be setuid. macOS builds must not include a privileged helper.

## Phases

Each phase is a separate PR. Do not start Phase 1 until Phase 0 has measured sizes on one OS.

### Phase 0 — Spike on one OS

- [ ] Freeze `run_gui(native=True)` on one developer OS (macOS first is fine) with the **full** phantom payload, `table_data/`, `corrections.db`, and `pywebview`.
- [ ] Download a **Chromium** build for that OS, not Chrome for Testing. Record its compressed and uncompressed size and paste the license finding into the progress log. Stop the Full-bundle path if redistribution is not allowed.
- [ ] Record onedir size, zip size, and cold-start time twice: without that browser (Light shape) and with it (Full shape).
- [ ] Launch with the network disabled. Load a local RDSR, calculate on a shipped human mesh, and export HTML, JSON, and CSV. With Chromium bundled and `BROWSER_PATH` set, export PNG with no system Chrome installed. Light must not offer PNG, and a PNG attempt in Light must not hang.
- [ ] Route package-data paths through one helper that works in a freeze. `correction_data.py` already uses `importlib.resources.files("guiskindose")`. These `__file__` sites do not, and they are in Phase 0:
  - `phantom_mesh_names.package_phantom_data_dir`
  - `gui/helpers.py` `_PHANTOM_DATA_DIR`
  - `gui/phantom_preview.py` `_PHANTOM_DATA_DIR`
  - `__init__.py` `load_settings_example_json` and `print_available_human_phantoms`
  - `helpers/parse_settings_to_settings_class.py` fallback to `settings_example.json`
- [ ] Document the PyInstaller hidden-import and data-file list that actually worked, including `pywebview`.

**Acceptance:** one OS produces a zip a maintainer can unzip and run through calculate + HTML export with the network off. Chromium's size and license finding are written down. If the license forbids shipping it, the progress log says Full will not bundle a browser. No release workflow yet.

### Phase 1 — Light and Full payloads

- [ ] One include list for Light (the set above, or the set chosen in review) and one for Full.
- [ ] The freeze writes `guiskindose/_edition.py` (`EDITION = "light"` or `"full"`). Light ships no browser. Full bundles the measured Chromium only if Phase 0 cleared its license, and points Kaleido at that binary with `BROWSER_PATH`.
- [ ] Both builds run the same tests that do not need a missing mesh. A Light build test proves a starter mesh loads and a non-starter stem is reported missing. A Light UI test proves the PNG action is absent. A Full test proves PNG bytes come back when the bundled browser is on `BROWSER_PATH`.
- [ ] `_reduced_1000t` is absent from both app payloads. Previews still resolve to `_reduced_3000t`.
- [ ] CI job matrix builds Windows, macOS, and Linux onedir zips on a release branch or a manual workflow. Artifacts expire. They are not committed. The browser binary is fetched in the Full job, not stored in git.
- [ ] Release notes name the two downloads per OS, say Light has no PNG dose map, and state that the app is not FDA-cleared.

**Acceptance:** three OS zips for Light and three for Full. Each launches, calculates once, and exports HTML. Full also exports PNG offline. Maintainer signs off the measured sizes before the first public asset.

### Phase 2 — User library and offline pack

- [ ] Resolve meshes from the user library, then the shipped payload, with the existing stem confinement.
- [ ] "Install phantom pack" picks a local zip, verifies the manifest, and copies only allow-listed STLs into the user library.
- [ ] Settings shows installed and not-installed catalog rows.
- [ ] A missing mesh blocks calculation with an install hint.
- [ ] Unit tests use a temp library and a tiny synthetic STL. They do not download anything.
- [ ] Help text states that packs are optional data and that Full already contains the catalog.

**Acceptance:** a Light app plus a pack zip gains a mesh that was not in the Light payload, survives restart, and is used for a calculation. A tampered STL is rejected.

### Phase 3 — Download from the matching release

- [ ] Download action fetches the pack (or one stem, if the release layout allows) from the build's pinned release URL.
- [ ] Hash check is the same as Phase 2. Partial files are not treated as installed.
- [ ] Cancel, retry, and offline failure leave the library unchanged.
- [ ] No request carries exam data, file names, or machine identifiers beyond what HTTPS already sends.

**Acceptance:** on a machine with network, Light can grow to the full catalog without a second app download. With network disabled, installed meshes and the local zip path still work.

### Phase 4 — Windows runtime without an admin install

Both Windows zips need this, Light and Full. It is separate from the Chromium browser Full uses for PNG.

- [ ] Pin `pywebview` at `>=6.1` (the lock already has 6.2.1). That version reads `webview.settings['WEBVIEW2_RUNTIME_PATH']` and sets WebView2's `BrowserExecutableFolder`.
- [ ] Download Microsoft's **Fixed Version** WebView2 runtime for the build arch, not the Evergreen machine-wide installer. Record its size (Microsoft documents it as over 250 MB) and the redistribution terms in the progress log.
- [ ] Place the decompressed runtime inside the onedir and set `WEBVIEW2_RUNTIME_PATH` before `run_gui(native=True)`. If the path is missing, fail with a short message. Do not fall through to a system install.
- [ ] On Windows 10, Fixed Version 120 and later needs AppContainer read-execute on that folder (`ALL APPLICATION PACKAGES` and `ALL RESTRICTED APPLICATION PACKAGES`). Do that from code or a user-level step on a folder the user owns. The acceptance run must not show a UAC prompt.
- [ ] Smoke on a Windows VM that does **not** have WebView2 installed: unzip into the user profile, launch, calculate, export HTML. Repeat from `Program Files` only to confirm we do not tell users to install there. Confirm the folder does not launch from a UNC path, and say that in the release notes.
- [ ] Add the runtime size to the Light and Full zip estimates. It dominates the phantom-catalog difference on Windows.

**Acceptance:** a standard user on Windows 10 without WebView2, and on Windows 11, opens the window after unzipping into their profile. No UAC prompt. The runtime is not fetched at launch.

### Phase 5 — Signing, and not tripping the usual blocks

- [ ] Windows: Authenticode on the executable users open. macOS: Developer ID sign and notarize the `.app`.
- [ ] Document secret storage. Signing keys never enter the repo or the plan.
- [ ] Re-smoke the signed artifact. Signing can break a PyInstaller layout.
- [ ] On a clean Windows VM, scan the signed zip with Microsoft Defender and record the result. If it is blocked, fix the layout or the signature. Do not pack, obfuscate, or advise turning antivirus off.
- [ ] Release notes say a new certificate can still show SmartScreen until it has reputation, and that AppLocker or WDAC allow-lists are an IT decision. The app does not remove Mark of the Web.

**Acceptance:** a clean machine opens the signed app without the unknown-publisher interstitial, on the OS that was signed. Defender does not quarantine that build. The notes state the AppLocker limit in one sentence.

## Progress log

- **2026-10-17** — Plan written from disk measurements. No freeze has been run, so compressed app size is still an estimate. The Kaleido browser binary has not been downloaded here, so its size is unmeasured.
- **2026-10-17** — Light omits PNG export and Chrome. Full bundles a Chromium for offline PNG, subject to the Phase 0 license check.
- **2026-10-17** — Review (`opencode-go/longcat-2.5-preview-free`) folded in: Chromium rather than Chrome for Testing, generated `_edition.py`, freeze path list, `pywebview`, per-OS double-click layout, separate Light/Full size ranges, and the Light mesh trade-off (~22 MB, not the 8.6 MB three-mesh starter).
- **2026-10-17** — Phases 0–3 are the zip. Phase 4 bundles the WebView2 Fixed Version runtime so Windows needs no admin install. Phase 5 signs. AppLocker bypass, MOTW stripping, and packers are out of scope.

## Decision log

- **2026-10-17** — Light + Full zips are the v1 product. In-app download is Phase 3 because many target machines are offline.
- **2026-10-17** — Pip wheels keep the full phantom tree. Only the frozen Light build is reduced.
- **2026-10-17** — PNG export needs a Chromium-family browser (Kaleido 1.5 / choreographer), not the native GUI window. Light does not offer PNG and does not ship a browser. HTML export stays in both.
- **2026-10-17** — Full's bundled browser is Chromium. Chrome for Testing, which choreographer downloads from `chrome-for-testing-public`, is not a ship candidate. If Chromium cannot be redistributed, the air-gapped PNG claim is dropped before Phase 1.
- **2026-10-17** — Edition is `guiskindose/_edition.py`, generated at freeze time. The source default is `full`. Users cannot flip it with an environment variable.
- **2026-10-17** — No update check and no crash reporting. The user phantom library survives deleting the app folder.
- **2026-10-17** — A no-admin Windows run is Phase 4 (Fixed Version WebView2 via `WEBVIEW2_RUNTIME_PATH`, pywebview ≥ 6.1) plus Phase 5 (Authenticode). Phases 0–3 do not claim it. AppLocker/WDAC bypass is out of scope.

## Related docs

| Doc | Role |
|-----|------|
| [references/PORTABLE_EXECUTABLE_PACKAGING.md](../references/PORTABLE_EXECUTABLE_PACKAGING.md) | Earlier research note (tooling, Java non-goal) |
| [RELEASES_AND_DISTRIBUTION.md](../RELEASES_AND_DISTRIBUTION.md) | Where release assets are described |
| [ADDITIONAL_PHANTOMS.md](../ADDITIONAL_PHANTOMS.md) | How the clinical library is produced |
| [PRIVACY_AND_SENSITIVE_ASSETS.md](../PRIVACY_AND_SENSITIVE_ASSETS.md) | STL hashes and what may ship |
