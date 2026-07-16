# Local PII/PHI text-model reference

_Last reviewed: 2026-07-15. This is an evaluation reference, not a claim that any model de-identifies clinical data._

## Purpose and boundary

This public repository uses a blocking deterministic gate for obvious identifier patterns, absolute paths, and
human clearance of every image, DICOM, opaque binary, and extensionless file. See
[`../PRIVACY_AND_SENSITIVE_ASSETS.md`](../PRIVACY_AND_SENSITIVE_ASSETS.md). Local machine-learning detectors are a
separate, **advisory** second opinion for tracked readable text. They must not become the authority that approves an
asset, replaces rendered-image/DICOM review, or upload source text or findings.

The current local baseline is [`../../scripts/run_presidio_advisory.py`](../../scripts/run_presidio_advisory.py).
It runs Microsoft Presidio locally, suppresses matched values in its output, and is intentionally not a CI gate.

## Running the local scanners

Exact invocations for the scanners set up for this repository. The first two are wired into CI/hooks; the last two
are **local-only** manual tools that never run in public CI. All are value-safe or write only to gitignored paths.

| Scanner | Layer | How to run |
|---|---|---|
| **phi-scan** | CSV/TSV secondary scan (tracked files) | Mirrors the [`phi-scan` workflow](../../.github/workflows/phi-scan.yml): `git archive HEAD \| tar -x -C <tmp>` then `uvx --from 'phi-scan==0.7.0' phi-scan scan . --config <repo>/.phi-scanner.yml --baseline --no-cache --quiet --workers 4`. New and expired high-severity findings fail; matched values and reports are not printed or uploaded. |
| **Presidio** | NLP text (tracked bounded text) | `uv sync --extra privacy-scan` once, then `uv run --no-sync python scripts/run_presidio_advisory.py`. Automation hashes paths, suppresses values, and excludes noisy `PERSON`@0.85 results. For a targeted local name review add `--include-person --verbose-paths`; every result then requires manual triage. |
| **HoundDog** | Code dataflow (tracked source) | Install the standalone binary, then `python scripts/run_hounddog_advisory.py` (local pre-push hook). The wrapper reports `NOT RUN`, clean, or a value-safe risky-flow count; a completed scan with findings exits 1. Raw JSON is private and ephemeral. |
| **dicom-phi-scan** | DICOM header + pixel OCR (local data) | Install in an **isolated Python 3.11 env** (its EasyOCR/Pillow/pydicom pins conflict with the 3.12 project env), then `dicom-phi-scan --dir <dicom-dir> --cpu -o <gitignored>.jsonl -v`. Force `--cpu` on macOS; first run downloads EasyOCR models. |

The JSONL report from dicom-phi-scan can itself contain identifier values, so always write it to a gitignored path
(e.g. `tmp/`) and delete it after review. Inspect it value-safely with `jq` on non-value keys
(`risk_level`, `.tag_findings[].tag`) rather than printing header values into a terminal or log.

## Recommended candidate: NVIDIA GLiNER-PII

[NVIDIA GLiNER-PII](https://huggingface.co/nvidia/gliner-PII) is a non-generative, span-classification model for
PII and PHI in structured or unstructured text. It produces a label, character offsets, and confidence score for
each finding. NVIDIA describes it as a GLiNER large-v2.1-derived, 570-million-parameter model covering more than
55 categories.

| Question | Current answer |
|---|---|
| Download | The `model.safetensors` weights are about 1.78 GiB. The repository is about 3.58 GiB because it includes duplicate PyTorch and safe-tensors weight formats. |
| Memory on a 128-GB Mac | More than sufficient for a local advisory scan; allow a few GiB for model/runtime overhead. This is not a large-language-model-scale memory load. Benchmark actual throughput and peak memory on the target machine. |
| Locality | Use the GLiNER Python/PyTorch runtime. After the initial model download, inference can run on the developer-controlled machine without sending repository text to a hosted inference provider. |
| LM Studio | It is not a GGUF generative model, so LM Studio is not the intended runtime. LM Studio can instead host a general LLM through its local API, but that should be a separately benchmarked, optional heuristic—not the primary detector. |
| macOS support | NVIDIA officially lists Linux, x86_64 CPU, and NVIDIA GPU platforms. PyTorch/MPS may work on Apple Silicon but is not an NVIDIA-supported deployment path; verify it locally before adopting it. |
| License | NVIDIA Open Model License Agreement. Review its terms before distribution or a production integration. |
| What it cannot scan | It accepts text. It does not inspect image pixels, DICOM pixel data, or binary metadata by itself. |

The model card reports benchmark results on synthetic and public PII datasets, but those are not evidence that it
will work on this repository’s documentation, fixtures, or DICOM-derived text. Treat model confidence as triage
information, not proof of safety.

## Comparable local candidates

| Model | Why consider it | Scale / license | Suggested role |
|---|---|---|---|
| [Fastino GLiNER2 Privacy Filter](https://huggingface.co/fastino/gliner2-privacy-filter-PII-multi) | PII-specific, multilingual (seven languages), 42 entity types; its model card reports comparisons against NVIDIA GLiNER-PII and other detectors. | 205M parameters; Apache-2.0. | First GLiNER-family comparison: smaller and permissively licensed. |
| [NVIDIA GLiNER-PII](https://huggingface.co/nvidia/gliner-PII) | Broad PII/PHI taxonomy and mature GLiNER API. | 570M parameters; NVIDIA Open Model License. | Second local detector if macOS trial is reliable. |
| [OpenAI Privacy Filter](https://huggingface.co/blog/openai-privacy-filter-web-apps) | Long-context PII span detector with a different architecture/taxonomy. | 1.5B total parameters, 50M active; Apache-2.0. | Later comparator; heavier and not needed for the first evaluation. |
| [urchade GLiNER Multi-PII](https://huggingface.co/urchade/gliner_multi_pii-v1) | Established multilingual GLiNER PII model. | 1.16-GiB safe-tensors weights; Apache-2.0. | Lightweight historical baseline if newer candidates disagree. |
| [Gretel GLiNER PII/PHI](https://huggingface.co/gretelai/gretel-gliner-bi-large-v1.0) | English PII/PHI fine-tune with a published entity-label list. | Apache-2.0. | Alternative English-focused GLiNER benchmark. |

Do not infer comparative accuracy from a vendor’s claimed benchmark alone. The listed models have different labels,
datasets, thresholds, languages, and span-matching rules.

## Other repository-scanning candidates

These tools address distinct layers. They are not interchangeable with the text-model comparison above.

| Tool | What it adds | Recommendation for this repository |
|---|---|---|
| [HoundDog.ai Privacy Code Scanner](https://github.com/hounddogai/hounddog) | Deterministic, interprocedural static analysis that traces named sensitive data through application code into logs, files, storage, APIs, third-party SDKs, and AI integrations. The free edition supports Python, JavaScript, and TypeScript. | **Highest-priority local-only proof of concept.** It addresses code paths that could over-log or export patient data; it does not discover literal PII/PHI already committed to fixtures. Until a maintainer explicitly changes this policy, use only the standalone local binary—no API key, cloud platform, GitHub App, managed scan, PR comments, report upload, or optional AI analysis. Pin the downloaded release and ensure reports are ignored and value-safe. |
| [dicom-phi-scan](https://github.com/elijahrockers/dicom-phi-scan) | Local two-layer DICOM scan: pydicom header-tag checks plus EasyOCR on pixel data when burned-in annotation is present or absent. | Technically aligned with the mandatory DICOM review because it checks pixels as well as tags. It is an early project with no published release at review time; evaluate only on synthetic fixtures after source/dependency/output review. Do not run it in public CI or write unprotected JSON reports, since findings may themselves be sensitive. |
| [phi-scan](https://github.com/phiscanhq/phi-scan) | Rule/heuristic text scan. | Already installed as the pinned, report-free advisory GitHub workflow. Keep it as a text supplement; it does not clear DICOM or image assets. Evaluate its optional NLP features only through the synthetic-fixture protocol. |
| [@certifieddata/pii-scan](https://github.com/certifieddata/pii-scan) | Local regex scan for CSV and JSON datasets, with risk levels and masked samples. | Do not add: it is narrower than the existing tracked-text gate and its normal output includes masked example values. It may be useful for an isolated developer dataset triage, never as a public-CI report. |

### HoundDog proof-of-concept boundary

HoundDog is intentionally a different kind of safeguard. It analyzes how source-code values flow; it cannot determine
whether an image or DICOM fixture contains a real patient identifier. Conversely, the existing sensitive-content gate
cannot determine that a value named `patient_name` reaches `logger.info()` after several transformations. Use both
layers if the HoundDog trial is successful.

The 2026-07-16 local check with HoundDog 3.3.0 detected a synthetic `patient_email` parameter flowing to
`logging.info`, but reported zero risky flows for the repository even before all project-specific identifier sinks
were removed. That confirms the generic engine works and also confirms its current rules do not recognize enough of
MyPySkinDose's DICOM/provenance vocabulary. Keep it as a required local second opinion for logging/write/ingestion
changes, with project Semgrep as the blocking source-specific control.

**Policy status: local-only until further notice.** A cloud account, GitHub App, CI job, managed scan, automated PR
comment, report upload, or optional AI analysis is prohibited unless a maintainer explicitly changes this documented
policy after a separate data-processing review.

For the initial local trial:

1. Download a specific HoundDog release directly from its official releases page; do not use a floating pipe-to-shell
   installer in the evaluation record.
2. Run the standalone binary locally with no `HOUNDDOG_API_KEY`. Do not install the GitHub App or enable Cloud,
   managed scans, automated PR configuration, optional AI analysis, or report upload.
3. Send generated reports only to an ignored local directory. Inspect whether reports contain source excerpts, paths,
   or values before retaining or sharing them.
4. Evaluate Python coverage on synthetic representative paths: DICOM/RDSR ingestion, output serialization, logging,
   temporary files, GUI error handling, and third-party calls. Confirm each finding manually and record only
   value-suppressed summaries.
5. Review the current proprietary terms, release integrity, and maintenance process before adding a pinned local
   pre-commit hook. A cloud account or GitHub App is a separate authorization and data-processing decision.

## Integration shape if evaluation succeeds

Keep any new model outside the default dependencies and CI. A safe interface would be a new optional extra and a
dedicated advisory command with an explicit `--engine gliner2` selection.

- Scan only tracked, UTF-8-readable text within a bounded file size.
- Reuse the existing runner’s value-suppressed output: path, location, entity type, score, and detector name only.
- Keep model caches and source text on the approved local machine; do not enable hosted inference, report upload, or
  automated pull-request comments.
- Preserve Presidio as a separate engine, or offer an explicit union mode that identifies which engine found each
  span. Presidio documents a GLiNER recognizer integration, so a unified Presidio-style result format is practical.
- Do not run a generic LM Studio chat model as a blocking scanner. It may be useful as a manually invoked third
  heuristic only after it has been evaluated for repeatability, prompt sensitivity, false positives, and missed
  identifiers.

## Evaluation protocol

1. Create only synthetic, non-identifying positive and negative fixtures. Cover emails, phone numbers, names,
   addresses, patient/medical-record identifiers, dates where context makes them identifying, and repository paths.
2. Run Presidio, Fastino GLiNER2, and—if the macOS trial succeeds—NVIDIA GLiNER-PII with documented model versions,
   labels, thresholds, elapsed time, and peak memory.
3. Record false positives and misses without copying protected values into logs, issue trackers, or this repository.
   Evaluate both detection and whether the reported character range is usable for review/redaction.
4. Compare union and intersection behavior. For this repository, high recall is helpful only when the alert volume
   remains reviewable; no detector result may auto-approve an asset.
5. Decide whether to retain one optional local engine, add a scheduled advisory run on synthetic/repository text, or
   stop. A CI job would require a separate privacy, licensing, cache, and runner-data review.

## Primary references

- [NVIDIA GLiNER-PII model card and files](https://huggingface.co/nvidia/gliner-PII)
- [Fastino GLiNER2 Privacy Filter model card](https://huggingface.co/fastino/gliner2-privacy-filter-PII-multi)
- [OpenAI Privacy Filter overview and model links](https://huggingface.co/blog/openai-privacy-filter-web-apps)
- [Microsoft Presidio samples, including GLiNER integration](https://microsoft.github.io/presidio/samples/)
- [Presidio installation and local runtime guidance](https://microsoft.github.io/presidio/installation/)
- [HoundDog scanner README, local-runtime statement, and free/enterprise feature matrix](https://github.com/hounddogai/hounddog)
- [HoundDog local/CI deployment options](https://docs.hounddog.ai/cloud/getting-started)
