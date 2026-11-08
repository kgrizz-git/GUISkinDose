# macOS release signing plan

_Status: implemented on branch; awaiting first green `workflow_dispatch` run id before the parent checkbox and archival. Parent item: the open Phase 1 checkbox in [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md)._

Public macOS zips are signed, notarized, and stapled with the Phase 0b recipe. Every nested Mach-O, including the bundled browser, is re-signed with our Developer ID Application certificate. Signing secrets live in the GitHub environment `macos-release` and are read only by the release signing job.

## What is already true

Phase 0b (2026-11-01, arm64, macOS 26) notarized a Light `GUISkinDose.app`. The recipe is committed.

| Piece | Where | What it does today |
|---|---|---|
| Freeze | `packaging/portable/guiskindose.spec` | On macOS, `BUNDLE` writes `GUISkinDose.app`. Bundle id `io.github.kgrizz-git.guiskindose`. `Info.plist` sets `NSAllowsLocalNetworking` true and `NSAllowsArbitraryLoads` false. Edition comes from `GUISKINDOSE_PORTABLE_EDITION`. |
| Sign, notarize, staple, zip | `packaging/portable/macos_sign_notarize.sh` | Inside-out Developer ID sign, hardened runtime, timestamp, no `--deep`. Then `ditto` zip, `notarytool submit --wait`, staple, `ditto` again, `spctl`. |
| Entitlements | `packaging/portable/macos_entitlements.plist` | Empty dictionary. The Light Developer ID build needed no extra key. |
| Ad-hoc CI | `.github/workflows/portable-spike.yml` | `macos-15` builds Light and Full arm64. Full copies Chromium to `Contents/Helpers/Chromium.app`, notices to `Contents/Resources/chromium/`, and re-signs with identity `-` and no hardened runtime. Header comment: no release signing or notarization. |
| PyPI release | `.github/workflows/release.yml` | `release: types: [published]`. Workflow and job both set `actions: read`. Checkout is `fetch-depth: 0`. The CI gate step sets `GH_TOKEN` and runs `gh run list`. No macOS runner and no signing secrets. |
| Full layout proof | [archive/PORTABLE_MAC_LINUX_CI_BUILDS_PLAN.md](archive/PORTABLE_MAC_LINUX_CI_BUILDS_PLAN.md) | Actions run [42339804464](https://github.com/kgrizz-git/GUISkinDose/actions/runs/42339804464). Frozen Full `--png-check` passed before and after the ad-hoc re-sign. Developer ID notarization of that layout is still open. |

Phase 0b measurements for Light: 210 Mach-O files, 23 s to sign, about 35 minutes (`2103 s`) in `notarytool submit --wait`, stapled zip 100.4 MB. `codesign --verify --deep --strict`, `xcrun stapler validate`, and `spctl -a -t exec -vv` (`accepted, source=Notarized Developer ID`) passed. A universal2 build is impractical. An x86_64 build needs an Intel runner.

The local proof froze Python 3.12. `portable-spike.yml` freezes Python 3.14. The first signed CI build is the Python 3.14 proof.

Upstream Chromium on the pinned disk image is already signed by `Developer ID Application: Qian Qian (B9A88FL5XJ)`, with flags `kill,restrict,library-validation,runtime` and a stapled ticket. Helper apps sit inside `Chromium.app` at `Contents/Frameworks/Chromium Framework.framework/.../Helpers/`. `ditto` of the whole `.app` carries them. That Team ID must not remain on the zip we publish. The release job re-signs those helpers with our identity.

`portable-macos-release.yml` wires `macos_sign_notarize.sh` for Developer ID release builds. The script signs inside-out with selective entitlements, `GUISKINDOSE_SIGN_ONLY` / `GUISKINDOSE_NOTARIZE_ONLY`, edition zip names, and a private notary work directory under `$RUNNER_TEMP`. `macos_ci_import_signing.sh` keeps notary material on step outputs until the notarize step. Chromium helper plist keys are captured at build time from upstream dumps. Ad-hoc spikes stay in `portable-spike.yml`.

## Workflow, job, and trigger

Add `.github/workflows/portable-macos-release.yml`. Leave `release.yml` on the PyPI path. Leave `portable-spike.yml` on ad-hoc builds.

One job, `sign-macos`, matrix `edition: [light, full]`, `fail-fast: false`, `runs-on: macos-15`, `timeout-minutes: 180`. Each edition is its own deployment so a Full failure still allows a finished Light asset to upload.

```yaml
on:
  release:
    types: [published]
  workflow_dispatch:
    inputs:
      attach_to_tag:
        description: Existing v* tag to receive assets. Empty keeps artifacts off the release.
        type: string
        default: ""
      macos_intel:
        description: Also sign Full on macos-15-intel
        type: boolean
        default: false
```

No `pull_request` and no `push`. A tag push is not a second trigger. `release.yml` already waits for `published`, and a draft release does not run it.

Job `permissions` are `contents: write` and `actions: read`. `contents: write` is what `gh release upload` needs. `actions: read` is what `gh run list` needs. A job `permissions` block sets every omitted scope to none, so `contents: write` alone cannot list workflow runs. Do not set `id-token`. Match `release.yml`: checkout uses `persist-credentials: false` and `fetch-depth: 0`. The spike checkout is shallow (default depth 1) and is the wrong pattern for the ancestor check. `git merge-base --is-ancestor` needs that full history. The repo is public, so the later `git fetch origin main` still works with `persist-credentials: false`, as `release.yml` already comments.

Before any secret is written to disk, repeat the `release.yml` gate in its own step with `GH_TOKEN: ${{ github.token }}`. The same env var is set again on the upload step. The gate checks that the commit is an ancestor of `origin/main` and that `ci.yml` has a successful run for that commit (`gh run list` on `ci.yml`). A dispatch uses the same check against `github.sha`.

When `attach_to_tag` is set, resolve that tag to a commit (`git rev-parse <tag>^{commit}`) and require it to equal `github.sha`, the commit that was checked out and frozen. Fail before upload when they differ. A dispatch from a newer `main` must not attach a zip onto an older tag. The retry dispatch ref is the `v*` tag itself. The environment already allows that tag.

`portable-spike.yml` stays `contents: read`, with no `environment:` and no signing secret names. Its `if: always()` artifact upload stays a spike behavior. The release job does not copy that condition.

## Environment protection

Every job that signs, including the Intel dispatch job, sets `environment: macos-release`. Secrets below are environment secrets. A job that omits the environment sees them as empty.

Observed on 2026-11-08 (names and policy only):

| Setting | Current value |
|---|---|
| Required reviewers | 1 |
| Deployment branches | custom: branch `main`, tag `v*` |
| Secret names | `DEVELOPER_ID_P12_BASE64`, `DEVELOPER_ID_P12_PASSWORD`, `NOTARY_KEY_P8`, `NOTARY_KEY_ID`, `NOTARY_ISSUER` |

There is no identity-string secret. The job asks the temporary keychain for identities and continues only when exactly one identity contains the prefix `Developer ID Application:`.

A published release runs as `refs/tags/<tag>`. The `v*` tag rule admits `v1.2.3`. A feature-branch dispatch is refused by the environment before steps run, so this branch cannot read the secrets. Do not add the implementation branch to the policy.

The reviewer approves each matrix job. Approval is what releases the secrets into the runner. Rejection or a timeout means the job never signs and never uploads.

## Secrets the job reads

Map environment secrets to the script's existing variables. The script already prefers all three `GUISKINDOSE_NOTARY_*` variables, refuses a partial set, and never prints the values, the key path, or the env-file contents.

| Environment secret | Job handling |
|---|---|
| `DEVELOPER_ID_P12_BASE64` | Decode to a mode-600 file under `$RUNNER_TEMP`. Delete after `security import`. |
| `DEVELOPER_ID_P12_PASSWORD` | Passed only as the `security import -P` value. |
| `NOTARY_KEY_P8` | Written to a mode-600 `.p8` file. `GUISKINDOSE_NOTARY_KEY` is that path. |
| `NOTARY_KEY_ID` | `GUISKINDOSE_NOTARY_KEY_ID` |
| `NOTARY_ISSUER` | `GUISKINDOSE_NOTARY_ISSUER` |

Write files from the environment with Python, `chmod 600`, and `set +x` on every step that can see a secret. Log `p12 decode failed` or `notary key file is not a private key PEM` with no payload. Treat `NOTARY_KEY_P8` as PEM text when it contains a `BEGIN` line, and as base64 of that PEM otherwise. Fail when the decoded bytes do not contain a private-key PEM. The maintainer confirms which form is stored so the first run is not a probe (see Open questions).

The `.p12` must hold the Developer ID Application private key and the Developer ID intermediate. The job cannot see that from the secret name. Confirm it before the first dispatch.

Do not create a `notarytool` keychain profile on the runner. API-key mode is the CI path the script already documents. Do not set `GUISKINDOSE_NOTARY_ENV`, `GUISKINDOSE_SKIP_NOTARIZE`, or `GUISKINDOSE_NOTARY_DRY_RUN` in this workflow.

## Keychain setup and teardown

The Phase 0b Mac already trusted the certificate in the login keychain, so no prompt appeared. A GitHub runner has an empty keychain. `codesign` returns `errSecInternalComponent` when the key needs a UI prompt. Import into a throwaway keychain and set the partition list.

In one step, after the CI gate:

1. `KEYCHAIN="$RUNNER_TEMP/guiskindose-signing.keychain-db"`.
2. Generate a keychain password with `openssl rand -base64 32`. Keep it in the step. Do not store it as a GitHub secret and do not print it.
3. `security create-keychain`, `set-keychain-settings -lut 21600` so it stays unlocked through a long job, and `unlock-keychain`.
4. Decode the `.p12`, `security import` into that keychain with `-T /usr/bin/codesign` and `-T /usr/bin/security`, then delete the `.p12`.
5. Save the current user search list, then run `security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "$KEYCHAIN_PASSWORD" "$KEYCHAIN"`. The `-k` password is required. Without it, `security` waits for a prompt the runner cannot answer.
6. Prepend the new keychain to the saved list: `security list-keychains -d user -s "$KEYCHAIN" <existing list>`. `list-keychains -s` replaces the list with whatever arguments it receives. Passing only the new keychain drops the login keychain. Then `security default-keychain -s "$KEYCHAIN"`.
7. `security find-identity -v -p codesigning`. Require exactly one `Developer ID Application:` identity. Export that full string as `GUISKINDOSE_SIGN_IDENTITY`.

Teardown is a final step with `if: always()`. `security delete-keychain` on that path, delete the `.p8`, and restore the search list saved in step 5. A failed or cancelled job still runs teardown. The runner is ephemeral. The delete and the restore are still required.

## Build, then sign

Match the spike toolchain: `actions/checkout`, `actions/setup-python`, and `astral-sh/setup-uv` at the SHAs already pinned in `portable-spike.yml`, Python 3.14, uv `0.11.25`, then `uv sync --locked --extra gui-native --group portable`. Pin any new action the same way `scripts/check_action_pins.py` already requires.

Freeze with `pyinstaller packaging/portable/guiskindose.spec`, `--distpath tmp/portable/dist`, and `GUISKINDOSE_PORTABLE_EDITION` set to the matrix edition. The app path is `tmp/portable/dist/GUISkinDose.app`.

Light stops there. Assert `Contents/Helpers/Chromium.app` is absent.

Full uses the spike pin: ungoogled-chromium `156.0.8078.79-1.1` arm64 disk image, sha256 `4ff3b084c49d2391aecdd3924ebd1bd7417fb1dd88e3da45891bee73f8e5c173`, URL already in `portable-spike.yml`. `packaging/portable/macos_bundle_chromium.sh` gains a switch the release job sets. With the switch, the script copies, checks the hash, clears extended attributes, verifies the upstream seal, and writes notices, then returns. That return is before `PNG_CHECK_LABEL=pre_resign` and before `adhoc_resign_app`. The pre-resign PNG launch stays in the spike, where the upstream signature is what the check is measuring. The release proof is the Developer ID `--png-check` below. The spike leaves the switch unset. Clearing attributes with `xattr -cr` stays a build step on the copy. It is not applied to a user download.

## Inside-out signing order

`macos_sign_notarize.sh` already walks in this order. Keep the walk. Change which invocations receive `--entitlements`. `--deep` stays off the sign command. `--verify --deep --strict` is a later check, not a way to sign.

Today `sign()` always passes `--entitlements`. That was harmless for the empty Light plist. It is the wrong place for a JIT key. Pass a plist only when signing a main executable: the outer app's main binary, `Chromium`'s main binary, and each helper `.app`'s main binary. Sign dylibs, `.so` files, and `.framework` bundles with `--force --timestamp --options runtime` and no `--entitlements`. Sealing a `.app` still uses the plist that belongs to that app, which `codesign` attaches to that app's main executable.

1. Every regular file under `Contents` whose `file` output contains `Mach-O`, skipping `_CodeSignature`. No entitlements on libraries. The main executable of a helper `.app` under `Contents/Helpers/Chromium.app`, and `Contents/MacOS/Chromium` inside that bundle, get the helper plist from the Entitlements section. The outer `Contents/MacOS/GUISkinDose` gets `GUISKINDOSE_ENTITLEMENTS` when set, otherwise the empty `macos_entitlements.plist`.
2. Each directory named `*.framework`, `*.app`, or `*.xpc`, with `find -depth`, so a helper `.app` is sealed before `Chromium Framework.framework`, that framework before `Chromium.app`, and `Chromium.app` before the outer app. Frameworks and `.xpc` bundles get no entitlements file. A helper `.app` is sealed with the helper plist. `Chromium.app` is sealed with that same helper plist only when its own main executable carries it. The outer app is sealed with the empty plist.
3. `GUISkinDose.app` itself, with the empty plist.

`find -depth` is what makes the Chromium helpers safe. Signing the outer app first would seal a bundle over unsigned children.

If `codesign --verify --deep --strict` reports an unsigned bundle whose suffix is not in that list, add that suffix to the find and fail the run until the new walk verifies. Do not switch the sign command to `--deep`.

Both editions use this walk. Full has more files because of Chromium. Light has no `Chromium.app`.

Add `GUISKINDOSE_SIGN_ONLY=1`. In that mode the script signs once, runs `codesign --verify --deep --strict`, and exits 0 without writing a zip and without calling `notarytool`. Add `GUISKINDOSE_NOTARIZE_ONLY=1`. In that mode the script skips the sign walk, requires the existing signature to verify, then notarizes, staples, and zips. The Full job signs once, runs `--png-check`, and on success calls notarize-only. It does not sign a second time on that path. A plist edit is a new run, not a second pass inside the green path. `GUISKINDOSE_SKIP_NOTARIZE` stays unused here because it writes an unstapled zip.

`GUISKINDOSE_ENTITLEMENTS`, when set, replaces `macos_entitlements.plist` for the outer app and for non-Chromium main executables. Unset, the script keeps the empty file. The Chromium helper plist is a separate variable, `GUISKINDOSE_CHROMIUM_HELPER_ENTITLEMENTS`, so the override cannot put JIT keys on Python.

Add `GUISKINDOSE_ZIP_NAME` so the stapled archive is `GUISkinDose-<edition>-macos-arm64.zip` (Intel: `GUISkinDose-<edition>-macos-x64.zip`). The script's current `uname -m` name would collide across editions.

## Entitlements

The outer app and the Python framework stay on the empty `macos_entitlements.plist` until a signed Light or outer-app crash names a key. That is the Phase 0b Light result. A shared Team ID satisfies library validation, so `disable-library-validation` is not added. The ad-hoc spike needed that key only because identity `-` has no Team ID. Hardened runtime is `--options runtime` on every `codesign`. It is not an entitlement key. `Info.plist` ATS already allows local networking. Phase 0b Light reached `127.0.0.1` through WebKit without `com.apple.security.network.client`. Leave that key off unless a signed build fails to open the local page.

If that crash happens, add the named key on the main executable that crashed, through `GUISKINDOSE_ENTITLEMENTS`, and record it in [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md). Do not spread it onto dylibs or the Chromium helper plist.

Chromium helpers are the exception. Hardened runtime refuses the writable executable memory V8 uses unless the helper's main executable carries `com.apple.security.cs.allow-jit` or `com.apple.security.cs.allow-unsigned-executable-memory`. The repo does not record which of those keys the pinned `156.0.8078.79-1.1` helpers already have. Before re-signing, on each helper `.app` main executable under `Contents/Helpers/Chromium.app` (Renderer, GPU, and the other `Chromium Helper*.app` bundles) and on `Chromium.app/Contents/MacOS/Chromium`, run `codesign -d --entitlements -` and log the key names only.

Build one helper plist from that dump:

- Keep `com.apple.security.cs.allow-jit` when any of those main executables has it.
- Keep `com.apple.security.cs.allow-unsigned-executable-memory` only when the dump already has it.
- If the dump has neither JIT key, still put `allow-jit` in the helper plist. An empty hardened-runtime signature on the Renderer is the case this step exists to avoid.
- Drop every other upstream key, including camera, microphone, location, Apple Events, `get-task-allow`, and `disable-library-validation`.

The script applies that plist only to those helper main executables and to the `.app` seal for `Chromium.app` and its nested helper apps. Libraries inside the framework stay without entitlements. `GUISKINDOSE_CHROMIUM_HELPER_ENTITLEMENTS` points at the file. The outer app and Python do not use it.

`--png-check` after this Developer ID sign, and before `notarytool submit`, is the proof the helpers still launch. Notarization does not execute the browser. Submit only after that check passes. If it fails, stop the job and record the key names. Do not add `disable-library-validation` in that same run. If the maintainer later accepts that Full cannot ship offline PNG, record the drop in the parent plan. The helper plist does not change on the success path before notarize-only.

After signing, `codesign -d --entitlements -` on the outer app's main executable must not contain `get-task-allow` or a JIT key. The same dump on a helper main executable must show the helper plist and the same Team ID as the outer app.

## Notarize, staple, zip, checksum

After the post-sign checks, run the rest of `macos_sign_notarize.sh`:

1. Private work directory (`mktemp -d`, mode 700) under `$RUNNER_TEMP` when that variable is set, which it is on the runner. The script today creates it inside the output directory (`$OUT/.notary-work.*`). Change that. A local run with `RUNNER_TEMP` unset uses a private `mktemp -d` outside the directory that will be uploaded. The release job's upload directory is `out/`. The work directory is never that path.
2. `ditto -c -k --keepParent` of the `.app` to a submit zip. `notarytool` accepts a zip. A zip cannot be stapled.
3. `xcrun notarytool submit <zip> --key <p8> --key-id <id> --issuer <issuer> --wait --timeout 45m --output-format plist`. Add the timeout flag to the script. The Phase 0b wait was 35 minutes. A stuck queue then fails the job inside the 180 minute job limit.
4. Read `:status` with `PlistBuddy`. Continue only when it is `Accepted`.
5. On any other status, fetch `notarytool log` into the private directory and print the script's bundle-relative issue lines (severity, path under the `.app`, message). Exit 1. Do not staple.
6. `xcrun stapler staple` the `.app`, then `xcrun stapler validate`.
7. `ditto -c -k --keepParent` the stapled app to `GUISkinDose-<edition>-macos-arm64.zip`. This second zip is the download. The submit zip is discarded.
8. `spctl -a -t exec -vv` on the stapled app.

The notary plist and log can carry account identifiers. They stay in the private work directory under `$RUNNER_TEMP`. On success the script removes that directory. On failure it prints the directory's basename. The job then copies only the stapled zip and its `.sha256` into `out/`. The submit zip, the log JSON, and the work directory stay out of `out/`.

Checksum the stapled zip with `shasum -a 256` before that copy. Write `GUISkinDose-<edition>-macos-arm64.zip.sha256` in the `shasum -c` form (digest, two spaces, file name). SHA-256 is the only digest.

## Verification

Run these on the stapled `.app` and again on the app expanded from the stapled zip with `ditto -x -k`. The expanded tree is what a user gets.

| Check | Pass condition |
|---|---|
| `codesign --verify --deep --strict --verbose=2` | Exit 0 on the outer app. |
| `codesign -dv --verbose=4` | Authority begins with `Developer ID Application:`, flags include `runtime`, a timestamp is present, and the Team ID matches the single imported identity. |
| Entitlements dump | No `get-task-allow`. |
| `xcrun stapler validate` | Ticket stapled. |
| `spctl -a -t exec -vv` | `accepted` and `source=Notarized Developer ID`. |
| `syspolicy_check distribution` | Exit 0 when the tool exists on the runner. Phase 0b passed this locally. |
| Full helpers | `find` every `*.app` under `Contents/Helpers/Chromium.app`. Each helper executable is Mach-O, `codesign --verify --strict` passes, and `codesign -dv` shows the same Team ID as the outer app. The upstream team `B9A88FL5XJ` is absent. |
| Quarantine round-trip | Copy the zip, set a `com.apple.quarantine` attribute, expand with `ditto -x -k`, repeat `spctl` and `stapler validate`. Phase 0b did this on the build Mac. |
| Full `--png-check` | After Developer ID sign and before submit, and again from the expanded stapled zip. `launched_outside_onedir` is 0. The browser path is `Helpers/Chromium.app/Contents/MacOS/Chromium`. |
| Light | No `Chromium.app`. Frozen `--self-check` from the expanded zip passes, with `git` removed from `PATH` the way the spike does. |

A real browser download on a Mac that did not build the app is a maintainer smoke. The quarantine attribute on the runner has no Launch Services download record. Phase 0b saw the prompt name the source as `null` for that reason. The CI `spctl` result still gates the upload.

If `spctl` on the hosted runner reports a syspolicy failure that `stapler validate` and the notary status both contradict, stop. Record the exact status line in the job summary. Do not drop `spctl` from the workflow in that same change. Ask the maintainer before treating it as a runner limit.

## Upload and failure behavior

The files that may leave the job are the stapled zip and its `.sha256`. Copy them into `out/` only after every check above has passed.

| Destination | When |
|---|---|
| `actions/upload-artifact` of `out/`, retention 14 days, `if-no-files-found: error` | `if: success()` |
| `gh release upload <tag> <zip> <sha> --clobber` | `if: success()`, and either the event is `release`, or `attach_to_tag` is a `v*` tag whose commit equals `github.sha` |

`github.ref_name` is the tag on a published release. A dispatch with an empty `attach_to_tag` uploads the Actions artifact only. The job does not create a GitHub Release. `--clobber` replaces an asset from a previous green retry of the same name. The commit equality check runs even when the tag exists. A mismatch fails the job with no upload.

Fail closed means an unsigned, unstapled, or unverified zip is never uploaded and never attached. Concretely:

- The upload steps use `if: success()`. They do not use `if: always()`.
- `GUISKINDOSE_SKIP_NOTARIZE` is unset, so the script cannot exit 0 with an unstapled zip.
- Notary status other than `Accepted` exits 1 before staple and before the release zip.
- `spctl`, `stapler validate`, or `codesign --verify` failing exits 1.
- The private notary directory is not an artifact path.
- Keychain teardown runs even when the job failed. It does not upload anything.

`release.yml` does not wait on this workflow. A signing failure leaves the PyPI publish and the GitHub Release in place, with no macOS zip attached. Release notes must not claim a macOS download until the asset is on the release. That split is deliberate: the PyPI job keeps `contents: read` and never sees these secrets.

The job summary lists edition, arch, zip size, sha256, notary status, verify, `spctl` source, stapler, and Full PNG counts. Relative names and numbers only.

## arm64 and x86_64

The published-release matrix is arm64 Light and arm64 Full on `macos-15`. PyInstaller does not cross-compile. Phase 0b ruled out universal2.

Intel is a separate job, `runs-on: macos-15-intel`, `if: github.event_name == 'workflow_dispatch' && inputs.macos_intel`. It sets `environment: macos-release`, `contents: read` and `actions: read` permissions (it never uploads to a release), `fetch-depth: 0`, and the same `GH_TOKEN` gate. Without the environment the job cannot read the certificate or the notary key. It signs Full with the spike's x86_64 pin (sha256 `152f0d67ab9301a2e6fa4d38b25e1382c0c74c72772d533ce7c4390e599a1db4`) and the same helper-plist rule, dumping the x86_64 artifact's own entitlements rather than reusing the arm64 key list unread. It does not run on `release: published`. Light Intel can follow the same way. The open Intel spike in the parent plan stays open until that dispatch is green. It is not a gate for the arm64 assets.

## Local versus CI

| Can run on a maintainer Mac | Needs the GitHub environment |
|---|---|
| `GUISKINDOSE_NOTARY_DRY_RUN=1` (redacted auth mode, no submit) | `.p12` import into a temporary keychain and the partition list |
| `GUISKINDOSE_SIGN_ONLY=1` against a local freeze, using the login keychain | Environment reviewer, `main` / `v*` gate |
| A full local notarize of Light, which Phase 0b already did on Python 3.12 | Python 3.14 freeze on `macos-15`, then notarize |
| Reading this plan and the script | `gh release upload` and the Actions artifact |
| | The first Developer ID Full `--png-check` |

A local green notarize does not replace the CI keychain path. The first `workflow_dispatch` from `main`, with `attach_to_tag` empty, is the rehearsal. Attach on a published `v*` release after that rehearsal is green.

## Tests and harness

Add `tests/unittests/test_portable_macos_release_workflow.py`. It loads the workflow YAML on any OS and asserts:

- Triggers are `release` published and `workflow_dispatch` only.
- `sign-macos` and the Intel job both set `environment: macos-release`.
- The arm64 job sets `contents: write` and `actions: read`. The Intel job sets `contents: read` and `actions: read`. Checkout sets `fetch-depth: 0`.
- The CI gate step and the upload step both set `GH_TOKEN`.
- The secret names in the file are only `DEVELOPER_ID_P12_BASE64`, `DEVELOPER_ID_P12_PASSWORD`, `NOTARY_KEY_P8`, `NOTARY_KEY_ID`, and `NOTARY_ISSUER`.
- `GUISKINDOSE_SKIP_NOTARIZE` does not appear.
- Upload steps are `if: success()`.
- The attach step's script compares the tag commit to `github.sha`.
- `portable-spike.yml` has no `environment:` and none of those secret names.
- `release.yml` does not mention `macos-release` or those secrets.
- The stapled zip name includes the edition and `macos-arm64`.

ShellCheck already lints `packaging/portable/*.sh` through pre-commit. Keep the new shell under that hook. `scripts/check_action_pins.py` covers the new workflow without a new linter. Do not add actionlint for this plan.

No unit test calls `notarytool`, `codesign`, or Apple. The macOS proof is the workflow run.

If the bundle script gains a skip-ad-hoc switch, a small test can assert the spike YAML does not set it and the release YAML does. Keep that assertion in the same YAML test.

New Python stays within the complexity gate. New shell stays a thin sequence of steps the script already owns.

## Docs to update in the implementation PR

| Doc | Change |
|---|---|
| [PORTABLE_APP_PLAN.md](PORTABLE_APP_PLAN.md) | Tick the Phase 1 signing checkbox only after a green release or rehearsal run id exists. Record Full entitlements, or the decision to drop offline PNG. Replace the Phase 0b sentence that says there is no macOS CI job. Ad-hoc CI already exists. This plan is the Developer ID job. |
| [RELEASES_AND_DISTRIBUTION.md](../RELEASES_AND_DISTRIBUTION.md) | Say the published macOS downloads are the stapled zips from this workflow. Spike artifacts are ad-hoc and expire. |
| [MAINTENANCE_LOG.md](../MAINTENANCE_LOG.md) | Record the workflow, the keychain lifetime, and the run id. |
| `CHANGELOG.md` | When the first release actually attaches the zips, one user-facing note: macOS downloads are notarized, Light has no PNG dose map, the app is not FDA-cleared. |
| [TO_DO.md](../TO_DO.md) | Drop the "macOS release signing" clause from the portable item in that same PR. |
| This file and [index.md](../index.md) | Point the status at the run id. Archive this plan when the parent checkbox is ticked. |

Release notes name the zip files, the edition, and the architecture. They state that Light has no PNG dose map and that the app is not FDA-cleared. That copy is the parent plan's smoke bullet. This job does not write the notes by itself.

## Acceptance

- A published `v*` release, or a `main` dispatch with a green CI ancestor, produces arm64 Light and arm64 Full zips.
- Each zip's app passes `codesign --verify --deep --strict`, `stapler validate`, and `spctl` with `Notarized Developer ID` on the runner and on the `ditto` expansion.
- Full's Chromium and its helper apps share our Team ID. The upstream team is gone. `--png-check` from the stapled expansion passes, or the parent plan records that offline PNG is dropped and Full macOS is not published with that claim.
- Light's stapled expansion passes `--self-check` and contains no `Chromium.app`.
- Each release asset has a SHA-256 sidecar. No upload step ran on a failed sign, notary, staple, or verify.
- `portable-spike.yml` and `release.yml` still have no signing secrets.
- The YAML test and ShellCheck pass.
- The maintainer downloads one stapled zip through a browser on a Mac that did not build it, opens it, and sees the normal downloaded-from-the-internet confirmation rather than a Gatekeeper block. Network-off calculate and HTML export stay the parent plan's manual smoke. Full PNG offline on that download is the parent Phase 0b checkbox.

## Out of scope

- Windows Authenticode (parent plan Phase 5).
- Changing the ad-hoc spike into a notarized build.
- Briefcase. Phase 0b kept PyInstaller.
- Intel on the published release matrix, until the dispatch leg has passed once.
- A second notary account, an Apple ID plus app-specific password, or a keychain profile on the runner.
- Blocking the PyPI job on this workflow.

## Implementation checklist

- [x] Add `GUISKINDOSE_SIGN_ONLY`, `GUISKINDOSE_NOTARIZE_ONLY`, `GUISKINDOSE_ZIP_NAME`, `GUISKINDOSE_ENTITLEMENTS`, `GUISKINDOSE_CHROMIUM_HELPER_ENTITLEMENTS`, and `notarytool --timeout` to `macos_sign_notarize.sh`. Keep the auth order and the inside-out walk. Pass entitlements only to main executables and `.app` seals. Put the notary work directory under `$RUNNER_TEMP`.
- [x] Add a skip-ad-hoc switch to `macos_bundle_chromium.sh` that returns before the pre-resign `--png-check` and before `adhoc_resign_app`. The spike leaves it unset.
- [x] Add `portable-macos-release.yml` with the environment on both jobs, `actions: read`, `fetch-depth: 0`, `GH_TOKEN` on the gate, the keychain prepend and `if: always()` restore, the tag-commit check, and `if: success()` uploads of the zip and sha256 only.
- [x] Add the YAML unit test.
- [ ] Rehearse with `workflow_dispatch` from `main` and an empty `attach_to_tag`.
- [ ] After that run is green, publish a `v*` release (or set `attach_to_tag` on a later dispatch) and confirm the assets.
- [ ] Update the docs in the table above. Tick the parent checkbox only with a run id.

## Decisions

Recorded from the maintainer after the first review:

- The `macos-release` environment stays at one required reviewer, branch `main`, and tags `v*`. The implementation branch is not added.
- A signing failure leaves the GitHub Release and the PyPI publish up. The macOS zip is absent until a green run attaches it.
- `workflow_dispatch` may re-attach to an existing `v*` tag. The built commit must equal that tag's commit.
- The published release signs arm64 Light and arm64 Full only. Intel Full stays dispatch-only.
- The outer app and Python stay on the empty plist until a crash names a key. Chromium helper main executables get the helper plist in the Entitlements section. `disable-library-validation` is not added ahead of a crash.

## Open questions for the maintainer

1. Is `NOTARY_KEY_P8` the `.p8` PEM text, or base64 of that file? The job can detect either, and the first run should not be the test.
2. Does `DEVELOPER_ID_P12_BASE64` decode to a Developer ID Application identity, with the private key and the Developer ID intermediate, and no second codesign identity?
