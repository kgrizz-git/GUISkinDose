# Security policy

## Supported versions

Security fixes are applied on a best-effort basis to the latest tagged release
and to `main`. Older tags are not routinely patched.

## Reporting a vulnerability

**Do not** open a public issue for security vulnerabilities, and **do not**
attach patient data, clinical RDSRs, credentials, or other sensitive material to
any public channel.

Use GitHub
[private vulnerability reporting](https://github.com/kgrizz-git/MyPySkinDose/security/advisories/new)
for this repository.

Please include:

- A clear description of the issue and impact
- Steps to reproduce with **synthetic** data only
- Affected versions or commit SHAs if known
- Whether you are coordinating disclosure with a timeline

We will acknowledge reports when we can and prefer coordinated disclosure. We do
**not** promise fixed response SLAs.

## Patient data and privacy incidents

If you believe real PHI/PII or clinical data was committed or leaked through
this project, treat it as an incident: stop sharing copies, report it through
GitHub
[private vulnerability reporting](https://github.com/kgrizz-git/MyPySkinDose/security/advisories/new)
(the same private intake used for security reports), and follow
[dev-docs/PRIVACY_INCIDENT_RESPONSE.md](dev-docs/PRIVACY_INCIDENT_RESPONSE.md).
Do not paste identifiers into public issues or pull requests.

## Scope notes

GUISkinDose is research / education / development / QA-oriented software and is
**not FDA-cleared**. Security reports about dose accuracy for clinical care are
out of scope for this policy unless they involve a concrete software defect that
misleads users about calculation inputs or outputs; clinical judgment remains
with qualified physicists and physicians.
