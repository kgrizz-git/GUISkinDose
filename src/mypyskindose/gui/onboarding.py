"""First-run onboarding preference helpers."""

from __future__ import annotations

from mypyskindose.debug import dprint

from .window_prefs import load_gui_config, save_gui_config

ONBOARDING_KEY = "onboardingDismissed"


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
        dprint("GUI", f"Failed to persist onboarding dismissal: {exc}")


def reset_onboarding() -> None:
    """Re-enable first-run onboarding."""
    try:
        data = load_gui_config()
        data[ONBOARDING_KEY] = False
        save_gui_config(data)
    except Exception as exc:
        dprint("GUI", f"Failed to reset onboarding: {exc}")
