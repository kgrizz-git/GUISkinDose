"""Unit tests for CLI kerma-meter correction flag wiring."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from mypyskindose import load_settings_example_json
from mypyskindose.cli_kerma_meter import (
    add_kerma_meter_cli_arguments,
    apply_kerma_meter_cli_flags,
)
from mypyskindose.settings import PyskindoseSettings


def _settings() -> PyskindoseSettings:
    """Fresh settings object with default kerma-meter block."""
    return PyskindoseSettings(settings=load_settings_example_json())


def test_add_kerma_meter_cli_arguments_registers_flags():
    """Parser exposes the four --kerma-meter-* options."""
    parser = argparse.ArgumentParser()
    add_kerma_meter_cli_arguments(parser)
    args = parser.parse_args(
        [
            "--kerma-meter-correction",
            "--kerma-meter-correction-file",
            "cf.csv",
            "--kerma-meter-correction-mode",
            "file",
            "--kerma-meter-explicit-label",
            "unit-01",
        ]
    )
    assert args.kerma_meter_correction is True
    assert args.kerma_meter_correction_file == Path("cf.csv")
    assert args.kerma_meter_correction_mode == "file"
    assert args.kerma_meter_explicit_label == "unit-01"


def test_apply_flags_enable_file_mode_and_label(tmp_path: Path):
    """File path forces enable and populates file/mode/label fields."""
    settings = _settings()
    cf = tmp_path / "factors.csv"
    cf.write_text("equipment,tube,correction_factor\nunit,single,1.1\n", encoding="utf-8")
    args = argparse.Namespace(
        kerma_meter_correction=False,
        kerma_meter_correction_file=cf,
        kerma_meter_correction_mode="file",
        kerma_meter_explicit_label="forced-unit",
    )
    apply_kerma_meter_cli_flags(settings, args)
    km = settings.kerma_meter_correction
    assert km.enable is True
    assert km.file == cf
    assert km.mode == "file"
    assert km.explicit_label == "forced-unit"


def test_apply_flags_enable_switch_alone():
    """Bare --kerma-meter-correction enables CF without requiring a file."""
    settings = _settings()
    args = argparse.Namespace(
        kerma_meter_correction=True,
        kerma_meter_correction_file=None,
        kerma_meter_correction_mode=None,
        kerma_meter_explicit_label=None,
    )
    apply_kerma_meter_cli_flags(settings, args)
    assert settings.kerma_meter_correction.enable is True
    assert settings.kerma_meter_correction.file is None


def test_prompt_mode_warns_on_cli():
    """mode=prompt is accepted but warns that CLI falls soft to default_factor.

    Attach a handler to the module logger — suite-wide logging state can leave
    WARNING on stderr without landing in pytest ``caplog``.
    """
    settings = _settings()
    args = argparse.Namespace(
        kerma_meter_correction=True,
        kerma_meter_correction_file=None,
        kerma_meter_correction_mode="prompt",
        kerma_meter_explicit_label=None,
    )
    messages: list[str] = []

    class _Capture(logging.Handler):
        """Collect log record messages for assertions."""

        def emit(self, record: logging.LogRecord) -> None:
            """Append the formatted log message to the capture list."""
            messages.append(record.getMessage())

    logger = logging.getLogger("mypyskindose.cli_kerma_meter")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        apply_kerma_meter_cli_flags(settings, args)
    finally:
        logger.removeHandler(handler)

    assert settings.kerma_meter_correction.mode == "prompt"
    assert any("GUI-only" in msg for msg in messages)
