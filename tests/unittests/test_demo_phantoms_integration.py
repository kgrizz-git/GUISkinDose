"""Integration tests for demo-phantom gating (meshes are no longer shipped).

Demo STLs were removed from ``phantom_data/`` (2026-07-24). A local recovery
stash may exist under gitignored ``tmp/phantom_data_demo_stash/``. These tests
cover the Settings gate helpers and ensure no demo stems appear in discovery.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("nicegui")

from mypyskindose.gui.helpers import (
    DEMO_HUMAN_MESHES,
    DEMO_MESH_SECTION_KEY,
    GUI_HIDDEN_HUMAN_MESHES,
    get_human_mesh_names,
    get_human_mesh_options,
)

PHANTOM_DATA = Path(__file__).resolve().parents[2] / "src" / "mypyskindose" / "phantom_data"
KNOWN_DEMO_STEMS = sorted(DEMO_HUMAN_MESHES | GUI_HIDDEN_HUMAN_MESHES)


@pytest.mark.parametrize("mesh_name", KNOWN_DEMO_STEMS)
def test_demo_meshes_are_not_shipped(mesh_name: str):
    assert not (PHANTOM_DATA / f"{mesh_name}.stl").exists()
    assert not (PHANTOM_DATA / f"{mesh_name}_reduced_1000t.stl").exists()
    assert not (PHANTOM_DATA / f"{mesh_name}_reduced_3000t.stl").exists()


def test_discovered_meshes_exclude_demo_stems():
    names = get_human_mesh_names()
    for mesh_name in KNOWN_DEMO_STEMS:
        assert mesh_name not in names
    options = get_human_mesh_options(include_demos=True)
    for mesh_name in KNOWN_DEMO_STEMS:
        assert mesh_name not in options
    assert DEMO_MESH_SECTION_KEY not in options
    assert "adult_female" in options
    assert "Mickey" not in str(options.values())


def test_show_demo_phantoms_enabled_defaults_false(monkeypatch, tmp_path):
    from mypyskindose.gui import window_prefs

    cfg = tmp_path / "gui.json"
    monkeypatch.setattr(window_prefs, "config_path", lambda: cfg)
    monkeypatch.delenv(window_prefs.SHOW_DEMO_PHANTOMS_ENV, raising=False)
    monkeypatch.setattr(window_prefs, "find_repo_root", lambda start=None: None)
    assert window_prefs.show_demo_phantoms_enabled() is False
    cfg.write_text('{"show_demo_phantoms": true}\n', encoding="utf-8")
    assert window_prefs.show_demo_phantoms_enabled() is True


def test_show_demo_phantoms_env_overrides_home_gui_json(monkeypatch, tmp_path):
    from mypyskindose.gui import window_prefs

    cfg = tmp_path / "gui.json"
    cfg.write_text('{"show_demo_phantoms": true}\n', encoding="utf-8")
    monkeypatch.setattr(window_prefs, "config_path", lambda: cfg)
    monkeypatch.setattr(window_prefs, "find_repo_root", lambda start=None: None)
    monkeypatch.setenv(window_prefs.SHOW_DEMO_PHANTOMS_ENV, "0")
    assert window_prefs.show_demo_phantoms_enabled() is False
    monkeypatch.setenv(window_prefs.SHOW_DEMO_PHANTOMS_ENV, "yes")
    assert window_prefs.show_demo_phantoms_enabled() is True


def test_show_demo_phantoms_new_env_wins_over_old_env(monkeypatch, tmp_path):
    from mypyskindose.gui import window_prefs

    cfg = tmp_path / "gui.json"
    cfg.write_text('{"show_demo_phantoms": true}\n', encoding="utf-8")
    monkeypatch.setattr(window_prefs, "config_path", lambda: cfg)
    monkeypatch.setattr(window_prefs, "find_repo_root", lambda start=None: None)
    monkeypatch.setenv(window_prefs.SHOW_DEMO_PHANTOMS_ENV, "1")
    monkeypatch.setenv(window_prefs.SHOW_DEMO_PHANTOMS_ENV_NEW, "0")
    assert window_prefs.show_demo_phantoms_enabled() is False


def test_show_demo_phantoms_unrecognized_new_env_falls_through_to_old_env(monkeypatch, tmp_path):
    from mypyskindose.gui import window_prefs

    cfg = tmp_path / "gui.json"
    cfg.write_text('{"show_demo_phantoms": true}\n', encoding="utf-8")
    monkeypatch.setattr(window_prefs, "config_path", lambda: cfg)
    monkeypatch.setattr(window_prefs, "find_repo_root", lambda start=None: None)
    monkeypatch.setenv(window_prefs.SHOW_DEMO_PHANTOMS_ENV_NEW, "bogus")
    monkeypatch.setenv(window_prefs.SHOW_DEMO_PHANTOMS_ENV, "1")
    assert window_prefs.show_demo_phantoms_enabled() is True


def test_show_demo_phantoms_new_local_json_wins_over_old_local_json(monkeypatch, tmp_path):
    from mypyskindose.gui import window_prefs

    (tmp_path / "pyproject.toml").write_text('[project]\nname = "mypyskindose"\n', encoding="utf-8")
    home_cfg = tmp_path / "home_gui.json"
    home_cfg.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(window_prefs, "config_path", lambda: home_cfg)
    monkeypatch.delenv(window_prefs.SHOW_DEMO_PHANTOMS_ENV_NEW, raising=False)
    monkeypatch.delenv(window_prefs.SHOW_DEMO_PHANTOMS_ENV, raising=False)
    monkeypatch.setattr(window_prefs, "find_repo_root", lambda start=None: tmp_path)

    new_local = tmp_path / window_prefs.REPO_LOCAL_GUI_CONFIG_NAME_NEW
    new_local.write_text('{"show_demo_phantoms": true}\n', encoding="utf-8")
    assert window_prefs.show_demo_phantoms_enabled(start=tmp_path) is True

    # New file present but without the key wins the path slot; old file is not consulted.
    new_local.write_text("{}\n", encoding="utf-8")
    old_local = tmp_path / window_prefs.REPO_LOCAL_GUI_CONFIG_NAME
    old_local.write_text('{"show_demo_phantoms": true}\n', encoding="utf-8")
    assert window_prefs.show_demo_phantoms_enabled(start=tmp_path) is False

    # Removing the new file falls back to the old one.
    new_local.unlink()
    assert window_prefs.show_demo_phantoms_enabled(start=tmp_path) is True


def test_show_demo_phantoms_new_dotenv_wins_over_old_dotenv(monkeypatch, tmp_path):
    from mypyskindose.gui import window_prefs

    (tmp_path / "pyproject.toml").write_text('[project]\nname = "mypyskindose"\n', encoding="utf-8")
    home_cfg = tmp_path / "home_gui.json"
    home_cfg.write_text('{"show_demo_phantoms": true}\n', encoding="utf-8")
    monkeypatch.setattr(window_prefs, "config_path", lambda: home_cfg)
    monkeypatch.delenv(window_prefs.SHOW_DEMO_PHANTOMS_ENV_NEW, raising=False)
    monkeypatch.delenv(window_prefs.SHOW_DEMO_PHANTOMS_ENV, raising=False)
    monkeypatch.setattr(window_prefs, "find_repo_root", lambda start=None: tmp_path)

    (tmp_path / ".env").write_text(
        f"# local\n{window_prefs.SHOW_DEMO_PHANTOMS_ENV}=true\n",
        encoding="utf-8",
    )
    assert window_prefs.show_demo_phantoms_enabled(start=tmp_path) is True

    (tmp_path / ".env").write_text(
        f"# local\n{window_prefs.SHOW_DEMO_PHANTOMS_ENV_NEW}=false\n",
        encoding="utf-8",
    )
    assert window_prefs.show_demo_phantoms_enabled(start=tmp_path) is False
