"""Unit tests for CLI kerma-meter correction flag wiring."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pytest

from guiskindose import load_settings_example_json
from guiskindose.cli_kerma_meter import (
    add_kerma_meter_cli_arguments,
    apply_kerma_meter_cli_flags,
)
from guiskindose.settings import PyskindoseSettings


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
    assert km.ask_for_missing is True  # legacy "file" mode is a no-op
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
    """Legacy mode=prompt maps to ask_for_missing and logs a deprecation warning.

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

    logger = logging.getLogger("guiskindose.settings.kerma_meter_correction_settings")
    handler = _Capture(level=logging.WARNING)
    logger.addHandler(handler)
    try:
        apply_kerma_meter_cli_flags(settings, args)
    finally:
        logger.removeHandler(handler)

    assert settings.kerma_meter_correction.ask_for_missing is True
    assert any("deprecated" in msg for msg in messages)


def test_mode_flag_help_says_deprecated():
    """The legacy --kerma-meter-correction-mode flag is documented as deprecated."""
    parser = argparse.ArgumentParser()
    add_kerma_meter_cli_arguments(parser)
    assert "DEPRECATED" in parser.format_help()


def test_cli_legacy_prompt_does_not_override_explicit_ask_for_missing_false():
    """An explicit ask_for_missing=False in the settings wins over --kerma-meter-correction-mode prompt."""
    from guiskindose.settings.kerma_meter_correction_settings import KermaMeterCorrectionSettings

    settings = _settings()
    settings.kerma_meter_correction = KermaMeterCorrectionSettings({"ask_for_missing": False})
    args = argparse.Namespace(
        kerma_meter_correction=False,
        kerma_meter_correction_file=None,
        kerma_meter_correction_mode="prompt",
        kerma_meter_explicit_label=None,
    )
    apply_kerma_meter_cli_flags(settings, args)
    assert settings.kerma_meter_correction.ask_for_missing is False


def test_prepare_cli_settings_reports_a_missing_settings_path_cleanly(tmp_path):
    import argparse

    from guiskindose.main import prepare_cli_settings

    args = argparse.Namespace(settings=str(tmp_path / "missing.json"))
    with pytest.raises(SystemExit) as excinfo:
        prepare_cli_settings(args)
    message = str(excinfo.value)
    assert message
    assert str(tmp_path) not in message
    assert "missing.json" not in message


def test_prepare_cli_settings_still_accepts_a_json_string_and_a_path(tmp_path):
    import argparse
    import json

    from guiskindose import load_settings_example_json
    from guiskindose.main import prepare_cli_settings

    payload = json.dumps(load_settings_example_json())
    from_string = prepare_cli_settings(argparse.Namespace(settings=payload))
    path = tmp_path / "s.json"
    path.write_text(payload, encoding="utf-8")
    from_path = prepare_cli_settings(argparse.Namespace(settings=str(path)))
    assert from_string.k_tab_mode == from_path.k_tab_mode == "measured_with_fallback"
