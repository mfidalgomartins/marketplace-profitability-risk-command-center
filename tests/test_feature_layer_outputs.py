from pathlib import Path

import pandas as pd


PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"


def _read(name: str) -> pd.DataFrame:
    return pd.read_csv(PROCESSED_DIR / f"{name}.csv")


def test_feature_tables_exist_and_have_required_columns() -> None:
    required = {
        "order_profitability_features": [
            "order_id",
            "order_date",
            "buyer_id",
            "seller_id",
            "category",
            "gross_value",
            "net_value",
            "subsidy_amount",
            "commission_fee",
            "refund_amount",
            "dispute_amount",
            "chargeback_loss_proxy",
            "realized_contribution_margin_proxy",
            "estimated_margin_after_risk",
            "risk_adjusted_order_value",
            "profitability_flag",
        ],
        "seller_monthly_quality": [
            "seller_id",
            "month",
            "orders",
            "GMV",
            "net_value",
            "avg_margin_proxy",
            "refund_rate",
            "dispute_rate",
            "chargeback_rate",
            "cancellation_rate",
            "delay_rate",
            "on_time_rate",
            "promo_dependency_rate",
            "repeat_buyer_rate",
            "seller_quality_proxy",
            "fragility_flag",
        ],
        "buyer_behavior_risk": [
            "buyer_id",
            "trailing_order_count",
            "refund_frequency",
            "dispute_frequency",
            "chargeback_frequency",
            "average_order_value",
            "promo_usage_rate",
            "abnormal_behavior_flags",
            "order_risk_proxy",
        ],
        "category_risk_summary": [
            "month",
            "category",
            "GMV",
            "net_value",
            "refund_rate",
            "dispute_rate",
            "subsidy_rate",
            "margin_fragility_index",
        ],
        "seller_risk_base": [
            "seller_id",
            "current_period",
            "quality_inputs",
            "fraud_inputs",
            "profitability_inputs",
            "operational_inputs",
            "concentration_inputs",
        ],
    }

    for table, cols in required.items():
        path = PROCESSED_DIR / f"{table}.csv"
        assert path.exists(), f"Missing table: {path}"
        df = pd.read_csv(path)
        assert all(col in df.columns for col in cols), f"Missing required columns in {table}"


def test_feature_layer_integrity_and_basic_sanity() -> None:
    opf = _read("order_profitability_features")
    smq = _read("seller_monthly_quality")
    brr = _read("buyer_behavior_risk")
    crs = _read("category_risk_summary")
    srb = _read("seller_risk_base")

    assert opf["order_id"].nunique() == len(opf)
    assert (opf["risk_adjusted_order_value"] <= opf["net_value"] + 1e-9).all()
    recon = (
        opf["commission_fee"]
        - opf["subsidy_amount"]
        - opf["refund_amount"]
        - opf["dispute_amount"]
        - opf["chargeback_loss_proxy"]
    )
    assert (recon - opf["realized_contribution_margin_proxy"]).abs().max() <= 1e-6
    assert set(opf["profitability_flag"].unique()) <= {"profitable", "fragile"}

    assert (smq["orders"] > 0).all()
    assert smq["seller_quality_proxy"].between(0, 100).all()
    assert smq["fragility_flag"].isin(["fragile", "stable"]).all()

    assert brr["buyer_id"].nunique() == len(brr)
    assert (brr["trailing_order_count"] >= 0).all()
    assert brr["order_risk_proxy"].between(0, 100).all()

    assert (crs["GMV"] > 0).all()
    assert crs["margin_fragility_index"].between(0, 100).all()

    assert srb["seller_id"].nunique() == len(srb)
    assert srb["current_period"].nunique() == 1
