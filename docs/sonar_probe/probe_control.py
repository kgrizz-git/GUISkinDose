"""TEMPORARY SonarCloud analysis probe — CONTROL (not excluded).

Part of a wildcard-exclusion experiment on this PR. Delete after the result is read.
The duplicated string literal below is a deliberate Sonar python:S1192 signal so we
can confirm this file was analyzed.
"""


def probe_control_markers() -> list[str]:
    return [
        "sonar_probe_duplicated_literal_value",
        "sonar_probe_duplicated_literal_value",
        "sonar_probe_duplicated_literal_value",
        "sonar_probe_duplicated_literal_value",
    ]
