# Privacy Admission Enforcement — Evidence Context

_Prepared: 2026-07-16_
_Source revision: `49814a7e0efc6174372bc4f58c23f59c825e6e10`_
_Source drift: present; the privacy hardening and rename plan are uncommitted working-tree changes._

This design review is based on the following repository controls and policy documents:

| Evidence | Role |
|---|---|
| `.gitignore` | Current local-output and cache containment patterns |
| `.pre-commit-config.yaml` | Installed pre-commit, pre-push, and commit-message routing |
| `scripts/check_ignored_asset_files.py` | Current risky ignored/untracked asset check |
| `scripts/check_sensitive_content.py` | Blocking tracked-content and approved-asset gate |
| `scripts/run_hounddog_advisory.py` | Local-only code-dataflow wrapper |
| `scripts/run_presidio_advisory.py` | Local value-suppressed text scanner |
| `.github/workflows/phi-scan.yml` | Changed-tabular and weekly phi-scan workflow |
| `.github/workflows/presidio.yml` | Changed-text and weekly Presidio workflow |
| `.github/workflows/ci.yml` | Required repository CI controls |
| `dev-docs/AGENT_PLAYBOOK.md` | Agent/contributor scanner-routing rules |
| `dev-docs/PRIVACY_AND_SENSITIVE_ASSETS.md` | Privacy admission and asset-review policy |

The collection digest is
`39aa91f7e3ceb96f7b00ebd85077aaee53388a5b73c56827cd226300481e0581`, calculated from each
repository-relative path plus its SHA-256 digest in the order shown above.

## Observations

- The deterministic sensitive-content and approved-asset gate is blocking locally and in CI.
- Risky ignored/untracked assets are checked strictly, but required `.gitignore` rules are not themselves protected by
  a versioned policy.
- Standard Git has no dependable pre-`git add` hook; current enforceable boundaries are commit, push, and CI.
- Presidio and phi-scan run in public ephemeral CI for relevant paths and on schedules.
- HoundDog is local-only and returns success when missing or when its scan does not complete, so instructions cannot
  prove that it ran.
- OCR and safe `dicom-phi-scan` wrappers are prerequisites in the active privacy/rename plan and are currently absent.
- A tracked wall-clock “last run” file would not prove that the current staged content or scanner configuration was
  evaluated.

## Decision constraints

- Scanner input, raw reports, OCR text, DICOM values, and matched text must never be uploaded or committed.
- Diagnostics must suppress values and use path tokens by default.
- Fast common commits should not run every heavyweight scanner.
- Relevant binary/clinical assets must fail closed when their required local review tool is unavailable.
- CI must catch policy bypass even when local hooks are absent or invoked with `--no-verify`.
- Windows, macOS, and Linux development must remain supported.
