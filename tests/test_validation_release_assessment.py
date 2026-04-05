from pathlib import Path

import pandas as pd


REPORTS = Path(__file__).resolve().parents[1] / "reports"


def _as_bool(v: object) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() == "true"


def test_validation_release_assessment_exists_and_has_required_fields() -> None:
    release_path = REPORTS / "validation_release_assessment.csv"
    summary_path = REPORTS / "validation_summary.csv"

    assert release_path.exists()
    assert summary_path.exists()

    release = pd.read_csv(release_path)
    summary = pd.read_csv(summary_path)

    required_cols = {
        "release_state",
        "technical_gate_passed",
        "analytical_gate_passed",
        "technically_valid",
        "analytically_acceptable",
        "decision_support_only",
        "screening_grade_only",
        "not_committee_grade",
        "publish_blocked",
        "committee_grade_ready",
        "critical_issues",
        "high_issues",
        "medium_issues",
        "low_issues",
        "blocker_count",
        "warning_count",
        "min_module_confidence",
        "rationale",
    }
    assert required_cols.issubset(release.columns)
    assert {"release_state", "publish_blocked", "committee_grade_ready"}.issubset(summary.columns)


def test_validation_release_assessment_logic_is_coherent() -> None:
    release = pd.read_csv(REPORTS / "validation_release_assessment.csv").iloc[0]
    summary = pd.read_csv(REPORTS / "validation_summary.csv").iloc[0]

    allowed_states = {
        "technically valid",
        "analytically acceptable",
        "decision-support only",
        "screening-grade only",
        "not committee-grade",
        "publish-blocked",
    }
    assert release["release_state"] in allowed_states
    assert release["release_state"] == summary["release_state"]
    assert _as_bool(release["publish_blocked"]) == _as_bool(summary["publish_blocked"])
    assert _as_bool(release["committee_grade_ready"]) == _as_bool(summary["committee_grade_ready"])

    if _as_bool(release["publish_blocked"]):
        assert release["release_state"] == "publish-blocked"
        assert int(release["blocker_count"]) > 0

    if release["release_state"] == "technically valid":
        assert int(release["critical_issues"]) == 0
        assert int(release["high_issues"]) == 0
        assert int(release["medium_issues"]) == 0
        assert int(release["low_issues"]) == 0
