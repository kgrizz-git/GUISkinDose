"""Value-safe descriptions of paths that tests changed in the checkout.

The write-containment guard in ``tests/conftest.py`` must never print a raw
path by default: its message reaches the pytest terminal reporter, and CI logs
for a public repository are world-readable.  A stable hash alone, however, is
undebuggable — identifying the offending file meant brute-forcing candidate
paths through SHA-256.

Three disclosure levels close that gap without weakening the default, selected
by ``GUISKINDOSE_TEST_CONTAINMENT_HINT``:

``token`` (default, and the value for anything unrecognized)
    Hash token plus *shape*: whether a tracked file changed or a new one
    appeared, the top-level directory (named only when it belongs to the
    published repository layout), the path depth, and the file suffix (only
    when it is an allowlisted extension).

``masked``
    Adds a per-segment masked path — first and last character of each name,
    with an allowlisted suffix kept verbatim.  Conveys segment count and those
    characters, but *not* name length: a single ellipsis stands for any number
    of withheld characters.

``full``
    The complete repo-relative path.  Local debugging only.

Threat model, stated precisely because the levels are easy to over-trust: the
default resists *accidental* disclosure — nothing in it echoes a name.  It does
not resist a *targeted confirmation attack*, because the token is an unsalted
digest an attacker can recompute for any path they can guess (see
:func:`path_token`).  ``masked`` additionally hands over the first and last
character of every segment, which prunes such a search substantially.  Both
escalated levels therefore refuse to activate in CI (see :func:`hint_mode`).
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Final

CONTAINMENT_HINT_ENV: Final = "GUISKINDOSE_TEST_CONTAINMENT_HINT"

HINT_TOKEN: Final = "token"
HINT_MASKED: Final = "masked"
HINT_FULL: Final = "full"
_HINT_MODES: Final = frozenset({HINT_TOKEN, HINT_MASKED, HINT_FULL})

# Escalated levels are refused when any of these is truthy, so copy-pasting the
# footer's advice into a workflow file cannot widen disclosure in a
# world-readable log. GitHub sets CI and GITHUB_ACTIONS to "true".
_CI_ENV_VARS: Final = ("CI", "GITHUB_ACTIONS")
_TRUTHY: Final = frozenset({"1", "true", "yes", "on"})

# Top-level entries of the published repository layout plus the scratch roots
# named by the workspace conventions (`PlotOutputs`, `backups`, `tmp` are
# gitignored; `wiki` is tracked). These names are safe to
# print because they are *conventional* — fixed by project layout rather than
# derived from data. (Not simply "because .gitignore lists them": `.gitignore`
# naming `tmp/` says nothing about what a test wrote inside it.) Anything else
# is withheld: a test that invents a top-level directory could have named it
# from data. Entries in conftest's `_EXCLUDED_DIRS` are omitted — the snapshot
# never walks them, so allowlisting them would be dead weight.
_PUBLIC_TOP_LEVEL: Final = frozenset(
    {
        "PlotOutputs",
        "backups",
        "dev-docs",
        "docs",
        "scripts",
        "src",
        "tests",
        "tmp",
        "wiki",
    }
)

# Suffixes echoed verbatim. Extend this when a new artifact type shows up and
# the hint starts reporting `<unlisted-suffix>` for something mundane: an
# over-tight list costs debuggability, which is the point of the feature. An
# allowlist rather than a shape pattern because
# `Path.suffix` is merely "text after the last dot": `x.Lastname_Firstname` has
# a *suffix* holding the identifier, and a pattern like `\.[A-Za-z0-9]{1,8}`
# still admits `.J` — a first initial dressed as an extension.
_SAFE_SUFFIXES: Final = frozenset(
    {
        ".bash",
        ".bat",
        ".cfg",
        ".conf",
        ".csv",
        ".db",
        ".dcm",
        ".dicom",
        ".docx",
        ".gz",
        ".html",
        ".ini",
        ".ipynb",
        ".json",
        ".jsonl",
        ".log",
        ".md",
        ".npy",
        ".npz",
        ".parquet",
        ".pdf",
        ".png",
        ".ps1",
        ".py",
        ".pyc",
        ".rst",
        ".sh",
        ".sql",
        ".stl",
        ".svg",
        ".toml",
        ".tsv",
        ".txt",
        ".xlsm",
        ".xlsx",
        ".xml",
        ".yaml",
        ".yml",
        ".zip",
        ".zsh",
    }
)

_WITHHELD_TOP_LEVEL: Final = "<unlisted-top-level>"
_REPO_ROOT_TOP_LEVEL: Final = "<repo-root>"
_OUTSIDE_REPO: Final = "<outside-repo>"
_NO_SUFFIX: Final = "<no-suffix>"
_WITHHELD_SUFFIX: Final = "<unlisted-suffix>"
_ELLIPSIS: Final = "…"
_WITHHELD_NAME: Final = _ELLIPSIS

# Cap the per-run listing: a badly behaved test can dirty hundreds of paths, and
# the point is to name enough to start debugging, not to dump the tree.
MAX_REPORTED_CHANGES: Final = 20

# Stripped before anything is printed, because a filename may legally contain
# any of these and the escalated levels would otherwise let it forge log lines,
# move the cursor, or reverse how the rest of the line renders:
#   \x00-\x1f, \x7f-\x9f  C0/C1 controls, incl. newline and ESC (ANSI escapes)
#   \u200b-\u200f          zero-width and directional marks
#   \u202a-\u202e          bidi embedding/override ("trojan source")
#   \u2028-\u2029          Unicode line/paragraph separators (real line breaks)
#   \u2066-\u2069          bidi isolates
#   \ufeff                 zero-width no-break space / BOM
# Deliberately NOT stripped: ordinary and exotic spaces (U+00A0, U+2000-200A,
# U+3000) and weak directional marks (U+061C, U+180E). None can forge a line or
# reverse rendering the way U+202E does, masked output is length-bounded anyway,
# and chasing full `\p{Cf}` coverage would trade clarity for no real gain.
# The bidi set matters even at the `masked` level: a segment whose first or last
# character is U+202E keeps it through first/last masking.
_CONTROL_CHARS: Final = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028\u2029\u202a-\u202e\u2066-\u2069\ufeff]")
_CONTROL_PLACEHOLDER: Final = "�"


def _sanitize(text: str) -> str:
    """Replace control and bidi characters so a filename cannot forge output."""
    return _CONTROL_CHARS.sub(_CONTROL_PLACEHOLDER, text)


def _is_truthy(value: object) -> bool:
    """Truthy env-flag test that tolerates a non-string value.

    A reporting helper must not raise over the failure it is describing, and
    ``hint_mode`` already coerces with ``str(...)`` — this matches it rather
    than calling ``.strip()`` on whatever it was handed.
    """
    return value is not None and str(value).strip().lower() in _TRUTHY


def running_in_ci(environ: Mapping[str, str] | None = None) -> bool:
    """Whether the environment advertises itself as CI."""
    source = os.environ if environ is None else environ
    return any(_is_truthy(source.get(name)) for name in _CI_ENV_VARS)


def requested_mode(environ: Mapping[str, str] | None = None) -> str:
    """The level the environment asked for, before the CI refusal is applied."""
    source = os.environ if environ is None else environ
    value = str(source.get(CONTAINMENT_HINT_ENV, "")).strip().lower()
    return value if value in _HINT_MODES else HINT_TOKEN


def hint_mode(environ: Mapping[str, str] | None = None) -> str:
    """Selected disclosure level, failing closed to ``token``.

    Closes on two conditions: an unrecognized value (so ``HINT=fulll`` cannot
    silently land on something more revealing than the author asked for), and a
    CI environment (so the escalated levels cannot reach a world-readable log
    even if the variable is set in a workflow).
    """
    source = os.environ if environ is None else environ
    value = requested_mode(source)
    if value == HINT_TOKEN:
        return HINT_TOKEN
    return HINT_TOKEN if running_in_ci(source) else value


def path_token(relative: Path) -> str:
    """Stable 12-hex-character token for a repo-relative path.

    Obscuring, not confidential. The digest is an unsalted SHA-256 over a short
    string, so anyone holding a candidate path can confirm it by hashing;
    truncation does not help, since the attacker truncates identically. That is
    trivial for ordinary repository paths, which a clone already lists, and is
    meaningful protection only for a path an observer cannot guess — the
    sensitive case. Determinism is the deliberate trade: it makes the token a
    cross-reference between runs and releases (pinned by test), at the cost of
    being a confirmation oracle. Rely on the coarse shape fields for the
    CI-safe signal, never on the token's secrecy.

    Computed from the true path, not the sanitized one, so it stays a stable
    identity. For the rare path containing control characters that means the
    token will not match a hash of the printed ``path=`` form.
    """
    return hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest()[:12]


def mask_name(name: str) -> str:
    """First and last character of ``name`` with an ellipsis between.

    Never returns its input. Names of one or two characters are withheld
    entirely: an initial, a CJK surname, or a two-letter code is short *and*
    identifying, so echoing it — as an earlier revision did — turned masking
    into the identity function for a path like ``tmp/J/D.dcm``.
    """
    if not name:
        return ""
    if len(name) <= 2:
        return _WITHHELD_NAME
    return f"{name[0]}{_ELLIPSIS}{name[-1]}"


def safe_suffix(relative: Path) -> str:
    """The path's suffix when it is an allowlisted extension, else ``""``."""
    return relative.suffix if relative.suffix.lower() in _SAFE_SUFFIXES else ""


def masked_path(relative: Path) -> str:
    """Per-segment masked path, keeping an allowlisted suffix verbatim.

    ``tmp/nongui.log`` becomes ``t…p/n…i.log``. The suffix survives only when
    :func:`safe_suffix` accepts it; otherwise the whole filename is masked as
    one unit, so a name whose "suffix" is really an identifier cannot escape.
    """
    parts = relative.parts
    if not parts:
        return ""
    name = _sanitize(parts[-1])
    suffix = safe_suffix(Path(name))
    stem = name[: len(name) - len(suffix)] if suffix else name
    masked = [mask_name(_sanitize(part)) for part in parts[:-1]]
    masked.append(f"{mask_name(stem)}{suffix}")
    return "/".join(masked)


def path_shape(relative: Path, *, tracked: bool, outside_repo: bool = False) -> str:
    """Value-safe shape of a changed path: kind, top-level dir, depth, suffix.

    ``<no-suffix>`` and ``<unlisted-suffix>`` stay distinct deliberately: "no
    dot at all" versus "a dot followed by something unrecognized" is one bit
    about a filename's form, and it is the difference between hunting a stray
    ``Makefile`` and a stray ``report.2026-01-01``.
    """
    parts = relative.parts
    kind = "modified tracked file" if tracked else "new file"
    if outside_repo:
        top = _OUTSIDE_REPO
    elif len(parts) <= 1:
        top = _REPO_ROOT_TOP_LEVEL
    elif parts[0] in _PUBLIC_TOP_LEVEL:
        top = f"{parts[0]}/"
    else:
        top = _WITHHELD_TOP_LEVEL
    suffix = _NO_SUFFIX if not relative.suffix else safe_suffix(relative) or _WITHHELD_SUFFIX
    return f"{kind} in {top}, depth {len(parts)}, suffix {suffix}"


def describe_change(
    relative: Path,
    *,
    tracked: bool,
    mode: str,
    outside_repo: bool = False,
) -> str:
    """One value-safe line describing a changed path at the given hint level."""
    shape = path_shape(relative, tracked=tracked, outside_repo=outside_repo)
    detail = f"{path_token(relative)} ({shape})"
    if mode == HINT_FULL:
        return f"{detail} path={_sanitize(relative.as_posix())}"
    if mode == HINT_MASKED:
        return f"{detail} masked={masked_path(relative)}"
    return detail


def hint_footer(mode: str, *, requested: str | None = None) -> str:
    """Trailing line telling the reader how to get a more useful hint.

    ``requested`` is the raw env value, so a request that CI downgraded can say
    so rather than looking ignored — otherwise a developer whose shell or
    devcontainer exports ``CI=1`` can lose a long time wondering why the
    variable does nothing.
    """
    if mode == HINT_TOKEN and requested in {HINT_MASKED, HINT_FULL}:
        return (
            f"{CONTAINMENT_HINT_ENV}={requested} was refused because this environment "
            "looks like CI (CI / GITHUB_ACTIONS is set); showing tokens only. Unset that "
            "variable if this is actually a local run."
        )
    if mode == HINT_FULL:
        return f"Full paths shown because {CONTAINMENT_HINT_ENV}=full (local debugging only)."
    if mode == HINT_MASKED:
        return (
            f"Masked paths shown because {CONTAINMENT_HINT_ENV}=masked; "
            f"set {CONTAINMENT_HINT_ENV}=full locally for exact paths."
        )
    return (
        f"Set {CONTAINMENT_HINT_ENV}=masked (partial names) or =full (exact paths) "
        "locally to identify these; both are refused in CI and unsafe for shared logs."
    )


def collect_changes(
    before: tuple[dict[Path, str], dict[Path, str]],
    after: tuple[dict[Path, str], dict[Path, str]],
) -> list[tuple[Path, bool]]:
    """Paths whose digest differs between two snapshots, with their group.

    Tracked files are the first element of a snapshot, so the group index
    separates "a committed file was rewritten" from "a new artifact appeared" —
    different causes, different fixes, worth telling apart in the message.

    Preserves a pre-existing behaviour worth knowing about: removing a file that
    was already present at session start also counts as a change, so a test that
    tidies away a stray artifact still fails the run.
    """
    return sorted(
        (path, group_index == 0)
        for group_index, (group_before, group_after) in enumerate(zip(before, after, strict=True))
        for path in set(group_before) | set(group_after)
        if group_before.get(path) != group_after.get(path)
    )


def change_report(
    changed: list[tuple[Path, bool]],
    *,
    repo_root: Path,
    mode: str,
    max_reported: int = MAX_REPORTED_CHANGES,
    requested: str | None = None,
) -> list[str]:
    """Full value-safe report for a containment violation, or ``[]`` if clean.

    Returned as lines so the caller owns presentation and this stays testable
    without a pytest session.
    """
    if not changed:
        return []
    lines = ["ERROR: tests changed the checkout; value-safe path hint(s):"]
    for path, tracked in changed[:max_reported]:
        relative, outside_repo = _relative_to(path, repo_root)
        described = describe_change(relative, tracked=tracked, mode=mode, outside_repo=outside_repo)
        lines.append(f"  - {described}")
    remainder = len(changed) - max_reported
    if remainder > 0:
        lines.append(f"  ... and {remainder} more")
    lines.append(hint_footer(mode, requested=requested))
    return lines


def _relative_to(path: Path, repo_root: Path) -> tuple[Path, bool]:
    """Repo-relative form plus whether ``path`` lay outside the checkout.

    A path outside the checkout should be impossible here, but returning the
    bare name rather than raising keeps a reporting helper from masking the real
    failure it was called to describe. The flag is returned so the caller can
    say ``<outside-repo>`` instead of fabricating a repo-root location.
    """
    try:
        return path.relative_to(repo_root), False
    except ValueError:
        return Path(path.name), True
