"""Unit tests for scripts/check_untracked_scratch.py."""
from scripts.check_untracked_scratch import check_untracked_scratch


def test_check_untracked_scratch_no_scratch_files():
    # Mock git output with no scratch files
    git_output = (
        " M src/guiskindose/gui/app.py\n"
        "?? src/guiskindose/new_feature.py\n"
        "?? tests/unittests/test_new_feature.py\n"
    )
    assert check_untracked_scratch(mock_git_output=git_output) is True

def test_check_untracked_scratch_detects_scratch_file():
    # Mock git output containing an untracked scratch file
    git_output = (
        "?? scripts/scratch_test.py\n"
        "?? debug_dump.json\n"
    )
    assert check_untracked_scratch(mock_git_output=git_output) is False

def test_check_untracked_scratch_detects_temp_file():
    # Mock git output containing an untracked temp file
    git_output = (
        "?? some_temp_file.txt\n"
    )
    assert check_untracked_scratch(mock_git_output=git_output) is False

def test_check_untracked_scratch_detects_tmp_directory_file():
    git_output = "?? tmp/assessment.md\n"
    assert check_untracked_scratch(mock_git_output=git_output) is False

def test_check_untracked_scratch_excludes_self():
    # Mock git output containing the script itself
    git_output = (
        "?? scripts/check_untracked_scratch.py\n"
    )
    assert check_untracked_scratch(mock_git_output=git_output) is True
