from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


# Domain priors used to smooth early-activity entities and avoid unstable rates.
SMOOTHING_STRENGTH = 12.0
GLOBAL_PRIORS = {
    "refund_flag": 0.17,
    "dispute_flag": 0.20,
    "chargeback_flag": 0.065,
}

CATEGORY_REFUND_PRIOR = {
    "Electronics": 0.14,
    "Fashion": 0.18,
    "Home": 0.13,
    "Beauty": 0.12,
    "Sports": 0.11,
    "Toys": 0.11,
    "Grocery": 0.09,
    "Digital Goods": 0.16,
}
CATEGORY_DISPUTE_PRIOR = {
    "Electronics": 0.22,
    "Fashion": 0.20,
    "Home": 0.18,
    "Beauty": 0.18,
    "Sports": 0.17,
    "Toys": 0.16,
    "Grocery": 0.13,
    "Digital Goods": 0.24,
}
CATEGORY_CHARGEBACK_PRIOR = {
    "Electronics": 0.08,
    "Fashion": 0.06,
    "Home": 0.05,
    "Beauty": 0.05,
    "Sports": 0.04,
    "Toys": 0.04,
    "Grocery": 0.03,
    "Digital Goods": 0.10,
}

PAYMENT_REFUND_PRIOR = {"low": 0.04, "medium": 0.08, "high": 0.14, "critical": 0.22}
PAYMENT_DISPUTE_PRIOR = {"low": 0.02, "medium": 0.06, "high": 0.13, "critical": 0.24}
PAYMENT_CHARGEBACK_PRIOR = {"low": 0.001, "medium": 0.004, "high": 0.02, "critical": 0.10}

CHANNEL_RISK_ADJ = {"web": 0.0, "mobile_app": 0.01, "social_commerce": 0.035}

ASSUMED_REFUND_SEVERITY = 0.85
ASSUMED_DISPUTE_SEVERITY = 0.70
ASSUMED_CHARGEBACK_SEVERITY = 0.22


@dataclass(frozen=True)
class FeatureBuildConfig:
    raw_dir: Path = Path("data/raw")
    output_dir: Path = Path("data/processed")
    trailing_window_days: int = 180


def _clip_series(series: pd.Series, low: float, high: float) -> pd.Series:
    return series.clip(lower=low, upper=high)


def _load_raw_tables(raw_dir: Path) -> Dict[str, pd.DataFrame]:
    return {
        "buyers": pd.read_csv(raw_dir / "buyers.csv", parse_dates=["signup_date"]),
        "sellers": pd.read_csv(raw_dir / "sellers.csv", parse_dates=["onboarding_date"]),
        "products": pd.read_csv(raw_dir / "products.csv"),
        "orders": pd.read_csv(raw_dir / "orders.csv", parse_dates=["order_date"]),
        "order_items": pd.read_csv(raw_dir / "order_items.csv"),
        "payments": pd.read_csv(raw_dir / "payments.csv"),
        "refunds": pd.read_csv(raw_dir / "refunds.csv", parse_dates=["refund_date"]),
        "disputes": pd.read_csv(raw_dir / "disputes.csv", parse_dates=["dispute_date"]),
        "logistics_events": pd.read_csv(
            raw_dir / "logistics_events.csv",
            parse_dates=["shipped_date", "delivered_date", "promised_delivery_date"],
        ),
    }


def _build_order_base(tables: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    orders = tables["orders"].copy()
    order_items = tables["order_items"].copy()
    products = tables["products"][["product_id", "category"]].copy()
    payments = tables["payments"].copy()
    refunds = tables["refunds"].copy()
    disputes = tables["disputes"].copy()
    logistics = tables["logistics_events"].copy()

    item_agg = (
        order_items.groupby("order_id", as_index=False)
        .agg(
            seller_id=("seller_id", "first"),
            commission_fee=("commission_fee", "sum"),
            order_margin_proxy=("margin_proxy", "sum"),
            gross_value_items=("gross_item_value", "sum"),
            net_value_items=("net_item_value", "sum"),
        )
        .copy()
    )

    item_with_category = order_items[["order_id", "product_id", "gross_item_value"]].merge(
        products, on="product_id", how="left"
    )
    item_with_category = item_with_category.sort_values(
        ["order_id", "gross_item_value", "product_id"], ascending=[True, False, True]
    )
    primary_category = item_with_category.drop_duplicates("order_id")[["order_id", "category"]]

    refund_agg = refunds.groupby("order_id", as_index=False)["refund_amount"].sum()
    dispute_agg = disputes.groupby("order_id", as_index=False)["dispute_amount"].sum()

    base = (
        orders.merge(item_agg, on="order_id", how="left")
        .merge(primary_category, on="order_id", how="left")
        .merge(payments[["order_id", "payment_status", "payment_attempts", "chargeback_flag", "payment_risk_signal"]], on="order_id", how="left")
        .merge(refund_agg, on="order_id", how="left")
        .merge(dispute_agg, on="order_id", how="left")
        .merge(
            logistics[
                [
                    "order_id",
                    "seller_id",
                    "shipped_date",
                    "delivered_date",
                    "promised_delivery_date",
                    "delay_days",
                    "cancellation_flag",
                ]
            ].rename(columns={"seller_id": "logistics_seller_id"}),
            on="order_id",
            how="left",
        )
    )

    base["seller_id"] = base["seller_id"].fillna(base["logistics_seller_id"])
    base["category"] = base["category"].fillna("Unknown")

    base["refund_amount"] = base["refund_amount"].fillna(0.0)
    base["dispute_amount"] = base["dispute_amount"].fillna(0.0)
    base["chargeback_flag"] = base["chargeback_flag"].fillna(0).astype(int)
    base["cancellation_flag"] = base["cancellation_flag"].fillna(0).astype(int)
    base["delay_days"] = base["delay_days"].fillna(0.0)
    base["commission_fee"] = base["commission_fee"].fillna(0.0)
    base["order_margin_proxy"] = base["order_margin_proxy"].fillna(0.0)

    base["gross_value"] = base["gross_order_value"].astype(float)
    base["net_value"] = base["net_paid_amount"].astype(float)
    base["promo_flag"] = base["promo_code_used"].notna().astype(int)
    base["refund_flag"] = (base["refund_amount"] > 0).astype(int)
    base["dispute_flag"] = (base["dispute_amount"] > 0).astype(int)

    delivery_eligible = (
        (base["cancellation_flag"] == 0)
        & (base["payment_status"] == "paid")
        & base["delivered_date"].notna()
        & base["promised_delivery_date"].notna()
    )
    base["delivery_eligible"] = delivery_eligible.astype(int)
    # Operationally, we treat delays of 3+ days as material and <=1 day as effectively on-time.
    base["delay_flag"] = ((base["delay_days"] >= 3) & delivery_eligible).astype(int)
    base["on_time_flag"] = ((base["delay_days"] <= 1) & delivery_eligible).astype(int)

    base = base.sort_values(["order_date", "order_id"]).reset_index(drop=True)
    return base


def _compute_entity_prior_rates(base: pd.DataFrame, entity_col: str, prefix: str) -> pd.DataFrame:
    temp = base[["order_id", entity_col, "order_date", "refund_flag", "dispute_flag", "chargeback_flag"]].copy()
    temp = temp.sort_values([entity_col, "order_date", "order_id"]).reset_index(drop=True)

    grouped = temp.groupby(entity_col, sort=False)
    temp[f"{prefix}_prior_orders"] = grouped.cumcount()

    for event_col in ["refund_flag", "dispute_flag", "chargeback_flag"]:
        prior_count = grouped[event_col].cumsum() - temp[event_col]
        prior_rate = (
            prior_count + SMOOTHING_STRENGTH * GLOBAL_PRIORS[event_col]
        ) / (temp[f"{prefix}_prior_orders"] + SMOOTHING_STRENGTH)
        temp[f"{prefix}_prior_{event_col}_rate"] = prior_rate.astype(float)

    return temp[
        [
            "order_id",
            f"{prefix}_prior_orders",
            f"{prefix}_prior_refund_flag_rate",
            f"{prefix}_prior_dispute_flag_rate",
            f"{prefix}_prior_chargeback_flag_rate",
        ]
    ]


def _add_repeat_buyer_flag(base: pd.DataFrame) -> pd.DataFrame:
    pair = base[["order_id", "seller_id", "buyer_id", "order_date"]].copy()
    pair = pair.sort_values(["seller_id", "buyer_id", "order_date", "order_id"]).reset_index(drop=True)
    pair["repeat_buyer_flag"] = (pair.groupby(["seller_id", "buyer_id"]).cumcount() > 0).astype(int)
    return pair[["order_id", "repeat_buyer_flag"]]


def _build_order_profitability_features(base: pd.DataFrame) -> pd.DataFrame:
    df = base.copy()

    df["category_refund_prior"] = df["category"].map(CATEGORY_REFUND_PRIOR).fillna(0.13)
    df["category_dispute_prior"] = df["category"].map(CATEGORY_DISPUTE_PRIOR).fillna(0.19)
    df["category_chargeback_prior"] = df["category"].map(CATEGORY_CHARGEBACK_PRIOR).fillna(0.06)

    df["payment_refund_prior"] = df["payment_risk_signal"].map(PAYMENT_REFUND_PRIOR).fillna(0.12)
    df["payment_dispute_prior"] = df["payment_risk_signal"].map(PAYMENT_DISPUTE_PRIOR).fillna(0.14)
    df["payment_chargeback_prior"] = df["payment_risk_signal"].map(PAYMENT_CHARGEBACK_PRIOR).fillna(0.04)

    df["channel_risk_adj"] = df["order_channel"].map(CHANNEL_RISK_ADJ).fillna(0.0)

    expected_refund_prob = (
        0.02
        + 0.25 * df["seller_prior_refund_flag_rate"]
        + 0.15 * df["buyer_prior_refund_flag_rate"]
        + 0.15 * df["payment_refund_prior"]
        + 0.10 * df["category_refund_prior"]
        + 0.04 * df["promo_flag"]
        + 0.03 * df["channel_risk_adj"]
    )

    expected_dispute_prob = (
        0.015
        + 0.23 * df["seller_prior_dispute_flag_rate"]
        + 0.12 * df["buyer_prior_dispute_flag_rate"]
        + 0.20 * df["payment_dispute_prior"]
        + 0.08 * df["category_dispute_prior"]
        + 0.06 * df["channel_risk_adj"]
    )

    expected_chargeback_prob = (
        0.002
        + 0.12 * df["seller_prior_chargeback_flag_rate"]
        + 0.10 * df["buyer_prior_chargeback_flag_rate"]
        + 0.28 * df["payment_chargeback_prior"]
        + 0.06 * df["category_chargeback_prior"]
        + 0.06 * df["channel_risk_adj"]
    )

    df["expected_refund_prob"] = _clip_series(expected_refund_prob, 0.01, 0.45)
    df["expected_dispute_prob"] = _clip_series(expected_dispute_prob, 0.005, 0.40)
    df["expected_chargeback_prob"] = _clip_series(expected_chargeback_prob, 0.001, 0.25)

    # Refund/dispute impact is modeled on commission exposure, while chargebacks can affect a broader value base.
    df["expected_refund_loss"] = df["commission_fee"] * df["expected_refund_prob"] * ASSUMED_REFUND_SEVERITY
    df["expected_dispute_loss"] = df["commission_fee"] * df["expected_dispute_prob"] * ASSUMED_DISPUTE_SEVERITY
    df["expected_chargeback_loss"] = df["net_value"] * df["expected_chargeback_prob"] * ASSUMED_CHARGEBACK_SEVERITY

    df["expected_total_risk_loss"] = (
        df["expected_refund_loss"] + df["expected_dispute_loss"] + df["expected_chargeback_loss"]
    )

    df["chargeback_loss_proxy"] = df["chargeback_flag"] * df["net_value"]
    df["realized_contribution_margin_proxy"] = (
        df["commission_fee"]
        - df["subsidy_amount"]
        - df["refund_amount"]
        - df["dispute_amount"]
        - df["chargeback_loss_proxy"]
    )
    df["estimated_margin_after_risk"] = df["order_margin_proxy"] - df["expected_total_risk_loss"]
    df["risk_adjusted_order_value"] = df["net_value"] - df["expected_total_risk_loss"]
    df["profitability_flag"] = np.where(df["estimated_margin_after_risk"] > 0, "profitable", "fragile")

    return df[
        [
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
        ]
    ].copy()


def _build_seller_monthly_quality(order_enriched: pd.DataFrame) -> pd.DataFrame:
    df = order_enriched.copy()
    df["month"] = df["order_date"].dt.to_period("M").astype(str)

    grouped = (
        df.groupby(["seller_id", "month"], as_index=False)
        .agg(
            orders=("order_id", "count"),
            GMV=("gross_value", "sum"),
            net_value=("net_value", "sum"),
            avg_margin_proxy=("order_margin_proxy", "mean"),
            refund_rate=("refund_flag", "mean"),
            dispute_rate=("dispute_flag", "mean"),
            chargeback_rate=("chargeback_flag", "mean"),
            cancellation_rate=("cancellation_flag", "mean"),
            delivery_eligible=("delivery_eligible", "sum"),
            delayed_orders=("delay_flag", "sum"),
            on_time_orders=("on_time_flag", "sum"),
            subsidy_sum=("subsidy_amount", "sum"),
            repeat_buyer_rate=("repeat_buyer_flag", "mean"),
            margin_sum=("order_margin_proxy", "sum"),
        )
        .copy()
    )

    grouped["delay_rate"] = grouped["delayed_orders"] / grouped["delivery_eligible"].replace(0, np.nan)
    grouped["on_time_rate"] = grouped["on_time_orders"] / grouped["delivery_eligible"].replace(0, np.nan)
    grouped["promo_dependency_rate"] = grouped["subsidy_sum"] / grouped["GMV"].replace(0, np.nan)

    grouped[["delay_rate", "on_time_rate", "promo_dependency_rate"]] = grouped[
        ["delay_rate", "on_time_rate", "promo_dependency_rate"]
    ].fillna(0.0)

    margin_rate = grouped["margin_sum"] / grouped["GMV"].replace(0, np.nan)
    margin_rate = margin_rate.fillna(0.0)

    quality_score = (
        100.0
        * (
            0.24 * (1.0 - grouped["refund_rate"])
            + 0.17 * (1.0 - grouped["dispute_rate"])
            + 0.12 * (1.0 - grouped["chargeback_rate"])
            + 0.12 * (1.0 - grouped["cancellation_rate"])
            + 0.13 * grouped["on_time_rate"]
            + 0.10 * (1.0 - grouped["promo_dependency_rate"].clip(upper=1.0))
            + 0.12 * grouped["repeat_buyer_rate"]
        )
    )
    quality_score = quality_score + (margin_rate * 100.0).clip(lower=-12.0, upper=12.0)
    grouped["seller_quality_proxy"] = quality_score.clip(lower=0.0, upper=100.0)

    grouped["fragility_flag"] = np.where(
        (
            (grouped["seller_quality_proxy"] < 60.0)
            | ((margin_rate < 0.0) & (grouped["promo_dependency_rate"] > 0.15))
            | ((grouped["refund_rate"] > 0.35) & (grouped["dispute_rate"] > 0.35))
            | (grouped["chargeback_rate"] > 0.20)
        ),
        "fragile",
        "stable",
    )

    return grouped[
        [
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
        ]
    ].copy()


def _build_buyer_behavior_risk(
    order_enriched: pd.DataFrame,
    buyers: pd.DataFrame,
    snapshot_date: pd.Timestamp,
    trailing_window_days: int,
) -> pd.DataFrame:
    start_date = snapshot_date - pd.Timedelta(days=trailing_window_days)

    window = order_enriched[
        (order_enriched["order_date"] >= start_date) & (order_enriched["order_date"] < snapshot_date)
    ].copy()

    buyer_agg = (
        window.groupby("buyer_id", as_index=False)
        .agg(
            trailing_order_count=("order_id", "count"),
            refund_count=("refund_flag", "sum"),
            dispute_count=("dispute_flag", "sum"),
            chargeback_count=("chargeback_flag", "sum"),
            gross_sum=("gross_value", "sum"),
            promo_count=("promo_flag", "sum"),
        )
        .copy()
    )

    out = buyers[["buyer_id"]].merge(buyer_agg, on="buyer_id", how="left")
    out[["trailing_order_count", "refund_count", "dispute_count", "chargeback_count", "gross_sum", "promo_count"]] = out[
        ["trailing_order_count", "refund_count", "dispute_count", "chargeback_count", "gross_sum", "promo_count"]
    ].fillna(0.0)

    out["trailing_order_count"] = out["trailing_order_count"].astype(int)

    denom_refund = out["trailing_order_count"] + 12.0
    denom_dispute = out["trailing_order_count"] + 12.0
    denom_chargeback = out["trailing_order_count"] + 20.0

    out["refund_frequency"] = (out["refund_count"] + 1.0) / denom_refund
    out["dispute_frequency"] = (out["dispute_count"] + 1.0) / denom_dispute
    out["chargeback_frequency"] = (out["chargeback_count"] + 0.5) / denom_chargeback

    out["average_order_value"] = out["gross_sum"] / out["trailing_order_count"].replace(0, np.nan)
    out["average_order_value"] = out["average_order_value"].fillna(0.0)

    out["promo_usage_rate"] = out["promo_count"] / out["trailing_order_count"].replace(0, np.nan)
    out["promo_usage_rate"] = out["promo_usage_rate"].fillna(0.0)

    def _flags(row: pd.Series) -> str:
        flags = []
        if row["trailing_order_count"] == 0:
            return "no_recent_activity"
        if row["refund_frequency"] > 0.25:
            flags.append("high_refund_frequency")
        if row["dispute_frequency"] > 0.18:
            flags.append("high_dispute_frequency")
        if row["chargeback_frequency"] > 0.08:
            flags.append("high_chargeback_frequency")
        if row["promo_usage_rate"] > 0.75:
            flags.append("promo_dependence")
        if row["trailing_order_count"] > 20 and (
            row["dispute_frequency"] > 0.12 or row["chargeback_frequency"] > 0.05
        ):
            flags.append("high_velocity_high_risk")
        if not flags:
            flags.append("none")
        return "|".join(flags)

    out["abnormal_behavior_flags"] = out.apply(_flags, axis=1)

    risk_score = 100.0 * (
        0.40 * out["refund_frequency"]
        + 0.30 * out["dispute_frequency"]
        + 0.20 * out["chargeback_frequency"]
        + 0.10 * out["promo_usage_rate"]
    )
    risk_score = risk_score + np.where(out["trailing_order_count"] >= 10, 5.0, 0.0)
    out["order_risk_proxy"] = _clip_series(risk_score, 0.0, 100.0)

    return out[
        [
            "buyer_id",
            "trailing_order_count",
            "refund_frequency",
            "dispute_frequency",
            "chargeback_frequency",
            "average_order_value",
            "promo_usage_rate",
            "abnormal_behavior_flags",
            "order_risk_proxy",
        ]
    ].copy()


def _build_category_risk_summary(order_enriched: pd.DataFrame) -> pd.DataFrame:
    df = order_enriched.copy()
    df["month"] = df["order_date"].dt.to_period("M").astype(str)
    df["negative_margin_flag"] = (df["estimated_margin_after_risk"] < 0).astype(int)

    out = (
        df.groupby(["month", "category"], as_index=False)
        .agg(
            GMV=("gross_value", "sum"),
            net_value=("net_value", "sum"),
            subsidy_sum=("subsidy_amount", "sum"),
            refund_rate=("refund_flag", "mean"),
            dispute_rate=("dispute_flag", "mean"),
            chargeback_rate=("chargeback_flag", "mean"),
            negative_margin_rate=("negative_margin_flag", "mean"),
        )
        .copy()
    )

    out["subsidy_rate"] = out["subsidy_sum"] / out["GMV"].replace(0, np.nan)
    out["subsidy_rate"] = out["subsidy_rate"].fillna(0.0)

    out["margin_fragility_index"] = 100.0 * (
        0.30 * out["refund_rate"]
        + 0.25 * out["dispute_rate"]
        + 0.15 * out["chargeback_rate"]
        + 0.20 * out["subsidy_rate"]
        + 0.10 * out["negative_margin_rate"]
    )
    out["margin_fragility_index"] = _clip_series(out["margin_fragility_index"], 0.0, 100.0)

    return out[
        [
            "month",
            "category",
            "GMV",
            "net_value",
            "refund_rate",
            "dispute_rate",
            "subsidy_rate",
            "margin_fragility_index",
        ]
    ].copy()


def _build_seller_risk_base(
    order_enriched: pd.DataFrame,
    buyer_behavior_risk: pd.DataFrame,
    snapshot_date: pd.Timestamp,
    trailing_window_days: int,
) -> pd.DataFrame:
    current_period = (snapshot_date - pd.Timedelta(days=1)).to_period("M").strftime("%Y-%m")
    start_date = snapshot_date - pd.Timedelta(days=trailing_window_days)

    window = order_enriched[
        (order_enriched["order_date"] >= start_date) & (order_enriched["order_date"] < snapshot_date)
    ].copy()

    window = window.merge(
        buyer_behavior_risk[["buyer_id", "order_risk_proxy"]],
        on="buyer_id",
        how="left",
    )
    window["high_risk_buyer_flag"] = (window["order_risk_proxy"].fillna(0.0) >= 60.0).astype(int)

    grouped = (
        window.groupby("seller_id", as_index=False)
        .agg(
            orders=("order_id", "count"),
            gmv=("gross_value", "sum"),
            net_value=("net_value", "sum"),
            avg_margin_after_risk=("estimated_margin_after_risk", "mean"),
            margin_after_risk_sum=("estimated_margin_after_risk", "sum"),
            refund_rate=("refund_flag", "mean"),
            dispute_rate=("dispute_flag", "mean"),
            chargeback_rate=("chargeback_flag", "mean"),
            cancellation_rate=("cancellation_flag", "mean"),
            delayed_order_rate=("delay_flag", "mean"),
            avg_delay_days=("delay_days", "mean"),
            on_time_rate=("on_time_flag", "mean"),
            promo_dependency_rate=("subsidy_amount", "sum"),
            repeat_buyer_rate=("repeat_buyer_flag", "mean"),
            high_risk_buyer_share=("high_risk_buyer_flag", "mean"),
        )
        .copy()
    )

    grouped["promo_dependency_rate"] = grouped["promo_dependency_rate"] / grouped["gmv"].replace(0, np.nan)
    grouped["promo_dependency_rate"] = grouped["promo_dependency_rate"].fillna(0.0)

    grouped["margin_rate"] = grouped["margin_after_risk_sum"] / grouped["gmv"].replace(0, np.nan)
    grouped["margin_rate"] = grouped["margin_rate"].fillna(0.0)

    total_gmv = grouped["gmv"].sum()
    total_orders = grouped["orders"].sum()

    grouped["gmv_share"] = grouped["gmv"] / total_gmv if total_gmv > 0 else 0.0
    grouped["order_share"] = grouped["orders"] / total_orders if total_orders > 0 else 0.0
    grouped["gmv_rank_percentile"] = grouped["gmv"].rank(method="average", pct=True)
    grouped["top_decile_volume"] = (grouped["gmv_rank_percentile"] >= 0.90).astype(int)

    def _pack_json(row: pd.Series, mapping: Dict[str, str]) -> str:
        payload = {out_key: round(float(row[in_key]), 6) for out_key, in_key in mapping.items()}
        return json.dumps(payload, sort_keys=True)

    grouped["quality_inputs"] = grouped.apply(
        lambda r: _pack_json(
            r,
            {
                "refund_rate": "refund_rate",
                "cancellation_rate": "cancellation_rate",
                "on_time_rate": "on_time_rate",
                "repeat_buyer_rate": "repeat_buyer_rate",
            },
        ),
        axis=1,
    )

    grouped["fraud_inputs"] = grouped.apply(
        lambda r: _pack_json(
            r,
            {
                "dispute_rate": "dispute_rate",
                "chargeback_rate": "chargeback_rate",
                "high_risk_buyer_share": "high_risk_buyer_share",
            },
        ),
        axis=1,
    )

    grouped["profitability_inputs"] = grouped.apply(
        lambda r: _pack_json(
            r,
            {
                "avg_margin_after_risk": "avg_margin_after_risk",
                "margin_rate": "margin_rate",
                "promo_dependency_rate": "promo_dependency_rate",
            },
        ),
        axis=1,
    )

    grouped["operational_inputs"] = grouped.apply(
        lambda r: _pack_json(
            r,
            {
                "delayed_order_rate": "delayed_order_rate",
                "avg_delay_days": "avg_delay_days",
                "cancellation_rate": "cancellation_rate",
            },
        ),
        axis=1,
    )

    grouped["concentration_inputs"] = grouped.apply(
        lambda r: _pack_json(
            r,
            {
                "gmv_share": "gmv_share",
                "order_share": "order_share",
                "gmv_rank_percentile": "gmv_rank_percentile",
                "top_decile_volume": "top_decile_volume",
            },
        ),
        axis=1,
    )

    grouped["current_period"] = current_period

    return grouped[
        [
            "seller_id",
            "current_period",
            "quality_inputs",
            "fraud_inputs",
            "profitability_inputs",
            "operational_inputs",
            "concentration_inputs",
        ]
    ].copy()


def build_feature_layer(cfg: FeatureBuildConfig) -> Dict[str, pd.DataFrame]:
    tables = _load_raw_tables(cfg.raw_dir)
    base = _build_order_base(tables)

    seller_priors = _compute_entity_prior_rates(base, entity_col="seller_id", prefix="seller")
    buyer_priors = _compute_entity_prior_rates(base, entity_col="buyer_id", prefix="buyer")
    repeat_flags = _add_repeat_buyer_flag(base)

    enriched = (
        base.merge(seller_priors, on="order_id", how="left")
        .merge(buyer_priors, on="order_id", how="left")
        .merge(repeat_flags, on="order_id", how="left")
    )
    enriched["repeat_buyer_flag"] = enriched["repeat_buyer_flag"].fillna(0).astype(int)

    order_profitability_features = _build_order_profitability_features(enriched)

    # Extend with intermediate features needed by later tables while keeping no-leakage priors.
    enriched = enriched.merge(
        order_profitability_features[
            ["order_id", "estimated_margin_after_risk", "risk_adjusted_order_value", "profitability_flag"]
        ],
        on="order_id",
        how="left",
    )

    seller_monthly_quality = _build_seller_monthly_quality(enriched)

    snapshot_date = tables["orders"]["order_date"].max().normalize() + pd.Timedelta(days=1)
    buyer_behavior_risk = _build_buyer_behavior_risk(
        order_enriched=enriched,
        buyers=tables["buyers"],
        snapshot_date=snapshot_date,
        trailing_window_days=cfg.trailing_window_days,
    )

    category_risk_summary = _build_category_risk_summary(enriched)

    seller_risk_base = _build_seller_risk_base(
        order_enriched=enriched,
        buyer_behavior_risk=buyer_behavior_risk,
        snapshot_date=snapshot_date,
        trailing_window_days=cfg.trailing_window_days,
    )

    return {
        "order_profitability_features": order_profitability_features,
        "seller_monthly_quality": seller_monthly_quality,
        "buyer_behavior_risk": buyer_behavior_risk,
        "category_risk_summary": category_risk_summary,
        "seller_risk_base": seller_risk_base,
    }


def save_feature_tables(feature_tables: Dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for table_name, df in feature_tables.items():
        df.to_csv(output_dir / f"{table_name}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build analytical feature layer for marketplace command center.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--trailing-window-days", type=int, default=180)

    args = parser.parse_args()

    cfg = FeatureBuildConfig(
        raw_dir=args.raw_dir,
        output_dir=args.output_dir,
        trailing_window_days=args.trailing_window_days,
    )

    tables = build_feature_layer(cfg)
    save_feature_tables(tables, cfg.output_dir)

    print("Analytical feature layer generated:")
    for name, df in tables.items():
        print(f"  - {name}: {len(df):,} rows")


if __name__ == "__main__":
    main()
