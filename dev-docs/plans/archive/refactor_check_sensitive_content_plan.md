# Complexity Refactoring Plan: Privacy Scan Script

> **Status:** Completed and archived (2026-07-18). Shipped as
> `scripts/check_sensitive_content.py` (policy/CLI) +
> `scripts/check_sensitive_helpers.py` (notebook/PDF/container readers).

This is the detailed companion to Phase 5 of
[the SonarQube remediation plan](../sonarqube_remediation_plan.md). It targets all
four `S3776` findings in `scripts/check_sensitive_content.py`:

| Function | Baseline complexity |
|---|---:|
| `has_notebook_embedded_visual_output` | 17 |
| `_pdf_text` | 25 |
| `_container_text` | 38 |
| `run_checks` | 76 |

This script participates in the repository privacy gate. A complexity reduction
must be behaviour-preserving and fail closed; it is not permission to loosen
inventory, container, or identifier checks.

---

## 1. Target Architecture

Extract format-specific readers into `scripts/check_sensitive_helpers.py` and
leave policy/configuration/CLI ownership in `check_sensitive_content.py`:

```text
scripts/
├── check_sensitive_content.py   # policy constants, run_checks orchestration, CLI
└── check_sensitive_helpers.py   # notebook/PDF/container reader helpers
```

The helper module must use no new optional dependencies and must never write
embedded content to disk or log it. Preserve importability both when the script
is executed directly and when its functions are imported by the unit tests.

### Contracts for extracted helpers

```python
def cell_data_mappings(cell: object) -> Iterable[Mapping[str, object]]: ...
def mapping_has_visual_mime(data: Mapping[str, object]) -> bool: ...

def extract_pdf_metadata(reader: PdfReader) -> list[tuple[str, str]]: ...
def extract_pdf_page_text(reader: PdfReader, page_number: int) -> tuple[str, str] | None: ...
def extract_pdf_attachments(reader: PdfReader) -> list[tuple[str, str]]: ...

def inspect_container_member(
    member_number: int, name: str, data: bytes
) -> tuple[list[tuple[str, str]], set[str], str | None]: ...
def iter_container_members(path: Path) -> Iterator[tuple[str, bytes] | ContainerReadError]: ...
```

`run_checks` may use small policy helpers (for example, asset-inventory status,
extracted-text scanning, and container-flag findings) but must retain the public
signature and return the same sorted, allowlist-filtered `Finding` sequence.
Do not move policy constants into a generic scanner class merely to reduce a
number.

---

## 2. Complexity Budget

| Function/method | Maximum complexity |
|---|---:|
| `has_notebook_embedded_visual_output` | 8 |
| Each notebook predicate/iterator | 6 |
| `_pdf_text` | 8 |
| Each PDF extractor | 10 |
| `_container_text` | 10 |
| Each container iterator/member helper | 12 |
| `run_checks` | 12 |
| Each policy/dispatch helper | 12 |

The desired maximum is **12**. SonarQube must be checked for every extracted
helper, not just the four original declarations.

---

## 3. Non-Negotiable Behaviour Invariants

1. **Fail closed:** unavailable or failed PDF/container extraction still yields
   the same error finding; encrypted PDFs, corrupt archives, and over-limit
   containers must not become silently clean.
2. **Bounded reads:** retain `MAX_CONTAINER_MEMBERS`, per-member byte limits, and
   total-byte limits for every archive format. Never extract archives to disk.
3. **Privacy-safe locations:** retain generated member/page location prefixes
   rather than raw member names; preserve sensitive-member-name detection without
   emitting the name.
4. **Asset policy:** retain asset kind detection, SHA-256 inventory matching,
   manual-review requirements, DICOM identifier/private-tag warnings, and the
   `require_approved_assets` distinction.
5. **Text coverage:** scan ordinary text, PostScript, PDF metadata/pages/
   attachments, supported container members, and notebook visual outputs using
   the same patterns and allowlist key `(path, rule, location)`.
6. **CLI contract:** retain command-line exit codes, stable error codes, sorted
   output, and private diagnostic discipline.

---

## 4. Characterization Tests and Review Steps

1. First add tests for edge cases that the existing suite does not pin: malformed
   notebook structure, encrypted/corrupt PDF, nested or over-limit container,
   non-UTF-8 member, and inventory/allowlist interaction. Use synthetic,
   non-identifying content only.
2. Extract notebook helpers and run the notebook/asset tests.
3. Extract PDF and container readers one format at a time; compare exact finding
   rule, level, location, and ordering with the characterization suite.
4. Split `run_checks` only after the readers are stable. Keep the final
   allowlist filtering and sort at the public boundary.
5. Re-run the privacy admission route appropriate to the change; any advisory
   finding must be triaged, not ignored.

```bash
uv run pytest tests/unittests/test_check_sensitive_content.py \
  tests/unittests/test_privacy_admission.py \
  tests/unittests/test_privacy.py
uv run python scripts/check_sensitive_content.py --require-approved-assets
uv run python scripts/privacy_admission.py route --mode staged
uv run python scripts/privacy_admission.py run --mode staged
uv run ruff check scripts tests/unittests/test_check_sensitive_content.py
uv run basedpyright
```

**Completion criterion:** the four baseline findings and all new helpers meet the
configured complexity threshold; the contracts above are covered with synthetic
fixtures; privacy-admission checks remain clean; and the local SonarQube scan
does not introduce new complexity findings.
