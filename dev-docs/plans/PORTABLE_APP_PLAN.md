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

Those eight are about **250 MB** before their smaller transitive dependencies and the embedded Python runtime (the local 3.14 framework is 81 MB; a freeze ships a subset). PyInstaller onedir output is larger than the sum of inputs, then a zip compresses it. **The first spike must publish the real onedir and zip sizes.** Until that measurement, treat a full app as hundreds of megabytes uncompressed, with a compressed download likely in the low hundreds of megabytes, not tens.

**Phantoms are the largest project asset and a small slice of the app.** 67 MB against ~250 MB of named libraries is roughly a fifth of the library payload, and less of the zipped download. Dropping the catalog to an ~9–20 MB starter saves on the order of **50 MB uncompressed**. That is worth doing. It does not turn the download into a small utility.

PNG export is a separate payload from the meshes. Kaleido 1.5 in this environment is 328 KB and does not vendor a browser. `fig.to_image()` starts a Chromium-family browser through `choreographer` (a previously downloaded Chrome build, then Google Chrome, Chromium, Edge, Brave, or Vivaldi). Safari and Firefox are not used. The native window uses the operating-system web view, and Kaleido does not drive that window. HTML dose maps do not need a browser. The browser binary is expected to outweigh the phantom library; Phase 0 measures the actual download per OS before Full ships it.

## Recommendation

1. **Ship Light and Full as two GitHub Release assets per OS.** Same code, different phantom payload. Full is the air-gapped clinical download. Light is the smaller first download.
2. **Add an in-app phantom library after the freeze works**, not before. The same signed manifest installs a pack from a zip (offline) or from the matching GitHub Release (online). Hospitals that block outbound traffic still get the full catalog by choosing the Full zip.
3. **Light omits PNG export and does not bundle a browser. Full bundles one.** Both builds still export HTML, JSON, and CSV. PDF and DOCX still generate; in Light, embedded dose-map images are omitted with the existing "image unavailable" notice. Full points Kaleido at a Chromium binary inside the onedir (`BROWSER_PATH` or Kaleido's bundled-Chrome lookup) so PNG works with no system browser and no network. Phase 0 confirms that binary's license allows redistribution; if it does not, Full falls back to "PNG uses an installed Chromium-family browser" and does not ship the binary.
4. **Do not vendor a second copy of the meshes inside the Python wheel and the app.** The wheel can keep today's full `phantom_data/` for `pip` users. The Light freeze uses an explicit include list. Pip behavior does not change in v1. `pip install` keeps Kaleido and still uses whatever Chromium-family browser is on the machine.

### Proposed Light set (product choice, not locked)

Enough to run a real adult case, a pediatric case, and one larger habitus, offline, with arms at the side:

- `hudfrid`, `adult_male`, `adult_female`
- `ped_5y_male`, `ped_5y_female`
- `adult_bariatric_male_1`, `adult_bariatric_female_1`
- the `_arms_down` twin of each
- `_reduced_3000t` previews only (Settings already prefers these)

Order of magnitude: under **25 MB**. The Full build keeps the current 23 + 23 clinical meshes. Drop `_reduced_1000t` from both app builds (2.3 MB, legacy preview). Keep those files in the wheel until a separate cleanup, so pip installs do not change in this plan.

Plane and cylinder phantoms are generated in code. They are in every build and are not part of the catalog.

## Non-goals

- One binary that runs on Windows, macOS, and Linux.
- Committing built executables, or putting PHI fixtures in a release zip.
- A Java / JVM wrap of the stack.
- An auto-updater that phones home with usage, hostnames, or exam metadata.
- Replacing `pip install` or the CLI. The frozen app is an extra channel.
- macOS App Store or Microsoft Store distribution.
- Trimming scipy/pandas to shrink the download. That is a different project, and it risks the dose path.

## Design

### Freeze

- Tooling: NiceGUI `nicegui-pack` / PyInstaller. `ui.run(reload=False)`. Native window (`--windowed`) so the first open is a desktop window, not a terminal plus a browser tab.
- Entry: the existing `run_gui` path, not a second toy script.
- Layout: **onedir**, zipped for download. Faster start and easier diagnosis than onefile.
- Rebuild on each OS. Artifacts are GitHub Release assets only, after privacy and release gates. No binaries in git.
- Bundle: Python runtime, runtime dependencies, `table_data/`, `corrections.db`, packaged GUI help, `settings_example.json`, and the selected phantom payload. Full also bundles the Chromium binary from Phase 0.
- Omit from the freeze: dev and docs extras, Playwright, Jupyter, Semgrep, example DICOM (users bring their own files; examples stay in the source tree and the wheel). Light also omits the Chromium binary.
- A build flag (`GUISKINDOSE_APP_EDITION=light|full`, set at freeze time) hides the PNG dose-map action in Light. The flag is not a user setting. Pip installs stay on today's behavior (PNG offered, browser discovered on the machine).

### Phantom library

Lookup order, still confined to known roots and safe stems (the current basename allow-list stays):

1. User library (writable, outside the bundle).
2. Shipped payload inside the bundle (`phantom_data/` or the frozen equivalent).

The user library lives in the OS application-support directory (`GUISkinDose/phantoms/`), not inside a signed app bundle. Resolution must keep rejecting `..`, separators, and stems outside the safe pattern.

A **phantom pack** is a zip of `.stl` files plus a manifest. The manifest lists stem, byte size, sha256, pack version, and the app versions it is allowed to serve. Install verifies the hash against the manifest, and the manifest hash against a value shipped in the app (or a release asset the app was built to expect). Unknown stems, extra archive members, and path traversal fail closed. The pack contains meshes only.

Settings lists the whole clinical catalog. Installed meshes are selectable. Missing meshes are visible as not installed, with two actions: install from a pack zip, and download this mesh or the full catalog when a network fetch is enabled. Dose calculation refuses a missing mesh with that same explanation. It does not silently fall back to another body.

Pack version follows the app version. A pack from 1.2 is not assumed to fit a 1.3 geometry frame. The manifest says which app versions it matches.

### Network

Download URL is fixed at build time to that version's GitHub Release asset (HTTPS). The app does not accept an arbitrary URL from the user. Redirects off the release host are rejected. No identifiers, filenames, or absolute paths are logged. Failure is offline-safe: the meshes already installed keep working.

Fetching is off until the user asks. There is no background check.

### Trust and first launch

An unsigned Windows `.exe` and an unsigned macOS `.app` will be warned on by SmartScreen and Gatekeeper. A zip of an onedir is the v1 download. Code signing and Apple notarization are a later phase; without them, "double-click" still needs the OS "open anyway" step. Document that in the release notes rather than calling the unsigned zip a finished installer.

## Phases

Each phase is a separate PR. Do not start Phase 1 until Phase 0 has measured sizes on one OS.

### Phase 0 — Spike on one OS

- [ ] Freeze `run_gui` on one developer OS (macOS first is fine) with the **full** phantom payload, `table_data/`, and `corrections.db`.
- [ ] Download the Kaleido/choreographer Chrome build for that OS, record its size, and read whether its license allows shipping it inside a third-party app.
- [ ] Record onedir size, zip size, and cold-start time twice: without that browser (Light shape) and with it (Full shape).
- [ ] Launch, load a local RDSR, calculate on a shipped human mesh, export HTML. With the browser bundled and `BROWSER_PATH` set, export PNG with no system Chrome installed.
- [ ] Fix path resolution under the freeze directory (`_MEIPASS` or the nicegui-pack equivalent) for package data only. Do not add the user library yet.
- [ ] Document the PyInstaller hidden-import and data-file list that actually worked.

**Acceptance:** one OS produces a zip a maintainer can unzip and run through calculate + HTML export. The Chrome binary's size and redistribution terms are written down. No release workflow yet.

### Phase 1 — Light and Full payloads

- [ ] One include list for Light (the set above, or the set chosen in review) and one for Full.
- [ ] Light sets `GUISKINDOSE_APP_EDITION=light` and ships no browser. Full sets `full`, bundles the measured Chromium only if Phase 0 cleared its license, and points Kaleido at that binary.
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

### Phase 4 — Signing (when a real double-click is required)

- [ ] Windows: Authenticode on the executable users open.
- [ ] macOS: Developer ID sign and notarize the `.app` (or the zip contents Gatekeeper checks).
- [ ] Document the secret storage. Signing keys never enter the repo or the plan.
- [ ] Re-smoke the signed artifact. Signing can break PyInstaller if the layout is wrong.

**Acceptance:** a clean machine opens the app without the unsigned-binary warning, on the OS that was signed.

## Progress log

- **2026-10-17** — Plan written from disk measurements. No freeze has been run, so compressed app size is still an estimate. The Kaleido browser binary has not been downloaded here, so its size is unmeasured.
- **2026-10-17** — Light omits PNG export and Chrome. Full bundles a Chromium for offline PNG, subject to the Phase 0 license check.

## Decision log

- **2026-10-17** — Light + Full zips are the v1 product. In-app download is Phase 3 because many target machines are offline.
- **2026-10-17** — Pip wheels keep the full phantom tree. Only the frozen Light build is reduced.
- **2026-10-17** — PNG export needs a Chromium-family browser (Kaleido 1.5 / choreographer), not the native GUI window. Light does not offer PNG and does not ship a browser. Full ships one when redistribution is allowed. HTML export stays in both.

## Related docs

| Doc | Role |
|-----|------|
| [references/PORTABLE_EXECUTABLE_PACKAGING.md](../references/PORTABLE_EXECUTABLE_PACKAGING.md) | Earlier research note (tooling, Java non-goal) |
| [RELEASES_AND_DISTRIBUTION.md](../RELEASES_AND_DISTRIBUTION.md) | Where release assets are described |
| [ADDITIONAL_PHANTOMS.md](../ADDITIONAL_PHANTOMS.md) | How the clinical library is produced |
| [PRIVACY_AND_SENSITIVE_ASSETS.md](../PRIVACY_AND_SENSITIVE_ASSETS.md) | STL hashes and what may ship |
