"""Unit tests for GUI equipment-profile match block collectors."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

from guiskindose.gui.equipment_profile_surfaces import (
    post_calc_equipment_profile_blocks,
    pre_calc_equipment_profile_blocks,
)


def _match(profile_id: str = "p1") -> dict:
    return {
        "profile_id": profile_id,
        "source": "custom",
        "level": "exact",
        "notice": {"kind": "partial", "entries": [], "text": "partial match notice"},
    }


def test_pre_calc_skips_exams_without_capture() -> None:
    app_state = SimpleNamespace(
        is_multi_exam=False,
        loaded_exams=[SimpleNamespace(equipment_capture=None)],
    )
    assert pre_calc_equipment_profile_blocks(cast(Any, app_state)) == []


def test_pre_calc_single_exam_unlabelled() -> None:
    capture = object()
    app_state = SimpleNamespace(
        is_multi_exam=False,
        loaded_exams=[SimpleNamespace(equipment_capture=capture)],
    )
    with mock.patch(
        "guiskindose.gui.equipment_profile_surfaces.capture_to_mapping",
        return_value={"match": _match()},
    ):
        blocks = pre_calc_equipment_profile_blocks(cast(Any, app_state))
    assert blocks == [(None, _match())]


def test_pre_calc_multi_exam_labels() -> None:
    app_state = SimpleNamespace(
        is_multi_exam=True,
        loaded_exams=[
            SimpleNamespace(equipment_capture=object()),
            SimpleNamespace(equipment_capture=None),
            SimpleNamespace(equipment_capture=object()),
        ],
    )
    with mock.patch(
        "guiskindose.gui.equipment_profile_surfaces.capture_to_mapping",
        side_effect=[{"match": _match("a")}, {"match": _match("b")}],
    ):
        blocks = pre_calc_equipment_profile_blocks(cast(Any, app_state))
    assert blocks == [("Exam 1", _match("a")), ("Exam 3", _match("b"))]


def test_pre_calc_forged_capture_returns_none() -> None:
    app_state = SimpleNamespace(
        is_multi_exam=False,
        loaded_exams=[SimpleNamespace(equipment_capture=object())],
    )
    with mock.patch(
        "guiskindose.gui.equipment_profile_surfaces.capture_to_mapping",
        side_effect=ValueError("invalid"),
    ):
        assert pre_calc_equipment_profile_blocks(cast(Any, app_state)) == []


def test_post_calc_single_dict_output() -> None:
    app_state = SimpleNamespace(
        is_multi_exam=False,
        multi_exam_result=None,
        output={"equipment_profile_match": _match()},
    )
    assert post_calc_equipment_profile_blocks(cast(Any, app_state)) == [(None, _match())]


def test_post_calc_non_dict_output_empty() -> None:
    app_state = SimpleNamespace(is_multi_exam=False, multi_exam_result=None, output=object())
    assert post_calc_equipment_profile_blocks(cast(Any, app_state)) == []


def test_post_calc_multi_mixed_matches() -> None:
    app_state = SimpleNamespace(
        is_multi_exam=True,
        multi_exam_result=SimpleNamespace(
            exams=[
                SimpleNamespace(exam_id="opaque-a", equipment_profile_match=_match("yes"), output=object()),
                SimpleNamespace(exam_id="opaque-b", equipment_profile_match=None, output=object()),
            ]
        ),
        output=None,
    )
    blocks = post_calc_equipment_profile_blocks(cast(Any, app_state))
    assert blocks == [("opaque-a", _match("yes"))]
