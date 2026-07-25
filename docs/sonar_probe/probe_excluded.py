"""TEMPORARY SonarCloud analysis probe — EXCLUDED via a wildcard in .sonarcloud.properties.

Part of a wildcard-exclusion experiment on this PR. Delete after the result is read.
If Automatic Analysis honors wildcard exclusions in .sonarcloud.properties, the
python:S1192 duplicated-literal signal below should NOT appear and this file should NOT
be in the analyzed component list; if it does appear, wildcard exclusions are ignored.
"""


def probe_excluded_markers() -> list[str]:
    return [
        "sonar_probe_duplicated_literal_value",
        "sonar_probe_duplicated_literal_value",
        "sonar_probe_duplicated_literal_value",
        "sonar_probe_duplicated_literal_value",
    ]
