from pathlib import Path

import pandas as pd


PROCESSED = Path(__file__).resolve().parents[1] / "data" / "processed"


def test_governance_action_register_exists_and_has_required_fields() -> None:
    path = PROCESSED / "governance_action_register.csv"
    assert path.exists()

    df = pd.read_csv(path)
    required_cols = {
        "entity_type",
        "entity_id",
        "priority_score",
        "risk_tier",
        "main_risk_driver",
        "recommended_action",
        "owner_team",
        "sla_days",
        "estimated_leakage_proxy",
        "status",
        "priority_rank",
    }
    assert required_cols.issubset(df.columns)


def test_governance_action_register_integrity() -> None:
    df = pd.read_csv(PROCESSED / "governance_action_register.csv")

    assert set(df["entity_type"].unique()) == {"seller", "order"}
    assert df["priority_score"].between(0, 100).all()
    assert (df["sla_days"] > 0).all()
    assert (df["estimated_leakage_proxy"] >= 0).all()
    assert df["owner_team"].notna().all()
    assert df["recommended_action"].notna().all()
    assert df["status"].eq("open").all()
    assert df.duplicated(subset=["entity_type", "entity_id"]).sum() == 0
