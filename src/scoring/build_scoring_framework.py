from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ScoringConfig:
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    trailing_window_days: int = 180


RISK_TIER_BINS = [0.0, 30.0, 55.0, 75.0, 100.0001]
RISK_TIER_LABELS = ["Low", "Moderate", "High", "Critical"]


def _clip(series: pd.Series, low: float = 0.0, high: float = 100.0) -> pd.Series:
    return series.clip(lower=low, upper=high)


def _to_score(rate: pd.Series, upper_ref: float) -> pd.Series:
    return _clip((rate / upper_ref) * 100.0)


def _tier_from_score(score: pd.Series) -> pd.Series:
    return pd.cut(score, bins=RISK_TIER_BINS, labels=RISK_TIER_LABELS, right=False).astype(str)


def _main_driver(df: pd.DataFrame, contrib_cols: Dict[str, str]) -> pd.Series:
    contrib_df = pd.DataFrame({name: df[col] for name, col in contrib_cols.items()})
    return contrib_df.idxmax(axis=1)


def _compute_prior_rates(
    df: pd.DataFrame,
    entity_col: str,
    time_col: str,
    event_cols: Iterable[str],
    smoothing_strength: float,
    priors: Dict[str, float],
    prefix: str,
) -> pd.DataFrame:
    temp = df[["order_id", entity_col, time_col, *event_cols]].copy()
    temp = temp.sort_values([entity_col, time_col, "order_id"]).reset_index(drop=True)
    grouped = temp.groupby(entity_col, sort=False)

    temp[f"{prefix}_prior_orders"] = grouped.cumcount()

    for event_col in event_cols:
        prior_count = grouped[event_col].cumsum() - temp[event_col]
        rate = (prior_count + smoothing_strength * priors[event_col]) / (
            temp[f"{prefix}_prior_orders"] + smoothing_strength
        )
        temp[f"{prefix}_prior_{event_col}_rate"] = rate.astype(float)

    keep = [
        "order_id",
        f"{prefix}_prior_orders",
        *[f"{prefix}_prior_{col}_rate" for col in event_cols],
    ]
    return temp[keep]


def _load_raw(raw_dir: Path) -> Dict[str, pd.DataFrame]:
    return {
        "buyers": pd.read_csv(raw_dir / "buyers.csv", parse_dates=["signup_date"]),
        "sellers": pd.read_csv(raw_dir / "sellers.csv", parse_dates=["onboarding_date"]),
        "products": pd.read_csv(raw_dir / "products.csv"),
        "orders": pd.read_csv(raw_dir / "orders.csv", parse_dates=["order_date"]),
        "order_items": pd.read_csv(raw_dir / "order_items.csv"),
        "payments": pd.read_csv(raw_dir / "payments.csv"),
        "refunds": pd.read_csv(raw_dir / "refunds.csv", parse_dates=["refund_date"]),
        "disputes": pd.read_csv(raw_dir / "disputes.csv", parse_dates=["dispute_date"]),
        "logistics": pd.read_csv(
            raw_dir / "logistics_events.csv",
            parse_dates=["shipped_date", "delivered_date", "promised_delivery_date"],
        ),
    }


def _load_processed(processed_dir: Path) -> Dict[str, pd.DataFrame]:
    return {
        "opf": pd.read_csv(processed_dir / "order_profitability_features.csv", parse_dates=["order_date"]),
        "smq": pd.read_csv(processed_dir / "seller_monthly_quality.csv"),
    }


def _build_order_base(raw: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    orders = raw["orders"]
    items = raw["order_items"]
    products = raw["products"]
    payments = raw["payments"]
    refunds = raw["refunds"]
    disputes = raw["disputes"]
    logistics = raw["logistics"]

    item_agg = items.groupby("order_id", as_index=False).agg(
        seller_id=("seller_id", "first"),
        commission_fee=("commission_fee", "sum"),
    )

    primary_cat = (
        items[["order_id", "product_id", "gross_item_value"]]
        .merge(products[["product_id", "category"]], on="product_id", how="left")
        .sort_values(["order_id", "gross_item_value", "product_id"], ascending=[True, False, True])
        .drop_duplicates("order_id")[["order_id", "category"]]
    )

    ref_agg = refunds.groupby("order_id", as_index=False)["refund_amount"].sum()
    dis_agg = disputes.groupby("order_id", as_index=False)["dispute_amount"].sum()

    base = (
        orders[
            [
                "order_id",
                "buyer_id",
                "order_date",
                "order_channel",
                "payment_method",
                "gross_order_value",
                "subsidy_amount",
                "net_paid_amount",
            ]
        ]
        .merge(item_agg, on="order_id", how="left")
        .merge(primary_cat, on="order_id", how="left")
        .merge(payments[["order_id", "payment_risk_signal", "chargeback_flag"]], on="order_id", how="left")
        .merge(ref_agg, on="order_id", how="left")
        .merge(dis_agg, on="order_id", how="left")
        .merge(
            logistics[["order_id", "delay_days", "cancellation_flag", "delivered_date", "promised_delivery_date"]],
            on="order_id",
            how="left",
        )
    )

    base["refund_amount"] = base["refund_amount"].fillna(0.0)
    base["dispute_amount"] = base["dispute_amount"].fillna(0.0)
    base["chargeback_flag"] = base["chargeback_flag"].fillna(0).astype(int)
    base["delay_days"] = base["delay_days"].fillna(0.0)
    base["cancellation_flag"] = base["cancellation_flag"].fillna(0).astype(int)
    base["category"] = base["category"].fillna("Unknown")

    base["refund_flag"] = (base["refund_amount"] > 0).astype(int)
    base["dispute_flag"] = (base["dispute_amount"] > 0).astype(int)

    base = base.sort_values(["order_date", "order_id"]).reset_index(drop=True)
    return base


def _order_actions(tier: str, driver: str) -> str:
    if tier == "Low":
        return "monitor only"
    if tier == "Moderate":
        if driver in {"seller_history", "buyer_history"}:
            return "escalate for manual review"
        if driver in {"channel_risk", "category_risk"}:
            return "tighten promo eligibility"
        return "review fraud controls"
    if tier == "High":
        if driver == "seller_history":
            return "investigate dispute cluster"
        if driver in {"payment_signal", "payment_method"}:
            return "review fraud controls"
        return "escalate for manual review"
    # Critical
    if driver == "seller_history":
        return "hold payouts"
    return "escalate for manual review"


def _seller_actions(tier: str, driver: str) -> str:
    if tier == "Low":
        return "monitor only"
    if tier == "Moderate":
        if driver in {"delay_risk", "on_time_risk", "cancellation_risk"}:
            return "seller coaching required"
        return "monitor only"
    if tier == "High":
        if driver in {"dispute_risk", "chargeback_risk"}:
            return "investigate dispute cluster"
        if driver in {"delay_risk", "on_time_risk", "cancellation_risk"}:
            return "improve fulfillment SLA enforcement"
        return "seller coaching required"
    # Critical
    if driver in {"dispute_risk", "chargeback_risk"}:
        return "hold payouts"
    return "audit seller operations"


def _fraud_actions(tier: str, driver: str) -> str:
    if tier == "Low":
        return "monitor only"
    if tier == "Moderate":
        return "review fraud controls"
    if tier == "High":
        if driver in {"suspicious_cluster_share", "high_risk_order_share"}:
            return "investigate dispute cluster"
        return "review fraud controls"
    return "hold payouts"


def _margin_actions(tier: str, driver: str) -> str:
    if tier == "Low":
        return "monitor only"
    if tier == "Moderate":
        return "reduce subsidy exposure"
    if tier == "High":
        if driver == "subsidy_dependency":
            return "tighten promo eligibility"
        return "reduce subsidy exposure"
    if driver in {"refund_value_risk", "dispute_value_risk"}:
        return "investigate dispute cluster"
    return "reduce subsidy exposure"


def _priority_actions(tier: str, driver: str) -> str:
    if tier == "Low":
        return "monitor only"
    if tier == "Moderate":
        return "seller coaching required"
    if tier == "High":
        if driver == "fraud_exposure":
            return "review fraud controls"
        if driver == "margin_fragility":
            return "reduce subsidy exposure"
        if driver == "seller_quality":
            return "audit seller operations"
        return "investigate dispute cluster"
    # Critical
    if driver == "fraud_exposure":
        return "hold payouts"
    if driver == "margin_fragility":
        return "tighten promo eligibility"
    if driver == "seller_quality":
        return "audit seller operations"
    return "escalate for manual review"


def _build_order_risk_scores(base: pd.DataFrame) -> pd.DataFrame:
    event_cols = ["refund_flag", "dispute_flag", "chargeback_flag"]
    priors = {col: float(base[col].mean()) for col in event_cols}

    seller_priors = _compute_prior_rates(
        df=base,
        entity_col="seller_id",
        time_col="order_date",
        event_cols=event_cols,
        smoothing_strength=10.0,
        priors=priors,
        prefix="seller",
    )
    buyer_priors = _compute_prior_rates(
        df=base,
        entity_col="buyer_id",
        time_col="order_date",
        event_cols=event_cols,
        smoothing_strength=12.0,
        priors=priors,
        prefix="buyer",
    )

    df = base.merge(seller_priors, on="order_id", how="left").merge(buyer_priors, on="order_id", how="left")

    payment_signal_map = {"low": 18.0, "medium": 40.0, "high": 67.0, "critical": 90.0}
    payment_method_map = {
        "bank_transfer": 30.0,
        "debit_card": 36.0,
        "credit_card": 40.0,
        "digital_wallet": 58.0,
        "prepaid_card": 85.0,
    }
    channel_map = {"web": 32.0, "mobile_app": 45.0, "social_commerce": 75.0}
    category_map = {
        "Sports": 35.0,
        "Toys": 38.0,
        "Beauty": 42.0,
        "Home": 45.0,
        "Grocery": 48.0,
        "Fashion": 55.0,
        "Electronics": 72.0,
        "Digital Goods": 78.0,
        "Unknown": 50.0,
    }

    df["comp_payment_signal"] = df["payment_risk_signal"].map(payment_signal_map).fillna(50.0)
    df["comp_payment_method"] = df["payment_method"].map(payment_method_map).fillna(50.0)
    df["comp_channel"] = df["order_channel"].map(channel_map).fillna(50.0)
    df["comp_category"] = df["category"].map(category_map).fillna(50.0)

    buyer_history = (
        0.45 * _to_score(df["buyer_prior_dispute_flag_rate"], 0.30)
        + 0.35 * _to_score(df["buyer_prior_chargeback_flag_rate"], 0.12)
        + 0.20 * _to_score(df["buyer_prior_refund_flag_rate"], 0.30)
    )
    seller_history = (
        0.45 * _to_score(df["seller_prior_dispute_flag_rate"], 0.30)
        + 0.35 * _to_score(df["seller_prior_chargeback_flag_rate"], 0.12)
        + 0.20 * _to_score(df["seller_prior_refund_flag_rate"], 0.30)
    )

    df["comp_buyer_history"] = _clip(buyer_history)
    df["comp_seller_history"] = _clip(seller_history)

    df["amount_pct_rank"] = df["gross_order_value"].rank(pct=True)
    df["comp_order_value"] = _clip(100.0 * df["amount_pct_rank"])

    weights = {
        "payment_signal": 0.25,
        "payment_method": 0.14,
        "channel_risk": 0.12,
        "category_risk": 0.12,
        "buyer_history": 0.17,
        "seller_history": 0.15,
        "order_value": 0.05,
    }

    df["order_risk_score"] = _clip(
        weights["payment_signal"] * df["comp_payment_signal"]
        + weights["payment_method"] * df["comp_payment_method"]
        + weights["channel_risk"] * df["comp_channel"]
        + weights["category_risk"] * df["comp_category"]
        + weights["buyer_history"] * df["comp_buyer_history"]
        + weights["seller_history"] * df["comp_seller_history"]
        + weights["order_value"] * df["comp_order_value"]
    )

    contrib_cols = {
        "payment_signal": "w_payment_signal",
        "payment_method": "w_payment_method",
        "channel_risk": "w_channel",
        "category_risk": "w_category",
        "buyer_history": "w_buyer_history",
        "seller_history": "w_seller_history",
        "order_value": "w_order_value",
    }
    df["w_payment_signal"] = weights["payment_signal"] * df["comp_payment_signal"]
    df["w_payment_method"] = weights["payment_method"] * df["comp_payment_method"]
    df["w_channel"] = weights["channel_risk"] * df["comp_channel"]
    df["w_category"] = weights["category_risk"] * df["comp_category"]
    df["w_buyer_history"] = weights["buyer_history"] * df["comp_buyer_history"]
    df["w_seller_history"] = weights["seller_history"] * df["comp_seller_history"]
    df["w_order_value"] = weights["order_value"] * df["comp_order_value"]

    df["order_risk_tier"] = _tier_from_score(df["order_risk_score"])
    df["order_risk_main_driver"] = _main_driver(df, contrib_cols)
    df["recommended_action"] = [
        _order_actions(tier, driver)
        for tier, driver in zip(df["order_risk_tier"], df["order_risk_main_driver"], strict=False)
    ]

    return df[
        [
            "order_id",
            "order_date",
            "buyer_id",
            "seller_id",
            "category",
            "order_channel",
            "payment_method",
            "order_risk_score",
            "order_risk_tier",
            "order_risk_main_driver",
            "recommended_action",
        ]
    ].copy()


def _build_seller_level_base(
    base: pd.DataFrame,
    order_scores: pd.DataFrame,
    processed: Dict[str, pd.DataFrame],
    trailing_window_days: int,
) -> pd.DataFrame:
    snapshot_date = base["order_date"].max().normalize() + pd.Timedelta(days=1)
    start_date = snapshot_date - pd.Timedelta(days=trailing_window_days)

    window = base[(base["order_date"] >= start_date) & (base["order_date"] < snapshot_date)].copy()
    window = window.merge(order_scores[["order_id", "order_risk_score"]], on="order_id", how="left")

    pair = window[["order_id", "seller_id", "buyer_id", "order_date"]].copy()
    pair = pair.sort_values(["seller_id", "buyer_id", "order_date", "order_id"])
    pair["repeat_buyer_flag"] = (pair.groupby(["seller_id", "buyer_id"]).cumcount() > 0).astype(int)
    window = window.merge(pair[["order_id", "repeat_buyer_flag"]], on="order_id", how="left")

    eligible = (
        (window["cancellation_flag"] == 0)
        & window["delivered_date"].notna()
        & window["promised_delivery_date"].notna()
    )
    window["delivery_eligible"] = eligible.astype(int)
    window["delay_flag"] = ((window["delay_days"] >= 3) & eligible).astype(int)
    window["on_time_flag"] = ((window["delay_days"] <= 1) & eligible).astype(int)
    window["high_risk_order_flag"] = (window["order_risk_score"] >= 75.0).astype(int)
    window["critical_payment_flag"] = (window["payment_risk_signal"] == "critical").astype(int)

    window["suspicious_cluster_flag"] = (
        (window["order_channel"] == "social_commerce")
        & (window["category"].isin(["Electronics", "Digital Goods"]))
        & (window["payment_method"].isin(["prepaid_card", "digital_wallet"]))
    ).astype(int)

    seller = (
        window.groupby("seller_id", as_index=False)
        .agg(
            orders=("order_id", "count"),
            gmv=("gross_order_value", "sum"),
            net_value=("net_paid_amount", "sum"),
            commission_fee=("commission_fee", "sum"),
            subsidy_amount=("subsidy_amount", "sum"),
            refund_amount=("refund_amount", "sum"),
            dispute_amount=("dispute_amount", "sum"),
            refund_rate=("refund_flag", "mean"),
            dispute_rate=("dispute_flag", "mean"),
            chargeback_rate=("chargeback_flag", "mean"),
            cancellation_rate=("cancellation_flag", "mean"),
            delay_rate=("delay_flag", "mean"),
            on_time_rate=("on_time_flag", "mean"),
            promo_dependency_rate=("subsidy_amount", "sum"),
            repeat_buyer_rate=("repeat_buyer_flag", "mean"),
            high_risk_order_share=("high_risk_order_flag", "mean"),
            critical_payment_share=("critical_payment_flag", "mean"),
            suspicious_cluster_share=("suspicious_cluster_flag", "mean"),
            average_order_risk=("order_risk_score", "mean"),
            margin_after_risk=("order_id", "count"),
        )
        .copy()
    )

    # Pull risk-adjusted margin from processed order features (no re-estimation).
    opf = processed["opf"]
    opf_window = opf[(opf["order_date"] >= start_date) & (opf["order_date"] < snapshot_date)].copy()
    # `order_profitability_features` already carries `seller_id`; no need to remap here.
    opf_seller = opf_window.groupby("seller_id", as_index=False).agg(
        margin_after_risk=("estimated_margin_after_risk", "sum"),
        negative_margin_share=("estimated_margin_after_risk", lambda x: (x < 0).mean()),
    )

    seller = seller.drop(columns=["margin_after_risk"]).merge(opf_seller, on="seller_id", how="left")

    seller["promo_dependency_rate"] = seller["promo_dependency_rate"] / seller["gmv"].replace(0, np.nan)
    seller["promo_dependency_rate"] = seller["promo_dependency_rate"].fillna(0.0)
    seller["refund_value_rate"] = seller["refund_amount"] / seller["net_value"].replace(0, np.nan)
    seller["dispute_value_rate"] = seller["dispute_amount"] / seller["net_value"].replace(0, np.nan)
    seller["commission_rate"] = seller["commission_fee"] / seller["net_value"].replace(0, np.nan)
    seller["margin_after_risk_rate"] = seller["margin_after_risk"] / seller["net_value"].replace(0, np.nan)

    rate_cols = [
        "refund_value_rate",
        "dispute_value_rate",
        "commission_rate",
        "margin_after_risk_rate",
        "negative_margin_share",
    ]
    for col in rate_cols:
        seller[col] = seller[col].fillna(0.0)

    seller["current_period"] = (snapshot_date - pd.Timedelta(days=1)).to_period("M").strftime("%Y-%m")

    # Enrich with monthly quality summary for stabilization.
    smq = processed["smq"]
    recent_months = sorted(smq["month"].unique())[-3:]
    smq_recent = smq[smq["month"].isin(recent_months)]
    smq_agg = smq_recent.groupby("seller_id", as_index=False).agg(
        smq_quality_proxy=("seller_quality_proxy", "mean"),
        smq_fragility_share=("fragility_flag", lambda x: (x == "fragile").mean()),
    )

    seller = seller.merge(smq_agg, on="seller_id", how="left")
    seller[["smq_quality_proxy", "smq_fragility_share"]] = seller[
        ["smq_quality_proxy", "smq_fragility_share"]
    ].fillna(0.0)

    # Concentration metrics.
    seller["gmv_rank_pct"] = seller["gmv"].rank(pct=True, method="average")
    seller["order_rank_pct"] = seller["orders"].rank(pct=True, method="average")

    return seller


def _build_seller_quality_scores(seller: pd.DataFrame) -> pd.DataFrame:
    df = seller.copy()

    df["c_refund"] = _to_score(df["refund_rate"], 0.30)
    df["c_dispute"] = _to_score(df["dispute_rate"], 0.30)
    df["c_chargeback"] = _to_score(df["chargeback_rate"], 0.15)
    df["c_cancellation"] = _to_score(df["cancellation_rate"], 0.20)
    df["c_delay"] = _to_score(df["delay_rate"], 0.45)
    df["c_on_time"] = _to_score(1.0 - df["on_time_rate"], 0.60)
    df["c_repeat_penalty"] = _to_score((0.45 - df["repeat_buyer_rate"]).clip(lower=0.0), 0.45)

    weights = {
        "refund_risk": 0.22,
        "dispute_risk": 0.20,
        "chargeback_risk": 0.16,
        "cancellation_risk": 0.10,
        "delay_risk": 0.12,
        "on_time_risk": 0.12,
        "repeat_buyer_risk": 0.08,
    }

    df["seller_quality_score"] = _clip(
        weights["refund_risk"] * df["c_refund"]
        + weights["dispute_risk"] * df["c_dispute"]
        + weights["chargeback_risk"] * df["c_chargeback"]
        + weights["cancellation_risk"] * df["c_cancellation"]
        + weights["delay_risk"] * df["c_delay"]
        + weights["on_time_risk"] * df["c_on_time"]
        + weights["repeat_buyer_risk"] * df["c_repeat_penalty"]
    )

    df["w_refund"] = weights["refund_risk"] * df["c_refund"]
    df["w_dispute"] = weights["dispute_risk"] * df["c_dispute"]
    df["w_chargeback"] = weights["chargeback_risk"] * df["c_chargeback"]
    df["w_cancellation"] = weights["cancellation_risk"] * df["c_cancellation"]
    df["w_delay"] = weights["delay_risk"] * df["c_delay"]
    df["w_on_time"] = weights["on_time_risk"] * df["c_on_time"]
    df["w_repeat"] = weights["repeat_buyer_risk"] * df["c_repeat_penalty"]

    contrib = {
        "refund_risk": "w_refund",
        "dispute_risk": "w_dispute",
        "chargeback_risk": "w_chargeback",
        "cancellation_risk": "w_cancellation",
        "delay_risk": "w_delay",
        "on_time_risk": "w_on_time",
        "repeat_buyer_risk": "w_repeat",
    }

    df["seller_quality_tier"] = _tier_from_score(df["seller_quality_score"])
    df["main_risk_driver"] = _main_driver(df, contrib)
    df["recommended_action"] = [
        _seller_actions(tier, driver)
        for tier, driver in zip(df["seller_quality_tier"], df["main_risk_driver"], strict=False)
    ]

    return df[
        [
            "seller_id",
            "current_period",
            "seller_quality_score",
            "seller_quality_tier",
            "main_risk_driver",
            "recommended_action",
        ]
    ].copy()


def _build_fraud_exposure_scores(seller: pd.DataFrame) -> pd.DataFrame:
    df = seller.copy()

    df["c_dispute"] = _to_score(df["dispute_rate"], 0.35)
    df["c_chargeback"] = _to_score(df["chargeback_rate"], 0.18)
    df["c_high_risk_orders"] = _to_score(df["high_risk_order_share"], 0.40)
    df["c_critical_payment"] = _to_score(df["critical_payment_share"], 0.60)
    df["c_suspicious_cluster"] = _to_score(df["suspicious_cluster_share"], 0.25)

    weights = {
        "dispute_risk": 0.30,
        "chargeback_risk": 0.30,
        "high_risk_order_share": 0.20,
        "critical_payment_share": 0.10,
        "suspicious_cluster_share": 0.10,
    }

    df["fraud_exposure_score"] = _clip(
        weights["dispute_risk"] * df["c_dispute"]
        + weights["chargeback_risk"] * df["c_chargeback"]
        + weights["high_risk_order_share"] * df["c_high_risk_orders"]
        + weights["critical_payment_share"] * df["c_critical_payment"]
        + weights["suspicious_cluster_share"] * df["c_suspicious_cluster"]
    )

    df["w_dispute"] = weights["dispute_risk"] * df["c_dispute"]
    df["w_chargeback"] = weights["chargeback_risk"] * df["c_chargeback"]
    df["w_highrisk"] = weights["high_risk_order_share"] * df["c_high_risk_orders"]
    df["w_critical"] = weights["critical_payment_share"] * df["c_critical_payment"]
    df["w_cluster"] = weights["suspicious_cluster_share"] * df["c_suspicious_cluster"]

    contrib = {
        "dispute_risk": "w_dispute",
        "chargeback_risk": "w_chargeback",
        "high_risk_order_share": "w_highrisk",
        "critical_payment_share": "w_critical",
        "suspicious_cluster_share": "w_cluster",
    }

    df["fraud_exposure_tier"] = _tier_from_score(df["fraud_exposure_score"])
    df["main_risk_driver"] = _main_driver(df, contrib)
    df["recommended_action"] = [
        _fraud_actions(tier, driver)
        for tier, driver in zip(df["fraud_exposure_tier"], df["main_risk_driver"], strict=False)
    ]

    return df[
        [
            "seller_id",
            "current_period",
            "fraud_exposure_score",
            "fraud_exposure_tier",
            "main_risk_driver",
            "recommended_action",
        ]
    ].copy()


def _build_margin_fragility_scores(seller: pd.DataFrame) -> pd.DataFrame:
    df = seller.copy()

    df["c_negative_margin"] = _to_score(df["negative_margin_share"], 0.60)
    df["c_subsidy"] = _to_score(df["promo_dependency_rate"], 0.12)
    df["c_refund_value"] = _to_score(df["refund_value_rate"], 0.25)
    df["c_dispute_value"] = _to_score(df["dispute_value_rate"], 0.30)
    df["c_commission_compression"] = _to_score((0.12 - df["commission_rate"]).clip(lower=0.0), 0.12)

    weights = {
        "negative_margin_share": 0.30,
        "subsidy_dependency": 0.25,
        "refund_value_risk": 0.20,
        "dispute_value_risk": 0.15,
        "commission_compression": 0.10,
    }

    df["margin_fragility_score"] = _clip(
        weights["negative_margin_share"] * df["c_negative_margin"]
        + weights["subsidy_dependency"] * df["c_subsidy"]
        + weights["refund_value_risk"] * df["c_refund_value"]
        + weights["dispute_value_risk"] * df["c_dispute_value"]
        + weights["commission_compression"] * df["c_commission_compression"]
    )

    df["w_neg_margin"] = weights["negative_margin_share"] * df["c_negative_margin"]
    df["w_subsidy"] = weights["subsidy_dependency"] * df["c_subsidy"]
    df["w_refund"] = weights["refund_value_risk"] * df["c_refund_value"]
    df["w_dispute"] = weights["dispute_value_risk"] * df["c_dispute_value"]
    df["w_commission"] = weights["commission_compression"] * df["c_commission_compression"]

    contrib = {
        "negative_margin_share": "w_neg_margin",
        "subsidy_dependency": "w_subsidy",
        "refund_value_risk": "w_refund",
        "dispute_value_risk": "w_dispute",
        "commission_compression": "w_commission",
    }

    df["margin_fragility_tier"] = _tier_from_score(df["margin_fragility_score"])
    df["main_risk_driver"] = _main_driver(df, contrib)
    df["recommended_action"] = [
        _margin_actions(tier, driver)
        for tier, driver in zip(df["margin_fragility_tier"], df["main_risk_driver"], strict=False)
    ]

    return df[
        [
            "seller_id",
            "current_period",
            "margin_fragility_score",
            "margin_fragility_tier",
            "main_risk_driver",
            "recommended_action",
        ]
    ].copy()


def _build_governance_priority_scores(
    seller: pd.DataFrame,
    seller_quality: pd.DataFrame,
    fraud: pd.DataFrame,
    margin: pd.DataFrame,
) -> pd.DataFrame:
    df = (
        seller[["seller_id", "current_period", "gmv_rank_pct", "order_rank_pct"]]
        .merge(seller_quality[["seller_id", "seller_quality_score"]], on="seller_id", how="left")
        .merge(fraud[["seller_id", "fraud_exposure_score"]], on="seller_id", how="left")
        .merge(margin[["seller_id", "margin_fragility_score"]], on="seller_id", how="left")
    )

    df["concentration_risk"] = _clip(100.0 * (0.65 * df["gmv_rank_pct"] + 0.35 * df["order_rank_pct"]))

    weights = {
        "seller_quality": 0.27,
        "fraud_exposure": 0.29,
        "margin_fragility": 0.24,
        "concentration_risk": 0.20,
    }

    df["governance_priority_score"] = _clip(
        weights["seller_quality"] * df["seller_quality_score"]
        + weights["fraud_exposure"] * df["fraud_exposure_score"]
        + weights["margin_fragility"] * df["margin_fragility_score"]
        + weights["concentration_risk"] * df["concentration_risk"]
    )

    df["w_quality"] = weights["seller_quality"] * df["seller_quality_score"]
    df["w_fraud"] = weights["fraud_exposure"] * df["fraud_exposure_score"]
    df["w_margin"] = weights["margin_fragility"] * df["margin_fragility_score"]
    df["w_concentration"] = weights["concentration_risk"] * df["concentration_risk"]

    contrib = {
        "seller_quality": "w_quality",
        "fraud_exposure": "w_fraud",
        "margin_fragility": "w_margin",
        "concentration_risk": "w_concentration",
    }

    df["governance_priority_tier"] = _tier_from_score(df["governance_priority_score"])
    df["main_risk_driver"] = _main_driver(df, contrib)
    df["recommended_action"] = [
        _priority_actions(tier, driver)
        for tier, driver in zip(df["governance_priority_tier"], df["main_risk_driver"], strict=False)
    ]

    return df[
        [
            "seller_id",
            "current_period",
            "governance_priority_score",
            "governance_priority_tier",
            "main_risk_driver",
            "recommended_action",
        ]
    ].copy()


def _sensitivity_summary(governance_base: pd.DataFrame, comp_df: pd.DataFrame) -> pd.DataFrame:
    scenarios = {
        "baseline": {"seller_quality": 0.27, "fraud_exposure": 0.29, "margin_fragility": 0.24, "concentration_risk": 0.20},
        "fraud_heavy": {"seller_quality": 0.20, "fraud_exposure": 0.42, "margin_fragility": 0.20, "concentration_risk": 0.18},
        "margin_heavy": {"seller_quality": 0.20, "fraud_exposure": 0.22, "margin_fragility": 0.40, "concentration_risk": 0.18},
        "quality_heavy": {"seller_quality": 0.42, "fraud_exposure": 0.22, "margin_fragility": 0.20, "concentration_risk": 0.16},
    }

    baseline_rank = governance_base.sort_values("governance_priority_score", ascending=False)
    baseline_top = set(baseline_rank.head(50)["seller_id"])

    rows = []
    for scenario, w in scenarios.items():
        score = (
            w["seller_quality"] * comp_df["seller_quality_score"]
            + w["fraud_exposure"] * comp_df["fraud_exposure_score"]
            + w["margin_fragility"] * comp_df["margin_fragility_score"]
            + w["concentration_risk"] * comp_df["concentration_risk"]
        ).clip(lower=0.0, upper=100.0)

        ranked = comp_df.assign(score=score).sort_values("score", ascending=False)
        top = set(ranked.head(50)["seller_id"])
        overlap = len(top & baseline_top)

        rows.append(
            {
                "scenario": scenario,
                "avg_score": float(score.mean()),
                "median_score": float(score.median()),
                "top50_overlap_vs_baseline": int(overlap),
                "top50_overlap_rate": float(overlap / 50.0),
            }
        )

    return pd.DataFrame(rows)


def build_scoring_tables(cfg: ScoringConfig) -> Dict[str, pd.DataFrame]:
    raw = _load_raw(cfg.raw_dir)
    processed = _load_processed(cfg.processed_dir)

    order_base = _build_order_base(raw)
    order_scores = _build_order_risk_scores(order_base)

    seller_base = _build_seller_level_base(
        base=order_base,
        order_scores=order_scores,
        processed=processed,
        trailing_window_days=cfg.trailing_window_days,
    )

    seller_quality = _build_seller_quality_scores(seller_base)
    fraud_exposure = _build_fraud_exposure_scores(seller_base)
    margin_fragility = _build_margin_fragility_scores(seller_base)
    governance = _build_governance_priority_scores(
        seller=seller_base,
        seller_quality=seller_quality,
        fraud=fraud_exposure,
        margin=margin_fragility,
    )

    seller_scorecard = (
        governance.merge(seller_quality[["seller_id", "seller_quality_score", "seller_quality_tier"]], on="seller_id", how="left")
        .merge(fraud_exposure[["seller_id", "fraud_exposure_score", "fraud_exposure_tier"]], on="seller_id", how="left")
        .merge(margin_fragility[["seller_id", "margin_fragility_score", "margin_fragility_tier"]], on="seller_id", how="left")
        .merge(seller_base[["seller_id", "orders", "gmv", "net_value"]], on="seller_id", how="left")
    )

    order_scorecard = order_scores.copy()

    top_high_priority_sellers = seller_scorecard.sort_values(
        ["governance_priority_score", "gmv"], ascending=[False, False]
    ).head(100)

    top_high_risk_orders = order_scorecard.sort_values(
        ["order_risk_score", "order_date"], ascending=[False, False]
    ).head(250)

    sensitivity_comp = (
        seller_quality[["seller_id", "seller_quality_score"]]
        .merge(fraud_exposure[["seller_id", "fraud_exposure_score"]], on="seller_id", how="left")
        .merge(margin_fragility[["seller_id", "margin_fragility_score"]], on="seller_id", how="left")
        .merge(seller_base[["seller_id", "gmv_rank_pct", "order_rank_pct"]], on="seller_id", how="left")
        .assign(concentration_risk=lambda d: _clip(100.0 * (0.65 * d["gmv_rank_pct"] + 0.35 * d["order_rank_pct"])))
    )

    sensitivity = _sensitivity_summary(
        governance_base=governance,
        comp_df=sensitivity_comp,
    )

    return {
        "order_risk_scores": order_scores,
        "seller_quality_scores": seller_quality,
        "fraud_exposure_scores": fraud_exposure,
        "margin_fragility_scores": margin_fragility,
        "governance_priority_scores": governance,
        "seller_scorecard": seller_scorecard,
        "order_scorecard": order_scorecard,
        "top_high_priority_sellers": top_high_priority_sellers,
        "top_high_risk_orders": top_high_risk_orders,
        "scoring_sensitivity_summary": sensitivity,
    }


def save_tables(tables: Dict[str, pd.DataFrame], processed_dir: Path) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(processed_dir / f"{name}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build scoring framework tables for marketplace risk and governance.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--trailing-window-days", type=int, default=180)
    args = parser.parse_args()

    cfg = ScoringConfig(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        trailing_window_days=args.trailing_window_days,
    )

    tables = build_scoring_tables(cfg)
    save_tables(tables, cfg.processed_dir)

    print("Scoring framework generated:")
    for name, df in tables.items():
        print(f"  - {name}: {len(df):,} rows")


if __name__ == "__main__":
    main()
