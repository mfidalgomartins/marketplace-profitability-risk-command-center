from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


@dataclass(frozen=True)
class VizConfig:
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    output_dir: Path = Path("outputs/charts")


def _set_style() -> None:
    sns.set_theme(
        style="whitegrid",
        context="talk",
        rc={
            "axes.titlesize": 17,
            "axes.labelsize": 12,
            "legend.fontsize": 10,
            "font.family": "DejaVu Sans",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        },
    )


def _load_tables(cfg: VizConfig) -> Dict[str, pd.DataFrame]:
    raw = cfg.raw_dir
    processed = cfg.processed_dir
    return {
        "opf": pd.read_csv(processed / "order_profitability_features.csv", parse_dates=["order_date"]),
        "seller_scorecard": pd.read_csv(processed / "seller_scorecard.csv"),
        "governance": pd.read_csv(processed / "governance_priority_scores.csv"),
        "seller_quality": pd.read_csv(processed / "seller_quality_scores.csv"),
        "margin_fragility": pd.read_csv(processed / "margin_fragility_scores.csv"),
        "buyer_risk": pd.read_csv(processed / "buyer_behavior_risk.csv"),
        "order_risk": pd.read_csv(processed / "order_risk_scores.csv", parse_dates=["order_date"]),
        "scenario_results": pd.read_csv(processed / "scenario_results_summary.csv"),
        "scenario_components": pd.read_csv(processed / "scenario_component_bridge.csv"),
        "orders": pd.read_csv(raw / "orders.csv", parse_dates=["order_date"]),
        "order_items": pd.read_csv(raw / "order_items.csv"),
        "refunds": pd.read_csv(raw / "refunds.csv"),
        "disputes": pd.read_csv(raw / "disputes.csv"),
        "payments": pd.read_csv(raw / "payments.csv"),
        "logistics": pd.read_csv(raw / "logistics_events.csv"),
        "products": pd.read_csv(raw / "products.csv"),
    }


def _ensure_output_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _save(fig: plt.Figure, output_dir: Path, filename: str) -> None:
    fig.tight_layout()
    fig.savefig(output_dir / filename, dpi=240, bbox_inches="tight")
    plt.close(fig)


def _pct_fmt(v: float) -> str:
    return f"{v * 100:.1f}%"


def _money_m(v: float) -> str:
    return f"${v / 1_000_000:.2f}M"


def _build_order_base(t: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    opf = t["opf"].copy()
    opf["month"] = opf["order_date"].dt.to_period("M").dt.to_timestamp()
    opf["has_refund"] = (opf["refund_amount"] > 0).astype(int)
    opf["has_dispute"] = (opf["dispute_amount"] > 0).astype(int)
    return opf


def chart_01_gmv_vs_risk_adjusted(opf: pd.DataFrame, output_dir: Path) -> None:
    monthly = opf.groupby("month", as_index=False).agg(
        gmv=("gross_value", "sum"),
        risk_adjusted_gmv=("risk_adjusted_order_value", "sum"),
    )
    monthly["gap_rate"] = 1 - monthly["risk_adjusted_gmv"] / monthly["gmv"]
    latest_gap = monthly["gap_rate"].iloc[-1]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(monthly["month"], monthly["gmv"] / 1_000_000, marker="o", lw=2.5, label="GMV")
    ax.plot(
        monthly["month"],
        monthly["risk_adjusted_gmv"] / 1_000_000,
        marker="o",
        lw=2.5,
        label="Risk-Adjusted GMV",
    )
    ax.set_title(f"Topline Growth Carries a {latest_gap*100:.1f}pp Risk Adjustment Gap in the Latest Month")
    ax.set_ylabel("Value ($M)")
    ax.set_xlabel("Month")
    ax.legend(loc="upper left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.tick_params(axis="x", rotation=45)

    ax.annotate(
        _money_m(monthly["gmv"].iloc[-1]),
        xy=(monthly["month"].iloc[-1], monthly["gmv"].iloc[-1] / 1_000_000),
        xytext=(12, 10),
        textcoords="offset points",
        fontsize=10,
    )
    _save(fig, output_dir, "01_gmv_vs_risk_adjusted_gmv_trend.png")


def chart_02_net_and_subsidy(opf: pd.DataFrame, output_dir: Path) -> None:
    monthly = opf.groupby("month", as_index=False).agg(
        net_value=("net_value", "sum"),
        subsidy=("subsidy_amount", "sum"),
        gmv=("gross_value", "sum"),
    )
    monthly["subsidy_share"] = monthly["subsidy"] / monthly["gmv"].replace(0, np.nan)
    avg_share = monthly["subsidy_share"].mean()

    fig, ax1 = plt.subplots(figsize=(14, 6))
    ax2 = ax1.twinx()

    bars = ax1.bar(monthly["month"], monthly["net_value"] / 1_000_000, alpha=0.75, label="Net Value ($M)")
    ax2.plot(monthly["month"], monthly["subsidy_share"] * 100, color="#b22222", marker="o", lw=2.2, label="Subsidy Share")

    ax1.set_title(f"Net Value Expansion Depends on an Average Subsidy Share of {avg_share*100:.1f}%")
    ax1.set_ylabel("Net Value ($M)")
    ax2.set_ylabel("Subsidy Share of GMV (%)")
    ax1.set_xlabel("Month")
    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax1.tick_params(axis="x", rotation=45)

    ax1.legend([bars], ["Net Value ($M)"], loc="upper left")
    ax2.legend(loc="upper right")
    _save(fig, output_dir, "02_net_value_and_subsidy_share_trend.png")


def chart_03_refund_rate_by_category(opf: pd.DataFrame, output_dir: Path) -> None:
    cat = opf.groupby("category", as_index=False).agg(
        orders=("order_id", "count"),
        refund_rate=("has_refund", "mean"),
    )
    cat = cat[cat["orders"] >= 500].sort_values("refund_rate", ascending=False)

    fig, ax = plt.subplots(figsize=(13, 7))
    sns.barplot(data=cat, y="category", x="refund_rate", color="#D66A6A", ax=ax)
    ax.set_title("Refund Burden Is Concentrated in Specific Categories")
    ax.set_xlabel("Refund Rate")
    ax.set_ylabel("Category")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x*100:.1f}%")

    for i, v in enumerate(cat["refund_rate"].values):
        ax.text(v + 0.0015, i, f"{v*100:.1f}%", va="center", fontsize=10)
    _save(fig, output_dir, "03_refund_rate_by_category.png")


def chart_04_dispute_rate_by_seller_cohort(opf: pd.DataFrame, output_dir: Path) -> None:
    seller_gmv = opf.groupby("seller_id", as_index=False)["gross_value"].sum()
    seller_gmv = seller_gmv.sort_values("gross_value", ascending=False).reset_index(drop=True)
    seller_gmv["rank_pct"] = (seller_gmv.index + 1) / len(seller_gmv)
    seller_gmv["seller_cohort"] = np.select(
        [seller_gmv["rank_pct"] <= 0.10, seller_gmv["rank_pct"] <= 0.50],
        ["Top 10% GMV Sellers", "Mid 40% GMV Sellers"],
        default="Long-Tail 50% Sellers",
    )

    cohort = opf.merge(seller_gmv[["seller_id", "seller_cohort"]], on="seller_id", how="left")
    cohort_summary = (
        cohort.groupby("seller_cohort", as_index=False)
        .agg(dispute_rate=("has_dispute", "mean"))
        .sort_values("dispute_rate", ascending=False)
    )

    fig, ax = plt.subplots(figsize=(11, 6))
    sns.barplot(data=cohort_summary, x="seller_cohort", y="dispute_rate", color="#DA7C30", ax=ax)
    ax.set_title("Dispute Risk Is Not Limited to the Long Tail and Persists in High-Volume Cohorts")
    ax.set_xlabel("")
    ax.set_ylabel("Dispute Rate")
    ax.yaxis.set_major_formatter(lambda x, _: f"{x*100:.1f}%")
    ax.tick_params(axis="x", rotation=10)

    for i, v in enumerate(cohort_summary["dispute_rate"].values):
        ax.text(i, v + 0.002, f"{v*100:.1f}%", ha="center", fontsize=10)
    _save(fig, output_dir, "04_dispute_rate_by_seller_cohort.png")


def chart_05_seller_quality_distribution(seller_quality: pd.DataFrame, output_dir: Path) -> None:
    median = seller_quality["seller_quality_score"].median()
    p75 = seller_quality["seller_quality_score"].quantile(0.75)

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.histplot(seller_quality["seller_quality_score"], bins=30, kde=True, color="#4C78A8", ax=ax)
    ax.axvline(median, color="#2F4F4F", linestyle="--", lw=1.8, label=f"Median: {median:.1f}")
    ax.axvline(p75, color="#B22222", linestyle="--", lw=1.8, label=f"75th pct: {p75:.1f}")
    ax.set_title("Seller Quality Risk Is Right-Skewed, Creating a Meaningful High-Risk Tail")
    ax.set_xlabel("Seller Quality Score (Higher = Riskier)")
    ax.set_ylabel("Seller Count")
    ax.legend()
    _save(fig, output_dir, "05_seller_quality_distribution.png")


def chart_06_margin_fragility_distribution(margin_fragility: pd.DataFrame, output_dir: Path) -> None:
    critical_share = (margin_fragility["margin_fragility_score"] >= 75).mean()

    fig, ax = plt.subplots(figsize=(12, 6))
    sns.histplot(margin_fragility["margin_fragility_score"], bins=30, kde=True, color="#F58518", ax=ax)
    ax.set_title(f"Margin Fragility Is Material with {critical_share*100:.1f}% of Sellers in Critical Exposure")
    ax.set_xlabel("Margin Fragility Score (Higher = More Fragile)")
    ax.set_ylabel("Seller Count")
    _save(fig, output_dir, "06_margin_fragility_distribution.png")


def chart_07_top_sellers_governance(seller_scorecard: pd.DataFrame, output_dir: Path) -> None:
    top = seller_scorecard.sort_values("governance_priority_score", ascending=False).head(20).copy()
    top = top.sort_values("governance_priority_score", ascending=True)
    palette = {"Low": "#9ecae1", "Moderate": "#6baed6", "High": "#3182bd", "Critical": "#08519c"}
    colors = top["governance_priority_tier"].map(palette)

    fig, ax = plt.subplots(figsize=(13, 9))
    ax.barh(top["seller_id"].astype(str), top["governance_priority_score"], color=colors)
    ax.set_title("A Small Group of Sellers Dominates Governance Priority Exposure")
    ax.set_xlabel("Governance Priority Score")
    ax.set_ylabel("Seller ID")

    for y, v in enumerate(top["governance_priority_score"].values):
        ax.text(v + 0.8, y, f"{v:.1f}", va="center", fontsize=9)
    _save(fig, output_dir, "07_top_sellers_by_governance_priority.png")


def chart_08_refunds_vs_delays(logistics: pd.DataFrame, refunds: pd.DataFrame, output_dir: Path) -> None:
    refund_flag = refunds[["order_id"]].drop_duplicates().assign(has_refund=1)
    x = logistics[["order_id", "delay_days"]].merge(refund_flag, on="order_id", how="left")
    x["has_refund"] = x["has_refund"].fillna(0).astype(int)
    x = x.dropna(subset=["delay_days"]).copy()
    x["delay_days_int"] = x["delay_days"].round().astype(int).clip(lower=0, upper=10)

    summary = x.groupby("delay_days_int", as_index=False).agg(
        refund_rate=("has_refund", "mean"),
        orders=("order_id", "count"),
    )
    summary = summary[summary["orders"] >= 300]

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(summary["delay_days_int"], summary["refund_rate"], marker="o", lw=2.5, color="#C44E52")
    ax.set_title("Refund Rates Rise Sharply as Delivery Delays Accumulate")
    ax.set_xlabel("Delay Days (0-10, clipped)")
    ax.set_ylabel("Refund Rate")
    ax.yaxis.set_major_formatter(lambda y, _: f"{y*100:.1f}%")

    if len(summary) >= 2:
        ax.annotate(
            f"{summary['refund_rate'].iloc[-1]*100:.1f}%",
            xy=(summary["delay_days_int"].iloc[-1], summary["refund_rate"].iloc[-1]),
            xytext=(8, 8),
            textcoords="offset points",
            fontsize=10,
        )
    _save(fig, output_dir, "08_refunds_vs_delays_relationship.png")


def chart_09_disputes_vs_chargeback_risk(
    payments: pd.DataFrame,
    disputes: pd.DataFrame,
    output_dir: Path,
) -> None:
    dispute_flag = disputes[["order_id"]].drop_duplicates().assign(has_dispute=1)
    df = payments.merge(dispute_flag, on="order_id", how="left")
    df["has_dispute"] = df["has_dispute"].fillna(0).astype(int)

    summary = df.groupby("payment_risk_signal", as_index=False).agg(
        dispute_rate=("has_dispute", "mean"),
        chargeback_rate=("chargeback_flag", "mean"),
        orders=("order_id", "count"),
    )

    fig, ax = plt.subplots(figsize=(11, 7))
    size = 100 + 0.02 * summary["orders"]
    scatter = ax.scatter(
        summary["chargeback_rate"],
        summary["dispute_rate"],
        s=size,
        c=summary["orders"],
        cmap="YlOrRd",
        alpha=0.85,
        edgecolor="black",
        linewidth=0.6,
    )

    for _, row in summary.iterrows():
        ax.annotate(
            row["payment_risk_signal"],
            (row["chargeback_rate"], row["dispute_rate"]),
            textcoords="offset points",
            xytext=(5, 6),
            fontsize=10,
        )

    ax.set_title("Higher Payment Risk Signals Align with Both Dispute and Chargeback Pressure")
    ax.set_xlabel("Chargeback Rate")
    ax.set_ylabel("Dispute Rate")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x*100:.1f}%")
    ax.yaxis.set_major_formatter(lambda y, _: f"{y*100:.1f}%")
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Order Count")
    _save(fig, output_dir, "09_disputes_vs_chargeback_risk_relationship.png")


def chart_10_promo_dependency_by_category(opf: pd.DataFrame, output_dir: Path) -> None:
    promo = opf.groupby("category", as_index=False).agg(
        subsidy=("subsidy_amount", "sum"),
        gmv=("gross_value", "sum"),
    )
    promo["promo_dependency"] = promo["subsidy"] / promo["gmv"].replace(0, np.nan)
    promo = promo.sort_values("promo_dependency", ascending=False)

    fig, ax = plt.subplots(figsize=(13, 7))
    sns.barplot(data=promo, y="category", x="promo_dependency", color="#4C9F70", ax=ax)
    ax.set_title("Promo Dependency Is Uneven Across Categories and Drives Margin Volatility")
    ax.set_xlabel("Subsidy Share of GMV")
    ax.set_ylabel("Category")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x*100:.1f}%")
    _save(fig, output_dir, "10_promo_dependency_by_category.png")


def chart_11_seller_concentration(opf: pd.DataFrame, output_dir: Path) -> None:
    seller_gmv = opf.groupby("seller_id", as_index=False)["gross_value"].sum().sort_values("gross_value", ascending=False)
    seller_gmv["cum_gmv_share"] = seller_gmv["gross_value"].cumsum() / seller_gmv["gross_value"].sum()
    seller_gmv["seller_share"] = (np.arange(1, len(seller_gmv) + 1)) / len(seller_gmv)

    top10_share = seller_gmv["gross_value"].head(10).sum() / seller_gmv["gross_value"].sum()

    fig, ax = plt.subplots(figsize=(12, 7))
    ax.plot(seller_gmv["seller_share"], seller_gmv["cum_gmv_share"], lw=2.5, color="#1f77b4", label="Observed")
    ax.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfect Equality")
    ax.set_title(f"Seller Concentration Is Material: Top 10 Sellers Capture {top10_share*100:.1f}% of GMV")
    ax.set_xlabel("Share of Sellers")
    ax.set_ylabel("Cumulative GMV Share")
    ax.xaxis.set_major_formatter(lambda x, _: f"{x*100:.0f}%")
    ax.yaxis.set_major_formatter(lambda y, _: f"{y*100:.0f}%")
    ax.legend(loc="lower right")
    _save(fig, output_dir, "11_seller_concentration_chart.png")


def chart_12_category_profitability_heatmap(opf: pd.DataFrame, output_dir: Path) -> None:
    x = opf.copy()
    x["month"] = x["order_date"].dt.to_period("M").astype(str)
    summary = x.groupby(["month", "category"], as_index=False).agg(
        margin=("estimated_margin_after_risk", "sum"),
        net=("net_value", "sum"),
    )
    summary["margin_rate"] = summary["margin"] / summary["net"].replace(0, np.nan)

    latest_months = sorted(summary["month"].unique())[-12:]
    summary = summary[summary["month"].isin(latest_months)]
    pivot = summary.pivot(index="category", columns="month", values="margin_rate")

    fig, ax = plt.subplots(figsize=(14, 8))
    sns.heatmap(
        pivot,
        cmap="RdYlGn",
        center=0.0,
        linewidths=0.4,
        cbar_kws={"label": "Margin Rate"},
        ax=ax,
    )
    ax.set_title("Category Expected Margin (After Risk) Reveals Persistent Pressure Pockets")
    ax.set_xlabel("Month")
    ax.set_ylabel("Category")
    _save(fig, output_dir, "12_category_profitability_heatmap.png")


def chart_13_buyer_risk_distribution(buyer_risk: pd.DataFrame, output_dir: Path) -> None:
    bins = [0, 30, 55, 75, 100]
    labels = ["Low", "Moderate", "High", "Critical"]
    tier = pd.cut(buyer_risk["order_risk_proxy"], bins=bins, labels=labels, include_lowest=True, right=False)
    dist = tier.value_counts().reindex(labels).fillna(0)
    critical_share = (tier == "Critical").mean()

    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(x=dist.index, y=dist.values, color="#5C88C3", ax=ax)
    ax.set_title(f"Buyer Risk Is Skewed with {critical_share*100:.1f}% in Critical-Risk Behavior Bands")
    ax.set_xlabel("Buyer Risk Tier")
    ax.set_ylabel("Buyer Count")
    for i, v in enumerate(dist.values):
        ax.text(i, v + dist.max() * 0.01, f"{int(v):,}", ha="center", fontsize=10)
    _save(fig, output_dir, "13_buyer_risk_distribution.png")


def chart_14_scenario_comparison(scenario_results: pd.DataFrame, output_dir: Path) -> None:
    x = scenario_results.copy()
    x["cm_change_m"] = x["contribution_margin_change_vs_baseline"] / 1_000_000
    x["size"] = 200 + x["top_risk_seller_downside_exposure"] / 5000

    fig, ax = plt.subplots(figsize=(12, 7))
    scatter = ax.scatter(
        x["gmv_change_vs_baseline_pct"],
        x["quality_ratio_change_pp_vs_baseline"],
        s=x["size"],
        c=x["cm_change_m"],
        cmap="RdYlGn",
        alpha=0.9,
        edgecolor="black",
        linewidth=0.7,
    )
    for _, row in x.iterrows():
        ax.annotate(row["scenario"], (row["gmv_change_vs_baseline_pct"], row["quality_ratio_change_pp_vs_baseline"]), xytext=(5, 6), textcoords="offset points", fontsize=9)

    ax.axhline(0, color="gray", linestyle="--", lw=1)
    ax.axvline(0, color="gray", linestyle="--", lw=1)
    ax.set_title("Fraud and Quality Interventions Improve Economics Despite Modest GMV Trade-offs")
    ax.set_xlabel("GMV Change vs Baseline (%)")
    ax.set_ylabel("Quality Ratio Change vs Baseline (pp)")
    cbar = fig.colorbar(scatter, ax=ax)
    cbar.set_label("Contribution Margin Change vs Baseline ($M)")
    _save(fig, output_dir, "14_scenario_comparison_chart.png")


def chart_15_seller_portfolio_matrix(
    seller_scorecard: pd.DataFrame,
    output_dir: Path,
) -> None:
    x = seller_scorecard.copy()
    x["gmv_m"] = x["gmv"] / 1_000_000
    x["size"] = 20 + x["governance_priority_score"] * 2.2
    tier_order = ["Low", "Moderate", "High", "Critical"]
    palette = {"Low": "#9ecae1", "Moderate": "#6baed6", "High": "#3182bd", "Critical": "#08519c"}

    fig, ax = plt.subplots(figsize=(12, 8))
    for tier in tier_order:
        d = x[x["governance_priority_tier"] == tier]
        ax.scatter(
            d["gmv_m"],
            d["seller_quality_score"],
            s=d["size"],
            alpha=0.55,
            color=palette[tier],
            label=tier,
            edgecolor="white",
            linewidth=0.4,
        )

    ax.set_xscale("log")
    ax.set_title("High-Volume Sellers with Weak Quality Scores Form the Highest Governance-Risk Quadrant")
    ax.set_xlabel("Seller GMV ($M, log scale)")
    ax.set_ylabel("Seller Quality Score (Higher = Riskier)")
    ax.axhline(55, color="gray", linestyle="--", lw=1)
    ax.legend(title="Governance Tier")
    _save(fig, output_dir, "15_seller_portfolio_matrix_volume_vs_quality.png")


def chart_16_risk_leakage_waterfall(scenario_components: pd.DataFrame, output_dir: Path) -> None:
    baseline = scenario_components[scenario_components["scenario"] == "baseline"].iloc[0]
    values = [
        baseline["commission_revenue"],
        -baseline["subsidy"],
        -baseline["refunds"],
        -baseline["disputes"],
        -baseline["chargeback_loss"],
    ]
    labels = ["Commission", "Subsidy", "Refunds", "Disputes", "Chargebacks"]
    cumulative = np.cumsum([0.0] + values)

    fig, ax = plt.subplots(figsize=(12, 7))
    colors = ["#2ca02c", "#d62728", "#d62728", "#d62728", "#d62728"]
    for i, (label, val, color) in enumerate(zip(labels, values, colors)):
        start = cumulative[i]
        ax.bar(i, val / 1_000_000, bottom=start / 1_000_000, color=color, width=0.65)
        ax.text(
            i,
            (start + val) / 1_000_000 + (0.02 if val >= 0 else -0.05),
            f"{val/1_000_000:.2f}M",
            ha="center",
            va="bottom" if val >= 0 else "top",
            fontsize=9,
        )

    final_cm = baseline["contribution_margin_proxy"]
    ax.bar(len(labels), final_cm / 1_000_000, color="#1f77b4", width=0.65)
    ax.text(
        len(labels),
        final_cm / 1_000_000 + (0.03 if final_cm >= 0 else -0.06),
        f"{final_cm/1_000_000:.2f}M",
        ha="center",
        va="bottom" if final_cm >= 0 else "top",
        fontsize=10,
        fontweight="bold",
    )

    ax.set_xticks(range(len(labels) + 1))
    ax.set_xticklabels(labels + ["Contribution Margin"])
    ax.set_title("Leakage Components Overwhelm Commission Revenue and Drive Negative Contribution Margin")
    ax.set_ylabel("Value ($M)")
    _save(fig, output_dir, "16_risk_leakage_waterfall.png")


def build_visualization_layer(cfg: VizConfig) -> None:
    _set_style()
    _ensure_output_dir(cfg.output_dir)
    t = _load_tables(cfg)
    opf = _build_order_base(t)

    chart_01_gmv_vs_risk_adjusted(opf, cfg.output_dir)
    chart_02_net_and_subsidy(opf, cfg.output_dir)
    chart_03_refund_rate_by_category(opf, cfg.output_dir)
    chart_04_dispute_rate_by_seller_cohort(opf, cfg.output_dir)
    chart_05_seller_quality_distribution(t["seller_quality"], cfg.output_dir)
    chart_06_margin_fragility_distribution(t["margin_fragility"], cfg.output_dir)
    chart_07_top_sellers_governance(t["seller_scorecard"], cfg.output_dir)
    chart_08_refunds_vs_delays(t["logistics"], t["refunds"], cfg.output_dir)
    chart_09_disputes_vs_chargeback_risk(t["payments"], t["disputes"], cfg.output_dir)
    chart_10_promo_dependency_by_category(opf, cfg.output_dir)
    chart_11_seller_concentration(opf, cfg.output_dir)
    chart_12_category_profitability_heatmap(opf, cfg.output_dir)
    chart_13_buyer_risk_distribution(t["buyer_risk"], cfg.output_dir)
    chart_14_scenario_comparison(t["scenario_results"], cfg.output_dir)
    chart_15_seller_portfolio_matrix(t["seller_scorecard"], cfg.output_dir)
    chart_16_risk_leakage_waterfall(t["scenario_components"], cfg.output_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build executive visualization layer for marketplace analytics.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/charts"))
    args = parser.parse_args()

    cfg = VizConfig(raw_dir=args.raw_dir, processed_dir=args.processed_dir, output_dir=args.output_dir)
    build_visualization_layer(cfg)

    print("Marketplace visualization layer generated:")
    for p in sorted(cfg.output_dir.glob("*.png")):
        print(f"  - {p.name}")


if __name__ == "__main__":
    main()
