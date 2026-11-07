# Windows code signing and distribution options

Research note for Phase 5 of [../plans/PORTABLE_APP_PLAN.md](../plans/PORTABLE_APP_PLAN.md). Prices and rules change, so re-check each source before acting.

All sources accessed 2026-11-07. "UNVERIFIED" marks claims not confirmed on a primary source.

## Comparison

| Option | Cost | Eligibility | Name on cert | CI fit | SmartScreen effect |
|---|---|---|---|---|---|
| SignPath Foundation (free OSS) | Free | OSI license, no proprietary code, already released, MFA, defined roles, verifiable CI builds, code-signing policy page | "SignPath Foundation" (project only in file product metadata) | Excellent: official GitHub Action, GitHub-hosted runners required, origin verification | Reputation builds over time; shared Foundation cert may carry existing reputation (UNVERIFIED) |
| Microsoft Artifact Signing (ex-Trusted Signing) | $9.99/mo Basic (5,000 sigs) | Paid Azure subscription; individuals in US or Canada only | Your validated legal name (CN/O), plus city/state/country | Excellent: GitHub Actions, SignTool, PowerShell, SDK; no hardware | No instant reputation; accumulates |
| Microsoft Store, MSIX | Free individual registration | Gov ID + selfie verification | Microsoft re-signs | Manual/Partner Center upload (API possible) | No warnings for Store installs |
| Microsoft Store, EXE/MSI | Free registration, but you must sign | As above | Your cert | Needs your own signing anyway | Store listing does not re-sign; downloaded installer still subject to normal reputation (inferred) |
| Certum Open Source Code Signing | From EUR 69 (set w/ card+reader) | Individual OSS developers | "Open Source Developer, <your name>" | Poor: physical smart card; no cloud option on that page | No instant reputation |
| SSL.com OV/IV + eSigner | eSigner Tier 1 $20/mo (20 signings); cert price extra (UNVERIFIED, ~$129+/yr) | Individual (IV) or org (OV) | Your name | Good: cloud HSM, CodeSignTool GitHub Action | No instant reputation |
| DigiCert OV + KeyLocker | ~$380-445/yr OV (reseller sources, UNVERIFIED); KeyLocker cost not found | Org or individual | Your name | Good (cloud HSM) | No instant reputation |
| Sectigo OV | ~$220-226/yr via resellers (UNVERIFIED) | Org or individual | Your name | Token/HSM required since 2023; cloud via reseller add-ons | No instant reputation |
| EV certs (any CA) | ~$290-685/yr (UNVERIFIED) | Organizations | Org name | As OV | EV no longer bypasses SmartScreen |

## Per-option notes

### 1. SignPath Foundation
- Rules: no malware/PUP; all components OSI-licensed, no commercial dual-licensing; no proprietary code; actively maintained; already released in the signed form; functionality documented on download page. Foundation-cert extras: sign only your own binaries; no hacking tools; privacy disclosure; uninstall instructions; MFA for SignPath and repo for all members; Authors/Reviewers/Approvers roles; binaries built from source verifiably; manual approval per release; product name/version metadata must match. Source: https://signpath.org/terms (2026-11-07).
- Home page must have a "Code signing policy" section stating free signing by SignPath.io, cert by SignPath Foundation, team roles, and a privacy statement. Source: same.
- Cert is issued to SignPath Foundation, so users see "SignPath Foundation" as publisher. Source: same.
- GitHub: `signpath/github-action-submit-signing-request@v3`; upload with `actions/upload-artifact` and pass the artifact id; OSS projects must run all jobs on GitHub-hosted runners; origin verified via GitHub. Source: https://docs.signpath.io/trusted-build-systems/github (2026-11-07).
- Application: via https://signpath.org/apply (form). Steps and turnaround not stated on the pages fetched. UNVERIFIED (community reports suggest weeks).
- Fit caveat: a PyInstaller onedir bundles third-party DLLs/pyds; the rules allow upstream libraries to ship unsigned, but sign only your own EXE. Bundled Python packages must be OSI-licensed; verify the full dependency tree.

### 2. SignPath.io paid tiers
- Pricing page (https://about.signpath.io/pricing) failed to load (HTTP parse error). UNVERIFIED. Not needed if the free OSS tier is accepted.

### 3. Microsoft Artifact Signing
- Renamed from Trusted Signing. Basic $9.99/mo, 5,000 signatures; overage $0.005 (overage from search snippet of Microsoft regional pages, UNVERIFIED on primary page; the pricing page rendered "$-"). $9.99 start confirmed: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation (2026-11-07).
- Individuals must be in the US or Canada; billing account type must be Individual; legal name and address must match gov ID; validation via Microsoft Verified ID / AU10TIX selfie. City, state, country appear on the cert. Source: https://learn.microsoft.com/en-us/azure/artifact-signing/quickstart (2026-11-07).
- No free/trial/sponsored subscriptions; no custom CN; no EV; billing not pro-rated. Source: https://learn.microsoft.com/en-us/azure/artifact-signing/faq (2026-11-07).
- Integrations: SignTool, PowerShell, GitHub Actions, SDK. Source: FAQ above. The exact action repository name was not confirmed (commonly `azure/trusted-signing-action`, UNVERIFIED for 2026 name).
- SmartScreen: reputation builds over time; no instant reputation. Source: FAQ and smartscreen page above.

### 4. Microsoft Store
- Individual registration is free (the $19 fee is waived) via https://storedeveloper.microsoft.com, with gov ID + selfie. Source: https://learn.microsoft.com/en-us/windows/apps/publish/whats-new-individual-developer (2026-11-07).
- MSIX gets free Microsoft signing and CDN hosting. EXE/MSI are accepted but must be signed with a cert chaining to the Microsoft Trusted Root Program, hosted on your own versioned HTTPS URL, silent install, offline installer. A zip is not accepted. Source: https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msi/app-package-requirements (2026-11-07).
- Store-installed apps are re-signed by Microsoft and never get SmartScreen warnings. Source: smartscreen page above. Free (unpaid) apps are allowed; specific policy text for free apps not separately fetched (UNVERIFIED beyond general policy).
- Fit: the PyInstaller onedir would need to be wrapped in MSIX (e.g. MSIX Packaging Tool or makeappx) to get free signing.

### 5. Other CAs
- Certum Open Source: from EUR 69, card + reader set, issued to a natural person with "Open Source Developer" prefix. Cloud (SimplySign) option not shown on that page (UNVERIFIED). Source: https://shop.certum.eu/open-source-code-signing.html (2026-11-07). A physical card does not fit GitHub-hosted runners.
- SSL.com eSigner: Tier 1 $20/mo for 1 credential and 20 signings; Tier 2 $85/mo 100 signings. Cert price not on that page. Source: https://ssl.com/guide/esigner-pricing-for-code-signing/ (2026-11-07).
- DigiCert, Sectigo: only reseller/affiliate prices found. UNVERIFIED.
- OV vs EV: "EV certificates no longer bypass SmartScreen." Signed OV/EV files show the publisher name but are still "unrecognized" until reputation accumulates. Source: https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation (2026-11-07).
- Since June 2023 OV keys must sit on FIPS hardware or a cloud HSM (via SSL.com search snippet, UNVERIFIED on CA/B Forum doc).

### 6. winget
- The submission docs list no signing requirement. Requirements: valid manifest, virus-free, silent install, HTTPS installer URL direct from publisher, Defender and multi-AV scans. Source: https://learn.microsoft.com/en-us/windows/package-manager/package/repository (2026-11-07).
- Manifest fields and SmartScreen behaviour are under [winget in detail](#winget-in-detail) below.

## Recommendation
1. Apply to SignPath Foundation now. It is free, CI-native, and fits an OSI-licensed, GitHub-Actions-built project. Add the code-signing policy section to the README/docs and set up MFA and roles. The downside is the publisher reads "SignPath Foundation."
2. If SignPath declines or is slow, use Artifact Signing at $9.99/mo. The maintainer qualifies as a US individual. The cert shows the maintainer's legal name and city/state.
3. Treat the Microsoft Store (MSIX) as the only route that removes SmartScreen warnings outright. Consider it later if MSIX packaging of the onedir proves practical.
4. Skip EV, Certum hardware, and full-price CA certs. They cost more and give no SmartScreen advantage.
5. Add winget after signing; it does not require signing but signed binaries reduce AV false positives.

Caveat: no option except the Store gives instant SmartScreen reputation; expect warnings for early releases.

## winget in detail

### Mark of the Web and SmartScreen

Short answer: mostly yes for the community `winget` source, with caveats. winget re-marks a hash-verified installer from a trusted source as Trusted zone, so the usual MOTW SmartScreen prompt should not fire. The behaviour for files extracted from a zip, and for Smart App Control, is UNVERIFIED.

- winget always writes an initial MOTW of `URLZONE_INTERNET` when it downloads an installer. Source: https://github.com/microsoft/winget-cli/blob/master/src/AppInstallerCLICore/Workflows/DownloadFlow.cpp (comment near `ApplyMotwIfApplicable`, about line 602).
- When the hash matches and the source has `TrustLevel::Trusted`, winget rewrites the MOTW to `URLZONE_TRUSTED`. The code comment says "We know the installer already went through multiple scans and we can trust it." Source: same file, about lines 589-609.
- When the hash matches but the source is not trusted, winget calls `IAttachmentExecute`, which runs anti-virus and attachment policy before it sets the MOTW. A failure there aborts the install with `APPINSTALLER_CLI_ERROR_INSTALLER_SECURITY_CHECK_FAILED`. Source: same file, about lines 611-636.
- The default `winget` and `msstore` sources get this MOTW downgrade. Private REST sources do not, unless they are added as trusted. Sources: https://github.com/microsoft/winget-cli/issues/4176 and https://github.com/microsoft/winget-cli/issues/3111 (a maintainer notes `winget source add --trust-level trusted`).
- The issue reporter states that "winget now skips SmartScreen for default sources." Source: https://github.com/microsoft/winget-cli/issues/3111.
- For MSIX installers, a trusted source also sets `SkipReputationCheck` on deployment. Source: https://github.com/microsoft/winget-cli/blob/master/src/AppInstallerCLICore/Workflows/InstallFlow.cpp.
- A full SmartScreen URL-reputation integration in the client is still an open feature request. Source: https://github.com/microsoft/winget-cli/issues/4902.
- A community commenter reports that MOTW prompts appear only on a ShellExecute launch, not on a direct CreateProcess launch. Source: https://github.com/microsoft/winget-cli/issues/4176 (comment by jantari). UNVERIFIED as official behaviour.
- Zip archives are extracted with the Shell API by default, or with `tar.exe` when `archiveExtractionMethod` is `Tar`. Source: https://github.com/microsoft/winget-cli/blob/master/doc/Settings.md and https://github.com/microsoft/winget-cli/blob/master/src/AppInstallerCLICore/Workflows/ArchiveFlow.cpp.
- Whether extracted files inherit the zip's MOTW, and therefore whether a portable EXE carries Trusted or Internet zone, is UNVERIFIED. Inference: with the Trusted-zone zip from the community source, any propagated mark would be Trusted, so a prompt is unlikely.
- winget runs an extra archive malware scan only for archives installed from a local manifest. `--ignore-local-archive-malware-scan` overrides it. Source: ArchiveFlow.cpp `ScanArchiveFromLocalManifest`, and https://learn.microsoft.com/en-us/windows/package-manager/winget/install.
- No winget user setting turns SmartScreen or Defender scanning on or off for community packages. Source: https://github.com/microsoft/winget-cli/blob/master/doc/Settings.md (no such setting listed).
- Whether Smart App Control evaluates a winget-installed unsigned EXE at first launch is UNVERIFIED. Inference: Smart App Control checks code reputation and signatures and does not depend on MOTW, so an unsigned, low-reputation EXE may still be blocked on a machine that has it enabled.

### Submitting a portable zip

- The newest manifest schema directory is `v1.28.0`. Earlier ones include `v1.12.0` and `v1.10.0`. Source: https://github.com/microsoft/winget-cli/tree/master/schemas/JSON/manifests.
- A zip-plus-portable installer uses `InstallerType: zip`, `NestedInstallerType: portable`, and `NestedInstallerFiles` entries with `RelativeFilePath` and an optional `PortableCommandAlias`. Source: https://github.com/microsoft/winget-cli/issues/6230 and https://learn.microsoft.com/en-us/windows/package-manager/package/manifest.
- Each installer node, for example x64 and arm64, needs its own `NestedInstallerFiles` list. Source: https://github.com/microsoft/winget-create/issues/660.
- winget rejects a `RelativeFilePath` that escapes the extract folder. Source: ArchiveFlow.cpp `VerifyAndSetNestedInstaller`.
- User-scope portable apps install under `%LOCALAPPDATA%/Microsoft/WinGet/Packages/` by default. Machine scope uses `%PROGRAMFILES%/WinGet/Packages/`. Source: https://github.com/microsoft/winget-cli/blob/master/doc/Settings.md.
- Validation is automated, and a moderator also reviews manually. Microsoft "reserves the right to refuse a submission for any reason." Source: https://learn.microsoft.com/en-us/windows/package-manager/package/repository.
- The pipeline runs a URL reputation test (`URL-Validation-Error`), a multi-antivirus Installers Scan (`Binary-Validation-Error`), and a Defender full scan after dynamic install (`Validation-Defender-Error`). Source: same page.
- The installer URL must be HTTPS and come directly from the publisher's release location, without a redirector. GitHub Releases URLs are the common case. Source: same page (`Validation-HTTP-Error`, `Validation-Indirect-URL`, `Validation-Domain`).
- The app must install and uninstall silently and cleanly for admins and non-admins. Source: same page.
- Code signing is not listed as a requirement. Source: same page and https://learn.microsoft.com/en-us/windows/package-manager/package/windows-package-manager-policies. Whether an unsigned PyInstaller binary has a higher chance of failing validation is UNVERIFIED. Inference: PyInstaller bootloaders are a known source of antivirus false positives, which would show up as `Binary-Validation-Error` or `Validation-Defender-Error`.
- `wingetcreate` is Microsoft's manifest creator CLI. It can create, update, and submit manifests. Source: https://github.com/microsoft/winget-create.
- The `vedantmgoyal9/winget-releaser` GitHub Action opens winget-pkgs PRs on each release and is not archived. Source: https://github.com/vedantmgoyal9/winget-releaser. It needs a classic PAT and a fork of winget-pkgs (UNVERIFIED detail; check its README).
- Local testing uses `winget validate` and `Tools/SandboxTest.ps1`. Source: https://learn.microsoft.com/en-us/windows/package-manager/package/repository.

## MSIX packaging of the PyInstaller onedir

- A full-trust desktop app declares `uap10:RuntimeBehavior="packagedClassicApp"` or `"win32App"` and `uap10:TrustLevel="mediumIL"`. The older equivalent is `EntryPoint="Windows.FullTrustApplication"` with the `rescap:Capability Name="runFullTrust"`. Source: https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes and https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/how-to-create-a-package-manifest-manually.
- The manifest needs `Identity` (Name, Publisher, Version, ProcessorArchitecture), `Properties` (DisplayName, PublisherDisplayName, Logo), `TargetDeviceFamily Name="Windows.Desktop"` with MinVersion and MaxVersionTested, and `uap:VisualElements` with Square150x150Logo and Square44x44Logo. Source: https://learn.microsoft.com/en-us/uwp/schemas/appxpackage/how-to-create-a-package-manifest-manually.
- The `Identity/@Publisher` string must exactly match the subject of the signing certificate. Source: https://learn.microsoft.com/en-us/windows/win32/appxpkg/how-to-sign-a-package-using-signtool.
- For Windows 10/11 Store packages, the fourth version field must be 0. Source: https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/app-package-requirements.
- The build is `makeappx pack /d <dir> /p app.msix` and then `signtool sign /fd SHA256 /f cert.pfx app.msix`. Source: https://learn.microsoft.com/en-us/windows/msix/package/create-app-package-with-makeappx-tool and the signtool page above.
- The GitHub `windows-2025` image ships Windows SDK 10.0.26100.0, which contains makeappx and signtool. Source: https://github.com/actions/runner-images/blob/main/images/windows/Windows2025-Readme.md.
- Package files install to the `WindowsApps` folder under Program Files and are read-only. Windows blocks launch if they are tampered with. Writes inside the package are not allowed. Source: https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes.
- On Windows 10 1903 and later, new files and folders created under `AppData\Local`, `Local\Microsoft`, `Roaming`, and `Roaming\Microsoft` are redirected to a private per-user, per-package location. Existing files at the real path are opened and modified in place. Source: same page.
- The private location is `%LOCALAPPDATA%\Packages\<PackageFamilyName>\LocalCache\...`. Source: https://www.powershellgallery.com/packages/msix/0.75.0/Content/MSIX.AppData.ps1 (community module). UNVERIFIED on Microsoft Learn in this pass.
- Redirection applies only to virtualized apps. Writes to HKCU are copied-on-write to a private hive. Redirected data is deleted on uninstall. Source: https://learn.microsoft.com/en-us/windows/msix/desktop/desktop-to-uwp-behind-the-scenes.
- Whether a bundled Chromium child process shares the package's virtualization is UNVERIFIED. Inference: child processes started by a packaged app normally inherit package identity, so they see the same redirection. Community reports show that processes outside the package do not see the virtual path. Source: https://github.com/anthropics/claude-code/issues/47977.
- Sideloading outside the Store requires a package signed by a certificate the machine trusts. Users install through App Installer or `Add-AppxPackage`. Source: https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/app-package-requirements and https://learn.microsoft.com/en-us/windows/msix/app-installer/app-installer-root.
- The Microsoft Store re-signs MSIX/AppX packages with a Microsoft certificate after certification, so no CA certificate is needed for Store submission. The Store does not re-sign MSI or EXE installers. Source: https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/app-package-requirements.
- Known PyInstaller gotchas: a onedir loaded through a symlinked or redirected path can fail to load the Python DLL. Source: https://github.com/pyinstaller/pyinstaller/issues/8300. Code that writes next to the executable, such as caches or config, will fail because the install dir is read-only. Sources: the behind-the-scenes page above. Code paths that compute locations from `sys.executable` will point into WindowsApps (inference).

### What this means for GUISkinDose

- The onedir needs no code changes to run from an MSIX, because the app writes nothing next to its executable.
- The phantom library lives under `%LOCALAPPDATA%`. MSIX redirects new files there to a private per-package folder, so the packaged app still finds its own installs. A pack installed by a zip copy of the app is not visible to the MSIX copy, and the reverse is also true. An MSIX spike should test this.
- The bundled Chromium child process is probably redirected the same way (UNVERIFIED). The Full PNG check should run inside the packaged app.
