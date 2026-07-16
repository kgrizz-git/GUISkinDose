"""First-run onboarding preference helpers."""

from __future__ import annotations

import logging

from mypyskindose.privacy import safe_error_event

from .window_prefs import load_gui_config, save_gui_config

ONBOARDING_KEY = "onboardingDismissed"
logger = logging.getLogger(__name__)


def is_onboarding_dismissed() -> bool:
    """Return whether the user chose to stop showing first-run onboarding."""
    data = load_gui_config()
    return bool(data.get(ONBOARDING_KEY, False))


def dismiss_onboarding() -> None:
    """Persist the user's choice to stop showing first-run onboarding."""
    try:
        data = load_gui_config()
        data[ONBOARDING_KEY] = True
        save_gui_config(data)
    except Exception as exc:
        safe_error_event(logger, "onboarding_dismiss", exc, level=logging.DEBUG)


def reset_onboarding() -> None:
    """Re-enable first-run onboarding."""
    try:
        data = load_gui_config()
        data[ONBOARDING_KEY] = False
        save_gui_config(data)
    except Exception as exc:
        safe_error_event(logger, "onboarding_reset", exc, level=logging.DEBUG)
