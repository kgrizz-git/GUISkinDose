# Privacy and sensitive-asset admission policy

This public repository must not contain PHI, PII that was not deliberately approved for publication, or local
absolute filesystem paths. The checks below are an admission control for future changes; they are not a legal or
clinical claim that data is de-identified.

## Blocking gate

Run the gate locally with:

```bash
python scripts/check_sensitive_content.py
```

CI-safe diagnostics use non-reversible path tokens so a sensitive filename is not copied into public logs. On an
approved local developer machine, add `--verbose-paths` when the exact repository path is needed for remediation.

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

The baseline review was completed on 2026-07-16 using reviewer initials `KG`; strict mode is now the hook and CI
default. Run the same admission boundary locally with:

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

## Protected paths and conditional scanner receipts

[`privacy_admission_policy.json`](privacy_admission_policy.json) defines privacy-critical ignore entries,
never-track paths, and the file/diff criteria that require secondary scanners. Run:

```bash
python scripts/privacy_admission.py route --mode staged
python scripts/privacy_admission.py run --mode staged
```

The first command explains which scanners the staged change requires without printing filenames. The second scans
an index snapshot, not arbitrary working-tree files, and writes only a content-bound, value-free receipt beneath
`.git/privacy-scan-receipts/`. Receipts contain scanner/config/tool digests, input Git object IDs, counts, status,
and expiry; they contain neither paths nor matched values and become invalid when inputs or scanner configuration
change. Commit and pre-push hooks fail when a required receipt is absent, stale, expired, or not clean. Standard Git
has no portable pre-`git add` hook, so the commit hook is the first enforceable admission boundary.

The same policy prevents tracking local logs, scanner reports/state, coverage output, build output, and known local
data directories. It also fails if required privacy ignore lines are deleted. Never weaken the protected list merely
to stage a file; prepare the asset through the documented review and inventory process instead.

## Additional scanners

Direct external privacy tools and runtimes are inventoried in
[`privacy_tool_inventory.json`](privacy_tool_inventory.json), with a generated review view in
[`privacy_tool_inventory.md`](privacy_tool_inventory.md). The inventory records reviewed versions, execution
location, purpose, and output boundary. Every conditional scanner must reference its tools; hooks and CI reject an
unknown tool or stale generated view. Candidate status does not authorize automated execution.

[`phi-scan`](https://pypi.org/project/phi-scan/) runs weekly and on pull requests that change CSV/TSV data. It is
pinned, quiet, and has no report upload or AI review enabled. Version 0.7.0 is calibrated to high-severity findings in
CSV/TSV files; broader source-code sinks are enforced by the project Semgrep rules. Its 90-day baseline contains only
finding hashes and metadata. The current 21 entries were reviewed by `KG` on 2026-07-16 as synthetic fixture headers,
synthetic numeric rows, or numeric correction-table combinations—not ignored findings. New or expired findings fail
the secondary workflow and must be triaged. phi-scan supplements, rather than replaces, the deterministic gate: it
does not authorise a binary asset or prove a DICOM is safe.

[Presidio](https://github.com/data-privacy-stack/presidio) is available as a local, advisory text scan. It does not
require a Presidio cloud service or an API key. Set it up on a developer-controlled machine with:

```bash
uv sync --extra privacy-scan
uv run --no-sync python scripts/run_presidio_advisory.py
```

The runner scans tracked, readable text files only (including when individual paths are supplied), skips
binary/DICOM/image content and text files larger than 64 KiB, never uploads source material or writes a report,
suppresses matched values in its output, and hashes paths by default. The weekly/PR workflow fails on structured
identifier findings or scan errors. Noisy spaCy `PERSON` detection is disabled in automation; use
`--include-person --verbose-paths` only for targeted, local free-text review and triage every result. It considers common
direct identifier types, rather than URLs, organizations, dates, or locations, and displays at most 100 summaries
by default. Do not point it at clinical data unless the machine and its local storage are approved for that data.
The scheduled job keeps model downloads and results local to its ephemeral runner, makes no external AI calls, and
uploads no findings. Presidio cannot establish complete PHI removal by itself.

[`references/LOCAL_PII_MODELS.md`](references/LOCAL_PII_MODELS.md) records the evaluated local-model options,
including NVIDIA GLiNER-PII, Fastino GLiNER2, and the boundaries for an optional LM Studio heuristic. Follow its
synthetic-fixture evaluation protocol before adding another detector or making any advisory scan scheduled.

The same reference records HoundDog as a candidate **code-dataflow** scanner. It is useful for detecting whether
code could send patient-like fields to logs, files, APIs, or third-party integrations; it is not a committed-content
or DICOM-pixel scanner. The local wrapper writes raw machine output only to a private ephemeral directory, prints a
value-safe count, and distinguishes `NOT RUN` from clean. A completed scan with risky flows exits 1; findings must be
triaged. **Until a maintainer explicitly changes this policy, HoundDog is local-only:** use only its
standalone binary, with no cloud features, GitHub App, managed scan, PR integration, report upload, or optional AI
analysis.

[`dicom-phi-scan`](https://github.com/elijahrockers/dicom-phi-scan) is required locally when a staged or outgoing
change adds or changes DICOM files. `privacy_admission.py` runs it against a private snapshot and reduces the raw
report to a clean/finding/error status and counts before deleting it. A clean result is advisory evidence only: the
exact-hash inventory and manual review of standard attributes, nested sequences, private tags, and pixels remain
mandatory. A scanner finding can satisfy receipt enforcement only when that exact file hash already has an approved
DICOM checklist in the staged inventory; this is explicit human triage, not a scanner allowlist.

Image OCR plus Presidio analysis is required locally for changed supported images, image-bearing office documents,
PDFs, and notebooks. The wrapper extracts only a bounded number of renderable images into a private temporary
directory, uses Poppler to rasterize bounded PDF pages, runs local Tesseract OCR, analyzes the captured text locally,
and emits only entity counts and path
tokens. Automated `PERSON` detection is enabled here at a deliberately higher threshold because OCR-bearing assets
are a narrow, high-risk set; ordinary repository-wide Presidio automation continues to exclude noisy name-only
detections. OCR cannot prove that an asset is safe and does not replace rendered human review.
OCR findings can satisfy receipt enforcement only through the staged inventory's exact-hash human approval.

ExifTool is inventoried as a candidate metadata second opinion, not an active hook. It can read metadata from many
image, PDF, Office, and DICOM formats, but normal output includes values and filenames and it does not inspect pixels.
Do not run it directly in shared logs. Promotion requires a synthetic-fixture evaluation and a wrapper that emits only
tag classes/counts and path tokens from private temporary output.

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
