# Privacy and sensitive-asset admission policy

This public repository must not contain PHI, PII that was not deliberately approved for publication, or local
absolute filesystem paths. The checks below are an admission control for future changes; they are not a legal or
clinical claim that data is de-identified.

## Blocking gate

Run the gate locally with:

```bash
python scripts/check_sensitive_content.py
```

It runs in pre-commit and CI. The checker scans every tracked, UTF-8-readable file (including notebooks, SVG/XML,
CSV/TSV/JSON, and XML content inside XLSX workbooks) for conservative direct-identifier, internal DICOM/PACS
endpoint, private-network-address, and absolute-path patterns. It also rejects common diagnostic artifacts
(`.log`, rotated `.log.N`, `.trace`, `.err`, `.out`, `.pkl`, `.pickle`, and `.cache`) even if their current text is
clean. It reports only a path, line/member location, and rule id; it never prints the matched value.

Every tracked image, DICOM file, PDF, PostScript/EPS file, supported archive/container, opaque binary file,
extensionless filename (including dotfiles), or notebook with an embedded rendered image/PDF output must have an
exact SHA-256 entry in
[`approved_asset_inventory.json`](approved_asset_inventory.json). The linked, reviewer-friendly
[`approved_asset_inventory.md`](approved_asset_inventory.md) is generated from that JSON and is checked in
pre-commit and CI; edit the JSON, then run `python scripts/render_asset_inventory.py --write`. This includes files
without a `.dcm` extension so an extensionless DICOM cannot bypass review. A new asset, a changed hash, or a
removed/stale inventory entry fails the gate.

TeX and other UTF-8-readable source files are scanned as ordinary text. PDFs are also parsed locally with `pypdf`:
page text, document metadata, and readable embedded attachments are checked with the same value-safe rules. A PDF
that cannot be parsed or decrypted fails closed. PostScript/EPS content is decoded conservatively and scanned for
text strings. PDF and PostScript/EPS review remains mandatory even when these scans are clean, because page images,
vector outlines, encoded content, or image-only attachments can still contain burned-in information.

Local OCR is a useful second layer for rendered images, image-only PDFs, Office/iWork previews, and DICOM pixels.
Evaluate it only on synthetic fixtures first: a conventional engine such as Tesseract and a local ML OCR engine are
both reasonable candidates. Keep inputs, model caches, intermediate images, and value-suppressed findings on an
approved local machine. OCR is advisory until its misses/false positives and report safety are documented; it must
not upload source material, emit matched text in CI logs, or replace the hash-pinned human review.

Supported containers are treated as reviewable assets: ZIP, TAR (including gzip/bzip2/xz variants), standalone GZIP,
and ZIP-based Office/iWork formats (`.docx`, `.pptx`, `.xlsx`, `.odt`, `.ods`, `.numbers`, `.pages`). The gate scans
bounded UTF-8 text/XML/TeX/RTF members, PDF/PostScript members, and raises a value-free warning when it recognizes a
DICOM member or nested archive. It fails closed if a supported container cannot be read or exceeds its bounded scan
limit. Each approved container also needs the inventory checklist for all embedded files, embedded images, and
embedded DICOM. This is why a clean spreadsheet scan is not sufficient to clear a workbook with images. Member names
are never printed by the gate, since a filename can itself contain sensitive information.

Notebook source text is still scanned normally. A notebook that embeds an image/PDF output is additionally treated as
a reviewable visual asset, because regex scanning cannot establish whether a base64-rendered output contains burned-in
information. The whole notebook hash is pinned, so changing its output requires a new review.

An extensionless file with the standard `DICM` marker is classified as DICOM rather than merely extensionless, so it
also requires the DICOM-specific inventory checklist. DICOM files without that standard preamble still require an
extensionless-file inventory entry and manual review; use the repository's DICOM preparation procedure to identify
them before admission.

The initial inventory deliberately records the pre-existing assets as `pending`. This is not approval. Until a
maintainer completes the baseline review, the default gate permits the unchanged baseline but emits warnings. Once
all entries have been reviewed, run the stricter command and make it the CI command:

```bash
python scripts/check_sensitive_content.py --require-approved-assets
```

Do not mark an entry approved merely because an automated scan is clean. The reviewer must record their initials or
a stable public reviewer handle and the date, confirm the asset's purpose/provenance, and review the rendered content
of images or other opaque files. A full legal name is unnecessary in this public inventory. A changed hash is a new
review.

## DICOM review

For each DICOM entry, a reviewer must set all three `dicom_review` flags to `true` only after checking:

1. direct-identifier attributes and all nested sequences;
2. private tags and vendor-specific content; and
3. pixel/graphic content for burned-in identifiers.

The gate warns when recognizable direct-identifier fields or private-tag values are present, without displaying
their values. A field being present does not itself establish whether a fixture is synthetic, pseudonymous, or
restricted; that is why human review is mandatory. Use a documented DICOM confidentiality/de-identification
procedure when preparing any fixture. Do not use the inventory as a substitute for that procedure.

## Intentional public text

The small, line-specific allowlist in
[`sensitive_content_allowlist.json`](sensitive_content_allowlist.json) is only for deliberate public material, such
as package-author contact information or a test fixture. Entries must have a reason and must not copy the sensitive
value. Prefer removing or replacing data over adding an allowlist entry.

## Commit messages and diagnostics

The `sensitive-commit-message` local `commit-msg` hook applies the same value-free text rules to the message before a
commit is created. Commit messages have no allowlist: remove sensitive wording instead of trying to exempt it. This
hook cannot change existing public history; use the public-history audit/runbook item in `TO_DO.md` for that work.
Run `bash scripts/setup-dev.sh` or `scripts\setup-dev.bat` after updating the checkout; those setup scripts install
the `pre-commit`, `pre-push`, and `commit-msg` hook types.

Diagnostic files are ignored by default and rejected by the blocking gate if tracked. Native GUI logs are local,
fresh per session, size-bounded, and owner-only on POSIX systems. GUI load errors deliberately record only an
operation label and exception type and show a generic UI message, rather than raw tracebacks, paths, or exception
messages. Do not attach diagnostic logs to issues or commits without reviewing them separately.

## Additional scanners

[`phi-scan`](https://pypi.org/project/phi-scan/) runs as a pinned, advisory GitHub workflow and is deliberately
configured to scan only text-like files. The initial pin does not install phi-scan's optional NLP extra, and has no
report upload or AI review enabled. It supplements, rather than replaces, the deterministic gate: it does not
authorise a binary asset or prove a DICOM is safe.

[Presidio](https://github.com/data-privacy-stack/presidio) is available as a local, advisory text scan. It does not
require a Presidio cloud service or an API key. Set it up on a developer-controlled machine with:

```bash
uv sync --extra privacy-scan
uv run --extra privacy-scan python scripts/run_presidio_advisory.py
```

The runner scans tracked, readable text files only (including when individual paths are supplied), skips
binary/DICOM/image content and text files larger than 64 KiB, never uploads source material or writes a report,
suppresses matched values in its output, and exits successfully after findings. It considers people and common
direct identifier types, rather than URLs, organizations, dates, or locations, and displays at most 100 summaries
by default. It is not wired to GitHub Actions. Do not point it at clinical data unless the machine and its local
storage are approved for that data. If Presidio is later used in CI, keep its model downloads and results local to
the runner, disable calls to external AI providers, and never upload raw findings. Its text/image detection is
useful for a future scheduled evaluation but cannot establish complete PHI removal by itself.

[`references/LOCAL_PII_MODELS.md`](references/LOCAL_PII_MODELS.md) records the evaluated local-model options,
including NVIDIA GLiNER-PII, Fastino GLiNER2, and the boundaries for an optional LM Studio heuristic. Follow its
synthetic-fixture evaluation protocol before adding another detector or making any advisory scan scheduled.

The same reference records HoundDog as a candidate **code-dataflow** scanner. It is useful for detecting whether
code could send patient-like fields to logs, files, APIs, or third-party integrations; it is not a committed-content
or DICOM-pixel scanner. **Until a maintainer explicitly changes this policy, HoundDog is local-only:** use only its
standalone binary, with no cloud features, GitHub App, managed scan, PR integration, report upload, or optional AI
analysis.

## Historical exposure audit

The blocking gate protects newly proposed revisions; it cannot remove information from a commit already public. The
P0 backlog item requires an isolated, local/private audit of every reachable commit, tag, release branch, and relevant
LFS/release artifact. The audit should use the same value-suppressed rules, prove its detector against synthetic
known-positive history, and keep raw evidence out of issues, Actions logs, and public reports. Its response runbook
must cover triage, private evidence handling, notification, history rewrite, cache/clone limitations, credential
rotation where relevant, and a post-remediation re-scan. Git history rewriting reduces future discoverability but
cannot guarantee deletion from existing clones, forks, caches, or third-party archives.

## Response to a finding

1. Stop sharing the affected revision or artifact and remove it from the working tree.
2. Treat a possible real identifier as sensitive even if the scanner's confidence is low.
3. Notify repository maintainers and follow the historical-exposure runbook once it is added.
4. Rotate any secrets separately; Gitleaks and GitHub secret scanning cover credentials, not PHI.
