from pathlib import Path

import pandas as pd


RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def _load() -> dict[str, pd.DataFrame]:
    return {
        "buyers": pd.read_csv(RAW_DIR / "buyers.csv", parse_dates=["signup_date"]),
        "sellers": pd.read_csv(RAW_DIR / "sellers.csv", parse_dates=["onboarding_date"]),
        "products": pd.read_csv(RAW_DIR / "products.csv"),
        "orders": pd.read_csv(RAW_DIR / "orders.csv", parse_dates=["order_date"]),
        "order_items": pd.read_csv(RAW_DIR / "order_items.csv"),
        "payments": pd.read_csv(RAW_DIR / "payments.csv"),
        "refunds": pd.read_csv(RAW_DIR / "refunds.csv", parse_dates=["refund_date"]),
        "disputes": pd.read_csv(RAW_DIR / "disputes.csv", parse_dates=["dispute_date"]),
        "logistics_events": pd.read_csv(
            RAW_DIR / "logistics_events.csv",
            parse_dates=["shipped_date", "delivered_date", "promised_delivery_date"],
        ),
    }


def test_required_files_exist() -> None:
    required = {
        "buyers.csv",
        "sellers.csv",
        "products.csv",
        "orders.csv",
        "order_items.csv",
        "payments.csv",
        "refunds.csv",
        "disputes.csv",
        "logistics_events.csv",
    }
    existing = {p.name for p in RAW_DIR.glob("*.csv")}
    assert required.issubset(existing)


def test_scale_targets_and_history_window() -> None:
    t = _load()

    assert 5000 <= len(t["buyers"]) <= 15000
    assert 800 <= len(t["sellers"]) <= 2000
    assert len(t["orders"]) >= 50000

    min_date = t["orders"]["order_date"].min()
    max_date = t["orders"]["order_date"].max()

    assert min_date.year == 2024 and min_date.month == 3
    assert max_date.year == 2026 and max_date.month == 2


def test_referential_integrity() -> None:
    t = _load()

    assert t["orders"]["buyer_id"].isin(t["buyers"]["buyer_id"]).all()
    assert t["products"]["seller_id"].isin(t["sellers"]["seller_id"]).all()
    assert t["order_items"]["order_id"].isin(t["orders"]["order_id"]).all()
    assert t["order_items"]["product_id"].isin(t["products"]["product_id"]).all()
    assert t["payments"]["order_id"].isin(t["orders"]["order_id"]).all()
    assert t["refunds"]["order_id"].isin(t["orders"]["order_id"]).all()
    assert t["disputes"]["order_id"].isin(t["orders"]["order_id"]).all()
    assert t["logistics_events"]["order_id"].isin(t["orders"]["order_id"]).all()



def test_behavioral_patterns_present() -> None:
    t = _load()

    items = t["order_items"]
    orders = t["orders"]
    refunds = t["refunds"]
    disputes = t["disputes"]
    logistics = t["logistics_events"]
    products = t["products"]
    payments = t["payments"]

    seller_gmv = items.groupby("seller_id")["gross_item_value"].sum().sort_values(ascending=False)
    top10_share = seller_gmv.head(10).sum() / seller_gmv.sum()
    assert top10_share > 0.12

    base = (
        orders[["order_id", "order_channel"]]
        .merge(logistics[["order_id", "delay_days"]], on="order_id", how="left")
        .merge(refunds[["order_id"]].assign(has_refund=1), on="order_id", how="left")
        .fillna({"has_refund": 0})
    )
    delay_low = base[base["delay_days"].fillna(0) <= 1]["has_refund"].mean()
    delay_high = base[base["delay_days"].fillna(0) >= 5]["has_refund"].mean()
    assert delay_high > delay_low + 0.03

    category_by_order = (
        items[["order_id", "product_id"]]
        .merge(products[["product_id", "category"]], on="product_id", how="left")
        .groupby("order_id", as_index=False)["category"]
        .first()
    )
    pay = payments.merge(orders[["order_id", "order_channel"]], on="order_id", how="left").merge(
        category_by_order, on="order_id", how="left"
    )

    cluster = pay[
        (pay["order_channel"] == "social_commerce")
        & (pay["category"].isin(["Electronics", "Digital Goods"]))
    ]
    assert cluster["chargeback_flag"].mean() > pay["chargeback_flag"].mean() + 0.02

    dispute_link = (
        disputes[["order_id"]]
        .assign(has_dispute=1)
        .merge(logistics[["order_id", "delay_days"]], on="order_id", how="left")
        .fillna({"has_dispute": 0})
    )
    assert dispute_link["delay_days"].mean() >= 2.0


def test_post_order_loss_overlap_is_bounded() -> None:
    t = _load()
    orders = t["orders"][["order_id", "net_paid_amount"]]
    payments = t["payments"][["order_id", "chargeback_flag"]]
    refunds = t["refunds"].groupby("order_id", as_index=False)["refund_amount"].sum()
    disputes = t["disputes"].groupby("order_id", as_index=False)["dispute_amount"].sum()

    chk = (
        orders.merge(refunds, on="order_id", how="left")
        .merge(disputes, on="order_id", how="left")
        .merge(payments, on="order_id", how="left")
        .fillna({"refund_amount": 0.0, "dispute_amount": 0.0, "chargeback_flag": 0})
    )
    chk["chargeback_loss"] = chk["chargeback_flag"] * chk["net_paid_amount"]
    overlap_rate = (
        (chk["refund_amount"] + chk["dispute_amount"] + chk["chargeback_loss"]) > chk["net_paid_amount"] + 1e-6
    ).mean()
    assert overlap_rate <= 0.05
