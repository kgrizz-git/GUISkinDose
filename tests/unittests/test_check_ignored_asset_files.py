"""Unit tests for scripts/check_ignored_asset_files.py."""

from pathlib import Path

from scripts.check_ignored_asset_files import check_ignored_asset_files


def test_no_warnings_for_clean_repo_state():
    git_ls = "src/guiskindose/main.py\ndocs/source/user/figures/ExampleSkinDoseMap.png\n"
    git_status = (
        " M src/guiskindose/main.py\n"
        "!! PlotOutputs/dosemap.html\n"
        "!! PlotOutputs/right.png\n"
    )
    assert (
        check_ignored_asset_files(
            repo_root=Path("."),
            git_ls_files_output=git_ls,
            git_status_output=git_status,
        )
        is True
    )


def test_warns_tracked_but_gitignored_wiki_png():
    git_ls = "wiki/human.png\n"
    git_status = ""
    assert (
        check_ignored_asset_files(
            repo_root=Path("."),
            git_ls_files_output=git_ls,
            git_status_output=git_status,
        )
        is True
    )


def test_strict_fails_on_tracked_but_gitignored_asset():
    git_ls = "wiki/human.png\n"
    assert (
        check_ignored_asset_files(
            repo_root=Path("."),
            git_ls_files_output=git_ls,
            git_status_output="",
            strict=True,
        )
        is False
    )


def test_warns_gitignored_asset_on_disk_outside_plot_outputs():
    git_ls = ""
    git_status = "!! wiki/human.png\n"
    assert (
        check_ignored_asset_files(
            repo_root=Path("."),
            git_ls_files_output=git_ls,
            git_status_output=git_status,
        )
        is True
    )


def test_warns_untracked_html_outside_plot_outputs():
    git_ls = ""
    git_status = "?? reports/summary.html\n"
    assert (
        check_ignored_asset_files(
            repo_root=Path("."),
            git_ls_files_output=git_ls,
            git_status_output=git_status,
        )
        is True
    )


def test_skips_plot_outputs_assets():
    git_ls = ""
    git_status = "!! PlotOutputs/dosemap.html\n!! PlotOutputs/right.png\n"
    assert (
        check_ignored_asset_files(
            repo_root=Path("."),
            git_ls_files_output=git_ls,
            git_status_output=git_status,
            strict=True,
        )
        is True
    )
