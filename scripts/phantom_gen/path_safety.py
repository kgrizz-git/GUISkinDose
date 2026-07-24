"""Confine phantom_gen filesystem paths under allowlisted roots.

Sonar S2083 / LLM-agent tooling can treat CLI- or catalog-derived ``Path`` values
as untrusted. Resolve and require ``is_relative_to`` an allowed root **before**
any open/mkdir/read/write so faulty arguments cannot escape the intended tree.
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHANTOM_GEN_ROOT = Path(__file__).resolve().parent


def default_allowed_roots() -> tuple[Path, ...]:
    """Repository root, phantom_gen tree, and the process temp dir (pytest / OS tmp)."""
    return (
        _REPO_ROOT.resolve(),
        _PHANTOM_GEN_ROOT.resolve(),
        Path(tempfile.gettempdir()).resolve(),
    )


def resolve_under_roots(
    path: Path | str,
    *,
    roots: Sequence[Path] | None = None,
    must_exist: bool = False,
    must_be_file: bool = False,
) -> Path:
    """Resolve ``path`` and require it stays under one of ``roots``.

    Relative paths are interpreted against the first root (normally the repo).
    Raises ``ValueError`` on escape; ``FileNotFoundError`` when existence is required.
    """
    allowed = [Path(r).resolve() for r in (roots if roots is not None else default_allowed_roots())]
    if not allowed:
        raise ValueError("no allowed path roots configured")

    raw = Path(path).expanduser()
    if not raw.is_absolute():
        candidate = (allowed[0] / raw).resolve()
    else:
        candidate = raw.resolve()

    if not any(candidate == root or candidate.is_relative_to(root) for root in allowed):
        raise ValueError("path escaped allowed roots")
    if must_exist and not candidate.exists():
        raise FileNotFoundError("path missing under allowed roots")
    if must_be_file and not candidate.is_file():
        raise ValueError("path is not a file under allowed roots")
    return candidate
