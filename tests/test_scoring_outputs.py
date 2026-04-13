from pathlib import Path

import pandas as pd


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
