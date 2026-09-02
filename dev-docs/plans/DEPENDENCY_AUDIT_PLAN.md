# Dependency Auditing Update Plan

This plan details how to update the pre-commit hook and CI workflow to audit dependencies based on the project's declared/locked dependencies ([pyproject.toml](../../pyproject.toml) and `uv.lock`) instead of scanning the active Python environment.

> **Status (2026-06-28):** Implemented. Wrapper wired into pre-push hook and CI; script uses `uv >= 0.11.19`,
> `--frozen` locally, `--locked` in CI. Archive this plan after merge.

---

## The Problem
If CI uses the wrapper, keep the audit tied to the locked project state so the result is reproducible and does not silently drift with the runner environment. If the lockfile is stale, CI should fail clearly rather than regenerating it.

Currently, both the pre-push git hook and the CI use:
```yaml
pip-audit --desc on
```
This audits the entire active Python environment. If a developer has other global packages or secondary dependencies installed in their local environment (like `torch` or `transformers`), they receive warning flags and hook failures for packages that GUISkinDose does not use or declare.

---

## The Proposed Solution: Hybrid Python Wrapper

To ensure cross-platform compatibility (macOS/Linux/Windows) and robust fallback behavior, we implement a wrapper script `scripts/audit_dependencies.py`.

* **If `uv` is installed (>= 0.11.19), supports the `audit` subcommand, and a `uv.lock` file is present:** It runs `uv audit` against the locked project dependencies at native Rust speeds. The intended default scope for this repository is the full maintained install surface, including dev and GUI dependencies, unless the command is intentionally narrowed later. (`uv audit` audits the **entire lockfile by default** and only supports *subtractive* scope flags such as `--no-group`, so no extra flag is needed to cover dev/GUI groups.)
* **Fallback:** It falls back gracefully to `pip-audit --desc on`, which scans the active environment just as it does today.

This provides the best experience for modern development workflows (which use `uv` and lockfiles) while remaining backward-compatible.

> **Important caveats (verified against `uv` docs/behavior, 2026-06):**
> 1. **`uv audit` is still an experimental preview command.** Running it emits
>    `warning: 'uv audit' is experimental and may change without warning. Pass '--preview-features audit' to disable this warning.`
>    The warning goes to **stderr** and does **not** affect the exit code, so the wrapper functions without the flag, but we
>    knowingly accept the stability risk of a preview command in our hooks/CI. Pin the `uv` version in CI to limit churn.
>    (Note: the exact preview-feature name has varied between `uv` releases; an unknown name only warns, never errors, so
>    the wrapper does not hard-code it.)
> 2. **`uv audit` requires `uv >= 0.11.19`** (the release where the subcommand was unhidden). Earlier 0.11.x builds do not
>    have it — so the `>= 0.11.0` gate originally proposed is wrong.
> 3. **`uv audit` performs a relock pre-pass and may download a CPython interpreter** unless `--frozen` is passed (even
>    `--locked` triggers the download). The wrapper therefore uses `--frozen` on the local path (fast, no interpreter
>    download, audits the committed lockfile as-is) and `--locked` in CI (asserts the lockfile is in sync with
>    `pyproject.toml`, failing loudly if it is stale).
> 4. **The `uv` path needs network access** (OSV database lookups), exactly like `pip-audit`. Offline runs of either tool
>    will fail.
> 5. **The `pip-audit` fallback does not solve the original problem** (see "Known Limitations"): when `uv` is unavailable
>    it still scans the active environment. This is a documented limitation, not a regression.

### Gaps Addressed in Review & Assessment
1. **Handling Missing `pip-audit`:** Added try-except blocks to catch `FileNotFoundError` in the fallback case, printing a helpful error message to guide the developer on installing `pip-audit` or using `uv`.
2. **`uv audit` Preview Status (CORRECTED):** `uv audit` is **not** a stable command as of 2026-06 — it is still an experimental preview feature that prints a `--preview-features audit` warning to stderr. The wrapper relies on the warning being non-fatal (stderr only, exit code unaffected) rather than asserting stability. We do not hard-code the `--preview-features` name because it has changed between releases and an unknown name only warns. The `uv` version is pinned in CI to limit preview churn.
3. **`uv` Version and Availability Probing (CORRECTED):** The script executes a version check (`uv --version` requiring **`>= 0.11.19`**, the release that unhid `uv audit`) followed by `uv audit --help` before attempting to run audit. If `uv` is present but is an old version that does not support the `audit` subcommand, it falls back to `pip-audit` instead of failing.
4. **`uv.lock` Existence Check:** Verifies that a `uv.lock` file is present in the repository root. If missing (e.g., in clean checkouts before `uv lock` has run), it falls back to `pip-audit` instead of failing.
5. **Argument Pass-through and Focused Flag Filtering:** Updated the wrapper to forward command-line arguments (`sys.argv[1:]`) but explicitly filter out long-form `pip-audit`-specific flags (`--desc`, `--vulnerability-service`, and `--format` / `-f`) in the `uv` path. This prevents `uv audit` from crashing or misinterpreting format/source arguments (as `-f` is used for `--find-links` in `uv`).
6. **Distinct Fallback Messages:** Provided distinct, clear fallback messages for each condition (missing uv, missing lockfile, outdated version, or unsupported subcommand) to make troubleshooting fallbacks easier.
7. **Repository Working Directory Guard:** Handled the working directory dynamically by resolving the repository root parent from `__file__` and passing it as `cwd` to all subprocess invocations, ensuring the wrapper runs correctly from subdirectories.
8. **CI `uv` Installation, Lock Check, and Interpreter Cost (CORRECTED):** The CI workflow diff installs `uv` via `astral-sh/setup-uv` (pinned to a full immutable tag/SHA — moving tags such as `@v8` no longer resolve), and the wrapper appends `--locked` to `uv audit` in CI (detected via the `CI` env variable) so a stale `uv.lock` fails loudly. Outside CI the wrapper uses `--frozen` instead, which audits the committed lockfile without a relock pre-pass and **avoids downloading a CPython interpreter** (a real cost: `uv audit` — including `uv audit --locked` — otherwise relocks and may fetch an interpreter). Because the project installs deps with `pip` (not `uv sync`), note that `uv audit` reads `uv.lock` directly and does **not** require the project to be synced into a uv-managed venv.
9. **Auditing Group Policy:** Auditing all groups (including optional `dev` and `gui` dependencies) is the intended behavior to keep development/testing libraries secure. This is satisfied **for free**: `uv audit` audits the entire lockfile by default and only offers subtractive scope flags (`--no-group`, `--no-dev`, etc.), so no additional flag is required.
10. **Test Coverage**: Added unit tests in `tests/unittests/test_audit_dependencies.py` to cover all code paths and mock subprocesses, including explicit coverage for both the `uv` and `pip-audit` `FileNotFoundError` exception paths. **The existing tests must be updated** to cover the corrected version gate (`>= 0.11.19`) and the `--frozen` (local) vs `--locked` (CI) branch.
11. **Developer Documentation**: Recommended `uv` in `AGENTS.md` and updated `dev-docs/HARNESS_ENGINEERING.md` to document the wrapper script.
12. **Retention of `pip-audit`**: Retained `pip-audit` in `pyproject.toml` `dev` dependencies to support the fallback execution path.
13. **`--frozen` vs `--locked` (NEW):** The wrapper passes `--frozen` locally and `--locked` in CI (see item 8) to avoid surprising interpreter downloads in the pre-push hook while still enforcing lockfile freshness in CI.
14. **`setup-uv` pin & version (NEW):** The CI step pins `astral-sh/setup-uv` to a full immutable tag or SHA (current line is **v8.x**; moving tags like `@v8`/`@v5` are deprecated/old) and requests a `uv` version `>= 0.11.19` so `uv audit` is available.

### Known Limitations
- **Fallback re-exposes the original problem.** When `uv` is not installed, the wrapper runs `pip-audit` against the *active* environment — the very noise (unrelated globally-installed packages) this plan set out to eliminate. The clean fix only applies to `uv` users. Mitigations to document for non-`uv` users: run `pip-audit` inside a dedicated project virtualenv, or export the locked deps and audit those, e.g. `uv export --format requirements-txt | pip-audit -r -` (still requires `uv`). Installing `uv` is the recommended path.
- **Preview instability.** Because `uv audit` is a preview command that "may change without warning," a future `uv` release could alter flags or output. Pinning `uv` in CI and keeping the `pip-audit` fallback are the safeguards.

---

## Implementation Details

### 1. Implement `scripts/audit_dependencies.py`
Create a new file [scripts/audit_dependencies.py](../../scripts/audit_dependencies.py):
```python
#!/usr/bin/env python3
"""Cross-platform wrapper for dependency auditing.

Uses 'uv audit' if available (scanning the lockfile), otherwise falls back to
'pip-audit' scanning the active environment.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

def main():
    repo_root = Path(__file__).resolve().parent.parent
    
    # Check if uv is installed in the system PATH
    uv_bin = shutil.which("uv")
    
    # Check if uv.lock exists
    lock_file = repo_root / "uv.lock"
    if uv_bin and not lock_file.exists():
        print("INFO: 'uv.lock' not found. Falling back to active environment scan using pip-audit...")
        sys.stdout.flush()
        uv_bin = None
        
    # Check uv version and availability (requires uv >= 0.11.19, the release that unhid 'uv audit')
    if uv_bin:
        try:
            version_out = subprocess.run([uv_bin, "--version"], capture_output=True, text=True, check=True).stdout
            match = re.search(r"uv\s+(\d+)\.(\d+)\.(\d+)", version_out)
            if match:
                major, minor, patch = map(int, match.groups())
                if (major, minor, patch) < (0, 11, 19):
                    print(f"INFO: 'uv' version {major}.{minor}.{patch} is too old (requires 0.11.19+ for 'uv audit'). Falling back to pip-audit...")
                    sys.stdout.flush()
                    uv_bin = None
            else:
                uv_bin = None
        except Exception:
            uv_bin = None

    # Probe if uv audit subcommand is available
    if uv_bin:
        try:
            probe = subprocess.run([uv_bin, "audit", "--help"], capture_output=True, text=True, cwd=repo_root)
            if probe.returncode != 0:
                print("INFO: 'uv audit' subcommand is not supported by this uv installation. Falling back to pip-audit...")
                sys.stdout.flush()
                uv_bin = None
        except Exception:
            uv_bin = None

    # Print general fallback message if uv was never found in the first place
    if not uv_bin and shutil.which("uv") is None:
        print("INFO: 'uv' not found in PATH. Auditing active Python environment instead using pip-audit...")
        sys.stdout.flush()

    # Pass any extra command line arguments (e.g. ignores) through
    extra_args = sys.argv[1:]
    
    if uv_bin:
        print("Using 'uv audit' to check locked dependencies...")
        sys.stdout.flush()
        
        # Filter out pip-audit specific flags that uv doesn't support
        uv_args = []
        i = 0
        while i < len(extra_args):
            arg = extra_args[i]
            if arg in ("--desc", "--vulnerability-service", "--format", "-f"):
                # Skip this flag and its value if it has one
                i += 1
                if i < len(extra_args) and not extra_args[i].startswith("-"):
                    i += 1
                continue
            if arg.startswith(("--desc=", "--vulnerability-service=", "--format=", "-f=")):
                i += 1
                continue
            uv_args.append(arg)
            i += 1

        # In CI, enforce --locked so a stale uv.lock fails loudly. Locally, use --frozen to audit
        # the committed lockfile as-is and avoid 'uv audit' relocking / downloading a CPython interpreter.
        if os.environ.get("CI"):
            if "--locked" not in uv_args and "--frozen" not in uv_args:
                uv_args.append("--locked")
        else:
            if "--frozen" not in uv_args and "--locked" not in uv_args:
                uv_args.append("--frozen")

        try:
            result = subprocess.run(
                [uv_bin, "audit"] + uv_args,
                cwd=repo_root
            )
            sys.exit(result.returncode)
        except FileNotFoundError:
            # Fallback if shutil.which returned a path that is not executable
            pass
            
    # Fallback to pip-audit
    try:
        # Default to include descriptions, but allow overriding/extending via extra_args
        cmd = ["pip-audit"]
        if not any(arg.startswith("--desc") for arg in extra_args):
            cmd.extend(["--desc", "on"])
        cmd.extend(extra_args)
        
        result = subprocess.run(cmd, cwd=repo_root)
        sys.exit(result.returncode)
    except FileNotFoundError:
        print("ERROR: 'pip-audit' is not installed or not found in PATH.", file=sys.stderr)
        print("Please install pip-audit or uv to run dependency auditing:", file=sys.stderr)
        print("  pip install pip-audit", file=sys.stderr)
        print("  or install development dependencies: pip install -e '.[dev]'", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### 2. Update `.pre-commit-config.yaml`
Modify [.pre-commit-config.yaml](../../.pre-commit-config.yaml) to run our wrapper script:
```diff
       - id: pip-audit
         name: pip-audit (dependency vulnerabilities)
-        entry: pip-audit --desc on
+        entry: python scripts/audit_dependencies.py
         language: system
         pass_filenames: false
         always_run: true
```

### 3. Update `.github/workflows/ci.yml`
Modify [.github/workflows/ci.yml](../../.github/workflows/ci.yml) to install `uv` and use the wrapper:
```diff
     - name: Basedpyright (strict — any type error fails)
       run: basedpyright
+    - name: Install uv
+      # setup-uv now ships immutable releases; moving tags like @v8 do NOT resolve.
+      # Pin to a full version tag (or, preferably, a commit SHA) and check the releases page for the latest.
+      uses: astral-sh/setup-uv@v8.2.0
+      with:
+        version: ">=0.11.19"   # 'uv audit' requires >= 0.11.19
     - name: Audit dependencies for CVEs and check licenses
       run: |
-        pip-audit --desc on
+        python scripts/audit_dependencies.py
         python scripts/check_licenses.py
```

### 4. Add Unit Tests
Add unit tests in [tests/unittests/test_audit_dependencies.py](../../tests/unittests/test_audit_dependencies.py) to cover all code paths:
- standard `uv audit` success path
- fallback when `uv` is missing
- fallback when `uv.lock` is missing
- fallback when `uv` version is too old (now `< 0.11.19`)
- fallback when `uv audit` subcommand is unsupported
- flag filtering (`--desc` and `--format` / `-f`)
- CI `--locked` enforcement **and** local `--frozen` default (assert the local path appends `--frozen`)
- preserve existing fallback arguments except for those that are genuinely incompatible with `uv audit`

---

## Compatibility Matrix

| Environment | Primary Tool | Target audited | Behavior |
|---|---|---|---|
| **Local dev (`uv` >= 0.11.19)** | `uv audit --frozen` | `uv.lock` | Ultra-fast; audits committed lockfile, no relock / interpreter download. |
| **CI (`uv` >= 0.11.19, `CI=true`)** | `uv audit --locked` | `uv.lock` | Audits locked deps; **fails if `uv.lock` is stale** vs `pyproject.toml`. |
| **Any OS (No `uv` / `uv` < 0.11.19 / no `uv.lock`)** | `pip-audit` | Active Env | Fallback; checks installed env packages. ⚠️ Re-exposes unrelated globals (see Known Limitations). |

---

## Next Steps

1. ~~Apply script and test corrections~~ — done.
2. ~~Wire `.pre-commit-config.yaml` and `ci.yml`~~ — done.
3. ~~Update `AGENTS.md` and `HARNESS_ENGINEERING.md`~~ — done.
4. Archive this plan under `dev-docs/plans/archive/` after merge (update `dev-docs/index.md`).
