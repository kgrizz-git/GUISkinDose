"""Native window geometry preferences for ``--native`` GUI mode.

Loads and saves normal (restored) window size/position and maximized state to
``~/.mypyskindose/gui.json``. This module intentionally does not import
pywebview so unit tests can run without the ``gui-native`` extra.

Demo / non-clinical mesh visibility (``show_demo_phantoms``) can also be enabled
via process env, a repo ``.env``, or a gitignored repo-local JSON — see
``show_demo_phantoms_enabled``.

Config paths support the in-progress GUISkinDose rename: reads prefer
``~/.guiskindose/gui.json`` and ``.guiskindose.local.json`` when those files
exist, and otherwise fall back to ``~/.mypyskindose/gui.json`` and
``.mypyskindose.local.json``. Writes still target the legacy paths until the
rename is complete.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mypyskindose.privacy import safe_error_event

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MIN_WIDTH = 640
MIN_HEIGHT = 480
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 768
TITLE_BAR_HEIGHT = 32
MIN_HORIZONTAL_OVERLAP = 50
MAXIMIZED_FILL_RATIO = 0.90

# Local opt-in for Settings Demo meshes (never commit true in shared configs).
SHOW_DEMO_PHANTOMS_ENV = "MYPYSKINDOSE_SHOW_DEMO_PHANTOMS"
SHOW_DEMO_PHANTOMS_ENV_NEW = "GUISKINDOSE_SHOW_DEMO_PHANTOMS"
REPO_LOCAL_GUI_CONFIG_NAME = ".mypyskindose.local.json"
REPO_LOCAL_GUI_CONFIG_NAME_NEW = ".guiskindose.local.json"


@dataclass
class ScreenBounds:
    """Logical pixel bounds for one display."""

    x: int | float
    y: int | float
    width: int | float
    height: int | float
    is_primary: bool = False

    def __post_init__(self) -> None:
        self.x = int(self.x)
        self.y = int(self.y)
        self.width = int(self.width)
        self.height = int(self.height)


@dataclass
class NativeWindowPrefs:
    """Persisted native window state (normal geometry + maximized flag)."""

    maximized: bool
    width: int
    height: int
    x: int
    y: int

    def __post_init__(self) -> None:
        self.width = int(self.width)
        self.height = int(self.height)
        self.x = int(self.x)
        self.y = int(self.y)


def config_path() -> Path:
    """Write path (and read fallback) for the legacy home GUI JSON."""
    return Path.home() / ".mypyskindose" / "gui.json"


def new_config_path() -> Path:
    """Preferred read path for the GUISkinDose home GUI JSON (PR 0 dual-read)."""
    return Path.home() / ".guiskindose" / "gui.json"


def _backup_bad_gui_config(path: Path) -> None:
    """Best-effort backup for invalid config files."""
    if not path.exists():
        return
    target = path.with_suffix(".json.corrupt")
    try:
        path.replace(target)
    except Exception as exc:
        safe_error_event(logger, "gui_config_backup", exc, level=logging.DEBUG)


def load_gui_config() -> dict[str, Any]:
    """Load the raw GUI config dict, defaulting safely on missing/invalid files."""
    new_path = new_config_path()
    old_path = config_path()
    target = new_path if new_path.exists() else old_path
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:
        safe_error_event(logger, "gui_config_load", exc, level=logging.DEBUG)
        _backup_bad_gui_config(target)
        return {}
    if not isinstance(data, dict):
        logger.debug("gui_config_non_object")
        _backup_bad_gui_config(target)
        return {}
    return data


def _parse_boolish(raw: Any) -> bool | None:
    """Parse common truthy/falsy strings; ``None`` means unset / unrecognized."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        if raw == 1:
            return True
        if raw == 0:
            return False
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return None


def _read_dotenv_value(path: Path, key: str) -> str | None:
    """Read a single ``KEY=VALUE`` from a dotenv file without loading all keys."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except Exception as exc:
        safe_error_event(logger, "demo_phantoms_dotenv_read", exc, level=logging.DEBUG)
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        name, value = stripped.split("=", 1)
        if name.strip() != key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value
    return None


def find_repo_root(start: Path | None = None) -> Path | None:
    """Return the nearest ancestor (including ``start``) that has ``pyproject.toml``."""
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "pyproject.toml").is_file():
            return candidate
    return None


def repo_local_gui_config_path(start: Path | None = None) -> Path | None:
    """Path to gitignored repo-local GUI config (new name preferred if present)."""
    root = find_repo_root(start)
    if root is None:
        return None
    new = root / REPO_LOCAL_GUI_CONFIG_NAME_NEW
    if new.is_file():
        return new
    old = root / REPO_LOCAL_GUI_CONFIG_NAME
    if old.is_file():
        return old
    return None


def _load_repo_local_gui_config(start: Path | None = None) -> dict[str, Any]:
    path = repo_local_gui_config_path(start)
    if path is None or not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        safe_error_event(logger, "repo_local_gui_config_load", exc, level=logging.DEBUG)
        return {}
    return data if isinstance(data, dict) else {}


def show_demo_phantoms_enabled(*, start: Path | None = None) -> bool:
    """Return whether Settings should list demo / non-clinical human meshes.

    First source that explicitly sets the flag wins (later sources ignored):

    1. Process env ``GUISKINDOSE_SHOW_DEMO_PHANTOMS``
    2. Process env ``MYPYSKINDOSE_SHOW_DEMO_PHANTOMS``
    3. Repo ``.env`` key ``GUISKINDOSE_SHOW_DEMO_PHANTOMS``
    4. Repo ``.env`` key ``MYPYSKINDOSE_SHOW_DEMO_PHANTOMS``
    5. Gitignored ``.guiskindose.local.json`` or ``.mypyskindose.local.json`` in the
       repo root (``{"show_demo_phantoms": true}``)
    6. ``~/.guiskindose/gui.json`` if present, else ``~/.mypyskindose/gui.json``
       (``show_demo_phantoms``)

    Missing / unrecognized values fall through. Default is ``False``.
    """
    env_raw = os.environ.get(SHOW_DEMO_PHANTOMS_ENV_NEW)
    parsed = _parse_boolish(env_raw)
    if parsed is not None:
        return parsed

    env_raw = os.environ.get(SHOW_DEMO_PHANTOMS_ENV)
    parsed = _parse_boolish(env_raw)
    if parsed is not None:
        return parsed

    root = find_repo_root(start)
    if root is not None:
        dotenv_raw = _read_dotenv_value(root / ".env", SHOW_DEMO_PHANTOMS_ENV_NEW)
        parsed = _parse_boolish(dotenv_raw)
        if parsed is not None:
            return parsed

        dotenv_raw = _read_dotenv_value(root / ".env", SHOW_DEMO_PHANTOMS_ENV)
        parsed = _parse_boolish(dotenv_raw)
        if parsed is not None:
            return parsed

        local = _load_repo_local_gui_config(start)
        if "show_demo_phantoms" in local:
            parsed = _parse_boolish(local.get("show_demo_phantoms"))
            if parsed is not None:
                return parsed

    home_raw = load_gui_config().get("show_demo_phantoms")
    parsed = _parse_boolish(home_raw)
    return bool(parsed) if parsed is not None else False


def save_gui_config(data: dict[str, Any]) -> None:
    """Atomically write the raw GUI config dict."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            delete=False,
            suffix=".tmp",
        ) as tmp:
            tmp_path = Path(tmp.name)
            json.dump(data, tmp, indent=2)
        tmp_path.replace(path)
    except Exception:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        raise


def primary_screen(screens: list[ScreenBounds]) -> ScreenBounds | None:
    if not screens:
        return None
    primaries = [s for s in screens if s.is_primary]
    if primaries:
        return max(primaries, key=lambda s: s.width * s.height)
    return max(screens, key=lambda s: s.width * s.height)


def geometry_looks_maximized(
    width: int,
    height: int,
    screens: list[ScreenBounds],
    *,
    fill_ratio: float = MAXIMIZED_FILL_RATIO,
) -> bool:
    if not screens:
        return False
    area = width * height
    return any(area >= fill_ratio * s.width * s.height for s in screens)


def title_bar_accessible_on_any_screen(
    x: int,
    y: int,
    width: int,
    _height: int,
    screens: list[ScreenBounds],
    *,
    title_bar_height: int = TITLE_BAR_HEIGHT,
    min_horizontal_overlap: int = MIN_HORIZONTAL_OVERLAP,
) -> bool:
    if not screens:
        return False
    for screen in screens:
        y_overlap = max(0, min(y + title_bar_height, screen.y + screen.height) - max(y, screen.y))
        x_overlap = max(0, min(x + width, screen.x + screen.width) - max(x, screen.x))
        if y_overlap >= title_bar_height and x_overlap >= min_horizontal_overlap:
            return True
    return False


def clamp_title_bar_on_screen(
    x: int,
    y: int,
    width: int,
    height: int,
    screen: ScreenBounds,
    *,
    title_bar_height: int = TITLE_BAR_HEIGHT,
    min_horizontal_overlap: int = MIN_HORIZONTAL_OVERLAP,
) -> tuple[int, int]:
    """Nudge origin so the title-bar strip is accessible on ``screen``."""
    del height  # width drives horizontal clamp; height unused for title-bar strip
    y_min = screen.y
    y_max = screen.y + screen.height - title_bar_height
    clamped_y = int(min(max(int(y), y_min), y_max))

    if width < min_horizontal_overlap:
        clamped_x = int(screen.x + (screen.width - width) // 2)
    else:
        x_min = screen.x + min_horizontal_overlap - width
        x_max = screen.x + screen.width - min_horizontal_overlap
        clamped_x = int(min(max(int(x), x_min), x_max))
    return clamped_x, clamped_y


def _clamp_dimensions(width: int, height: int) -> tuple[int, int]:
    return max(MIN_WIDTH, width), max(MIN_HEIGHT, height)


def default_normal_bounds(screens: list[ScreenBounds]) -> NativeWindowPrefs:
    """75% of primary/largest screen centered; fallback 1024×768 at origin."""
    screen = primary_screen(screens)
    if screen is None:
        width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT
        return NativeWindowPrefs(maximized=False, width=width, height=height, x=0, y=0)
    width = max(MIN_WIDTH, int(screen.width * 0.75))
    height = max(MIN_HEIGHT, int(screen.height * 0.75))
    x = screen.x + (screen.width - width) // 2
    y = screen.y + (screen.height - height) // 2
    return NativeWindowPrefs(
        maximized=False, width=width, height=height, x=int(x), y=int(y),
    )


def validate_prefs(prefs: NativeWindowPrefs, screens: list[ScreenBounds]) -> NativeWindowPrefs:
    width, height = _clamp_dimensions(prefs.width, prefs.height)
    maximized = prefs.maximized
    x, y = prefs.x, prefs.y

    if not screens:
        return NativeWindowPrefs(maximized=maximized, width=width, height=height, x=x, y=y)

    if title_bar_accessible_on_any_screen(x, y, width, height, screens):
        return NativeWindowPrefs(maximized=maximized, width=width, height=height, x=x, y=y)

    for screen in screens:
        cx, cy = clamp_title_bar_on_screen(x, y, width, height, screen)
        if title_bar_accessible_on_any_screen(cx, cy, width, height, screens):
            return NativeWindowPrefs(maximized=maximized, width=width, height=height, x=cx, y=cy)

    fallback = default_normal_bounds(screens)
    return NativeWindowPrefs(
        maximized=maximized,
        width=fallback.width,
        height=fallback.height,
        x=fallback.x,
        y=fallback.y,
    )


def _parse_native_window(data: dict[str, Any]) -> NativeWindowPrefs | None:
    if data.get("schema_version") != SCHEMA_VERSION:
        return None
    block = data.get("native_window")
    if not isinstance(block, dict):
        return None
    try:
        return NativeWindowPrefs(
            maximized=bool(block["maximized"]),
            width=int(block["width"]),
            height=int(block["height"]),
            x=int(block["x"]),
            y=int(block["y"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def load_native_window_prefs() -> NativeWindowPrefs | None:
    raw = load_gui_config()
    if not isinstance(raw, dict):
        return None
    return _parse_native_window(raw)


def save_native_window_prefs(prefs: NativeWindowPrefs) -> None:
    data = load_gui_config()
    data["schema_version"] = SCHEMA_VERSION
    data["native_window"] = {
        "maximized": prefs.maximized,
        "width": prefs.width,
        "height": prefs.height,
        "x": prefs.x,
        "y": prefs.y,
    }
    save_gui_config(data)
