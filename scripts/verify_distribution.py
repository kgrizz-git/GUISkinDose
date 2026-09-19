#!/usr/bin/env python3
"""Phase D distribution proof: packaged correction data from an installed wheel.

Builds the wheel/sdist, installs the wheel into a hermetic proof venv under
gitignored ``tmp/dist-proof/``, and asserts the installed distribution
reproduces checkout-numerical results with no working-directory writes, no
ignored-DB resurrection, and no absolute paths in exports.

Parity is direct comparison (installed vs checkout), never new hardcoded
goldens. Tolerances mirror the golden suite (PSD abs=1e-6, rel=1e-9).

Preconditions: ``uv`` on PATH. The hermetic venv resolves runtime deps from
the index (CI) or the local ``uv`` cache (offline). ``--quick`` reuses the
host environment via ``--system-site-packages`` for offline iteration only
(never the canonical evidence) behind the same import-path guard.

Exit 0 with a PASS report on success, nonzero on any failure.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
PROOF_DIR = REPO / "tmp" / "dist-proof"
LEGACY_DB = REPO / "tests" / "manual_tests" / "corrections.db"
RDSR_NAME = "siemens_axiom_artis.dcm"

# Golden-suite tolerances for installed-vs-checkout parity.
PSD_ABS, PSD_REL = 1e-6, 1e-9
DOSE_SUM_ABS, DOSE_SUM_REL = 1e-6, 1e-9
AIR_KERMA_ABS = 1e-9

# Tolerance per compared metric: (rel_tol, abs_tol).
_TOLERANCES = {
    "psd": (PSD_REL, PSD_ABS),
    "psd-seeded": (PSD_REL, PSD_ABS),
    "psd-explicit": (PSD_REL, PSD_ABS),
    "dose_sum": (DOSE_SUM_REL, DOSE_SUM_ABS),
    "air_kerma": (0.0, AIR_KERMA_ABS),
}

# Runs in BOTH interpreters (checkout baseline + proof venv). Resolves the
# fixture via the imported package's own API so each side uses the data it
# ships. Prints one JSON report line to stdout.
SNIPPET = r"""
import json, os
import guiskindose
from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.main import main
from guiskindose.settings import PyskindoseSettings

report = {"guiskindose_file": guiskindose.__file__}
base = load_settings_example_json()
base["mode"] = "calculate_dose"
base["silence_pydicom_warnings"] = True
base["phantom"]["model"] = "cylinder"
base["plot"]["notebook_mode"] = False
base["plot"]["plot_dosemap"] = False
if os.environ.get("PROOF_MODE") == "explicit":
    base["corrections_db_path"] = os.environ["PROOF_EXPLICIT_DB"]
rdsr = str(get_path_to_example_rdsr_files() / "siemens_axiom_artis.dcm")
out = main(file_path=rdsr, settings=PyskindoseSettings(settings=base, output_format="dict"))
report["psd"] = float(out["psd"])
report["dose_sum"] = float(sum(d for _, d in out["dose_map"]))
report["air_kerma"] = float(out["air_kerma"])
report["n_events"] = int(out["events"]["number_of_events"])
payload = json.dumps(out, default=str)
json_out = main(file_path=rdsr, settings=PyskindoseSettings(settings=base, output_format="json"))
markers = (os.environ["PROOF_CWD"], ".db")
report["leaks"] = sorted({m for m in markers if m in payload or m in str(json_out)})
print(json.dumps(report))
"""


def _clean_env(extra: dict[str, str]) -> dict[str, str]:
    """Subprocess env without checkout leakage plus proof variables."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
    env.pop("VIRTUAL_ENV", None)
    env.pop("VIRTUAL_ENV_PROMPT", None)
    env.update(extra)
    return env


def _run(python: Path, snippet: Path, cwd: Path, extra: dict[str, str]) -> dict[str, Any]:
    proc = subprocess.run(
        [str(python), str(snippet)],
        cwd=cwd,
        env=_clean_env(extra),
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"proof run failed in {cwd}:\n{proc.stderr[-2000:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _check(condition: bool, failures: list[str], message: str) -> None:
    print(("PASS" if condition else "FAIL") + f": {message}")
    if not condition:
        failures.append(message)


def _close_enough(label: str, got: float, want: float, failures: list[str]) -> None:
    rel_tol, abs_tol = _TOLERANCES[label]
    ok = math.isclose(got, want, rel_tol=rel_tol, abs_tol=abs_tol)
    _check(ok, failures, f"{label} installed={got!r} checkout={want!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="reuse newest dist/* artifacts")
    parser.add_argument(
        "--quick", action="store_true", help="offline shortcut: --system-site-packages (not canonical evidence)"
    )
    args = parser.parse_args()
    failures: list[str] = []

    uv = shutil.which("uv")
    if uv is None:
        print("FAIL: `uv` not found on PATH (precondition for build + venv)")
        return 1
    if not LEGACY_DB.is_file():
        print(f"FAIL: explicit-DB fixture missing: {LEGACY_DB}")
        return 1

    dist = REPO / "dist"
    if not args.skip_build:
        print("--- uv build ---")
        proc = subprocess.run([uv, "build"], cwd=REPO, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            print(f"FAIL: uv build failed:\n{proc.stderr[-2000:]}")
            return 1
    wheels = sorted(dist.glob("guiskindose-*.whl"))
    if not wheels:
        print("FAIL: no guiskindose wheel in dist/ (run without --skip-build)")
        return 1
    wheel = wheels[-1]
    print(f"wheel under test: {wheel.name}")

    if PROOF_DIR.exists():
        shutil.rmtree(PROOF_DIR)
    venv_dir = PROOF_DIR / "venv"
    venv_args = [uv, "venv", str(venv_dir)]
    if args.quick:
        venv_args.append("--system-site-packages")
        print("NOTE: --quick mode (system-site-packages); not canonical §5 evidence")
    subprocess.run(venv_args, cwd=REPO, check=True, capture_output=True)
    bin_dir = venv_dir / ("Scripts" if os.name == "nt" else "bin")
    proof_python = bin_dir / "python"
    print("--- install wheel into proof venv ---")
    proc = subprocess.run(
        [uv, "pip", "install", "--python", str(proof_python), str(wheel)],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print(f"FAIL: wheel install failed:\n{proc.stderr[-2000:]}")
        return 1

    snippet = PROOF_DIR / "snippet.py"
    snippet.write_text(SNIPPET, encoding="utf-8")

    # Import-path guard: the installed import must resolve inside the proof
    # venv, never to the checkout src/ (editable-install shadowing).
    guard_proc = subprocess.run(
        [str(proof_python), "-c", "import guiskindose; print(guiskindose.__file__)"],
        cwd=PROOF_DIR,
        env=_clean_env({}),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    guard_file = Path(guard_proc.stdout.strip()).resolve() if guard_proc.returncode == 0 else None
    _check(
        guard_file is not None and guard_file.is_relative_to(venv_dir.resolve()) and "src" not in guard_file.parts,
        failures,
        f"installed import resolves to proof venv ({guard_file})",
    )
    if failures:
        return 1

    def fresh_cwd(name: str) -> Path:
        path = PROOF_DIR / name
        path.mkdir(parents=True, exist_ok=False)
        return path

    # Checkout baseline (own interpreter, clean env, fresh CWD).
    baseline_cwd = fresh_cwd("baseline-cwd")
    baseline = _run(
        Path(sys.executable), snippet, baseline_cwd, {"PROOF_MODE": "packaged", "PROOF_CWD": str(baseline_cwd)}
    )
    _check(list(baseline_cwd.iterdir()) == [], failures, "checkout baseline writes no CWD artifacts")

    # Installed run 1: clean CWD, packaged mode.
    run_cwd = fresh_cwd("run-cwd-clean")
    installed = _run(proof_python, snippet, run_cwd, {"PROOF_MODE": "packaged", "PROOF_CWD": str(run_cwd)})
    _check(list(run_cwd.iterdir()) == [], failures, "installed run writes no CWD artifacts")
    _check(installed["n_events"] == baseline["n_events"] == 21, failures, "event count is 21 both sides")
    _close_enough("psd", installed["psd"], baseline["psd"], failures)
    _close_enough("dose_sum", installed["dose_sum"], baseline["dose_sum"], failures)
    _close_enough("air_kerma", installed["air_kerma"], baseline["air_kerma"], failures)
    _check(installed["leaks"] == [], failures, f"no path leaks in installed exports (got {installed['leaks']})")

    # Installed run 2: sentinel-seeded CWD DB must be ignored, bytes untouched.
    seed_cwd = fresh_cwd("run-cwd-seeded")
    sentinel = seed_cwd / "corrections.db"
    conn = sqlite3.connect(sentinel)
    conn.execute("CREATE TABLE hvl_combined (kvp_kv REAL)")
    conn.execute("INSERT INTO hvl_combined VALUES (1.0)")
    conn.commit()
    conn.close()
    before = sentinel.read_bytes()
    seeded = _run(proof_python, snippet, seed_cwd, {"PROOF_MODE": "packaged", "PROOF_CWD": str(seed_cwd)})
    _check(sentinel.read_bytes() == before, failures, "seeded CWD DB left untouched")
    _check({p.name for p in seed_cwd.iterdir()} == {"corrections.db"}, failures, "seeded CWD gains no artifacts")
    _close_enough("psd-seeded", seeded["psd"], baseline["psd"], failures)

    # Installed run 3: explicit legacy SQLite mode + export leak check.
    explicit_cwd = fresh_cwd("run-cwd-explicit")
    explicit = _run(
        proof_python,
        snippet,
        explicit_cwd,
        {
            "PROOF_MODE": "explicit",
            "PROOF_EXPLICIT_DB": str(LEGACY_DB),
            "PROOF_CWD": str(explicit_cwd),
        },
    )
    checkout_explicit = _run(
        Path(sys.executable),
        snippet,
        fresh_cwd("baseline-cwd-explicit"),
        {
            "PROOF_MODE": "explicit",
            "PROOF_EXPLICIT_DB": str(LEGACY_DB),
            "PROOF_CWD": str(explicit_cwd),
        },
    )
    _close_enough("psd-explicit", explicit["psd"], checkout_explicit["psd"], failures)
    _check(explicit["leaks"] == [], failures, f"no path leaks in explicit exports (got {explicit['leaks']})")

    print("---")
    if failures:
        print(f"RESULT: FAIL ({len(failures)} failing check(s))")
        return 1
    print("RESULT: PASS — installed wheel reproduces checkout results (packaged + explicit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
