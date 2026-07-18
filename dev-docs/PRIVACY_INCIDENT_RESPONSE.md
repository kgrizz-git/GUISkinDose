# Privacy incident response and history-audit runbook

_Last reviewed: 2026-07-16_

Use this runbook for suspected PHI/PII in repository content, filenames, logs, CI output, release artifacts, package
indexes, or Git history. Do not copy the suspected value into an issue, chat, commit message, terminal transcript, or
public scanner report.

## Immediate containment

1. Stop sharing the affected revision/artifact and pause releases. Do not delete the only evidence.
2. Record a value-free incident identifier, affected object type, rule/entity ID, and private evidence location.
3. Notify the maintainers through an approved private channel. Escalate through the organization’s privacy/legal and
   clinical-data process when the value could identify a real person.
4. Remove the value from the working tree and replace it with synthetic data. Run the strict gate and relevant local
   scanner before committing the fix.
5. Rotate credentials separately if the finding also contains a secret.

## Private historical audit

Run on an approved developer-controlled machine, not a public CI runner. Keep temporary archives, model caches, and
raw findings outside the repository with owner-only permissions and delete them after the approved retention period.

Audit all of the following:

- every reachable commit and tree on every local/remote branch;
- annotated/lightweight tags and release branches;
- Git LFS objects and other large-file stores;
- GitHub release assets, Actions artifacts/logs, package-index sdists/wheels, documentation builds, and mirrors;
- commit messages, PR titles/bodies, issue attachments, and scanner reports.

Before trusting a clean result, validate the procedure in an isolated synthetic Git repository containing a fake
identifier in a current file, a deleted historical file, a filename, a commit message, an archive member, and a
binary/visual placeholder. Automated text scans do not clear DICOM pixels, images, PDFs, Office files, or opaque
history; render/inspect those privately and use dicom-phi-scan for historical DICOM objects.

Public reporting records only detector version, rule/entity, commit/object token, path token, status, reviewer
initials, date, and follow-up. Never publish matched values, raw reports, source excerpts, private endpoints, or a
potentially sensitive filename.

## Remediation and verification

If historical rewriting is approved, coordinate it before force-pushing. Revoke affected releases/packages where
possible, replace published artifacts, invalidate caches under maintainer control, notify known consumers, and give
fork/clone owners precise value-free cleanup instructions. A rewrite reduces discoverability but cannot erase existing
clones, forks, caches, screenshots, backups, or third-party archives.

After remediation, repeat the private audit from a fresh clone and verify current-tree strict admission, blocking
privacy Semgrep, phi-scan/Presidio status, ignored-artifact sweep, test containment, and built wheel/sdist contents.
Record residual limitations and the decision owner privately.

## Release checklist

- Strict sensitive-content/approved-asset gate passes.
- Blocking privacy Semgrep passes.
- No untriaged phi-scan, Presidio, HoundDog, DICOM/OCR, or ignored-artifact findings remain.
- Tests leave the checkout clean and use synthetic identifiers only.
- Built wheel, sdist, documentation, and release attachments are inspected/scanned.
- The private history/release delta audit is completed or explicitly revalidated by reviewer initials and date.
- Scanner versions, hooks, CI workflows, and this runbook are current.
