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
import hashlib, json, os, re
import guiskindose
from importlib import resources
from guiskindose import get_path_to_example_rdsr_files, load_settings_example_json
from guiskindose.main import main
from guiskindose.settings import PyskindoseSettings

report = {"guiskindose_file": guiskindose.__file__}
pkg = resources.files("guiskindose") / "table_data"
manifest = json.loads((pkg / "correction_data_manifest.json").read_text())
report["tables_sha"] = {
    table["file"]: hashlib.sha256((pkg / table["file"]).read_bytes()).hexdigest()
    for table in manifest["tables"]
    if table.get("role") == "runtime_lookup"
}
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


def _flat(values):
    flat = []
    for value in values:
        if isinstance(value, (list, tuple)):
            flat.extend(_flat(value))
        else:
            flat.append(float(value))
    return flat


report["corrections"] = {key: _flat(out["corrections"][key]) for key in ("medium", "table", "backscatter")}
import pandas as pd
from guiskindose.geom_calc import fetch_and_append_hvl

probe_frame = pd.DataFrame(
    {
        "kVp": [70.0, 100.0],
        "filter_thickness_Cu": [0.0, 0.3],
        "filter_thickness_Al": [0.0, 1.0],
    }
)
hvl_db = os.environ.get("PROOF_HVL_DB", "corrections.db")
probe_out = fetch_and_append_hvl(data_norm=probe_frame, inherent_filtration=2.5, corrections_db=hvl_db)
report["hvl_probe"] = [float(v) for v in probe_out["HVL"]]
payload = json.dumps(out, default=str)
json_out = main(file_path=rdsr, settings=PyskindoseSettings(settings=base, output_format="json"))
combined = payload + str(json_out)
markers = {
    "cwd": os.environ["PROOF_CWD"],
    "repo": os.environ["PROOF_REPO"],
    "home": os.path.expanduser("~"),
    "explicit_db": os.environ.get("PROOF_EXPLICIT_DB", ""),
    "db_suffix": ".db",
}
leaks = sorted(label for label, value in markers.items() if value and value in combined)
abs_pattern = r"(/(Users|home|private|tmp|opt|usr|var)/|[A-Za-z]:[\\/]|\\\\)"
if re.search(abs_pattern, combined):
    leaks.append("abs_path_shape")
report["leaks"] = sorted(leaks)
print(json.dumps(report))
"""


def _clean_env(extra: dict[str, str]) -> dict[str, str]:
    """Subprocess env without checkout leakage plus proof variables."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.pop("VIRTUAL_ENV", None)
    env.pop("VIRTUAL_ENV_PROMPT", None)
    env.update(extra)
    return env


def _safe(text: str) -> str:
    """Redact absolute local paths from failure output (privacy rule)."""
    redacted = text.replace(str(REPO), "<repo>")
    home = os.path.expanduser("~")
    if home and home != "/":
        redacted = redacted.replace(home, "<home>")
    return redacted


def _run(python: Path, snippet: Path, cwd: Path, extra: dict[str, str]) -> dict[str, Any]:
    """Execute the proof snippet in one interpreter, return its JSON report."""
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
        raise RuntimeError(f"proof run failed in {cwd.name}:\n{_safe(proc.stderr[-2000:])}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _check(condition: bool, failures: list[str], message: str) -> None:
    """Record a PASS/FAIL line, collecting failures for the final verdict."""
    print(("PASS" if condition else "FAIL") + f": {message}")
    if not condition:
        failures.append(message)


def _close_lists(label: str, got: list[float], want: list[float], failures: list[str]) -> None:
    """Element-wise tolerance comparison for per-event value arrays."""
    ok = len(got) == len(want) and all(
        math.isclose(g, w, rel_tol=PSD_REL, abs_tol=PSD_ABS) for g, w in zip(got, want, strict=False)
    )
    _check(ok, failures, f"{label} per-event values match checkout ({len(want)} values)")


def _close_enough(label: str, got: float, want: float, failures: list[str]) -> None:
    """Tolerance comparison for scalar metrics using the per-label budget."""
    rel_tol, abs_tol = _TOLERANCES[label]
    ok = math.isclose(got, want, rel_tol=rel_tol, abs_tol=abs_tol)
    _check(ok, failures, f"{label} installed={got!r} checkout={want!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="reuse the dist/* wheel (fails unless exactly one)")
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
        print(f"FAIL: explicit-DB fixture missing: {LEGACY_DB.relative_to(REPO)}")
        return 1

    dist = REPO / "dist"
    if not args.skip_build:
        print("--- uv build ---")
        proc = subprocess.run(
            [uv, "build", "--clear"], cwd=REPO, capture_output=True, text=True, timeout=600, check=False
        )
        if proc.returncode != 0:
            print(f"FAIL: uv build failed:\n{_safe(proc.stderr[-2000:])}")
            return 1
    wheels = sorted(dist.glob("guiskindose-*.whl"))
    if not wheels:
        print("FAIL: no guiskindose wheel in dist/ (run without --skip-build)")
        return 1
    if len(wheels) != 1:
        # Never guess: lexicographic [-1] can select a stale artifact across
        # versions (e.g. 1.0.10 sorts before 1.0.9). Fail with names only.
        names = sorted(candidate.name for candidate in wheels)
        print(f"FAIL: expected exactly one guiskindose wheel, found {len(names)}: {names}")
        return 1
    wheel = wheels[0]
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
        timeout=600,
        check=False,
    )
    if proc.returncode != 0:
        print(f"FAIL: wheel install failed:\n{_safe(proc.stderr[-2000:])}")
        return 1

    snippet = PROOF_DIR / "snippet.py"
    snippet.write_text(SNIPPET, encoding="utf-8")

    # Import-path guard: the installed import must resolve inside the proof
    # venv (containment is the whole check — no extra path-component rules,
    # which would false-fail when the checkout itself lives under a "src"
    # directory). Never print guard_file: on failure it is an absolute
    # checkout path and raw paths must not be emitted (privacy rule).
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
    guard_ok = guard_file is not None and guard_file.is_relative_to(venv_dir.resolve())
    _check(guard_ok, failures, "installed import resolves inside proof venv")
    if failures:
        return 1

    def fresh_cwd(name: str) -> Path:
        path = PROOF_DIR / name
        path.mkdir(parents=True, exist_ok=False)
        return path

    checkout_src = str(REPO / "src")

    def baseline_env(cwd: Path, mode: str, explicit_db: str = "") -> dict[str, str]:
        """Baseline env: import the checkout via PYTHONPATH (no editable-install assumption)."""
        env = {"PROOF_MODE": mode, "PROOF_CWD": str(cwd), "PROOF_REPO": str(REPO), "PYTHONPATH": checkout_src}
        if explicit_db:
            env["PROOF_EXPLICIT_DB"] = explicit_db
            env["PROOF_HVL_DB"] = explicit_db
        return env

    def check_baseline_import(report: dict[str, Any], failures: list[str]) -> None:
        imported = Path(str(report["guiskindose_file"])).resolve()
        _check(
            imported.is_relative_to((REPO / "src" / "guiskindose").resolve()),
            failures,
            "baseline imports the checkout package",
        )

    # Checkout baseline (own interpreter, fresh CWD, checkout on PYTHONPATH).
    baseline_cwd = fresh_cwd("baseline-cwd")
    baseline = _run(Path(sys.executable), snippet, baseline_cwd, baseline_env(baseline_cwd, "packaged"))
    check_baseline_import(baseline, failures)
    _check(list(baseline_cwd.iterdir()) == [], failures, "checkout baseline writes no CWD artifacts")

    # Installed run 1: clean CWD, packaged mode.
    run_cwd = fresh_cwd("run-cwd-clean")
    installed = _run(
        proof_python,
        snippet,
        run_cwd,
        {"PROOF_MODE": "packaged", "PROOF_CWD": str(run_cwd), "PROOF_REPO": str(REPO)},
    )
    _check(list(run_cwd.iterdir()) == [], failures, "installed run writes no CWD artifacts")
    _check(installed["tables_sha"] == baseline["tables_sha"], failures, "packaged table bytes identical")
    _check(installed["n_events"] == baseline["n_events"], failures, "event count matches checkout")
    _close_enough("psd", installed["psd"], baseline["psd"], failures)
    _close_enough("dose_sum", installed["dose_sum"], baseline["dose_sum"], failures)
    _close_enough("air_kerma", installed["air_kerma"], baseline["air_kerma"], failures)
    for key in ("medium", "table", "backscatter"):
        _close_lists(f"k-{key}", installed["corrections"][key], baseline["corrections"][key], failures)
    _close_lists("hvl-probe", installed["hvl_probe"], baseline["hvl_probe"], failures)
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
    seeded = _run(
        proof_python,
        snippet,
        seed_cwd,
        {"PROOF_MODE": "packaged", "PROOF_CWD": str(seed_cwd), "PROOF_REPO": str(REPO)},
    )
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
            "PROOF_HVL_DB": str(LEGACY_DB),
            "PROOF_CWD": str(explicit_cwd),
            "PROOF_REPO": str(REPO),
        },
    )
    checkout_explicit_cwd = fresh_cwd("baseline-cwd-explicit")
    checkout_explicit = _run(
        Path(sys.executable),
        snippet,
        checkout_explicit_cwd,
        baseline_env(checkout_explicit_cwd, "explicit", explicit_db=str(LEGACY_DB)),
    )
    check_baseline_import(checkout_explicit, failures)
    _check(list(explicit_cwd.iterdir()) == [], failures, "explicit run writes no CWD artifacts")
    _check(list(checkout_explicit_cwd.iterdir()) == [], failures, "explicit baseline writes no CWD artifacts")
    _check(explicit["tables_sha"] == baseline["tables_sha"], failures, "explicit mode ships packaged tables")
    _close_enough("psd-explicit", explicit["psd"], checkout_explicit["psd"], failures)
    for key in ("medium", "table", "backscatter"):
        _close_lists(f"k-{key}-explicit", explicit["corrections"][key], checkout_explicit["corrections"][key], failures)
    _close_lists("hvl-probe-explicit", explicit["hvl_probe"], checkout_explicit["hvl_probe"], failures)
    _check(explicit["leaks"] == [], failures, f"no path leaks in explicit exports (got {explicit['leaks']})")

    print("---")
    if failures:
        print(f"RESULT: FAIL ({len(failures)} failing check(s))")
        return 1
    print("RESULT: PASS — installed wheel reproduces checkout results (packaged + explicit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
