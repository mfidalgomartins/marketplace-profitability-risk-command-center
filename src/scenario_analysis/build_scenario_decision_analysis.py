from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ScenarioConfig:
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    baseline_months: int = 6
    horizon_months: int = 6


def _load_raw(raw_dir: Path) -> Dict[str, pd.DataFrame]:
    return {
        "orders": pd.read_csv(raw_dir / "orders.csv", parse_dates=["order_date"]),
        "order_items": pd.read_csv(raw_dir / "order_items.csv"),
        "payments": pd.read_csv(raw_dir / "payments.csv"),
        "refunds": pd.read_csv(raw_dir / "refunds.csv"),
        "disputes": pd.read_csv(raw_dir / "disputes.csv"),
        "products": pd.read_csv(raw_dir / "products.csv"),
    }


def _load_processed(processed_dir: Path) -> Dict[str, pd.DataFrame]:
    return {
        "opf": pd.read_csv(processed_dir / "order_profitability_features.csv", parse_dates=["order_date"]),
        "governance": pd.read_csv(processed_dir / "governance_priority_scores.csv"),
        "seller_scorecard": pd.read_csv(processed_dir / "seller_scorecard.csv"),
    }


def _build_order_analytical_base(raw: Dict[str, pd.DataFrame], processed: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    orders = raw["orders"]
    items = raw["order_items"]
    payments = raw["payments"]
    refunds = raw["refunds"]
    disputes = raw["disputes"]
    products = raw["products"]
    opf = processed["opf"]

    item_agg = items.groupby("order_id", as_index=False).agg(
        seller_id=("seller_id", "first"),
        commission_fee=("commission_fee", "sum"),
        gross_value_items=("gross_item_value", "sum"),
    )

    primary_cat = (
        items[["order_id", "product_id", "gross_item_value"]]
        .merge(products[["product_id", "category"]], on="product_id", how="left")
        .sort_values(["order_id", "gross_item_value", "product_id"], ascending=[True, False, True])
        .drop_duplicates("order_id")[["order_id", "category"]]
    )

    refund_agg = refunds.groupby("order_id", as_index=False)["refund_amount"].sum()
    dispute_agg = disputes.groupby("order_id", as_index=False)["dispute_amount"].sum()

    opf_cols = ["order_id", "risk_adjusted_order_value", "estimated_margin_after_risk"]
    if "realized_contribution_margin_proxy" in opf.columns:
        opf_cols.append("realized_contribution_margin_proxy")
    if "chargeback_loss_proxy" in opf.columns:
        opf_cols.append("chargeback_loss_proxy")

    base = (
        orders[
            [
                "order_id",
                "order_date",
                "gross_order_value",
                "net_paid_amount",
                "subsidy_amount",
                "order_channel",
                "payment_method",
            ]
        ]
        .merge(item_agg, on="order_id", how="left")
        .merge(primary_cat, on="order_id", how="left")
        .merge(payments[["order_id", "chargeback_flag"]], on="order_id", how="left")
        .merge(refund_agg, on="order_id", how="left")
        .merge(dispute_agg, on="order_id", how="left")
        .merge(opf[opf_cols], on="order_id", how="left")
    )

    base["category"] = base["category"].fillna("Unknown")
    base["refund_amount"] = base["refund_amount"].fillna(0.0)
    base["dispute_amount"] = base["dispute_amount"].fillna(0.0)
    base["chargeback_flag"] = base["chargeback_flag"].fillna(0).astype(int)

    base["chargeback_loss"] = base["chargeback_flag"] * base["net_paid_amount"]
    if "chargeback_loss_proxy" in base.columns:
        base["chargeback_loss"] = base["chargeback_loss_proxy"].fillna(base["chargeback_loss"])

    if "realized_contribution_margin_proxy" not in base.columns:
        base["realized_contribution_margin_proxy"] = (
            base["commission_fee"]
            - base["subsidy_amount"]
            - base["refund_amount"]
            - base["dispute_amount"]
            - base["chargeback_loss"]
        )

    base["total_leakage"] = (
        base["subsidy_amount"] + base["refund_amount"] + base["dispute_amount"] + base["chargeback_loss"]
    )

    base["month"] = base["order_date"].dt.to_period("M").astype(str)
    return base


def _get_baseline_window(base: pd.DataFrame, baseline_months: int) -> pd.DataFrame:
    latest_ts = base["order_date"].max().normalize()
    start = latest_ts - pd.DateOffset(months=baseline_months) + pd.Timedelta(days=1)
    return base[(base["order_date"] >= start) & (base["order_date"] <= latest_ts)].copy()


def _baseline_metrics(window: pd.DataFrame) -> Dict[str, float]:
    gmv = float(window["gross_order_value"].sum())
    net = float(window["net_paid_amount"].sum())
    commission = float(window["commission_fee"].sum())
    subsidy = float(window["subsidy_amount"].sum())
    refunds = float(window["refund_amount"].sum())
    disputes = float(window["dispute_amount"].sum())
    chargeback = float(window["chargeback_loss"].sum())
    risk_adjusted = float(window["risk_adjusted_order_value"].sum())
    contribution_margin = float(window["realized_contribution_margin_proxy"].sum())

    return {
        "gmv": gmv,
        "net_value": net,
        "commission": commission,
        "subsidy": subsidy,
        "refunds": refunds,
        "disputes": disputes,
        "chargeback_loss": chargeback,
        "risk_adjusted_gmv": risk_adjusted,
        "contribution_margin_proxy": contribution_margin,
        "net_to_gmv": net / gmv if gmv else 0.0,
        "commission_rate": commission / gmv if gmv else 0.0,
        "subsidy_rate": subsidy / gmv if gmv else 0.0,
        "refund_rate": refunds / net if net else 0.0,
        "dispute_rate": disputes / net if net else 0.0,
        "chargeback_rate": chargeback / net if net else 0.0,
        "risk_gap_rate": (net - risk_adjusted) / net if net else 0.0,
        "leakage_rate": (subsidy + refunds + disputes + chargeback) / net if net else 0.0,
        "cm_rate": contribution_margin / net if net else 0.0,
    }


def _seller_exposure_metrics(
    window: pd.DataFrame,
    governance: pd.DataFrame,
    seller_scorecard: pd.DataFrame,
) -> Dict[str, float]:
    merged = window.merge(
        governance[["seller_id", "governance_priority_tier", "governance_priority_score"]],
        on="seller_id",
        how="left",
    )

    top_risk = merged[merged["governance_priority_tier"].isin(["High", "Critical"])]
    top_risk_net_share = float(top_risk["net_paid_amount"].sum() / merged["net_paid_amount"].sum())
    top_risk_leak_rate = float(top_risk["total_leakage"].sum() / top_risk["net_paid_amount"].sum()) if top_risk["net_paid_amount"].sum() else 0.0

    # Bad actors: top 5% by governance score, constrained to critical tier.
    threshold = seller_scorecard["governance_priority_score"].quantile(0.95)
    bad_actor_ids = seller_scorecard[
        (seller_scorecard["governance_priority_tier"] == "Critical")
        & (seller_scorecard["governance_priority_score"] >= threshold)
    ]["seller_id"].unique()
    if len(bad_actor_ids) == 0:
        # Fallback ensures downside exposure modeling remains populated even when no seller hits Critical tier.
        fallback_n = max(1, int(np.ceil(len(seller_scorecard) * 0.01)))
        bad_actor_ids = (
            seller_scorecard.sort_values("governance_priority_score", ascending=False)
            .head(fallback_n)["seller_id"]
            .unique()
        )

    bad = merged[merged["seller_id"].isin(bad_actor_ids)]

    bad_actor_gmv_share = float(bad["gross_order_value"].sum() / merged["gross_order_value"].sum()) if merged["gross_order_value"].sum() else 0.0
    bad_actor_net_share = float(bad["net_paid_amount"].sum() / merged["net_paid_amount"].sum()) if merged["net_paid_amount"].sum() else 0.0
    bad_actor_leak_rate = float(bad["total_leakage"].sum() / bad["net_paid_amount"].sum()) if bad["net_paid_amount"].sum() else 0.0

    return {
        "top_risk_net_share": top_risk_net_share,
        "top_risk_leak_rate": top_risk_leak_rate,
        "bad_actor_gmv_share": bad_actor_gmv_share,
        "bad_actor_net_share": bad_actor_net_share,
        "bad_actor_leak_rate": bad_actor_leak_rate,
        "bad_actor_seller_count": int(len(bad_actor_ids)),
    }


def _scenario_definitions() -> pd.DataFrame:
    rows = [
        {
            "scenario": "baseline",
            "scenario_type": "reference",
            "gmv_factor": 1.00,
            "net_to_gmv_factor": 1.00,
            "subsidy_rate_factor": 1.00,
            "refund_rate_factor": 1.00,
            "dispute_rate_factor": 1.00,
            "chargeback_rate_factor": 1.00,
            "risk_gap_factor": 1.00,
            "top_risk_exposure_factor": 1.00,
            "remove_bad_actor_intensity": 0.00,
            "correct_bad_actor_effectiveness": 0.00,
            "assumption_summary": "Status-quo run-rate continuation.",
        },
        {
            "scenario": "seller_quality_improvement",
            "scenario_type": "quality_upside",
            "gmv_factor": 0.985,
            "net_to_gmv_factor": 1.003,
            "subsidy_rate_factor": 0.96,
            "refund_rate_factor": 0.82,
            "dispute_rate_factor": 0.85,
            "chargeback_rate_factor": 0.90,
            "risk_gap_factor": 0.86,
            "top_risk_exposure_factor": 0.78,
            "remove_bad_actor_intensity": 0.02,
            "correct_bad_actor_effectiveness": 0.40,
            "assumption_summary": "SLA enforcement + seller coaching reduce post-order leakage with small near-term GMV drag.",
        },
        {
            "scenario": "subsidy_tightening",
            "scenario_type": "policy_upside",
            "gmv_factor": 0.955,
            "net_to_gmv_factor": 1.012,
            "subsidy_rate_factor": 0.72,
            "refund_rate_factor": 0.93,
            "dispute_rate_factor": 0.96,
            "chargeback_rate_factor": 0.98,
            "risk_gap_factor": 0.95,
            "top_risk_exposure_factor": 0.92,
            "remove_bad_actor_intensity": 0.01,
            "correct_bad_actor_effectiveness": 0.25,
            "assumption_summary": "Promo eligibility tightening lowers subsidy burn but reduces short-term GMV.",
        },
        {
            "scenario": "fraud_control_improvement",
            "scenario_type": "risk_upside",
            "gmv_factor": 0.990,
            "net_to_gmv_factor": 0.997,
            "subsidy_rate_factor": 1.00,
            "refund_rate_factor": 0.90,
            "dispute_rate_factor": 0.74,
            "chargeback_rate_factor": 0.60,
            "risk_gap_factor": 0.72,
            "top_risk_exposure_factor": 0.65,
            "remove_bad_actor_intensity": 0.03,
            "correct_bad_actor_effectiveness": 0.35,
            "assumption_summary": "Stricter fraud controls and review friction suppress disputes/chargebacks with modest conversion drag.",
        },
        {
            "scenario": "downside_high_risk_deterioration",
            "scenario_type": "downside",
            "gmv_factor": 1.035,
            "net_to_gmv_factor": 0.992,
            "subsidy_rate_factor": 1.08,
            "refund_rate_factor": 1.22,
            "dispute_rate_factor": 1.30,
            "chargeback_rate_factor": 1.28,
            "risk_gap_factor": 1.35,
            "top_risk_exposure_factor": 1.40,
            "remove_bad_actor_intensity": 0.00,
            "correct_bad_actor_effectiveness": 0.00,
            "assumption_summary": "Risky cohorts expand faster; refunds/disputes/chargebacks worsen despite topline growth.",
        },
    ]
    return pd.DataFrame(rows)


def _evaluate_scenarios(
    baseline: Dict[str, float],
    exposure: Dict[str, float],
    assumptions: pd.DataFrame,
) -> pd.DataFrame:
    rows = []

    baseline_row = assumptions[assumptions["scenario"] == "baseline"].iloc[0]

    for r in assumptions.itertuples(index=False):
        gmv = baseline["gmv"] * r.gmv_factor
        net = gmv * baseline["net_to_gmv"] * r.net_to_gmv_factor
        commission = gmv * baseline["commission_rate"]

        subsidy = gmv * baseline["subsidy_rate"] * r.subsidy_rate_factor
        refunds = net * baseline["refund_rate"] * r.refund_rate_factor
        disputes = net * baseline["dispute_rate"] * r.dispute_rate_factor
        chargeback = net * baseline["chargeback_rate"] * r.chargeback_rate_factor

        leakage_total = subsidy + refunds + disputes + chargeback
        contribution_margin = commission - leakage_total

        risk_adjusted = net * (1.0 - baseline["risk_gap_rate"] * r.risk_gap_factor)

        top_risk_downside_exposure = (
            net
            * exposure["top_risk_net_share"]
            * exposure["top_risk_leak_rate"]
            * r.top_risk_exposure_factor
        )

        remove_bad_actor_gmv_loss = gmv * exposure["bad_actor_gmv_share"] * r.remove_bad_actor_intensity
        remove_bad_actor_leakage_avoided = (
            net
            * exposure["bad_actor_net_share"]
            * exposure["bad_actor_leak_rate"]
            * r.remove_bad_actor_intensity
        )
        correct_bad_actor_leakage_avoided = (
            net
            * exposure["bad_actor_net_share"]
            * exposure["bad_actor_leak_rate"]
            * r.correct_bad_actor_effectiveness
        )

        rows.append(
            {
                "scenario": r.scenario,
                "scenario_type": r.scenario_type,
                "gmv": gmv,
                "net_value": net,
                "risk_adjusted_gmv": risk_adjusted,
                "contribution_margin_proxy": contribution_margin,
                "commission_revenue": commission,
                "subsidy": subsidy,
                "refunds": refunds,
                "disputes": disputes,
                "chargeback_loss": chargeback,
                "total_leakage": leakage_total,
                "leakage_rate": leakage_total / net if net else 0.0,
                "cm_rate": contribution_margin / net if net else 0.0,
                "top_risk_seller_downside_exposure": top_risk_downside_exposure,
                "remove_bad_actor_gmv_loss": remove_bad_actor_gmv_loss,
                "remove_bad_actor_leakage_avoided": remove_bad_actor_leakage_avoided,
                "correct_bad_actor_leakage_avoided": correct_bad_actor_leakage_avoided,
                "total_bad_actor_intervention_leakage_avoided": remove_bad_actor_leakage_avoided
                + correct_bad_actor_leakage_avoided,
                "assumption_summary": r.assumption_summary,
            }
        )

    out = pd.DataFrame(rows)
    baseline_metrics = out[out["scenario"] == "baseline"].iloc[0]

    out["gmv_change_vs_baseline_pct"] = (out["gmv"] / baseline_metrics["gmv"] - 1.0) * 100.0
    out["risk_adjusted_change_vs_baseline_pct"] = (
        out["risk_adjusted_gmv"] / baseline_metrics["risk_adjusted_gmv"] - 1.0
    ) * 100.0
    out["contribution_margin_change_vs_baseline"] = (
        out["contribution_margin_proxy"] - baseline_metrics["contribution_margin_proxy"]
    )
    out["leakage_avoided_vs_baseline"] = baseline_metrics["total_leakage"] - out["total_leakage"]

    baseline_quality_ratio = baseline_metrics["risk_adjusted_gmv"] / baseline_metrics["net_value"]
    out["quality_ratio"] = out["risk_adjusted_gmv"] / out["net_value"].replace(0, np.nan)
    out["quality_ratio_change_pp_vs_baseline"] = (out["quality_ratio"] - baseline_quality_ratio) * 100.0

    out["tradeoff_index"] = out["gmv_change_vs_baseline_pct"] + 0.7 * out["quality_ratio_change_pp_vs_baseline"]

    def _tradeoff_label(row: pd.Series) -> str:
        if row["gmv_change_vs_baseline_pct"] > 0 and row["quality_ratio_change_pp_vs_baseline"] > 0:
            return "healthy_growth_tradeoff"
        if row["gmv_change_vs_baseline_pct"] > 0 and row["quality_ratio_change_pp_vs_baseline"] < 0:
            return "growth_at_risk"
        if row["gmv_change_vs_baseline_pct"] < 0 and row["quality_ratio_change_pp_vs_baseline"] > 0:
            return "discipline_over_growth"
        return "double_deterioration"

    out["growth_quality_tradeoff"] = out.apply(_tradeoff_label, axis=1)

    # decision ranking: prioritize higher CM improvement + leakage avoided + risk-adjusted value.
    baseline_cm_abs = max(abs(float(baseline_metrics["contribution_margin_proxy"])), 1.0)
    baseline_leak_abs = max(abs(float(baseline_metrics["total_leakage"])), 1.0)
    out["decision_priority_score"] = (
        0.45 * (out["contribution_margin_change_vs_baseline"] / baseline_cm_abs)
        + 0.35 * (out["leakage_avoided_vs_baseline"] / baseline_leak_abs)
        + 0.20 * (out["risk_adjusted_change_vs_baseline_pct"] / 100.0)
    ) * 100.0

    return out.sort_values("decision_priority_score", ascending=False)


def _decision_matrix(results: pd.DataFrame) -> pd.DataFrame:
    df = results.copy()

    def _recommend(row: pd.Series) -> str:
        scenario = row["scenario"]
        if scenario == "seller_quality_improvement":
            return "prioritize seller coaching and SLA enforcement in high-risk tiers"
        if scenario == "fraud_control_improvement":
            return "tighten fraud controls and expand manual review for critical orders"
        if scenario == "subsidy_tightening":
            return "tighten promo eligibility with staged rollout by category"
        if scenario == "downside_high_risk_deterioration":
            return "pre-emptively cap high-risk cohort growth and hold payouts for critical sellers"
        return "maintain baseline monitoring"

    df["recommended_decision"] = df.apply(_recommend, axis=1)

    return df[
        [
            "scenario",
            "scenario_type",
            "decision_priority_score",
            "gmv_change_vs_baseline_pct",
            "quality_ratio_change_pp_vs_baseline",
            "contribution_margin_change_vs_baseline",
            "leakage_avoided_vs_baseline",
            "growth_quality_tradeoff",
            "recommended_decision",
        ]
    ].sort_values("decision_priority_score", ascending=False)


def build_scenarios(cfg: ScenarioConfig) -> Dict[str, pd.DataFrame]:
    raw = _load_raw(cfg.raw_dir)
    processed = _load_processed(cfg.processed_dir)

    order_base = _build_order_analytical_base(raw, processed)
    baseline_window = _get_baseline_window(order_base, baseline_months=cfg.baseline_months)

    baseline = _baseline_metrics(baseline_window)
    exposure = _seller_exposure_metrics(
        baseline_window,
        governance=processed["governance"],
        seller_scorecard=processed["seller_scorecard"],
    )

    # Scale baseline period metrics to forward horizon.
    horizon_scale = cfg.horizon_months / cfg.baseline_months
    baseline_scaled = baseline.copy()
    for metric in [
        "gmv",
        "net_value",
        "commission",
        "subsidy",
        "refunds",
        "disputes",
        "chargeback_loss",
        "risk_adjusted_gmv",
        "contribution_margin_proxy",
    ]:
        baseline_scaled[metric] = baseline_scaled[metric] * horizon_scale

    assumptions = _scenario_definitions()
    results = _evaluate_scenarios(baseline_scaled, exposure, assumptions)

    decision = _decision_matrix(results)

    exposure_table = pd.DataFrame(
        [
            {
                "horizon_months": cfg.horizon_months,
                "baseline_months_used": cfg.baseline_months,
                "top_risk_net_share": exposure["top_risk_net_share"],
                "top_risk_leak_rate": exposure["top_risk_leak_rate"],
                "bad_actor_seller_count": exposure["bad_actor_seller_count"],
                "bad_actor_gmv_share": exposure["bad_actor_gmv_share"],
                "bad_actor_net_share": exposure["bad_actor_net_share"],
                "bad_actor_leak_rate": exposure["bad_actor_leak_rate"],
            }
        ]
    )

    component = results[
        [
            "scenario",
            "commission_revenue",
            "subsidy",
            "refunds",
            "disputes",
            "chargeback_loss",
            "total_leakage",
            "contribution_margin_proxy",
            "leakage_avoided_vs_baseline",
            "contribution_margin_change_vs_baseline",
        ]
    ].copy()

    return {
        "scenario_assumptions": assumptions,
        "scenario_results_summary": results,
        "scenario_component_bridge": component,
        "scenario_top_risk_exposure": exposure_table,
        "scenario_decision_matrix": decision,
    }


def save_tables(tables: Dict[str, pd.DataFrame], processed_dir: Path) -> None:
    processed_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(processed_dir / f"{name}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build marketplace scenario and decision analysis tables.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--baseline-months", type=int, default=6)
    parser.add_argument("--horizon-months", type=int, default=6)
    args = parser.parse_args()

    cfg = ScenarioConfig(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        baseline_months=args.baseline_months,
        horizon_months=args.horizon_months,
    )

    tables = build_scenarios(cfg)
    save_tables(tables, cfg.processed_dir)

    print("Scenario and decision analysis generated:")
    for name, df in tables.items():
        print(f"  - {name}: {len(df):,} rows")


if __name__ == "__main__":
    main()
