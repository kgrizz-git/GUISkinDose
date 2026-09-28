"""First-run onboarding preference helpers."""

from __future__ import annotations

import logging

from guiskindose.privacy import safe_error_event

from .window_prefs import load_gui_config, save_gui_config

ONBOARDING_KEY = "onboardingDismissed"
# Versioned separately from the onboarding dismissal, so installs that already
# chose "Don't show this again" still see the intended-use notice once, and a
# future wording change can re-show it by bumping the version.
INTENDED_USE_ACK_KEY = "intendedUseAcknowledgedVersion"
INTENDED_USE_NOTICE_VERSION = 1
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


def is_intended_use_acknowledged() -> bool:
    """Return whether the user already acknowledged the current intended-use notice."""
    value = load_gui_config().get(INTENDED_USE_ACK_KEY)
    # Only a real integer counts: bool is an int subclass (a stray `true` is not
    # version 1), and floats or strings must not be truncated into a version.
    return isinstance(value, int) and not isinstance(value, bool) and value >= INTENDED_USE_NOTICE_VERSION


def acknowledge_intended_use() -> None:
    """Persist that the user saw the current intended-use notice."""
    try:
        data = load_gui_config()
        data[INTENDED_USE_ACK_KEY] = INTENDED_USE_NOTICE_VERSION
        save_gui_config(data)
    except Exception as exc:
        safe_error_event(logger, "intended_use_ack", exc, level=logging.DEBUG)
