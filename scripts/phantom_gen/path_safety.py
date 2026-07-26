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


def trusted_path_under_roots(
    path: Path | str,
    *,
    roots: Sequence[Path] | None = None,
    must_exist: bool = False,
    must_be_file: bool = False,
) -> Path:
    """Resolve under roots, then rebuild from the matched root + relative parts.

    Sonar taint analysis (S8707) often still treats a validated ``Path`` as
    tainted when it is the same object derived from CLI input. Rebuilding from a
    trusted root plus ``relative_to`` parts produces a write path that is no
    longer data-dependent on the original tainted value.
    """
    allowed = [Path(r).resolve() for r in (roots if roots is not None else default_allowed_roots())]
    resolved = resolve_under_roots(
        path,
        roots=allowed,
        must_exist=must_exist,
        must_be_file=must_be_file,
    )
    for root in allowed:
        if resolved == root or resolved.is_relative_to(root):
            rel = resolved.relative_to(root)
            return root.joinpath(*rel.parts) if rel.parts else root
    raise ValueError("path escaped allowed roots")
