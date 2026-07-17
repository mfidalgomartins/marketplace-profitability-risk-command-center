from pathlib import Path

import pandas as pd
import pytest
from src.scoring.build_scoring_framework import (
    ScoringConfig,
    _build_order_risk_scores,
    _maturation_lag_from_policy,
    build_scoring_tables,
)

PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"


TIERS = {"Low", "Moderate", "High", "Critical"}


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED / f"{name}.csv")


def test_scoring_tables_exist() -> None:
    required = [
        "order_risk_scores",
        "seller_quality_scores",
        "fraud_exposure_scores",
        "margin_fragility_scores",
        "governance_priority_scores",
        "seller_scorecard",
        "top_high_priority_sellers",
        "top_high_risk_orders",
        "scoring_sensitivity_summary",
    ]
    for table in required:
        assert (PROCESSED / f"{table}.csv").exists()


def test_score_ranges_and_tiers() -> None:
    checks = [
        ("order_risk_scores", "order_risk_score", "order_risk_tier"),
        ("seller_quality_scores", "seller_quality_score", "seller_quality_tier"),
        ("fraud_exposure_scores", "fraud_exposure_score", "fraud_exposure_tier"),
        ("margin_fragility_scores", "margin_fragility_score", "margin_fragility_tier"),
        ("governance_priority_scores", "governance_priority_score", "governance_priority_tier"),
    ]

    for table, score_col, tier_col in checks:
        df = _read(table)
        assert df[score_col].between(0, 100).all(), f"{table}.{score_col} out of range"
        assert set(df[tier_col].dropna().unique()).issubset(TIERS), f"{table}.{tier_col} invalid tiers"


def test_recommended_actions_and_top_tables() -> None:
    seller = _read("seller_quality_scores")
    order = _read("order_risk_scores")

    assert seller["recommended_action"].notna().all()
    assert order["recommended_action"].notna().all()

    top_sellers = _read("top_high_priority_sellers")
    top_orders = _read("top_high_risk_orders")

    assert len(top_sellers) <= 100
    assert len(top_orders) <= 250
    assert top_sellers["governance_priority_score"].is_monotonic_decreasing
    assert top_orders["order_risk_score"].is_monotonic_decreasing


def test_sensitivity_summary_shape() -> None:
    sens = _read("scoring_sensitivity_summary")
    assert set(sens["scenario"]) == {"baseline", "fraud_heavy", "margin_heavy", "quality_heavy"}
    assert sens["top50_overlap_rate"].between(0, 1).all()


def _temporal_score_base() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "order_id": ["O1", "O2"],
            "seller_id": ["S1", "S1"],
            "buyer_id": ["B1", "B1"],
            "order_date": pd.to_datetime(["2025-01-01", "2025-04-01"]),
            "payment_risk_signal": ["medium", "medium"],
            "payment_method": ["credit_card", "credit_card"],
            "order_channel": ["web", "web"],
            "category": ["Home", "Home"],
            "gross_order_value": [100.0, 100.0],
            "refund_flag": [0, 0],
            "dispute_flag": [0, 0],
            "chargeback_flag": [0, 0],
        }
    )


def test_current_order_outcome_does_not_change_its_score() -> None:
    base = _temporal_score_base()
    original = _build_order_risk_scores(base).set_index("order_id")
    changed = base.copy()
    changed.loc[changed["order_id"] == "O1", ["refund_flag", "dispute_flag", "chargeback_flag"]] = 1
    rescored = _build_order_risk_scores(changed).set_index("order_id")

    assert rescored.loc["O1", "order_risk_score"] == pytest.approx(original.loc["O1", "order_risk_score"])
    assert rescored.loc["O2", "order_risk_score"] > original.loc["O2", "order_risk_score"]


def test_future_order_does_not_change_historical_scores() -> None:
    base = _temporal_score_base()
    original = _build_order_risk_scores(base).set_index("order_id")
    future = base.iloc[[1]].assign(
        order_id="O3",
        order_date=pd.Timestamp("2026-01-01"),
        gross_order_value=100_000.0,
        refund_flag=1,
        dispute_flag=1,
        chargeback_flag=1,
    )
    rescored = _build_order_risk_scores(pd.concat([base, future], ignore_index=True)).set_index("order_id")

    pd.testing.assert_series_equal(
        original.loc[["O1", "O2"], "order_risk_score"],
        rescored.loc[["O1", "O2"], "order_risk_score"],
    )


def test_same_date_outcomes_do_not_leak_between_orders() -> None:
    base = _temporal_score_base()
    base["order_date"] = pd.Timestamp("2025-01-01")
    original = _build_order_risk_scores(base).set_index("order_id")
    changed = base.copy()
    changed.loc[changed["order_id"] == "O1", ["refund_flag", "dispute_flag", "chargeback_flag"]] = 1
    rescored = _build_order_risk_scores(changed).set_index("order_id")

    pd.testing.assert_series_equal(original["order_risk_score"], rescored["order_risk_score"])


def test_unmatured_outcomes_do_not_enter_history() -> None:
    base = _temporal_score_base()
    base.loc[base["order_id"] == "O2", "order_date"] = pd.Timestamp("2025-02-01")
    original = _build_order_risk_scores(base, outcome_maturation_lag_days=60).set_index("order_id")
    changed = base.copy()
    changed.loc[changed["order_id"] == "O1", ["refund_flag", "dispute_flag", "chargeback_flag"]] = 1
    rescored = _build_order_risk_scores(changed, outcome_maturation_lag_days=60).set_index("order_id")

    assert original.loc["O2", "order_risk_score"] == pytest.approx(rescored.loc["O2", "order_risk_score"])


def test_scoring_rejects_nonpositive_window() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        build_scoring_tables(ScoringConfig(raw_dir=PROCESSED, processed_dir=PROCESSED, trailing_window_days=0))


def test_scoring_rejects_negative_maturation_lag() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        build_scoring_tables(ScoringConfig(raw_dir=PROCESSED, processed_dir=PROCESSED, outcome_maturation_lag_days=-1))


def test_scoring_reads_maturation_lag_from_governed_policy(tmp_path: Path) -> None:
    policy_file = tmp_path / "policy.json"
    policy_file.write_text('{"outcome_maturation_lag_days": 45}', encoding="utf-8")
    assert _maturation_lag_from_policy(policy_file) == 45

    policy_file.write_text('{"outcome_maturation_lag_days": -1}', encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative"):
        _maturation_lag_from_policy(policy_file)
