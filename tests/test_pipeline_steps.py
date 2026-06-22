from pathlib import Path

import pytest
from src.pipeline.run_full_pipeline import (
    PROJECT_ROOT,
    RELEASE_STATES,
    build_parser,
    build_pipeline_steps,
)
from src.validation.enforce_release_gate import STATE_ORDER

EXPECTED_STEP_ORDER = [
    "generate synthetic data",
    "build feature layer",
    "build scoring layer",
    "build governance action register",
    "build scenario analysis",
    "run scenario monte carlo",
    "run score policy backtesting",
    "generate executive snapshot",
    "generate schema contracts",
    "validate schema contracts",
    "generate schema drift report",
    "run formal validation",
    "build executive dashboard",
    "enforce release gate",
    "build publication chart pack",
    "build publication PDF report",
    "publish GitHub Pages dashboard entrypoint",
]


def _args(**overrides):
    parser = build_parser()
    return parser.parse_args([f"--{k.replace('_', '-')}={v}" for k, v in overrides.items()])


def test_release_states_match_gate_source_of_truth() -> None:
    # Regression: the pipeline must only offer states the release gate understands,
    # otherwise selecting one crashes the gate step with "Unknown required state".
    assert list(STATE_ORDER.keys()) == RELEASE_STATES


def test_parser_defaults() -> None:
    args = build_parser().parse_args([])
    assert args.required_release_state == "decision-support only"
    assert args.monte_carlo_iterations == 2000
    assert args.require_committee_grade is False


def test_parser_rejects_unknown_release_state() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["--required-release-state", "technically valid"])


def test_pipeline_steps_full_order() -> None:
    steps = build_pipeline_steps(_args())
    assert [s.name for s in steps] == EXPECTED_STEP_ORDER


def test_pipeline_steps_use_absolute_script_paths_and_given_interpreter() -> None:
    steps = build_pipeline_steps(_args(), python_executable="/usr/bin/python3")
    for step in steps:
        assert step.command[0] == "/usr/bin/python3"
        script = Path(step.command[1])
        assert script.is_absolute()
        assert str(script).startswith(str(PROJECT_ROOT))
        assert script.exists()


def test_pipeline_steps_thread_monte_carlo_iterations() -> None:
    steps = build_pipeline_steps(_args(monte_carlo_iterations=123))
    mc = next(s for s in steps if s.name == "run scenario monte carlo")
    assert "--iterations" in mc.command
    assert "123" in mc.command


def test_pipeline_steps_committee_grade_flag_propagates() -> None:
    parser = build_parser()
    args = parser.parse_args(["--require-committee-grade"])
    gate = next(s for s in build_pipeline_steps(args) if s.name == "enforce release gate")
    assert "--require-committee-grade" in gate.command


def test_pipeline_steps_reject_nonpositive_iterations() -> None:
    with pytest.raises(ValueError):
        build_pipeline_steps(_args(monte_carlo_iterations=0))
