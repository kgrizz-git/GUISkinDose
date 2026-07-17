# Privacy tool inventory

This file is generated from [`privacy_tool_inventory.json`](privacy_tool_inventory.json).
It inventories direct external privacy tools and runtimes; it is not an approval for raw report output.

Last reviewed: 2026-07-16

| Tool | Status | Version | Execution | Role | Output boundary |
|---|---|---:|---|---|---|
| [phi-scan](https://github.com/phiscanhq/phi-scan) | active | 0.7.0 | local and GitHub Actions | Secondary CSV/TSV PHI heuristic scan | Quiet, value-suppressed, no uploaded report |
| [Microsoft Presidio Analyzer](https://github.com/microsoft/presidio) | active | 2.2.363 | local and GitHub Actions | Structured identifier and targeted OCR-text analysis | Matched values suppressed; no report upload |
| [spaCy en_core_web_sm](https://github.com/explosion/spacy-models) | active | 3.8.0 | local and GitHub Actions | Local Presidio NLP recognizer model | Runs in-process; model output is reduced by the Presidio wrapper |
| [HoundDog Privacy Code Scanner](https://github.com/hounddogai/hounddog) | active | 3.3.0 | local only | Sensitive-value dataflow into logging, files, APIs, and storage | Raw JSON is private and ephemeral; only counts/status are printed |
| [dicom-phi-scan](https://github.com/elijahrockers/dicom-phi-scan) | active | 0.1.0 | local only | DICOM header and pixel-PHI secondary scan | Raw report is private and ephemeral; only counts/status are printed |
| [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) | active | 5.5.2 | local only | OCR of changed images and privately rendered document pages | OCR text exists only in process/private temporary storage |
| [Poppler pdftoppm](https://poppler.freedesktop.org/) | active | 26.07.0 | local only | Rasterize bounded PDF pages for local OCR | Rendered pages stay in private temporary storage and are deleted |
| [Pillow](https://python-pillow.github.io/) | active | 12.3.0 | local privacy wrapper | Normalize extracted images to PNG for OCR | Converted images stay in private temporary storage |
| [pypdf](https://github.com/py-pdf/pypdf) | active | 6.14.2 | local and GitHub Actions | Bounded PDF validation/page counting and text/metadata admission checks | Extracted content is scanned in-process and values are suppressed |
| [Semgrep](https://github.com/semgrep/semgrep) | active | 1.168.0 | local and GitHub Actions | Blocking project privacy and general SAST rules | Metrics disabled; project wrapper emits value-safe findings |
| [SonarQube Community Build](https://www.sonarsource.com/products/sonarqube/downloads/) | optional | 26.7.0.124771 | local only | Optional code-quality and security second opinion | Raw scanner log is ephemeral; only status/digests are retained under .git |
| [SonarScanner CLI](https://docs.sonarsource.com/sonarqube-server/analyzing-source-code/scanners/sonarscanner/) | optional | 8.1.0.6389 | local only | Submit analysis to the loopback SonarQube server | Console output is captured privately and deleted after safe classification |
| [ExifTool](https://exiftool.org/) | candidate | 13.55 | not yet automated | Candidate secondary metadata inventory for images, PDF, Office, and DICOM | Do not run directly in shared logs; future wrapper must suppress values and paths |

Version provenance and installation details remain authoritative in the JSON inventory. Active tools
must also be referenced by the privacy admission policy when they participate in conditional receipts.
Candidate tools are not authorized for automated use until a value-safe wrapper and synthetic tests exist.
