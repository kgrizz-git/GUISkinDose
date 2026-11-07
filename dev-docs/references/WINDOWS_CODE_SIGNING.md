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
- Zip/portable installer types are supported in manifest schema 1.4+ (UNVERIFIED, not on the page fetched).
- winget itself does not trigger the SmartScreen download prompt for the installed binary in typical use (UNVERIFIED). Smart App Control on Windows 11 can still block unsigned files.

## Recommendation
1. Apply to SignPath Foundation now. It is free, CI-native, and fits an OSI-licensed, GitHub-Actions-built project. Add the code-signing policy section to the README/docs and set up MFA and roles. The downside is the publisher reads "SignPath Foundation."
2. If SignPath declines or is slow, use Artifact Signing at $9.99/mo. The maintainer qualifies as a US individual. The cert shows the maintainer's legal name and city/state.
3. Treat the Microsoft Store (MSIX) as the only route that removes SmartScreen warnings outright. Consider it later if MSIX packaging of the onedir proves practical.
4. Skip EV, Certum hardware, and full-price CA certs. They cost more and give no SmartScreen advantage.
5. Add winget after signing; it does not require signing but signed binaries reduce AV false positives.

Caveat: no option except the Store gives instant SmartScreen reputation; expect warnings for early releases.
