from pathlib import Path

import numpy as np
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


def test_scenario_tables_exist() -> None:
    required = [
        "scenario_assumptions",
        "scenario_results_summary",
        "scenario_component_bridge",
        "scenario_top_risk_exposure",
        "scenario_decision_matrix",
    ]
    for table in required:
        assert (PROCESSED / f"{table}.csv").exists()


def test_scenario_assumptions_are_complete_and_bounded() -> None:
    assumptions = _read("scenario_assumptions")

    assert set(assumptions["scenario"]) == SCENARIOS
    assert (assumptions["gmv_factor"] > 0).all()
    assert (assumptions["net_to_gmv_factor"] > 0).all()
    assert assumptions["remove_bad_actor_intensity"].between(0, 1).all()
    assert assumptions["correct_bad_actor_effectiveness"].between(0, 1).all()
    assert assumptions["assumption_summary"].notna().all()


def test_scenario_results_reconcile_to_business_math() -> None:
    results = _read("scenario_results_summary")

    assert set(results["scenario"]) == SCENARIOS
    assert (results["risk_adjusted_gmv"] <= results["net_value"] + 1e-9).all()
    assert (results["leakage_rate"] >= 0).all()

    baseline = results[results["scenario"] == "baseline"].iloc[0]
    assert np.isclose(baseline["gmv_change_vs_baseline_pct"], 0.0, atol=1e-9)
    assert np.isclose(baseline["leakage_avoided_vs_baseline"], 0.0, atol=1e-9)

    expected_leakage = (
        results["subsidy"] + results["refunds"] + results["disputes"] + results["chargeback_loss"]
    )
    assert np.allclose(results["total_leakage"], expected_leakage)

    expected_cm = results["commission_revenue"] - results["total_leakage"]
    assert np.allclose(results["contribution_margin_proxy"], expected_cm)

    expected_bad_actor_avoided = (
        results["remove_bad_actor_leakage_avoided"] + results["correct_bad_actor_leakage_avoided"]
    )
    assert np.allclose(
        results["total_bad_actor_intervention_leakage_avoided"],
        expected_bad_actor_avoided,
    )

    downside = results[results["scenario"] == "downside_high_risk_deterioration"].iloc[0]
    assert downside["growth_quality_tradeoff"] == "growth_at_risk"
    assert np.isfinite(results["decision_priority_score"]).all()


def test_decision_matrix_and_exposure_outputs_are_actionable() -> None:
    decision = _read("scenario_decision_matrix")
    exposure = _read("scenario_top_risk_exposure")

    assert set(decision["scenario"]) == SCENARIOS
    assert decision["recommended_decision"].notna().all()
    assert decision["decision_priority_score"].is_monotonic_decreasing

    assert len(exposure) == 1
    row = exposure.iloc[0]
    assert 0 <= row["top_risk_net_share"] <= 1
    assert 0 <= row["bad_actor_gmv_share"] <= 1
    assert 0 <= row["bad_actor_net_share"] <= 1
    assert row["bad_actor_seller_count"] >= 1
