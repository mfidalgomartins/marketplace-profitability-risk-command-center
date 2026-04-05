from pathlib import Path

import pandas as pd


PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"

SCENARIOS = {
    "baseline",
    "seller_quality_improvement",
    "subsidy_tightening",
    "fraud_control_improvement",
    "downside_high_risk_deterioration",
}


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED / f"{name}.csv")


def test_backtesting_tables_exist_and_are_coherent() -> None:
    required = [
        "backtesting_threshold_curve",
        "backtesting_action_impact",
        "backtesting_recommended_policy",
    ]
    for table in required:
        assert (PROCESSED / f"{table}.csv").exists()

    curve = _read("backtesting_threshold_curve")
    impact = _read("backtesting_action_impact")
    policy = _read("backtesting_recommended_policy")

    assert curve["threshold"].is_monotonic_increasing
    assert curve["review_rate"].between(0, 1).all()
    assert curve["precision"].between(0, 1).all()
    assert curve["recall"].between(0, 1).all()

    assert set(impact["efficacy_assumption"].unique()) == {0.2, 0.35, 0.5}
    assert len(policy) == 1
    threshold = int(policy.iloc[0]["recommended_threshold"])
    assert threshold in set(curve["threshold"].tolist())


def test_monte_carlo_tables_exist_and_capture_uncertainty() -> None:
    required = [
        "scenario_monte_carlo_samples",
        "scenario_monte_carlo_summary",
        "scenario_monte_carlo_decision",
    ]
    for table in required:
        assert (PROCESSED / f"{table}.csv").exists()

    samples = _read("scenario_monte_carlo_samples")
    summary = _read("scenario_monte_carlo_summary")
    decision = _read("scenario_monte_carlo_decision")

    assert set(samples["scenario"].unique()) == SCENARIOS
    assert set(summary["scenario"].unique()) == SCENARIOS
    assert set(decision["scenario"].unique()) == SCENARIOS

    assert (
        summary["contribution_margin_proxy_p05"]
        <= summary["contribution_margin_proxy_p50"]
    ).all()
    assert (
        summary["contribution_margin_proxy_p50"]
        <= summary["contribution_margin_proxy_p95"]
    ).all()

    assert decision["decision_score_uncertain"].is_monotonic_decreasing
    assert decision["prob_cm_positive"].between(0, 1).all()
    assert decision["prob_cm_better_than_baseline"].between(0, 1).all()
    assert decision["prob_leakage_better_than_baseline"].between(0, 1).all()
