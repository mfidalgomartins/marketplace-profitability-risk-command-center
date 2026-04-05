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
    parser.add_argument("--preview-image", type=Path, default=Path("outputs/charts/00_executive_preview_pack.png"))
    parser.add_argument("--preview-manifest", type=Path, default=Path("outputs/charts/00_executive_preview_pack.md"))
    parser.add_argument(
        "--dashboard-file",
        type=Path,
        default=Path("outputs/dashboard/marketplace_command_center_dashboard.html"),
    )
    parser.add_argument(
        "--dashboard-demo-file",
        type=Path,
        default=Path("outputs/dashboard/marketplace_command_center_dashboard_demo.html"),
    )
    parser.add_argument("--dashboard-demo-max-orders", type=int, default=25000)
    parser.add_argument(
        "--build-demo-dashboard",
        action="store_true",
        help="Build optional sampled dashboard artifact (non-official).",
    )
    parser.add_argument("--monte-carlo-iterations", type=int, default=2000)
    parser.add_argument("--schema-file", type=Path, default=Path("schemas/v1/schema_contracts.json"))
    parser.add_argument("--metric-contract-file", type=Path, default=Path("schemas/v1/metric_governance_contract.csv"))
    parser.add_argument("--schema-history-dir", type=Path, default=Path("schemas/history"))
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
        "build executive preview pack",
        [
            py,
            "src/visualization/generate_executive_preview_pack.py",
            "--charts-dir",
            str(args.charts_dir),
            "--output-image",
            str(args.preview_image),
            "--output-manifest",
            str(args.preview_manifest),
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
    if args.build_demo_dashboard:
        _run(
            "build executive dashboard (demo mode)",
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
                str(args.dashboard_demo_file),
                "--max-orders",
                str(args.dashboard_demo_max_orders),
                "--sample-seed",
                "42",
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
