# Portable Full build: which Chromium to bundle

_Researched 2026-10-31 for the Phase 0 checkbox "Pick the exact Chromium artifact to fetch" in
[`../plans/PORTABLE_APP_PLAN.md`](../plans/PORTABLE_APP_PLAN.md)._

The Full portable build ships a browser so Kaleido can export PNG with no network and no system
browser. The plan rules out Chrome for Testing and `chrome-headless-shell`, which are Google
Chrome builds. Two Chromium candidates were compared. Both may be redistributed.

**Recommendation: ungoogled-chromium for Windows, pinned to `156.0.8078.73-1.1`.** It tracks the
Chromium stable channel, it is smaller, and it removes the Google service calls that an air-gapped
site would otherwise see as blocked traffic. The upstream snapshot is the fallback if the maintainer
prefers a Google-built binary over a community build.

## Pinned artifact (Windows x64)

| Field | Value |
|-------|-------|
| Provider | `ungoogled-software/ungoogled-chromium-windows`, GitHub Release `156.0.8078.73-1.1` (published 2026-10-30) |
| Chromium version | 156.0.8078.73 (stable branch) |
| URL | `https://github.com/ungoogled-software/ungoogled-chromium-windows/releases/download/156.0.8078.73-1.1/ungoogled-chromium_156.0.8078.73-1.1_windows_x64.zip` |
| sha256 | `360406931fb55b04ac276bcf409511bd86e4e67e6950029fc45ca5ca63443090` (matches the digest GitHub publishes for the asset) |
| Zip size | 200,854,085 bytes (191.5 MB) |
| Unpacked size | 443,240,984 bytes (422.7 MB), 75 files; `chrome.dll` alone is 302 MB |
| Built by | the repository's own GitHub Actions workflows (`build-x64.yml`, `publish-release.yml`); the release author is `github-actions[bot]` |
| Code signing | none; the Windows binaries are not Authenticode-signed |

`.github/workflows/portable-spike.yml` holds the same URL and sha256. The Full job downloads the
zip, refuses it unless the sha256 matches, and moves its single top-level folder to
`GUISkinDose/chromium/` beside `GUISkinDose.exe`. No browser binary is committed to this repository.

## Licence and notices that must ship

Chromium is BSD-3-Clause. ungoogled-chromium and its Windows packaging are BSD-3-Clause too. Both
allow redistribution in binary form if the copyright notice, the conditions, and the disclaimer
ship in the documentation or other materials. Chromium also bundles many third-party libraries
(for example ICU, FFmpeg, libvpx, and V8 dependencies) under their own licences.

Neither candidate zip contains a licence or credits file. In the ungoogled-chromium build the
third-party notices are compiled into the binary and shown at `chrome://credits`. The upstream
snapshot does not have them: its `chrome://credits` is a placeholder that says the build lacks
`generate_about_credits=true` (checked on the `Mac_Arm/1732297` snapshot). Shipping a snapshot would
mean generating the notices from a Chromium source checkout. The Full onedir carries three files in
`GUISkinDose/chromium/`:

| File | Source |
|------|--------|
| `LICENSE.chromium.txt` | the Chromium source `LICENSE` at tag `156.0.8078.73`, committed at [`../../packaging/portable/chromium/`](../../packaging/portable/chromium/) |
| `LICENSE.ungoogled-chromium-windows.txt` | `LICENSE` of `ungoogled-chromium-windows` at tag `156.0.8078.73-1.1`, committed beside it |
| `CREDITS.html` | generated in CI from the exact bundled build by [`../../packaging/portable/dump_chromium_credits.py`](../../packaging/portable/dump_chromium_credits.py), which opens `chrome://credits` over DevTools (5,451,755 bytes, 497 credited products for `156.0.8078.73-1.1`) |

`CREDITS.html` is generated rather than committed, so it always matches the binary that ships. The
dump script fails on a placeholder page, and the Full PNG check (`packaging/portable/pngcheck.py`)
fails if any of the three files is missing or the credits dump is under 100 kB. `--dump-dom
chrome://credits` on the command line does not work here: it returned a New Tab page. A bump of the pinned version must refresh both committed licence
files.

## Candidates compared

| | ungoogled-chromium (Windows) | Upstream Chromium snapshot |
|---|---|---|
| Version | 156.0.8078.73-1.1 (stable) | revision 1732287, `159.0.8136.0` (trunk tip on 2026-10-31) |
| URL | GitHub Release asset (above) | `https://commondatastorage.googleapis.com/chromium-browser-snapshots/Win_x64/1732287/chrome-win.zip` |
| sha256 | `360406931fb55b04ac276bcf409511bd86e4e67e6950029fc45ca5ca63443090` | `3affeb37c59699964793bb1ee4710f72125e0894b0025f1d2b0b3c271d2747a1` |
| Zip / unpacked | 191.5 MB / 422.7 MB (75 files) | 352.4 MB / 830.0 MB (258 files) |
| Contents | browser only | browser plus `interactive_ui_tests.exe` (357 MB), `setup.exe`, and other test or installer files that would need pruning |
| Built by | community project, on public GitHub Actions | Google's Chromium continuous builders |
| Licence | BSD-3-Clause, plus Chromium's third-party notices | BSD-3-Clause, plus the same third-party notices |
| Redistribution | allowed with the notices above | allowed with the notices above |
| Notices file in zip | none; `chrome://credits` holds them | none, and `chrome://credits` is a placeholder |
| Update cadence | a release per Chromium stable update, roughly weekly (six releases between 2026-10-06 and 2026-10-30) | a new build per trunk commit range, many per day; no stable channel and no security backports |
| Google service calls | removed by the project's patches | present (Safe Browsing, component updater, and similar) |
| Retention | GitHub Release assets stay until the project deletes them | old revisions stay available for bisecting, but there is no published retention promise |
| `--headless` with Kaleido 1.5 / choreographer 1.4 | works: two PNGs rendered in CI run [41230921691](https://github.com/kgrizz-git/GUISkinDose/actions/runs/41230921691) | headless loads pages (the `Mac_Arm/1732297` snapshot ran under choreographer locally); a Kaleido PNG render was not run |

The snapshot's provenance is Google's own build infrastructure, which is its main advantage. It is a
trunk build with no release testing, twice the unpacked size before pruning, and no compiled-in
credits. ungoogled-chromium
is a stable-branch build with a smaller footprint, but its binaries come from a volunteer project.
Its build logs are public on GitHub Actions, which makes the provenance auditable, not
equivalent to Google's.

## Other operating systems (not yet tested)

| OS | ungoogled-chromium | Upstream snapshot |
|----|--------------------|-------------------|
| macOS arm64 | `ungoogled-chromium-macos` release `156.0.8078.47-1.1`, `..._arm64-macos.dmg`, 150.9 MB | `Mac_Arm/1732297/chrome-mac.zip`, 180.1 MB |
| Linux x86_64 | `ungoogled-chromium-portablelinux` release `156.0.8078.79-1`, `..._x86_64.AppImage`, 209.5 MB (a `.tar.xz` is also published) | `Linux_x64/1732295/chrome-linux.zip`, 254.9 MB |

The macOS build is a nested `.app` with helper apps. Phase 0b must re-sign it inside-out with the
project identity before notarization. The macOS and Linux sha256 values are not pinned yet.

## Kaleido and choreographer facts that shape the integration

These come from the installed `kaleido` 1.5.0 and `choreographer` 1.4.0 (`uv.lock`).

- choreographer prefers a Chrome it downloaded earlier, then `BROWSER_PATH`, then typical install
  paths. The frozen app therefore passes the bundled path explicitly:
  `kaleido.start_sync_server(path=<onedir>/chromium/chrome.exe, mathjax=False)`. Plotly's
  `fig.to_image` then routes through that server.
- `mathjax=False` drops the only CDN script. With `plotlyjs` unset, Kaleido's page loads
  `plotly.min.js` from the installed plotly package as a `file://` URI. The PNG check captures the
  generated page and fails on any `http(s)` script `src`.
- Kaleido starts the browser with `--no-sandbox` by default (`enable_sandbox=False`). The spike keeps
  that default and records the flag. Turning the sandbox on is an open Phase 1 question.

## What the Full CI job proves

Run [41230921691](https://github.com/kgrizz-git/GUISkinDose/actions/runs/41230921691) passed. The job blocks outbound traffic for both `GUISkinDose.exe` and the bundled `chromium/chrome.exe`
with Windows Firewall rules. It sets `BROWSER_PATH` to the runner's system Chrome as a decoy. The
frozen `GUISkinDose.exe --png-check` must then render PNG dose maps, every browser process started
under it must run from inside the onedir, and the Kaleido page must reference no `http` script.

The run rendered 2 PNGs (545,872 bytes) in 9.9 s. Seven browser processes started, all from
`chromium/chrome.exe`, none from outside the onedir, although the runner has a system Chrome and
`BROWSER_PATH` pointed at it. The browser flags included `--headless`, `--no-sandbox`, and
`--disable-gpu`. The captured Kaleido page had 0 `http` script references and no MathJax.
