from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(step_name: str, cmd: list[str]) -> None:
    print(f"[pipeline] {step_name}")
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run full marketplace analytics pipeline end-to-end.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--charts-dir", type=Path, default=Path("outputs/charts"))
    parser.add_argument(
        "--dashboard-file",
        type=Path,
        default=Path("outputs/dashboard/executive-marketplace-command-center.html"),
    )
    parser.add_argument(
        "--pages-dashboard-file",
        type=Path,
        default=Path("docs/executive-marketplace-command-center.html"),
    )
    parser.add_argument(
        "--pages-index-file",
        type=Path,
        default=Path("docs/index.html"),
    )
    parser.add_argument("--monte-carlo-iterations", type=int, default=2000)
    parser.add_argument("--schema-file", type=Path, default=Path("config/contracts/v1/schema_contracts.json"))
    parser.add_argument("--metric-contract-file", type=Path, default=Path("config/contracts/v1/metric_governance_contract.csv"))
    parser.add_argument("--schema-history-dir", type=Path, default=Path("config/contracts/history"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument(
        "--required-release-state",
        type=str,
        default="decision-support only",
        choices=[
            "publish-blocked",
            "screening-grade only",
            "decision-support only",
            "analytically acceptable",
            "technically valid",
        ],
    )
    parser.add_argument("--require-committee-grade", action="store_true")
    args = parser.parse_args()

    py = sys.executable

    _run(
        "generate synthetic data",
        [
            py,
            "src/data_generation/generate_synthetic_marketplace_data.py",
            "--output-dir",
            str(args.raw_dir),
        ],
    )
    _run(
        "build feature layer",
        [
            py,
            "src/features/build_analytical_feature_layer.py",
            "--raw-dir",
            str(args.raw_dir),
            "--output-dir",
            str(args.processed_dir),
        ],
    )
    _run(
        "build scoring layer",
        [
            py,
            "src/scoring/build_scoring_framework.py",
            "--raw-dir",
            str(args.raw_dir),
            "--processed-dir",
            str(args.processed_dir),
        ],
    )
    _run(
        "build governance action register",
        [
            py,
            "src/governance/build_governance_action_register.py",
            "--processed-dir",
            str(args.processed_dir),
            "--output-dir",
            str(args.processed_dir),
        ],
    )
    _run(
        "build scenario analysis",
        [
            py,
            "src/scenario_analysis/build_scenario_decision_analysis.py",
            "--raw-dir",
            str(args.raw_dir),
            "--processed-dir",
            str(args.processed_dir),
            "--baseline-months",
            "6",
            "--horizon-months",
            "6",
        ],
    )
    _run(
        "run scenario monte carlo",
        [
            py,
            "src/scenario_analysis/run_scenario_monte_carlo.py",
            "--processed-dir",
            str(args.processed_dir),
            "--output-dir",
            str(args.processed_dir),
            "--charts-dir",
            str(args.charts_dir),
            "--iterations",
            str(args.monte_carlo_iterations),
        ],
    )
    _run(
        "run score policy backtesting",
        [
            py,
            "src/backtesting/run_score_policy_backtest.py",
            "--raw-dir",
            str(args.raw_dir),
            "--processed-dir",
            str(args.processed_dir),
            "--output-dir",
            str(args.processed_dir),
            "--charts-dir",
            str(args.charts_dir),
        ],
    )
    _run(
        "build chart pack",
        [
            py,
            "src/visualization/build_marketplace_visualizations.py",
            "--raw-dir",
            str(args.raw_dir),
            "--processed-dir",
            str(args.processed_dir),
            "--output-dir",
            str(args.charts_dir),
        ],
    )
    _run(
        "generate executive snapshot",
        [
            py,
            "src/validation/generate_executive_snapshot.py",
            "--raw-dir",
            str(args.raw_dir),
            "--processed-dir",
            str(args.processed_dir),
            "--reports-dir",
            str(args.reports_dir),
        ],
    )
    _run(
        "build executive dashboard",
        [
            py,
            "src/dashboard/build_executive_dashboard.py",
            "--raw-dir",
            str(args.raw_dir),
            "--processed-dir",
            str(args.processed_dir),
            "--reports-dir",
            str(args.reports_dir),
            "--output-file",
            str(args.dashboard_file),
        ],
    )
    _run(
        "publish GitHub Pages dashboard entrypoint",
        [
            py,
            "src/dashboard/publish_github_pages.py",
            "--source-html",
            str(args.dashboard_file),
            "--destination-html",
            str(args.pages_dashboard_file),
            "--index-html",
            str(args.pages_index_file),
        ],
    )
    _run(
        "generate schema contracts",
        [
            py,
            "src/validation/generate_schema_contracts.py",
            "--raw-dir",
            str(args.raw_dir),
            "--processed-dir",
            str(args.processed_dir),
            "--output-file",
            str(args.schema_file),
        ],
    )
    _run(
        "validate schema contracts",
        [
            py,
            "src/validation/validate_schema_contracts.py",
            "--schema-file",
            str(args.schema_file),
            "--output-file",
            str(args.reports_dir / "schema_contract_issues.csv"),
        ],
    )
    _run(
        "generate schema drift report",
        [
            py,
            "src/validation/generate_schema_drift_report.py",
            "--current-schema-file",
            str(args.schema_file),
            "--history-dir",
            str(args.schema_history_dir),
            "--output-csv",
            str(args.reports_dir / "schema_drift_changes.csv"),
            "--output-report",
            str(args.reports_dir / "schema_drift_report.md"),
            "--snapshot-current",
        ],
    )
    _run(
        "run formal validation",
        [
            py,
            "src/validation/run_full_validation.py",
            "--raw-dir",
            str(args.raw_dir),
            "--processed-dir",
            str(args.processed_dir),
            "--report-dir",
            str(args.reports_dir),
            "--schema-file",
            str(args.schema_file),
            "--metric-contract-file",
            str(args.metric_contract_file),
        ],
    )
    _run(
        "enforce release gate",
        [
            py,
            "src/validation/enforce_release_gate.py",
            "--release-file",
            str(args.reports_dir / "validation_release_assessment.csv"),
            "--required-state",
            args.required_release_state,
            *(["--require-committee-grade"] if args.require_committee_grade else []),
        ],
    )

    print("[pipeline] complete")


if __name__ == "__main__":
    main()
