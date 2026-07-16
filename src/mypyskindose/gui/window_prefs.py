"""Native window geometry preferences for ``--native`` GUI mode.

Loads and saves normal (restored) window size/position and maximized state to
``~/.mypyskindose/gui.json``. This module intentionally does not import
pywebview so unit tests can run without the ``gui-native`` extra.
"""

from __future__ import annotations

import json
import logging
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
    return Path.home() / ".mypyskindose" / "gui.json"


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
    path = config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as exc:
        safe_error_event(logger, "gui_config_load", exc, level=logging.DEBUG)
        _backup_bad_gui_config(path)
        return {}
    if not isinstance(data, dict):
        logger.debug("gui_config_non_object")
        _backup_bad_gui_config(path)
        return {}
    return data


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
    height: int,
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
