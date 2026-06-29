"""Unit tests for the score-policy backtesting decision logic — the pure
functions that turn order risk scores into a recommended review threshold."""

import pandas as pd
import pytest
from src.backtesting.run_score_policy_backtest import (
    BacktestConfig,
    _build_recommended_policy,
    _curve_for_thresholds,
    _validate_config,
)


def _base() -> pd.DataFrame:
    # Ten orders; the high-score ones carry the bad events and loss.
    return pd.DataFrame(
        {
            "order_risk_score": [10, 20, 30, 40, 50, 60, 70, 80, 90, 95],
            "bad_event_flag": [0, 0, 0, 0, 0, 1, 1, 1, 1, 1],
            "event_loss_proxy": [0, 0, 0, 0, 0, 100, 200, 300, 400, 500],
            "net_value": [50, 60, 70, 80, 90, 40, 30, 20, 10, 5],
        }
    )


def test_validate_config_accepts_defaults() -> None:
    _validate_config(BacktestConfig())  # should not raise


@pytest.mark.parametrize(
    "kwargs",
    [
        {"thresholds": ()},
        {"thresholds": (150,)},
        {"thresholds": (-5,)},
        {"manual_review_cost": -1.0},
        {"friction_rate": 1.5},
        {"base_efficacy": 2.0},
        {"efficacy_scenarios": (0.2, 1.4)},
    ],
)
def test_validate_config_rejects_bad_values(kwargs) -> None:
    with pytest.raises(ValueError):
        _validate_config(BacktestConfig(**kwargs))


def test_curve_metrics_are_monotonic_in_the_right_direction() -> None:
    curve = _curve_for_thresholds(
        _base(), thresholds=[30, 60, 90], manual_review_cost=1.0, friction_rate=0.0, efficacy=0.5
    ).set_index("threshold")

    # Raising the threshold reviews fewer orders and lifts precision.
    assert curve.loc[30, "reviewed_orders"] > curve.loc[90, "reviewed_orders"]
    assert curve.loc[90, "precision"] >= curve.loc[30, "precision"]
    # Review rate is a proper fraction; precision/recall bounded in [0, 1].
    assert (curve["review_rate"].between(0, 1)).all()
    assert (curve["precision"].between(0, 1)).all()
    assert (curve["recall"].between(0, 1)).all()


def test_curve_net_benefit_uses_efficacy_and_costs() -> None:
    curve = _curve_for_thresholds(
        _base(), thresholds=[60], manual_review_cost=1.0, friction_rate=0.0, efficacy=0.5
    ).iloc[0]
    # At threshold 60, the 5 high-score bad orders (loss 100+200+300+400+500=1500)
    # are reviewed: avoided loss = 1500 * 0.5 = 750; cost = 5 reviewed * 1.0 = 5.
    assert curve["expected_avoided_loss"] == pytest.approx(750.0)
    assert curve["review_cost"] == pytest.approx(5.0)
    assert curve["net_benefit"] == pytest.approx(745.0)


def test_recommended_policy_prefers_practical_review_capacity() -> None:
    curve = _curve_for_thresholds(
        _base(), thresholds=[30, 50, 70, 90], manual_review_cost=1.0, friction_rate=0.001, efficacy=0.4
    )
    rec = _build_recommended_policy(curve).iloc[0]
    # The recommendation respects the <=35% review-capacity guardrail.
    assert rec["review_rate"] <= 0.35
    assert "holdout" in rec["deployment_status"]
    assert rec["recommended_threshold"] in set(curve["threshold"])
