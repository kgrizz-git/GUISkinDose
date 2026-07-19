"""Tests for GUI Plotly figure builders."""

from __future__ import annotations

import pytest

pytest.importorskip("nicegui")

from mypyskindose.plotting.plot_layout import COORDINATE_FRAME_NOTE


def test_make_dosemap_fig_includes_coordinate_frame_annotation():
    from mypyskindose.gui.figures import make_dosemap_fig

    patient = {
        "patient": {
            "patient_skin_cells": {
                "x": [0.0, 1.0, 0.0],
                "y": [0.0, 0.0, 1.0],
                "z": [0.0, 0.0, 0.0],
            },
            "triangle_vertex_indices": {"i": [0], "j": [1], "k": [2]},
        }
    }

    fig = make_dosemap_fig(explicit_dose_map=[1.0, 2.0, 3.0], explicit_patient=patient)

    assert fig is not None
    assert COORDINATE_FRAME_NOTE in fig["layout"]["annotations"][0]["text"]
    assert fig["layout"]["scene"]["xaxis"]["title"]["text"] == "X - LON / PT L-R [cm]"
    assert fig["layout"]["scene"]["yaxis"]["title"]["text"] == "Y - VER / PT A-P [cm]"
    assert fig["layout"]["scene"]["zaxis"]["title"]["text"] == "Z - LAT / PT S-I [cm]"


_PATIENT_FOR_EXPORT_TESTS = {
    "patient": {
        "patient_skin_cells": {
            "x": [0.0, 1.0, 0.0],
            "y": [0.0, 0.0, 1.0],
            "z": [0.0, 0.0, 0.0],
        },
        "triangle_vertex_indices": {"i": [0], "j": [1], "k": [2]},
    }
}


def test_make_dosemap_html_returns_html_bytes():
    from mypyskindose.gui.figures import make_dosemap_html

    patient = {
        "patient": {
            "patient_skin_cells": {
                "x": [0.0, 1.0, 0.0],
                "y": [0.0, 0.0, 1.0],
                "z": [0.0, 0.0, 0.0],
            },
            "triangle_vertex_indices": {"i": [0], "j": [1], "k": [2]},
        }
    }
    content = make_dosemap_html(explicit_dose_map=[1.0, 2.0, 3.0], explicit_patient=patient)
    assert isinstance(content, bytes)
    assert b"<html" in content.lower() or b"plotly" in content.lower()


def test_make_dosemap_html_raises_when_fig_unavailable(monkeypatch):
    from mypyskindose.gui import figures

    monkeypatch.setattr(figures, "make_dosemap_fig", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="could not be built|Dose map"):
        figures.make_dosemap_html(explicit_dose_map=[1.0], explicit_patient={"patient": {}})


def test_make_dosemap_png_returns_png_bytes():
    from mypyskindose.gui.figures import make_dosemap_png

    content = make_dosemap_png(
        explicit_dose_map=[1.0, 2.0, 3.0], explicit_patient=_PATIENT_FOR_EXPORT_TESTS
    )
    assert isinstance(content, bytes)
    assert content[:8] == b"\x89PNG\r\n\x1a\n"


def test_make_dosemap_png_raises_when_fig_unavailable(monkeypatch):
    from mypyskindose.gui import figures

    monkeypatch.setattr(figures, "make_dosemap_fig", lambda *a, **k: None)
    with pytest.raises(RuntimeError, match="could not be built|Dose map"):
        figures.make_dosemap_png(explicit_dose_map=[1.0], explicit_patient={"patient": {}})


def _assert_logs_operation_code(monkeypatch, caplog, render_fn, operation_code: str) -> None:
    """Run ``render_fn`` and assert it both raises and logs ``operation_code``.

    Attaches ``caplog``'s handler directly to the ``mypyskindose.gui.figures``
    logger instead of relying on root-logger propagation: other test modules in
    this suite exercise the CLI, which calls ``debug.configure_logging()`` and
    permanently sets ``mypyskindose.propagate = False`` for the rest of the test
    session (it is idempotent via a module-level flag, so nothing resets it).
    Depending on propagation-to-root would make this test's outcome depend on
    unrelated test ordering; attaching the handler here keeps it order-independent.
    """
    import logging

    from mypyskindose.gui import figures

    def _boom(*a, **k):
        raise ValueError("synthetic render failure")

    monkeypatch.setattr(figures, "make_dosemap_fig", _boom)
    target_logger = logging.getLogger("mypyskindose.gui.figures")
    target_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level("ERROR", logger="mypyskindose.gui.figures"):
            with pytest.raises(ValueError, match="synthetic render failure"):
                render_fn(explicit_dose_map=[1.0], explicit_patient={"patient": {}})
    finally:
        target_logger.removeHandler(caplog.handler)
    assert any(operation_code in rec.message for rec in caplog.records)


def test_make_dosemap_html_raises_and_logs_on_render_exception(monkeypatch, caplog):
    """A downstream failure (not just a None fig) must also raise, not swallow."""
    from mypyskindose.gui.figures import make_dosemap_html

    _assert_logs_operation_code(monkeypatch, caplog, make_dosemap_html, "dosemap_html_render")


def test_make_dosemap_png_raises_and_logs_on_render_exception(monkeypatch, caplog):
    from mypyskindose.gui.figures import make_dosemap_png

    _assert_logs_operation_code(monkeypatch, caplog, make_dosemap_png, "dosemap_png_render")
