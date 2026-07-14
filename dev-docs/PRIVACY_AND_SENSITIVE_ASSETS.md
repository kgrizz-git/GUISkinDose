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
CSV/TSV/JSON, and XML content inside XLSX workbooks) for conservative direct-identifier and absolute-path patterns.
It reports only a path, line/member location, and rule id; it never prints the matched value.

Every tracked image, DICOM file, opaque binary file, or extensionless filename (including dotfiles) must have an exact SHA-256 entry in
[`approved_asset_inventory.json`](approved_asset_inventory.json). The linked, reviewer-friendly
[`approved_asset_inventory.md`](approved_asset_inventory.md) is generated from that JSON and is checked in
pre-commit and CI; edit the JSON, then run `python scripts/render_asset_inventory.py --write`. This includes files
without a `.dcm` extension so an extensionless DICOM cannot bypass review. A new asset, a changed hash, or a
removed/stale inventory entry fails the gate.

The initial inventory deliberately records the pre-existing assets as `pending`. This is not approval. Until a
maintainer completes the baseline review, the default gate permits the unchanged baseline but emits warnings. Once
all entries have been reviewed, run the stricter command and make it the CI command:

```bash
python scripts/check_sensitive_content.py --require-approved-assets
```

Do not mark an entry approved merely because an automated scan is clean. The reviewer must record their name and
date, confirm its purpose/provenance, and review the rendered content of images or other opaque files. A changed
hash is a new review.

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

## Response to a finding

1. Stop sharing the affected revision or artifact and remove it from the working tree.
2. Treat a possible real identifier as sensitive even if the scanner's confidence is low.
3. Notify repository maintainers and follow the historical-exposure runbook once it is added.
4. Rotate any secrets separately; Gitleaks and GitHub secret scanning cover credentials, not PHI.
