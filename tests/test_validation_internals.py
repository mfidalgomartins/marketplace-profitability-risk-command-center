"""In-process tests for the validation engine's pure logic and an end-to-end
recomputation against the committed synthetic dataset."""

from pathlib import Path

import pandas as pd
import pytest
from src.validation import run_full_validation as rfv_module
from src.validation.enforce_release_gate import _as_bool
from src.validation.run_full_validation import (
    ValidationConfig,
    _coverage_summary,
    _release_assessment,
    _render_report,
    _tier,
    run_validation,
    save_outputs,
)

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.0, "Low"),
        (29.9, "Low"),
        (30.0, "Moderate"),
        (54.9, "Moderate"),
        (55.0, "High"),
        (74.9, "High"),
        (75.0, "Critical"),
        (100.0, "Critical"),
    ],
)
def test_tier_boundaries(score: float, expected: str) -> None:
    assert _tier(score) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, True),
        (False, False),
        ("True", True),
        ("true", True),
        ("  TRUE ", True),
        ("False", False),
        ("anything", False),
    ],
)
def test_as_bool(value: object, expected: bool) -> None:
    assert _as_bool(value) is expected


def test_coverage_summary_classifies_modules() -> None:
    issues = pd.DataFrame(
        [
            {"module": "scoring", "severity": "Critical"},
            {"module": "narrative", "severity": "Low"},
        ]
    )
    summary = _coverage_summary(issues).set_index("module")
    assert summary.loc["scoring", "validation_status"] == "blocked"
    assert summary.loc["scoring", "blocker_issues"] == 1
    assert summary.loc["narrative", "validation_status"] == "passed_with_warnings"
    # A module configured with checks but no issues is fully passed.
    assert summary.loc["synthetic_data", "validation_status"] == "passed"


def test_release_assessment_empty_summary_is_publish_blocked() -> None:
    row = _release_assessment(pd.DataFrame(), pd.DataFrame()).iloc[0]
    assert row["release_state"] == "publish-blocked"
    assert row["publish_blocked"]


def _summary(critical=0, high=0, medium=0, low=0) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "critical_issues": critical,
                "high_issues": high,
                "medium_issues": medium,
                "low_issues": low,
            }
        ]
    )


def test_release_assessment_clean_is_decision_support() -> None:
    row = _release_assessment(pd.DataFrame(columns=["severity", "module", "check_name"]), _summary()).iloc[0]
    assert row["release_state"] == "decision-support only"
    assert not row["publish_blocked"]
    assert row["public_release_ready"]
    assert not row["committee_grade_ready"]  # never auto-promoted to committee grade


def test_release_assessment_critical_issue_blocks_publication() -> None:
    issues = pd.DataFrame([{"severity": "Critical", "module": "scoring", "check_name": "x"}])
    row = _release_assessment(issues, _summary(critical=1)).iloc[0]
    assert row["release_state"] == "publish-blocked"
    assert row["publish_blocked"]


def test_release_assessment_nonblocker_warnings_are_screening_grade() -> None:
    # A high-severity issue outside the blocker modules/checks is a warning,
    # not a publication blocker, so the release drops to screening grade.
    issues = pd.DataFrame([{"severity": "High", "module": "narrative", "check_name": "tone"}])
    row = _release_assessment(issues, _summary(high=1)).iloc[0]
    assert row["release_state"] == "screening-grade only"
    assert not row["publish_blocked"]
    assert not row["public_release_ready"]


def test_run_validation_against_committed_data_matches_release_assessment() -> None:
    """Recompute the entire validation suite in-process and confirm it agrees
    with the committed release assessment artifact."""
    results = run_validation(ValidationConfig(raw_dir=ROOT / "data" / "raw", processed_dir=ROOT / "data" / "processed"))
    recomputed = results["release"].iloc[0]
    committed = pd.read_csv(ROOT / "reports" / "validation_release_assessment.csv").iloc[0]

    assert recomputed["release_state"] == committed["release_state"] == "decision-support only"
    assert bool(recomputed["publish_blocked"]) is False
    assert int(recomputed["critical_issues"]) == 0
    # Coverage summary covers every configured module.
    assert not results["coverage"].empty
    assert set(results["issues"].columns) >= {"severity", "module", "check_name"}


def test_render_report_and_save_outputs(tmp_path: Path) -> None:
    results = run_validation(ValidationConfig(raw_dir=RAW, processed_dir=PROC))
    report = _render_report(results)
    assert "# " in report  # has a markdown heading
    assert "decision-support only" in report

    cfg = ValidationConfig(raw_dir=RAW, processed_dir=PROC, report_dir=tmp_path)
    out = save_outputs(results, cfg)
    for path in out.values():
        assert path.exists()
    assert (tmp_path / "validation_report.md").read_text(encoding="utf-8").strip()


def test_run_full_validation_cli_writes_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_full_validation.py",
            "--raw-dir",
            str(RAW),
            "--processed-dir",
            str(PROC),
            "--report-dir",
            str(tmp_path),
            "--schema-file",
            str(ROOT / "config" / "contracts" / "v1" / "schema_contracts.json"),
            "--metric-contract-file",
            str(ROOT / "config" / "contracts" / "v1" / "metric_governance_contract.csv"),
        ],
    )
    rfv_module.main()
    assert (tmp_path / "validation_report.md").exists()
    assert (tmp_path / "validation_release_assessment.csv").exists()
    assert "Validation outputs written" in capsys.readouterr().out
