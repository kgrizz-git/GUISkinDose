# Portable app Phase 3 — download the phantom pack from the matching release

_Status: in progress. Implementation landed on `portable/phase3-pack-download`; the manual Light smoke, frozen Light download, live draft-release workflow run, and `--update-pin` helper remain open. Execution plan for Phase 3 of [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md) (lines 338–345)._
_Created: 2026-11-27. Revised 2026-11-27 after ERNIE, Muse, and maintainer review._
_Parent: [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md). Builds on the shipped Phase 2 code in [PORTABLE_PHANTOM_PACKS_PLAN.md](PORTABLE_PHANTOM_PACKS_PLAN.md)._

This file is the checklist. Do the steps in order. Each step is one reviewable PR, or a smaller PR that finishes every box in that step. Do not start the next step with the previous step's tests red.

SemVer: this is a minor feature. Put the user-facing change under `[Unreleased]` → Added in `CHANGELOG.md`. Put test-only, workflow, and harness notes in `dev-docs/MAINTENANCE_LOG.md`.

## Objective

A Light install (or any install with clinical meshes missing from both roots) can add the clinical catalog from the phantom pack that was built for **its own release**, with one explicit user action. The download is optional, never automatic, and never runs at startup.

Requirements:

1. One **Download phantom pack** action fetches one release asset over HTTPS from a URL fixed in code. The public API takes no URL and no insecure flag.
2. Integrity is the same SHA-256 manifest pin Phase 2 already enforces, plus the per-member hashes. A downloaded file that does not verify is never installed. Authenticity limits are stated explicitly in **Trust and integrity**.
3. Cancel, retry, network failure, TLS failure, an oversized body, and a terminated connection all leave the user library byte-for-byte unchanged.
4. The request carries no exam data, source filename, host name, user name, machine identifier, or absolute path. The only added header is a fixed `User-Agent` carrying the app version already present in the URL.
5. Nothing contacts the network unless the user presses the button or passes the CLI flag.
6. Light and Full share one code path. When the catalog is complete, both the download and the local-zip actions are hidden behind a single "catalog complete" caption.
7. Cancellation is bounded: a cancel closes the response so a blocked read returns promptly, instead of waiting for a full socket timeout.

## Non-goals

- Per-stem downloads and per-stem release assets. Decision: one whole pack. The manifest already pins every stem, so a later phase can add per-stem downloads without changing the trust model.
- Pack signing and key management. Decision: defer signing. The `signature` seam stays as Phase 2 left it.
- A user-editable release URL, an in-app proxy editor, a mirror list, or an auto-updater. Decision: no mirrors; the local-zip install is the restricted-network path.
- Changing `edition.py` payload lists, the manifest schema, or the 80 MiB install caps.
- Installing a pack from the network during a dose calculation.

## Current state (evidence)

| Area | What exists today |
|---|---|
| Phase 3 scope | `dev-docs/plans/PORTABLE_APP_PLAN.md:338-345` lists the download action, the same hash check, cancel/retry/offline safety, and the no-identifiers rule. Acceptance is at line 345. |
| Local pack install | `src/guiskindose/phantom_pack_install.py:508` (`install_phantom_pack`) validates a stream, stages inside the library, and `Path.replace()`s each mesh. Caps are at `phantom_pack_install.py:38-45`; the compressed cap is 80 MiB at line 39. |
| Atomic publish | `phantom_pack_install.py:274` creates a `.incoming-<token>` stage, `:289` publishes one file with a backup, and `:336` rolls back every publish on failure. A partial download never reaches this path. |
| Manifest and pin | `src/guiskindose/phantom_pack.py:58` (`verify_manifest_pin`) compares the canonical manifest hash to the expected pin. `src/guiskindose/phantom_pack_pin.py:7` holds the single production pin. `phantom_pack.py:41` is the signing seam and still rejects any `signature` key. |
| Pack builder | `scripts/build_phantom_pack.py:29-41` selects every shipped STL outside `light_phantom_stl_names()` and omits `_reduced_1000t`; `:93-116` builds the zip or checks the pin with `--check`. |
| GUI install control | `src/guiskindose/gui/tabs/_phantom_catalog.py:178-193` mounts either the native dialog or a browser upload. `:113-137` installs on a worker thread. `:213` shows the Phase 3 placeholder caption. |
| Placeholder copy | `dev-docs/ui_copy.json:144` (`settings.phantom_catalog.phase3_caption`) says a future version may download a signed pack. That sentence is replaced by this phase. |
| CLI install | `src/guiskindose/phantom_pack_cli.py:60` opens a path, installs, prints counts, and never prints the path. `src/guiskindose/cli_args.py:99-105` declares `--install-phantom-pack`; `src/guiskindose/__main__.py:234-239` refuses it with `--mode gui`. |
| Light set | `src/guiskindose/edition.py:28-45` lists the starter meshes. The pack is everything else in the clinical catalog. |
| Release workflows | No workflow publishes a phantom pack. `.github/workflows/release.yml` publishes PyPI and runs `check_sensitive_content.py --require-approved-assets`, `check_ignored_asset_files.py --strict`, and `run_semgrep_privacy.py`. `.github/workflows/portable-macos-release.yml:280-299` uploads macOS assets after `release: published` with `--clobber`; that pattern does not work for immutable releases and is not copied. |
| NiceGUI cancellation | Installed NiceGUI 4.0.0 (`pyproject.toml:40`) documents in `nicegui/run.py:139-145` that `run.io_bound` raises `asyncio.CancelledError` when the call is cancelled, but the worker thread keeps running. Cancellation must be cooperative inside the worker, and the worker must close its own response and spool. |
| TLS trust | `certifi` is currently a direct dependency only on the `gui`/`gui-native` extras (`pyproject.toml:40`). Decision: promote it to core dependencies so the CLI and GUI share one trust store. |
| Settings preview | `src/guiskindose/gui/phantom_preview.py:127-136` documents and calls the preview resolver with `user_library_dir=None`; `:179` calls `resolve_human_mesh_stl_path` without a user library. The resolver treats `None` as the default library (`src/guiskindose/phantom_mesh_names.py:278,321`), so this is behavior-preserving today, but the stale package-only docstring hides the dependency and no test proves a downloaded mesh appears in the preview. |
| Busy state | `src/guiskindose/gui/state.py:192` has an in-memory `busy` flag. A page reload during a draining download must not turn the next retry into a hard failure. |
| User library | `src/guiskindose/phantom_library.py:70-95` resolves macOS Application Support, Windows LocalAppData, and the Linux XDG data home. Install creates it only at commit. |
| Help page | `docs/source/gui_help/phantom_packs.md:12-24` documents the zip install and CLI, and says nothing yet about a download. |

## Design

### 1. Release layout and the code-owned pin

One platform-independent asset per release tag:

```
https://github.com/kgrizz-git/GUISkinDose/releases/download/v<APP_VERSION>/guiskindose-phantom-pack-<APP_VERSION>.zip
```

- `<APP_VERSION>` is `guiskindose.__version__` verbatim. The frozen app's version is fixed at build time, so the URL is pinned per build.
- New module `src/guiskindose/phantom_pack_release.py` owns the repository slug, the asset-name template, the tag template, the URL builder, and the allowed redirect hosts. No environment variable and no settings key overrides them.
- `pack_release_url(version)` returns `None` unless `version` matches `^\d+\.\d+\.\d+$`. A source tree reporting `0.0.0+unknown` and a pre-release/local suffix therefore fail closed with a fixed sentence. Releases use plain `vX.Y.Z` tags.
- The integrity anchor stays `EXPECTED_PHANTOM_PACK_SHA256` in `phantom_pack_pin.py`. The zip's own SHA-256 is **not** pinned in code: zip bytes are not reproducible (member mtimes and deflate output vary), while the canonical manifest is.
- The release publishes `…zip.sha256` only as a convenience for humans and manual offline copying. **It is not a trust signal**, and neither the app nor the docs present it as one.
- The pin must be refreshed in the same release-preparation commit that bumps `pyproject.toml`. `scripts/build_phantom_pack.py --check` already fails when they disagree; the release workflow runs it before uploading.
- Because the manifest's `app_versions` contains only the exact app version (Phase 2 contract), every app release needs its own pack asset even when the mesh bytes did not change. That is intentional: it keeps the URL derivable and the pin verifiable. `dev-docs/RELEASES_AND_DISTRIBUTION.md` states that a per-release pack does **not** imply new meshes.

### 2. Trust and integrity

Order of checks, all before any library write:

1. URL policy: HTTPS, host `github.com`, no userinfo, default port.
2. Redirect policy: every hop is HTTPS and its host is in `{github.com, release-assets.githubusercontent.com, objects.githubusercontent.com}`; at most five hops; anything else stops the request and raises a fixed error. Signed query strings on the CDN hop are preserved for the request and never logged.
3. Body cap: 80 MiB, enforced both from `Content-Length` and on the bytes actually read.
4. Complete body: a short read or `IncompleteRead` fails.
5. Phase 2 validation on the spilled stream: zip structure, member names, manifest pin, per-member byte counts and SHA-256, app-version match.
6. Phase 2 publish: stage inside the library, `Path.replace()` per mesh, roll back all publishes on any failure.

No whole-zip hash is compared, because the manifest pin covers every installed byte.

**Trust model (explicit).** The manifest pin plus per-member SHA-256 gives **integrity**: a substituted zip, a tampered STL, a truncated body, or a different manifest is rejected, regardless of where it came from. It does **not** give **authenticity** against compromise of the GitHub release itself: the app binary and the pack are published from the same repository and host, so an attacker who can replace both can also replace the pin in a new app release. Phase 3 does not add an independent signing key or transparency log. The `.zip.sha256` asset is a transport/check convenience, not a signature and not an independent trust root. Users who need a stronger authenticity boundary must obtain the app and pack through a separately authenticated channel.

### 3. HTTP client

Use the standard library only:

- `urllib.request` with a custom `HTTPRedirectHandler`, an explicit `HTTPSHandler(context=…)`, and the default `ProxyHandler()`.
- `certifi` moves to core dependencies. TLS context is always `ssl.create_default_context(cafile=certifi.where())`, with `check_hostname=True`, `verify_mode=ssl.CERT_REQUIRED`, and `minimum_version=TLSVersion.TLSv1_2`. There is no flag, environment variable, or public seam that disables verification or substitutes an HTTP/loopback transport.
- Frozen builds: PyInstaller's standard `certifi` hook normally collects `cacert.pem`; add a boolean `--self-check` field for "CA bundle readable" (never the path) and, if the hook does not fire, an explicit `collect_data_files("certifi")` in `packaging/portable/guiskindose.spec`. A frozen Light download is the proof.
- Proxies: `urllib` reads `http_proxy`/`https_proxy`/`no_proxy` from the environment. That is the only proxy support; no in-app field, and no proxy value is ever logged. HTTPS through a proxy still verifies the GitHub certificate end to end.
- Request: `GET`, `Accept: application/zip`, `User-Agent: GUISkinDose/<version>`, `Connection: close`. No cookies, no auth, no referer, no query parameters added by the app; a redirect's signed query is forwarded unchanged and never logged.
- Timeout: **5 seconds** per blocking socket operation, so a cancel that cannot close the socket still drains quickly. There is no total wall-clock limit, so a large pack on a slow link can finish.
- Streaming: read 64 KiB chunks, write to `tempfile.SpooledTemporaryFile(max_size=8 MiB, prefix="guiskindose-pack-")`, and check the cancel event each chunk. The spool may spill to the OS temporary directory; where the platform gives the temp file a name, it carries that prefix. The path is never logged. It is closed and deleted by the worker in `finally`.
- Retry is manual (button or rerun the command). There is no automatic retry and no backoff loop.

Why not `requests`/`httpx`: one GET with a redirect policy and a progress loop does not justify another dependency, and the standard library keeps the frozen payload and the audit surface unchanged.

### 4. Download → verify → install

New `src/guiskindose/phantom_pack_download.py` with a deliberately narrow public surface:

```python
def download_release_pack(
    *,
    expected_manifest_sha256: str,
    app_version: str,
    user_library_dir: Path,
    shipped_dir: Path,
    control: DownloadControl,
    progress: DownloadProgress,
) -> InstallResult: ...

def _download_from(
    url: str,
    *,
    transport: _Transport,
    expected_manifest_sha256: str,
    app_version: str,
    user_library_dir: Path,
    shipped_dir: Path,
    control: DownloadControl,
    progress: DownloadProgress,
) -> InstallResult: ...
```

- The public function takes **no URL, no opener, and no insecure flag**. It calls `pack_release_url(app_version)`, raises the fixed unavailable sentence when that is `None`, and uses the production transport and policy.
- `_download_from` is private. Tests import it and pass a separate test-only transport/factory that maps allowed hostnames to loopback servers. Production code never constructs that transport.
- Tests assert the public path cannot enable HTTP or loopback: inspect the public signature for forbidden parameters, and call it with `url=...` / `allow_insecure_loopback=True` to prove both raise `TypeError`.
- The worker owns the spool, the response, and the installer call. It closes the spool in `finally`, so an abandoned thread cleans up after itself.
- It calls the existing `install_phantom_pack`; it does not duplicate zip, manifest, or hash logic.
- `download_release_pack` runs only on a worker thread. No UI element is touched from that thread.

**Failure-to-sentence map.** Every path produces exactly one fixed, code-owned sentence, so the user and the tests can tell them apart:

| Trigger | User sentence |
|---|---|
| `__version__` is not `X.Y.Z` (for example `0.0.0+unknown`) or `pack_release_url` returns `None` | This build has no downloadable phantom pack. Install a pack zip instead. |
| HTTP 404 for the versioned asset | No phantom pack is published for this GUISkinDose version. Install a pack zip, or use the GUISkinDose Full download. |
| DNS failure, connection refused, proxy failure | Could not reach the GUISkinDose release server. Installed meshes are unchanged. |
| TLS certificate or handshake failure | A secure connection to the GUISkinDose release server could not be established. |
| Redirect to a host outside the allow-list, or a non-HTTPS hop | The download was redirected to an untrusted host and was stopped. |
| Declared or actual body over 80 MiB | The phantom pack download exceeded the size limit and was stopped. |
| Short read, reset, or `IncompleteRead` | The phantom pack download did not finish. Installed meshes are unchanged. |
| Cancel event set, including a closed response during cancel | Download cancelled. Installed meshes are unchanged. |
| Manifest hash differs from `EXPECTED_PHANTOM_PACK_SHA256` | This phantom pack manifest is not recognized. (Phase 2 sentence) |
| Member byte count or SHA-256 differs | This phantom pack file hash does not match the manifest. (Phase 2 sentence) |
| Any other transport failure | Phantom pack download failed. Installed meshes are unchanged. |

The first eight are new `PhantomPackDownloadError(PhantomPackError)` constants in `phantom_pack_download.py`; the two verification sentences already exist in `phantom_pack.py:28-29`. The CLI and GUI print `user_message()` and never add the URL, proxy, or path.

### 5. Progress, cancellation, and the controller

`run.io_bound` cannot stop its thread. Put orchestration in a small module, `src/guiskindose/gui/phantom_pack_download_controller.py`, not in `_phantom_catalog.py`:

- `DownloadController` owns the `DownloadProgress` object (`received`, `total: int | None`, `phase`) written under a `threading.Lock`, the cancel event, the response handle, the `ui.timer`, and the retry label.
- The handler starts a `ui.timer(0.2, poll)` that reads a snapshot and updates a `ui.linear_progress` + caption. The timer is stopped in `finally`. This avoids cross-thread UI writes.
- **Cancel is bounded.** `DownloadControl.cancel()` sets the event **and closes the response/socket** under a lock. The worker checks the event between 64 KiB reads and also maps an `OSError`/`ValueError` from a closed response to the cancelled sentence when the event is set. The socket timeout is 5 s, so even a read that cannot be interrupted ends quickly.
- The **Cancel** button calls `control.cancel()`; the UI shows "Cancelling download…" until the worker returns. Because nothing is written to the library before install, the wait cannot corrupt anything.
- If the page disconnects and the awaited call is cancelled, `finally` calls `control.cancel()` and stops the timer; the worker still exits on its own, closes the response and spool, and clears the busy guard.
- **Busy guard survives page reload.** A process-level active-download record is set before the worker starts and cleared in the worker's `finally`, not in the handler's `finally`. A reload or a second page that retries while the old download is draining gets one fixed sentence ("A phantom pack download is still finishing. Try again in a moment.") and does not start a second request or report a failure. This is module state, not `state.busy`, so a reload cannot lose it.
- On failure the same control becomes **Retry download**; there is no new row. On success the existing install-success path runs (`report_install_success`), which clears measurement caches and refreshes rows, select options, geometry, and the Settings preview.
- The controller disables both download and local install while either is running.

### 6. GUI placement

`src/guiskindose/gui/tabs/_phantom_catalog.py` mounts the controls; the controller owns behavior:

- If at least one full-resolution clinical stem is missing from both roots: show **Download phantom pack** next to **Install phantom pack**, with a caption naming the matching release and the optional nature of the data.
- If the build's version is not downloadable: show the unavailable sentence instead of the button, and keep the local-zip install available.
- **If nothing is missing (typical Full, or a completed Light): hide both the download and the local-zip actions**, and show one `settings.phantom_catalog.catalog_complete` caption. No split where one action remains and the other disappears. Keep the help link.
- Add `missing_clinical_stems(*, shipped_dir, user_library_dir)` next to `installed_full_clinical_stems` in `phantom_library.py` rather than recomputing the catalog in the tab.
- Progress/cancel/retry live inside the catalog section, not a modal, so the user can still see which meshes are installed.

**Settings preview after install.** `phantom_preview.py` already resolves the user library because the resolver treats `None` as the default (`phantom_mesh_names.py:278,321`), but that contract is implicit and the docstring at `phantom_preview.py:127-136` says package-only. Pass `user_library_dir=default_user_library_dir()` explicitly at `phantom_preview.py:136` and `:179`, correct the docstring, and add a preview-after-download test that installs a synthetic mesh into a temp user library and asserts the preview figure loads that mesh. This is behavior-preserving today and locks the contract so a downloaded mesh cannot silently disappear from Settings.

### 7. CLI counterpart

- `--download-phantom-pack` on the headless parser, mutually exclusive with `--install-phantom-pack`.
- It installs and exits, like `--install-phantom-pack`; no `--file-path` is required.
- `--mode gui` plus either pack flag exits 1 with a fixed sentence (extend `cli.phantom_pack.gui_mode_refusal` or add a sibling key).
- Success prints the existing counts sentence. Failure prints the fixed `user_message()` and exits 1.
- `KeyboardInterrupt` (Ctrl-C) calls the same `cancel()` path: set the event and close the response, print the cancelled sentence, and exit 130. With the 5 s socket timeout and the closed response, a blocked read returns promptly; a blocked-read test asserts the command finishes without waiting for the download to complete.
- No progress bar and no per-chunk output; nothing about the URL, proxy, signed query, or paths is printed.
- Tests use the private `_download_from` with a test transport; the parser takes no URL argument.

### 8. Editions, offline, and startup

- **Light:** the download is the intended way to reach the full catalog without a second app download.
- **Full:** the pack adds nothing. When the catalog is complete, both download and local-zip actions are hidden behind the "catalog complete" caption. The local zip remains available while any clinical stem is missing (for example a trimmed or damaged payload).
- **Offline/air-gapped:** no automatic request at import, startup, page render, upload, or calculation. The button is the only trigger in the GUI. Installed meshes and the local zip install keep working. Failure leaves the library unchanged and is reported in one sentence.
- **Source checkout:** a version such as `1.1.1` from `pip install -e .` may point at a real release and fail the pin if local meshes differ. That is fail-closed and safe; the unavailable caption appears for non-`X.Y.Z` versions.
- **Restricted networks:** no mirrors. A blocked `github.com` or CDN host is an offline failure; the local-zip install is the supported path.

### 9. Publishing the pack

New workflow `.github/workflows/phantom-pack-release.yml`. It attaches assets **while the release is a draft**, because GitHub immutable releases lock assets after publication:

- Triggers: **`workflow_dispatch` only**, with a required `tag` input. GitHub does not trigger workflows for `created`/`edited`/`deleted` on draft releases, so a `release: created` trigger cannot attach to a draft and is not used. The maintainer runs this dispatch while the release is a draft.
- **Explicitly skip prereleases**: query the release and refuse when `isPrerelease == true`. No prerelease pack.
- Tag policy: the tag must match `^v[0-9]+\.[0-9]+\.[0-9]+$` exactly, the git tag must exist, its commit must be on `main`, and that commit must have a successful `ci.yml` run. Also assert `tag == "v" + <pyproject version>` so the asset name and URL cannot disagree. If the draft was created before the tag was pushed, fail with a "push the tag, then re-run" message.
- Query the release and require `isDraft == true` before attaching. Publication is the separate opt-in step below, not part of the default attach path.
- Checkout with `persist-credentials: false`. Pin every action by SHA.
- Least privilege: `contents: read` at workflow level; `contents: write` only on the attach job and the separate public-verification job does not need it.
- Carry over `release.yml`'s privacy gates before building: `python scripts/check_sensitive_content.py --require-approved-assets`, `python scripts/check_ignored_asset_files.py --strict`, and `python scripts/run_semgrep_privacy.py`, using the locked `dev` extra.
- Build and verify: `scripts/build_phantom_pack.py --check`, then build the asset into `out/` and run `scripts/build_phantom_pack.py --verify out/<asset>` against the committed pin.
- Attach without clobber: inspect `gh release view <tag> --json assets` first. If the asset is absent, `gh release upload <tag> <asset> <asset>.sha256` **without `--clobber`**. If it exists, fetch it with authenticated `gh release download <tag> --pattern <asset>` and compare bytes (or the API digest). Identical bytes are an idempotent success; different bytes fail loudly and the workflow refuses to overwrite. Never `--clobber`.
- **Pre-publish verification uses the authenticated draft asset.** A draft's assets are not publicly downloadable, so fetch the just-attached asset with `gh release download <tag> --pattern <asset> --dir out/verify` and run `--verify` on that file. This proves the attached bytes match the committed pin before publication.
- Publication happens only after the pack, macOS zips, and any other assets are attached. By default the maintainer publishes the draft; a manual dispatch may set `publish_after_attach=true` to run `gh release edit <tag> --draft=false` after verification. A published immutable release cannot gain assets, so attaching after publication is not a supported path.
- **Separate read-only post-publish job.** Add a second job on `release: types: [published]`, skipping prereleases, that re-downloads the public versioned URL with `curl -fsSL --proto '=https' --tlsv1.2` into `out/`, polling with exponential backoff (for example 2, 4, 8, 16, 32 s, five attempts), runs `--verify` against the committed pin, and fails loudly. It never uploads and needs no `contents: write`.
- The job is cheap (one ~40 MB upload) and runs for every stable release; a missing asset is a user-facing 404, so do not make it conditional on mesh changes.
- Update `dev-docs/RELEASES_AND_DISTRIBUTION.md:52-58` so the release checklist runs the pack build/pin refresh, expects the new asset on the draft, and says that a per-release pack does not imply new meshes.
- Release notes name all four: the in-app download, the manual `…zip` asset, the offline fallback (installed meshes and local zip), and that the pack is optional data.

## Files

| File | Change |
|---|---|
| `pyproject.toml` | Promote `certifi` from the `gui`/`gui-native` extras to core `dependencies`; `uv lock`. Update license/notices if the checker requires it. |
| `src/guiskindose/phantom_pack_release.py` | New. Repository slug, asset/tag templates, URL builder, redirect host set, version guard. |
| `src/guiskindose/phantom_pack_download.py` | New. TLS context, redirect handler, streaming download, progress object, cancel/close, installer handoff, fixed errors. Public API with no URL or insecure flag; private `_download_from`. |
| `src/guiskindose/phantom_pack_install.py` | Export the compressed-size cap as a public constant (keep the private alias for compatibility). No behavior change. |
| `src/guiskindose/phantom_library.py` | Add `missing_clinical_stems()` next to the installed-stem query. |
| `src/guiskindose/phantom_pack_cli.py` | Add `run_cli_phantom_pack_download()` and a flag-presence helper. |
| `src/guiskindose/cli_args.py` | Add `--download-phantom-pack`; make the two pack flags mutually exclusive. |
| `src/guiskindose/__main__.py` | Dispatch the download flag; refuse both flags with `--mode gui`. |
| `src/guiskindose/gui/phantom_pack_messages.py` | GUI-mode refusal for the download flag if a separate sentence is used. |
| `src/guiskindose/gui/phantom_pack_download_controller.py` | New. Progress snapshot, timer, cancel/close, retry, process-level busy guard that survives reload. |
| `src/guiskindose/gui/tabs/_phantom_catalog.py` | Mount download controls when meshes are missing; hide both actions behind the catalog-complete caption when none are. Delegate behavior to the controller. |
| `src/guiskindose/gui/phantom_preview.py` | Pass `default_user_library_dir()` explicitly at the two resolver calls; correct the package-only docstring. |
| `dev-docs/ui_copy.json` | New button, caption, catalog-complete, progress, cancel, retry, and busy keys (table below). |
| `docs/source/gui_help/phantom_packs.md` | Download section, offline behavior, size, trust/authenticity sentence. Mirror with `scripts/sync_gui_help.py`. |
| `dev-docs/help_registry.json` | No new page id expected; update the source list if the page gains a component. |
| `dev-docs/feature_doc_matrix.json` | Add the new modules, tests, workflow, and this plan to `phantom_packs`. |
| `dev-docs/glossary.json` | Extend the `phantom pack` entry with the release download. |
| `packaging/portable/guiskindose.spec` | Collect `certifi` CA data in the frozen app. |
| `packaging/portable/selfcheck.py` | Report `certifi_ca_bundle` as a boolean; never the path. |
| `scripts/build_phantom_pack.py` | Add `--verify PATH`; optional `--update-pin` deferred. |
| `.github/workflows/phantom-pack-release.yml` | New draft-release attach-and-verify workflow plus read-only public re-check on publication. |
| `dev-docs/RELEASES_AND_DISTRIBUTION.md` | Draft-release checklist, per-release pack note, distribution table. |
| `dev-docs/plans/PORTABLE_APP_PLAN.md` | Tick Phase 3 boxes only as behavior lands; link this plan from the Phase 3 heading. |
| `tests/unittests/test_phantom_pack_release.py` | New. URL builder, version guard, redirect policy. |
| `tests/unittests/test_phantom_pack_download.py` | New. Test transport, loopback servers, caps, cancel/close latency, offline, incomplete, TLS context, signed-query logging. |
| `tests/unittests/test_phantom_pack_cli.py` | Extend with download-flag, Ctrl-C, and blocked-read cases. |
| `tests/gui/test_gui_phantom_pack_download.py` | New. Controller, button, progress, cancel, retry, busy-after-reload, catalog-complete hiding, no startup network. |
| `tests/gui/test_phantom_preview_download.py` | New. A mesh installed into the temp user library appears in the Settings preview. |

Keep new Python files under 800 lines and every function at Ruff `C901` ≤ 10. Split transport, policy, controller, and UI wiring into separate functions rather than one long handler.

## UI copy keys

Add under `dev-docs/ui_copy.json` → `keys` (progress/cancel/retry owners point at `gui/phantom_pack_download_controller.py`; the rest at `gui/tabs/_phantom_catalog.py`):

| Key | Text | Notes |
|---|---|---|
| `settings.phantom_catalog.download_button` | Download phantom pack | Replaces the placeholder action. |
| `settings.phantom_catalog.download_caption` | Adds the clinical meshes missing from this build from the matching GUISkinDose release. The download is optional; installed meshes keep working offline. | Replaces `phase3_caption`. |
| `settings.phantom_catalog.catalog_complete` | This build includes the full clinical phantom catalog. | Shown when both actions are hidden. |
| `settings.phantom_catalog.download_progress` | Downloading… {percent}% | Placeholder is an integer. |
| `settings.phantom_catalog.download_progress_unknown` | Downloading… | Used when `Content-Length` is absent. |
| `settings.phantom_catalog.download_cancelling` | Cancelling download… | Shown until the worker returns. |
| `settings.phantom_catalog.download_busy` | A phantom pack download is still finishing. Try again in a moment. | Retry during drain, including after reload. |
| `settings.phantom_catalog.download_cancel_button` | Cancel download | |
| `settings.phantom_catalog.download_retry_button` | Retry download | Same control, relabelled. |
| `cli.phantom_pack_download.gui_mode_refusal` | Phantom pack download is only available in headless mode. Use Settings in the GUI, or run without --mode gui. | `gui/phantom_pack_messages.py`. |

`settings.phantom_catalog.install_success` and `install_failure` are reused. Remove `settings.phantom_catalog.phase3_caption` and its call site in the same PR.

The unavailable, cancelled, offline, TLS, redirect, size, and generic failure sentences live once in `phantom_pack_download.py`, following the `phantom_pack.py` error pattern, because both the CLI and the GUI show them. The GUI imports the unavailable constant for its caption and otherwise calls `user_message()`. Do not duplicate those sentences in `ui_copy.json`; the busy sentence is UI-only and belongs in the catalog because it describes controller state, not a download error.

## Privacy review

- **Sent:** one HTTPS `GET` to a fixed URL, with `Accept`, `Connection: close`, and `User-Agent: GUISkinDose/<version>`. The version is already in the URL path. HTTPS necessarily exposes the destination host, TLS SNI, and the client IP to GitHub and its CDN. No exam data, file names, patient/study/institution fields, user name, host name, machine ID, or absolute path is added. No cookie jar, no auth header, no app-added query string, no referer, no telemetry.
- **Redirect query:** the CDN's signed query string is forwarded exactly as GitHub returns it and is never logged, displayed, or included in an error sentence.
- **Proxies:** only environment-configured proxies are used. The app never reads, logs, or displays proxy variables. A proxy operator can see the fixed destination host, as with any HTTPS client.
- **Logging:** `safe_error_event(logger, "phantom_pack_download", exc)` records only an operation code, the exception class, and a package-relative code location. Byte counts may be logged as scalars; the URL, redirect query, proxy values, spool path, and library paths are never logged. The spool is created with the `guiskindose-pack-` prefix, but its full path never appears. No `print` of a path.
- **User text:** every failure sentence is code-owned and path-free. Host names and query strings are not echoed.
- **Files:** the download lives in a prefixed `SpooledTemporaryFile` and is deleted in `finally`. It never enters the library as a partial file. Phase 2 stages and replaces atomically, so no reader can observe a half-written mesh.
- **Trust:** certificate verification is mandatory; redirects are host-allow-listed; the manifest pin and per-member hashes are the integrity anchor. Authenticity against a compromised GitHub release is explicitly out of scope and documented in the help page.
- **Scanners:** this change adds outbound network code and logging-adjacent error paths, so run `python scripts/privacy_admission.py route --mode staged` → `run --mode staged`, the blocking Semgrep privacy rules, and a HoundDog receipt if the route requires one. No new tracked assets are expected (no certificates, no downloaded zips).

## Tests

No test may contact the real GitHub. Production hosts are asserted only through pure policy functions and a test transport that maps allowed hostnames to loopback servers.

### `tests/unittests/test_phantom_pack_release.py`

- `pack_release_url("1.1.1")` returns the exact tag/asset URL; `"0.0.0+unknown"`, `"1.1"`, `"v1.1.1"`, an empty string, and a string with `/` or NUL return `None`.
- Redirect policy accepts `https://github.com/...`, `https://release-assets.githubusercontent.com/...`, and `https://objects.githubusercontent.com/...` (case-insensitive host), and rejects `http://`, `https://evil.example/...`, `https://github.com.evil.example/...`, a URL with userinfo, a non-default port, and a relative URL.
- The version guard refuses a local suffix rather than guessing a tag.

### `tests/unittests/test_phantom_pack_download.py`

Use `ThreadingHTTPServer` instances bound to `127.0.0.1:0` (the pattern in `tests/gui/test_loopback_security.py:419-503`) and the synthetic pack helpers in `tests/unittests/phantom_pack_test_helpers.py`. The test transport maps `github.com` and the two CDN hosts to those servers and may speak plain HTTP to loopback; it is a test-only seam that the public API cannot construct. Production code never builds it, and the production transport always speaks verified HTTPS.

- **Public API cannot weaken the policy:** `download_release_pack` has no `url`, `opener`, `transport`, or `allow_insecure_loopback` parameter; passing each as a keyword raises `TypeError`.
- **Happy path:** serve a valid pack; the worker installs the missing stem into a temp library, returns counts, and closes/deletes the spool. The shipped temp directory is unchanged.
- **404:** fixed "no pack published" sentence; temp library tree hash is identical before and after.
- **Connection refused:** fixed offline sentence; no library write.
- **TLS failure:** an injected `ssl.SSLCertVerificationError` maps to the fixed TLS sentence; `_tls_context()` has `check_hostname=True`, `verify_mode=CERT_REQUIRED`, and `minimum_version >= TLSv1_2`. Do not commit a test certificate.
- **Declared oversize:** `Content-Length` above the cap is refused before the body is read.
- **Lying oversize:** a small `Content-Length` with a body past the cap is stopped mid-stream; fixed oversize sentence; no library write.
- **Truncated body:** the server declares more than it sends and closes; fixed incomplete sentence; no library write.
- **Cancel latency:** a transport read blocks on an event; `cancel()` (which closes the response) makes `_download_from` return within about one second, not the 5 s timeout. No install runs, and the spool is closed.
- **Redirect with a signed query:** server A returns a GitHub-shaped 302 to `https://release-assets.githubusercontent.com/...?...X-Amz-Signature=…`; server B serves the pack. The request to B keeps the query intact, and captured logs at DEBUG contain neither the signature value nor `X-Amz-Signature`. A 302 to `https://evil.example/` stops with the refused sentence and never opens the second connection.
- **Pin mismatch:** serve a valid zip whose manifest hashes to a different value; the installer raises the Phase 2 pin sentence; the library is unchanged.
- **Tampered member:** flip one STL byte; the member hash fails; the library is unchanged.
- **Sentence map:** one test per row of the failure-to-sentence table asserts the exact sentence, so a new path cannot silently reuse the wrong one.
- **No production network:** assert every URL used in the suite points at a test transport or loopback; a test fails if `pack_release_url` output reaches the opener.

### `tests/gui/test_gui_phantom_pack_download.py`

Follow `tests/gui/test_phantom_pack_settings.py` (temp shipped dir, temp library, monkeypatched pin). Do not build a real browser window; instantiate the controller with fake status/progress objects.

- Pressing download with a stub worker runs the progress timer, then installs and flips the rows to Installed without a restart.
- Cancel sets the event, shows the cancelling text, then the cancelled sentence; rows and library are unchanged.
- A failed download leaves rows unchanged and relabels the button Retry; retry with a good stub succeeds.
- **Busy survives reload:** start a blocked download, construct a second controller (simulating a page reload), and invoke retry. It shows `download_busy`, starts no second worker, and does not report a failure. Release the first worker; the next retry succeeds.
- Offline error text is the fixed sentence and contains no path, URL, or query string.
- A Full-shaped shipped dir with the whole catalog hides **both** the download and the local-zip controls and shows the catalog-complete caption.
- A non-`X.Y.Z` version shows the unavailable caption, hides the download button, and keeps the local-zip install.
- Instantiating the Settings tab (or importing the catalog module) performs no network call: monkeypatch `socket.socket` to raise for the duration and assert it is not called.

### `tests/gui/test_phantom_preview_download.py`

- Install a synthetic full-resolution mesh into a temp user library, point `default_user_library_dir` at it, and build the Settings preview for that stem. The figure loads the downloaded mesh rather than returning `None` or substituting another body.
- The reduced-preview preference still checks the shipped root first, then the user library.
- The preview docstring/contract no longer claims package-only resolution.

### `tests/unittests/test_phantom_pack_cli.py` (extend)

- `--download-phantom-pack` with a stubbed downloader exits 0 and prints counts.
- Offline, pin mismatch, and cancel each exit non-zero with the matching fixed sentence.
- `--mode gui --download-phantom-pack` exits 1 with the GUI refusal and does not start the server.
- `--download-phantom-pack` and `--install-phantom-pack` together are rejected by the parser.
- **Ctrl-C with a blocked read:** a test transport raises `KeyboardInterrupt` after the first chunk; the command calls `cancel()`, closes the response, prints the cancelled sentence, and returns 130 without waiting for a full download.
- Captured stderr and logs contain no temp path, home path, URL, or redirect query string.

### Verification commands

```bash
uv run --extra dev --extra gui --locked pytest \
  tests/unittests/test_phantom_pack_release.py \
  tests/unittests/test_phantom_pack_download.py \
  tests/unittests/test_phantom_pack_install.py \
  tests/unittests/test_phantom_pack_cli.py \
  tests/gui/test_gui_phantom_pack_download.py \
  tests/gui/test_phantom_pack_settings.py \
  tests/gui/test_phantom_preview_download.py
python scripts/check_file_sizes.py
python scripts/check_complexity.py
python scripts/check_ui_copy.py
python scripts/check_help_registry.py
python scripts/check_feature_doc_matrix.py
python scripts/sync_gui_help.py --check
uv run --extra dev --extra gui --locked python scripts/check_licenses.py
python scripts/run_semgrep_privacy.py
python scripts/privacy_admission.py run --mode staged
```

## Steps

### Step 0 — Register

- [x] Add this file under **Master plans** in `dev-docs/index.md`.
- [x] Add a short pointer in `dev-docs/TO_DO.md` next to the portable phantom-packs item.
- [x] Link this plan from the Phase 3 heading in `dev-docs/plans/PORTABLE_APP_PLAN.md`.
- [ ] Do not tick any parent Phase 3 box until the matching behavior has landed.

### Step 1 — Release constants and URL policy

- [x] Add `phantom_pack_release.py` with the repo slug, asset and tag templates, `pack_release_url()`, the version guard, and the redirect host set.
- [x] Add `tests/unittests/test_phantom_pack_release.py`.
- [x] No network, no GUI, and no installer changes in this step.

### Step 2 — Downloader transport

- [x] Promote `certifi` to core dependencies in `pyproject.toml` and refresh `uv.lock`; confirm the license/notices check still passes.
- [x] Add `phantom_pack_download.py` with the always-verified TLS context, redirect handler, size caps, prefixed spool, progress object, cancel/close, and fixed errors.
- [x] Implement the public API with no URL/insecure flag and the private `_download_from(url, *, transport)` used by tests.
- [x] Export the compressed cap from `phantom_pack_install.py` and reuse it; add a test that the two constants agree.
- [x] Add the local-server unit tests, including the public-signature guard, cancel latency, caps, truncation, signed-query redirect, and pin mismatch.
- [x] Confirm no UI import in the module, so the CLI can use it without NiceGUI.

### Step 3 — Installer handoff and CLI

- [x] Call `install_phantom_pack` from the worker; do not duplicate validation.
- [x] Add `--download-phantom-pack`, mutual exclusion, `__main__` dispatch, and the GUI-mode refusal.
- [x] Add CLI tests, including Ctrl-C with a blocked read and bounded return.
- [x] Extend `scripts/build_phantom_pack.py` with `--verify PATH` (manifest hash equals the committed pin) and, if used, `--update-pin`.

### Step 4 — Controller, GUI action, and preview

- [x] Add the controller module with progress polling, cancel/close, retry, and the process-level busy guard.
- [x] Add `missing_clinical_stems()` and use it to decide the three states: missing (both actions), unavailable version (no download, local zip), complete (both hidden + caption).
- [x] Mount the controller from `_phantom_catalog.py`; keep that file under the 800-line cap.
- [x] Pass `default_user_library_dir()` explicitly in `phantom_preview.py` and correct its docstring.
- [x] Replace `phase3_caption` with the new keys; add all keys to `dev-docs/ui_copy.json`.
- [x] Add the GUI tests: controller states, busy-after-reload, catalog-complete hiding, no-network-at-startup, and preview-after-download.

### Step 5 — Docs, registry, and release workflow

- [x] Update `docs/source/gui_help/phantom_packs.md`, run `python scripts/sync_gui_help.py`, and commit the mirror.
- [x] Update `dev-docs/glossary.json`, `dev-docs/feature_doc_matrix.json`, `dev-docs/RELEASES_AND_DISTRIBUTION.md`, and the help registry if the page composition changed.
- [x] Add `.github/workflows/phantom-pack-release.yml` with the draft trigger, tag/version asserts, prerelease skip, privacy gates, no-clobber idempotency, and backoff re-download.
- [x] Add the pack publication and pin refresh to the release checklist, including the "per-release pack does not imply new meshes" note.
- [ ] Confirm the frozen Light build carries a readable CA bundle (`--self-check` field) and downloads the pack from the signed/notarized zip or the Windows Light zip, not only from a source run.
- [x] Update `AGENTS.md` and `dev-docs/ADDITIONAL_PHANTOMS.md` with one sentence about the download path and its offline fallback.
- [x] Changelog Added bullet; maintenance log bullet for the workflow and tests.

### Step 6 — Parent closeout

- [x] Tick the four Phase 3 boxes in `dev-docs/plans/PORTABLE_APP_PLAN.md` only after their tests land.
- [ ] Keep the parent acceptance open until the manual smoke below is recorded.
- [ ] Remove the `TO_DO.md` pointer once the plan is archived.

## Acceptance criteria

- [ ] On a machine with network, a Light build downloads the pack from its own release URL, shows progress, installs, and lists the full clinical catalog without a restart or a second app download. A downloaded mesh is used for a calculation and appears in the Settings preview.
- [ ] Cancel during the body (including a blocked read) returns within about one second of the cancel, retry after an injected failure works, and offline failure leaves the user library byte-for-byte identical (tree hash before/after).
- [ ] A retry during a draining download, including after a page reload, shows the busy sentence and starts no second request or failure state.
- [ ] A truncated download, an oversized body, a tampered member, and a manifest-pin mismatch are rejected; no partial mesh becomes "Installed".
- [ ] Redirects to any host outside GitHub and its asset CDN are refused; a signed CDN query is preserved for the request and absent from logs; TLS verification cannot be disabled and the public API exposes no URL or insecure option.
- [ ] No request carries exam data, source filenames, user/machine identifiers, or app-added query parameters. Captured logs and user text contain no absolute path, URL, redirect query, proxy value, or spool path.
- [ ] No network activity occurs at import, startup, page render, upload, or calculation; only the button or the CLI flag initiates a request.
- [ ] A complete catalog hides both download and local-zip actions behind the catalog-complete caption. A non-`X.Y.Z` build shows the unavailable sentence and keeps the local zip.
- [ ] The draft release gains `guiskindose-phantom-pack-<version>.zip` and `.zip.sha256` before publication; the tag matches `^v[0-9]+\.[0-9]+\.[0-9]+$` and the pyproject version; prereleases are skipped; an existing different asset fails without clobbering; a public re-download with backoff passes `--verify`.
- [ ] The release notes name the in-app download, the manual zip, the offline fallback, and that the pack is optional data.
- [ ] Light and headless paths work; the download module imports without NiceGUI. A frozen Light build has a readable CA bundle and completes a download, proving `certifi` data was collected.
- [ ] `check_file_sizes`, `check_complexity`, `check_ui_copy`, `check_help_registry`, `check_feature_doc_matrix`, `sync_gui_help --check`, `check_licenses`, the privacy gates, and the test list above pass.
- [ ] Manual smoke on a Light zip from the matching release: download, cancel once, retry, install, restart, preview the mesh, calculate. Record it on the parent plan.

## Resolved decisions (2026-11-27)

Eight decisions from the review; none remains open for planning:

1. **`certifi` placement.** Promoted to core dependencies. CLI and GUI use the same CA bundle; TLS 1.2+, `CERT_REQUIRED`, and hostname checking stay mandatory.
2. **Per-stem downloads.** Whole pack only in Phase 3. The manifest pins each stem, so a later phase can add per-stem downloads without changing the trust model.
3. **Pack signing.** Deferred. The manifest pin and per-member hashes give integrity, not authenticity if the GitHub release itself is compromised; the help page and release notes say so. The `.zip.sha256` is not presented as a trust signal.
4. **Mirrors.** None. The local-zip install is the restricted-network path.
5. **Proxies.** Environment variables only; no in-app proxy field.
6. **Asset publication cadence.** One pack asset per `vX.Y.Z` release, even when meshes are unchanged. `RELEASES_AND_DISTRIBUTION.md` states this does not imply new meshes.
7. **Complete catalog.** Hide both the download and the local-zip actions behind one "catalog complete" caption. No split behavior.
8. **Release notes.** Name the in-app download, the manual `…zip` asset, the offline fallback, and that the pack is optional data.

## Deferred / open after implementation

- **Manual Light smoke** — download, cancel once, retry, install, restart, preview, calculate on a built Light zip. Record on the parent plan.
- **Frozen Light CA bundle proof** — `--self-check` field plus a real download from the signed/notarized macOS zip or the Windows Light zip. The source/unit path is proven; the frozen path is not.
- **Live release-workflow run** — the draft attach/verify dispatch and the published public re-download job have not been exercised on GitHub. No workflow was dispatched from this branch.
- **`--update-pin` helper** — the release checklist still edits `phantom_pack_pin.py` by hand; the optional automated writer was not added.
