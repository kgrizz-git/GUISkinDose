"""Tests for the tqdm progress hook's UI labels and fractions."""

from __future__ import annotations

import pytest

from guiskindose.gui.helpers import _patch_tqdm


def _patched_calls(total: int, actions):
    """Run *actions(bar)* with the hook installed; return recorded callbacks."""
    import io

    import tqdm as tqdm_module
    from tqdm import tqdm

    calls: list[tuple[float, str]] = []
    original_update = tqdm_module.tqdm.update
    restore = _patch_tqdm(lambda fraction, label: calls.append((fraction, label)), total=total)
    try:
        # Not disable=True: a disabled bar short-circuits update() before
        # advancing n. Render into a throwaway stream instead.
        bar = tqdm(total=total, file=io.StringIO())
        actions(bar)
        bar.close()
    finally:
        restore()
    assert tqdm_module.tqdm.update is original_update
    return calls


def test_completed_events_keep_plain_label():
    calls = _patched_calls(10, lambda bar: bar.update())
    assert calls == [(pytest.approx(0.1), "Event 1 / 10")]


def test_mid_event_fraction_shows_pose_percent():
    calls = _patched_calls(10, lambda bar: (bar.update(), bar.update(0.35)))
    fraction, label = calls[-1]
    assert fraction == pytest.approx(0.135)
    assert label == "Event 1 / 10 (rotational poses 35%)"


def test_near_integer_float_renders_as_completed_event():
    calls = _patched_calls(10, lambda bar: bar.update(2.9999999999999996))
    fraction, label = calls[-1]
    assert fraction == pytest.approx(0.3)
    assert label == "Event 3 / 10"


def test_fraction_is_clamped_to_unit_interval():
    calls = _patched_calls(2, lambda bar: bar.update(5))
    fraction, _label = calls[-1]
    assert fraction == pytest.approx(1.0)


def test_restore_prevents_stacked_hooks_across_runs():
    """A second run must not re-fire the first run's callback."""
    first = _patched_calls(10, lambda bar: bar.update())
    second = _patched_calls(10, lambda bar: bar.update())
    assert len(first) == len(second) == 1
