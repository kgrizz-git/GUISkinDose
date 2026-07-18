# Security Hardening Review: Privacy Admission Enforcement

## Evidence Basis

I inspected the current ignore rules, hook configuration, blocking sensitive-content gate, local scanner wrappers,
scheduled workflows, and agent guidance listed in [context.md](context.md). The project already owns good individual
controls; the remaining opportunity is to make conditional scanner routing and protected output paths one enforceable
policy instead of a mixture of hook configuration and human memory.

**Implementation status (2026-07-16):** Option 3 is implemented in `scripts/privacy_admission.py` and
`dev-docs/privacy_admission_policy.json`, with staged/range hooks, CI policy routing, safe OCR/DICOM wrappers, and
private content-bound receipts. Asset scanner findings are accepted only through the exact-hash approved inventory;
other secondary findings remain blocking until fixed. Runtime/false-positive measurement remains follow-up work.

## Constraints

We must keep scanner data local and value-suppressed, preserve cross-platform development, avoid running expensive OCR
or NLP on unrelated commits, and ensure missing local hooks cannot bypass merge policy. The design is source-derived;
no hook-latency or scanner-resource benchmark has yet been performed.

## Opportunity Portfolio

| Opportunity | Evidence | Options | Recommendation | Proposal |
|---|---|---|---|---|
| Bind privacy admission to staged content | Existing hooks, ignore rules, scanner wrappers, CI workflows, and agent routing guidance | 1. Instructions/current hooks; 2. Run every scanner; 3. Conditional content-bound receipts | Option 3 | [Conditional privacy admission](proposals/conditional-privacy-admission.md) |

## Recommendation Summary

I recommend Option 3: one versioned policy determines which tools apply to the exact staged snapshot, protected
ignore/never-track rules block unsafe paths, and content-bound local receipts prove that expensive local scanners ran.
Required CI independently reruns public-runner-safe controls. This gives us stronger enforcement than a tracked
timestamp without making every source-only commit pay the cost and dependency burden of OCR, DICOM scanning, and NLP.

Option 2 becomes preferable only if scanner startup and runtime prove negligible across all supported platforms and
we are willing to make every tool a default development dependency. Option 1 remains acceptable only as a temporary
baseline while the wrappers and synthetic tests required by Option 3 are built.

## Follow-up validation

- Measure scanner latency and false-positive load across macOS, Linux, and Windows and adjust the current 168-hour
  expiry only with recorded evidence.
- Keep HoundDog, DICOM scanning, and image OCR local-only unless a separate data-processing review authorizes CI.
- Exercise a safe synthetic PR that bypasses hooks and verify CI policy/independent public-safe scanners still gate it.
- Add a general expiring disposition manifest only if non-asset false positives prove unavoidable; do not weaken the
  current fix-or-fail behavior preemptively.
