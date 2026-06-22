from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.validation.enforce_release_gate import STATE_ORDER

# The release gate is the single source of truth for valid release states, so the
# pipeline can only require a state the gate actually understands.
RELEASE_STATES = list(STATE_ORDER.keys())


@dataclass(frozen=True)
class PipelineStep:
    name: str
    command: list[str]


def _script(path: str) -> str:
    return str(PROJECT_ROOT / path)


def _run(step_name: str, cmd: list[str]) -> None:
    print(f"[pipeline] {step_name}")
    # Commands are built from a fixed list of in-repo scripts (see build_pipeline_steps);
    # there is no shell and no untrusted input, so this subprocess call is safe.
    subprocess.run(cmd, check=True, cwd=PROJECT_ROOT)  # noqa: S603  # nosec B603


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run full marketplace analytics pipeline end-to-end.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--charts-dir", type=Path, default=Path(".tmp/charts"))
    parser.add_argument(
        "--dashboard-file",
        type=Path,
        default=Path("outputs/dashboard/executive-marketplace-command-center.html"),
    )
    parser.add_argument(
        "--pages-dashboard-file",
        type=Path,
        default=Path(".pages/executive-marketplace-command-center.html"),
    )
    parser.add_argument("--pages-index-file", type=Path, default=Path(".pages/index.html"))
    parser.add_argument("--monte-carlo-iterations", type=int, default=2000)
    parser.add_argument("--schema-file", type=Path, default=Path("config/contracts/v1/schema_contracts.json"))
    parser.add_argument(
        "--metric-contract-file",
        type=Path,
        default=Path("config/contracts/v1/metric_governance_contract.csv"),
    )
    parser.add_argument("--schema-history-dir", type=Path, default=Path("config/contracts/history"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument(
        "--required-release-state",
        type=str,
        default="decision-support only",
        choices=RELEASE_STATES,
    )
    parser.add_argument("--require-committee-grade", action="store_true")
    return parser


def build_pipeline_steps(args: argparse.Namespace, python_executable: str | None = None) -> list[PipelineStep]:
    if args.monte_carlo_iterations <= 0:
        raise ValueError("--monte-carlo-iterations must be greater than zero.")

    py = python_executable or sys.executable
    return [
        PipelineStep(
            "generate synthetic data",
            [
                py,
                _script("src/data_generation/generate_synthetic_marketplace_data.py"),
                "--output-dir",
                str(args.raw_dir),
            ],
        ),
        PipelineStep(
            "build feature layer",
            [
                py,
                _script("src/features/build_analytical_feature_layer.py"),
                "--raw-dir",
                str(args.raw_dir),
                "--output-dir",
                str(args.processed_dir),
            ],
        ),
        PipelineStep(
            "build scoring layer",
            [
                py,
                _script("src/scoring/build_scoring_framework.py"),
                "--raw-dir",
                str(args.raw_dir),
                "--processed-dir",
                str(args.processed_dir),
            ],
        ),
        PipelineStep(
            "build governance action register",
            [
                py,
                _script("src/governance/build_governance_action_register.py"),
                "--processed-dir",
                str(args.processed_dir),
                "--output-dir",
                str(args.processed_dir),
            ],
        ),
        PipelineStep(
            "build scenario analysis",
            [
                py,
                _script("src/scenario_analysis/build_scenario_decision_analysis.py"),
                "--raw-dir",
                str(args.raw_dir),
                "--processed-dir",
                str(args.processed_dir),
                "--baseline-months",
                "6",
                "--horizon-months",
                "6",
            ],
        ),
        PipelineStep(
            "run scenario monte carlo",
            [
                py,
                _script("src/scenario_analysis/run_scenario_monte_carlo.py"),
                "--processed-dir",
                str(args.processed_dir),
                "--output-dir",
                str(args.processed_dir),
                "--charts-dir",
                str(args.charts_dir),
                "--iterations",
                str(args.monte_carlo_iterations),
            ],
        ),
        PipelineStep(
            "run score policy backtesting",
            [
                py,
                _script("src/backtesting/run_score_policy_backtest.py"),
                "--raw-dir",
                str(args.raw_dir),
                "--processed-dir",
                str(args.processed_dir),
                "--output-dir",
                str(args.processed_dir),
                "--charts-dir",
                str(args.charts_dir),
            ],
        ),
        PipelineStep(
            "generate executive snapshot",
            [
                py,
                _script("src/validation/generate_executive_snapshot.py"),
                "--raw-dir",
                str(args.raw_dir),
                "--processed-dir",
                str(args.processed_dir),
                "--reports-dir",
                str(args.reports_dir),
            ],
        ),
        PipelineStep(
            "generate schema contracts",
            [
                py,
                _script("src/validation/generate_schema_contracts.py"),
                "--raw-dir",
                str(args.raw_dir),
                "--processed-dir",
                str(args.processed_dir),
                "--output-file",
                str(args.schema_file),
            ],
        ),
        PipelineStep(
            "validate schema contracts",
            [
                py,
                _script("src/validation/validate_schema_contracts.py"),
                "--schema-file",
                str(args.schema_file),
                "--output-file",
                str(args.reports_dir / "schema_contract_issues.csv"),
            ],
        ),
        PipelineStep(
            "generate schema drift report",
            [
                py,
                _script("src/validation/generate_schema_drift_report.py"),
                "--current-schema-file",
                str(args.schema_file),
                "--history-dir",
                str(args.schema_history_dir),
                "--output-csv",
                str(args.reports_dir / "schema_drift_changes.csv"),
                "--output-report",
                str(args.reports_dir / "schema_drift_report.md"),
            ],
        ),
        PipelineStep(
            "run formal validation",
            [
                py,
                _script("src/validation/run_full_validation.py"),
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
        ),
        PipelineStep(
            "build executive dashboard",
            [
                py,
                _script("src/dashboard/build_executive_dashboard.py"),
                "--raw-dir",
                str(args.raw_dir),
                "--processed-dir",
                str(args.processed_dir),
                "--reports-dir",
                str(args.reports_dir),
                "--output-file",
                str(args.dashboard_file),
            ],
        ),
        PipelineStep(
            "enforce release gate",
            [
                py,
                _script("src/validation/enforce_release_gate.py"),
                "--release-file",
                str(args.reports_dir / "validation_release_assessment.csv"),
                "--required-state",
                args.required_release_state,
                *(["--require-committee-grade"] if args.require_committee_grade else []),
            ],
        ),
        PipelineStep("build publication chart pack", [py, _script("src/visualization/build_report_graphs.py")]),
        PipelineStep("build publication PDF report", [py, _script("src/visualization/build_report_pdf.py")]),
        PipelineStep(
            "publish GitHub Pages dashboard entrypoint",
            [
                py,
                _script("src/dashboard/publish_github_pages.py"),
                "--source-html",
                str(args.dashboard_file),
                "--destination-html",
                str(args.pages_dashboard_file),
                "--index-html",
                str(args.pages_index_file),
            ],
        ),
    ]


def main() -> None:
    args = build_parser().parse_args()

    for step in build_pipeline_steps(args):
        _run(step.name, step.command)

    print("[pipeline] complete")


if __name__ == "__main__":
    main()
