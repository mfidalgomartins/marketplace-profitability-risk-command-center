"""Generate the publication chart pack from processed marketplace data."""

from __future__ import annotations

import os
from pathlib import Path

_matplotlib_cache = Path(".tmp/matplotlib").resolve()
_matplotlib_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_matplotlib_cache))
os.environ.setdefault("MPLBACKEND", "Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data" / "processed"
RAW = ROOT / "data" / "raw"
OUT = ROOT / "outputs" / "graphs"

# Brand palette — kept identical to the executive dashboard's light-mode CSS
# tokens (src/dashboard/build_executive_dashboard.py) and the PDF report's
# palette (src/visualization/build_report_pdf.py) so the dashboard, chart
# pack, and PDF read as one cohesive product rather than three near-matches.
INK = "#0A1628"
MUTE = "#5C6B80"
FAINT = "#D4DAE3"
GRID = "#EEF1F5"
PANEL = "#F3F5F8"
ACCENT = "#5B54E0"
LOSS = "#C5453B"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "text.color": INK,
        "axes.edgecolor": "#D4DAE3",
        "axes.labelcolor": MUTE,
        "axes.linewidth": 0.8,
        "axes.titlesize": 13,
        "xtick.color": MUTE,
        "ytick.color": MUTE,
        "figure.dpi": 180,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
    }
)


def style(ax, grid="y"):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis=grid, color=GRID, lw=0.8)
    ax.set_axisbelow(True)


def title(ax, headline, subtitle):
    ax.set_title(subtitle, loc="left", fontsize=9, color=MUTE, pad=7)
    ax.annotate(
        headline,
        (0, 1),
        xycoords="axes fraction",
        xytext=(0, 25),
        textcoords="offset points",
        ha="left",
        va="bottom",
        fontsize=13,
        fontweight="bold",
        color=INK,
    )


def save(fig, name):
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / name, facecolor="white")
    plt.close(fig)
    print("wrote", name)


def pct(v, _=None):
    return f"{v:.0f}%"


def money_m(v, _=None):
    return f"${v:.1f}M"


def horizontal_bars(df, value, label, headline, subtitle, filename, fmt="{:.1f}%", accent_rows=2):
    g = df.sort_values(value)
    fig, ax = plt.subplots(figsize=(8.4, 4.7))
    style(ax, "x")
    ax.grid(axis="y", visible=False)
    colors = [FAINT] * len(g)
    for i in range(max(0, len(g) - accent_rows), len(g)):
        colors[i] = ACCENT
    bars = ax.barh(g[label], g[value], color=colors, height=0.64)
    for b, v in zip(bars, g[value], strict=True):
        ax.annotate(
            fmt.format(v),
            (v, b.get_y() + b.get_height() / 2),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=MUTE,
        )
    ax.set_xlim(0, g[value].max() * 1.2)
    # Data is already on a 0-100 percentage scale and the per-bar labels show
    # "%" (fmt); label the shared x-axis the same way so the two don't disagree.
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0f}%"))
    title(ax, headline, subtitle)
    save(fig, filename)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.png"):
        old.unlink()

    opf = pd.read_csv(PROC / "order_profitability_features.csv", parse_dates=["order_date"])
    risk = pd.read_csv(PROC / "order_risk_scores.csv", parse_dates=["order_date"])
    score = pd.read_csv(PROC / "seller_scorecard.csv")
    buyers = pd.read_csv(PROC / "buyer_behavior_risk.csv")
    cat_month = pd.read_csv(PROC / "category_risk_summary.csv")
    curve = pd.read_csv(PROC / "backtesting_threshold_curve.csv")
    rec = pd.read_csv(PROC / "backtesting_recommended_policy.csv").iloc[0]
    mc = pd.read_csv(PROC / "scenario_monte_carlo_summary.csv")
    monte_carlo_draws = pd.read_csv(
        PROC / "scenario_monte_carlo_samples.csv",
        usecols=["iteration"],
    )["iteration"].nunique()
    scenarios = pd.read_csv(PROC / "scenario_results_summary.csv")
    orders = pd.read_csv(RAW / "orders.csv")
    buyer_dim = pd.read_csv(RAW / "buyers.csv")
    sellers = pd.read_csv(RAW / "sellers.csv", parse_dates=["onboarding_date"])
    logistics = pd.read_csv(RAW / "logistics_events.csv")

    facts = (
        opf.merge(risk[["order_id", "order_risk_score", "order_risk_tier"]], on="order_id")
        .merge(orders[["order_id", "order_channel", "payment_method"]], on="order_id")
        .merge(buyer_dim[["buyer_id", "region"]], on="buyer_id")
        .merge(logistics[["order_id", "delay_days"]], on="order_id")
    )
    facts["month"] = facts["order_date"].dt.to_period("M").dt.to_timestamp()
    facts["adverse"] = (
        (facts["refund_amount"] > 0) | (facts["dispute_amount"] > 0) | (facts["chargeback_loss_proxy"] > 0)
    ).astype(int)

    # 01 Growth-quality gap
    m = facts.groupby("month", as_index=False).agg(
        gmv=("gross_value", "sum"), risk_adjusted=("risk_adjusted_order_value", "sum")
    )
    fig, ax = plt.subplots(figsize=(8.4, 4.5))
    style(ax)
    ax.plot(m.month, m.gmv / 1e6, color=MUTE, lw=1.8)
    ax.plot(m.month, m.risk_adjusted / 1e6, color=ACCENT, lw=2.5)
    ax.fill_between(m.month, m.risk_adjusted / 1e6, m.gmv / 1e6, color=ACCENT, alpha=0.08)
    ax.text(m.month.iloc[-1], m.gmv.iloc[-1] / 1e6, "  GMV", color=MUTE, va="center")
    ax.text(m.month.iloc[-1], m.risk_adjusted.iloc[-1] / 1e6, "  Risk-adjusted", color=ACCENT, va="center")
    ax.yaxis.set_major_formatter(FuncFormatter(money_m))
    ax.set_ylabel("Monthly value")
    title(
        ax,
        "Growth consistently overstates protected value",
        "Monthly GMV and risk-adjusted value, Mar 2024 to Feb 2026",
    )
    save(fig, "01_growth_quality_gap.png")

    # 02 Monthly margin variance
    mm = facts.groupby("month", as_index=False).agg(margin=("realized_contribution_margin_proxy", "sum"))
    fig, ax = plt.subplots(figsize=(8.4, 4.5))
    style(ax)
    ax.bar(mm.month, mm.margin / 1e3, width=20, color=LOSS, alpha=0.82)
    ax.plot(mm.month, mm.margin.rolling(3).mean() / 1e3, color=INK, lw=2.1)
    ax.axhline(0, color=INK, lw=0.9)
    ax.set_ylabel("Contribution margin ($000)")
    title(
        ax,
        "Every month is contribution-negative",
        "Monthly realized contribution margin; black line is the three-month average",
    )
    save(fig, "02_monthly_margin_variance.png")

    # 03 Leakage waterfall
    vals = {
        "Commission": facts.commission_fee.sum(),
        "Subsidy": -facts.subsidy_amount.sum(),
        "Refunds": -facts.refund_amount.sum(),
        "Disputes": -facts.dispute_amount.sum(),
        "Chargebacks": -facts.chargeback_loss_proxy.sum(),
    }
    running = 0
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    style(ax)
    for i, (_lab, val) in enumerate(vals.items()):
        bottom = running if val >= 0 else running + val
        ax.bar(i, abs(val) / 1e6, bottom=bottom / 1e6, color=FAINT if val >= 0 else LOSS, width=0.62)
        ax.text(i, (bottom + abs(val)) / 1e6, f"{val / 1e6:+.2f}", ha="center", va="bottom", fontsize=9)
        running += val
    ax.bar(5, running / 1e6, color=ACCENT, width=0.62)
    # Anchor at the bar's zero-line edge (not its negative tip) with va="bottom" so the
    # label sits in open space above the bar, matching the other bars' treatment. Anchoring
    # at the tip with va="top" pushed the label past the bar into the axis tick labels below.
    ax.text(5, 0, f"{running / 1e6:.2f}", ha="center", va="bottom", color=ACCENT, fontweight="bold")
    ax.set_xticks(range(6), [*vals.keys(), "Contribution\nmargin"])
    ax.yaxis.set_major_formatter(FuncFormatter(money_m))
    title(
        ax,
        "Post-order leakage overwhelms commission revenue",
        "Bridge from commission revenue to realized contribution margin, $M",
    )
    save(fig, "03_leakage_waterfall.png")

    # 04 Leakage composition
    leakage = pd.Series(
        {
            "Refunds": facts.refund_amount.sum(),
            "Disputes": facts.dispute_amount.sum(),
            "Chargebacks": facts.chargeback_loss_proxy.sum(),
            "Subsidy": facts.subsidy_amount.sum(),
        }
    )
    fig, ax = plt.subplots(figsize=(8.4, 4.5))
    style(ax, "x")
    ax.grid(axis="y", visible=False)
    left = 0
    for i, (lab, val) in enumerate(leakage.items()):
        color = ACCENT if lab == "Refunds" else [LOSS, MUTE, FAINT][i - 1]
        ax.barh(["Total leakage"], [val / 1e6], left=left, color=color, label=lab, height=0.52)
        ax.text(
            left + val / 2e6,
            0,
            f"{lab}\n${val / 1e6:.2f}M",
            ha="center",
            va="center",
            fontsize=9,
            color="white" if lab != "Subsidy" else INK,
            fontweight="bold",
        )
        left += val / 1e6
    ax.set_xlabel("Value ($M)")
    ax.xaxis.set_major_formatter(FuncFormatter(money_m))
    title(ax, "Refunds are the largest controllable leakage pool", "Composition of subsidy and post-order leakage")
    save(fig, "04_leakage_composition.png")

    # Category summaries
    cat = (
        facts.groupby("category")
        .agg(
            orders=("order_id", "size"),
            gmv=("gross_value", "sum"),
            refunds=("refund_amount", "sum"),
            margin=("realized_contribution_margin_proxy", "sum"),
            adverse_rate=("adverse", "mean"),
        )
        .reset_index()
    )
    cat["refund_rate"] = cat.refunds / cat.gmv * 100
    cat["margin_rate"] = cat.margin / cat.gmv * 100
    horizontal_bars(
        cat,
        "refund_rate",
        "category",
        "Electronics and Fashion lead refund pressure",
        "Refund value as a share of GMV by category",
        "05_refund_rate_by_category.png",
    )

    # 06 Category economics matrix
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    style(ax)
    ax.scatter(cat.gmv / 1e6, cat.margin_rate, s=cat.orders / 45, color=FAINT, edgecolor="white")
    for _, r in cat.iterrows():
        col = ACCENT if r.category == "Electronics" else MUTE
        ax.text(r.gmv / 1e6, r.margin_rate, r.category, fontsize=8.5, color=col, ha="center", va="center")
    ax.axhline(0, color=INK, lw=0.9)
    ax.set_xlabel("GMV ($M)")
    ax.set_ylabel("Contribution margin / GMV")
    ax.yaxis.set_major_formatter(PercentFormatter())
    ax.xaxis.set_major_formatter(FuncFormatter(money_m))
    title(
        ax,
        "Electronics dominates both scale and absolute downside",
        "Category portfolio: GMV, margin rate and order volume",
    )
    save(fig, "06_category_economics_matrix.png")

    # 07 Category risk heatmap
    heat = cat_month.groupby("category")[
        ["refund_rate", "dispute_rate", "subsidy_rate", "margin_fragility_index"]
    ].mean()
    heat = (heat - heat.mean()) / heat.std()
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    ax.imshow(heat.values, cmap="RdBu_r", aspect="auto", vmin=-2, vmax=2)
    ax.set_xticks(range(4), ["Refund", "Dispute", "Subsidy", "Fragility"])
    ax.set_yticks(range(len(heat)), heat.index)
    for i in range(len(heat)):
        for j in range(4):
            ax.text(
                j,
                i,
                f"{heat.iloc[i, j]:+.1f}",
                ha="center",
                va="center",
                fontsize=8,
                color="white" if abs(heat.iloc[i, j]) > 1 else INK,
            )
    title(
        ax,
        "Category risk is multidimensional, not a single-rate problem",
        "Standardized category risk indicators; positive values are above portfolio average",
    )
    save(fig, "07_category_risk_heatmap.png")

    # 08 Governance distribution
    tiers = score.governance_priority_tier.value_counts().reindex(["Low", "Moderate", "High", "Critical"]).fillna(0)
    fig, ax = plt.subplots(figsize=(8.4, 4.5))
    style(ax)
    bars = ax.bar(tiers.index, tiers.values, color=[FAINT, FAINT, ACCENT, LOSS])
    for b, v in zip(bars, tiers.values, strict=True):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{int(v):,}", ha="center", va="bottom", fontweight="bold")
    ax.set_ylabel("Sellers")
    title(ax, "Seller governance concentrates into a finite queue", "Current seller count by governance priority tier")
    save(fig, "08_seller_governance_distribution.png")

    # 09 Seller portfolio
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    style(ax)
    colors = np.where(score.governance_priority_tier.eq("High"), ACCENT, FAINT)
    ax.scatter(score.gmv / 1e3, score.seller_quality_score, s=18, color=colors, alpha=0.65, edgecolor="none")
    ax.axhline(score.seller_quality_score.median(), color=MUTE, ls="--", lw=1)
    ax.set_xlabel("Seller GMV ($000)")
    ax.set_ylabel("Seller quality risk score")
    title(
        ax,
        "High-priority sellers combine quality risk with meaningful volume",
        "Seller portfolio by GMV and seller quality score",
    )
    save(fig, "09_seller_portfolio_matrix.png")

    # 10 Seller concentration
    sgmv = score.gmv.sort_values(ascending=False).reset_index(drop=True)
    cum = sgmv.cumsum() / sgmv.sum() * 100
    x = (np.arange(len(cum)) + 1) / len(cum) * 100
    fig, ax = plt.subplots(figsize=(8.4, 4.5))
    style(ax)
    ax.plot(x, cum, color=ACCENT, lw=2.5)
    ax.plot([0, 100], [0, 100], color=FAINT, ls="--")
    ax.set_xlabel("Cumulative share of sellers")
    ax.set_ylabel("Cumulative share of GMV")
    ax.xaxis.set_major_formatter(PercentFormatter())
    ax.yaxis.set_major_formatter(PercentFormatter())
    title(
        ax,
        "GMV is dispersed, but the upper tail still merits controls",
        "Seller concentration curve, current scorecard period",
    )
    save(fig, "10_seller_concentration_curve.png")

    # 11 Risk distribution
    fig, ax = plt.subplots(figsize=(8.4, 4.5))
    style(ax)
    ax.hist(facts.order_risk_score, bins=np.arange(0, 105, 5), color=FAINT, edgecolor="white")
    ax.axvline(rec.recommended_threshold, color=ACCENT, lw=2.5)
    ax.text(
        rec.recommended_threshold + 1,
        ax.get_ylim()[1] * 0.86,
        f"Review threshold\n{rec.recommended_threshold:.0f}",
        color=ACCENT,
    )
    ax.set_xlabel("Order risk score")
    ax.set_ylabel("Orders")
    title(ax, "The score-60 threshold selects the upper quarter of orders", "Distribution of order risk scores")
    save(fig, "11_order_risk_distribution.png")

    # 12 Risk separation
    sep = (
        facts.groupby("order_risk_tier")
        .agg(orders=("order_id", "size"), adverse=("adverse", "mean"))
        .reindex(["Low", "Moderate", "High", "Critical"])
        .dropna()
        .reset_index()
    )
    sep["adverse"] *= 100
    horizontal_bars(
        sep,
        "adverse",
        "order_risk_tier",
        "Observed adverse events rise with risk tier",
        "Share of orders with refund, dispute or chargeback by risk tier",
        "12_risk_tier_separation.png",
        accent_rows=1,
    )

    # 13 Review funnel
    reviewed = facts.order_risk_score.ge(rec.recommended_threshold)
    values = [len(facts), reviewed.sum(), facts.loc[reviewed, "adverse"].sum(), facts.loc[~reviewed, "adverse"].sum()]
    labels = ["All orders", "Sent to review", "Adverse captured", "Adverse missed"]
    fig, ax = plt.subplots(figsize=(8.4, 4.5))
    style(ax)
    bars = ax.bar(labels, values, color=[FAINT, ACCENT, ACCENT, LOSS])
    for b, v in zip(bars, values, strict=True):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{int(v):,}", ha="center", va="bottom", fontweight="bold")
    ax.set_ylabel("Orders / events")
    # Headline must state recall (share of adverse orders captured), not
    # precision — a prior hardcoded version quoted precision (41.8%) under
    # the word "captures", which describes recall (31.3%) instead.
    title(
        ax,
        f"A {rec.review_rate:.0%} review queue captures {rec.recall:.0%} of adverse orders",
        "Operational review funnel at the recommended score threshold",
    )
    save(fig, "13_review_funnel.png")

    # 14 Buyer risk distribution
    fig, ax = plt.subplots(figsize=(8.4, 4.5))
    style(ax)
    ax.hist(buyers.order_risk_proxy, bins=25, color=FAINT, edgecolor="white")
    q90 = buyers.order_risk_proxy.quantile(0.9)
    ax.axvline(q90, color=ACCENT, lw=2.5)
    ax.text(q90 + 0.5, ax.get_ylim()[1] * 0.84, "Top-risk decile", color=ACCENT)
    ax.set_xlabel("Buyer risk proxy")
    ax.set_ylabel("Buyers")
    title(ax, "Buyer risk has a long but manageable upper tail", "Distribution of buyer behavior risk proxy")
    save(fig, "14_buyer_risk_distribution.png")

    # 15 Geography
    geo = (
        facts.groupby("region")
        .agg(gmv=("gross_value", "sum"), margin=("realized_contribution_margin_proxy", "sum"))
        .reset_index()
    )
    geo["margin_rate"] = geo.margin / geo.gmv * 100
    fig, ax = plt.subplots(figsize=(8.4, 4.7))
    style(ax)
    bars = ax.bar(geo.region, geo.gmv / 1e6, color=FAINT)
    ax2 = ax.twinx()
    ax2.plot(geo.region, geo.margin_rate, color=ACCENT, marker="o", lw=2.2)
    ax.set_ylabel("GMV ($M)")
    ax2.set_ylabel("Contribution margin / GMV", color=ACCENT)
    ax.yaxis.set_major_formatter(FuncFormatter(money_m))
    ax2.yaxis.set_major_formatter(PercentFormatter())
    ax2.spines[["top"]].set_visible(False)
    title(
        ax,
        "Regional GMV scale does not materially change negative economics",
        "GMV bars and contribution margin rate line by buyer region",
    )
    save(fig, "15_geography_value_and_margin.png")

    # 16 Correlation
    corr_cols = [
        "gross_value",
        "subsidy_amount",
        "refund_amount",
        "dispute_amount",
        "chargeback_loss_proxy",
        "delay_days",
        "order_risk_score",
        "realized_contribution_margin_proxy",
    ]
    corr = facts[corr_cols].corr()
    fig, ax = plt.subplots(figsize=(8.4, 5.5))
    ax.imshow(corr, cmap="RdBu_r", vmin=-1, vmax=1)
    labels = ["GMV", "Subsidy", "Refund", "Dispute", "Chargeback", "Delay", "Risk score", "Margin"]
    ax.set_xticks(range(len(labels)), labels, rotation=35, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(
                j,
                i,
                f"{corr.iloc[i, j]:.2f}",
                ha="center",
                va="center",
                fontsize=7.5,
                color="white" if abs(corr.iloc[i, j]) > 0.55 else INK,
            )
    title(
        ax,
        "Loss events, not order value alone, drive margin deterioration",
        "Pearson correlation across order-level economic and risk measures",
    )
    save(fig, "16_correlation_matrix.png")

    # 17 Seller onboarding cohort
    cohort = score.merge(sellers[["seller_id", "onboarding_date"]], on="seller_id")
    cohort["cohort"] = cohort.onboarding_date.dt.to_period("Q").astype(str)
    cg = (
        cohort.groupby("cohort")
        .agg(
            score=("governance_priority_score", "median"),
            high_share=("governance_priority_tier", lambda x: x.eq("High").mean()),
        )
        .tail(10)
    )
    fig, ax = plt.subplots(figsize=(8.4, 4.7))
    style(ax)
    ax.plot(cg.index, cg.score, color=ACCENT, marker="o", lw=2.2)
    ax.set_ylabel("Median governance priority score")
    ax.tick_params(axis="x", rotation=35)
    title(
        ax,
        "Recent onboarding cohorts do not show a clean quality improvement",
        "Median governance priority score by seller onboarding quarter",
    )
    save(fig, "17_seller_onboarding_cohort.png")

    # 18 Scenario ranges
    order = [
        "downside_high_risk_deterioration",
        "baseline",
        "subsidy_tightening",
        "seller_quality_improvement",
        "fraud_control_improvement",
    ]
    nice = {
        "downside_high_risk_deterioration": "Downside deterioration",
        "baseline": "Baseline",
        "subsidy_tightening": "Subsidy tightening",
        "seller_quality_improvement": "Seller quality",
        "fraud_control_improvement": "Fraud control",
    }
    mmc = mc.set_index("scenario").loc[order]
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    style(ax, "x")
    ax.grid(axis="y", visible=False)
    for i, s in enumerate(order):
        col = ACCENT if s == "fraud_control_improvement" else LOSS if s.startswith("downside") else MUTE
        p05, p50, p95 = [mmc.loc[s, f"contribution_margin_proxy_{p}"] / 1e6 for p in ["p05", "p50", "p95"]]
        ax.plot([p05, p95], [i, i], color=col, lw=2.5, solid_capstyle="round")
        ax.scatter(p50, i, color=col, s=45)
    ax.axvline(0, color=INK, lw=1)
    ax.set_yticks(range(len(order)), [nice[x] for x in order])
    ax.xaxis.set_major_formatter(FuncFormatter(money_m))
    ax.set_xlabel("Contribution margin, P5 to P95")
    title(
        ax,
        "No modeled scenario reaches break-even",
        f"Monte Carlo contribution margin ranges, {monte_carlo_draws:,} draws per scenario",
    )
    save(fig, "18_scenario_margin_ranges.png")

    # 19 Scenario before vs after
    sc = scenarios.set_index("scenario").loc[order]
    fig, ax = plt.subplots(figsize=(8.4, 4.8))
    style(ax, "x")
    ax.grid(axis="y", visible=False)
    y = np.arange(len(order))
    ax.barh(y, sc.contribution_margin_proxy / 1e6, color=[LOSS, FAINT, FAINT, FAINT, ACCENT])
    ax.set_yticks(y, [nice[x] for x in order])
    ax.axvline(0, color=INK, lw=1)
    ax.xaxis.set_major_formatter(FuncFormatter(money_m))
    ax.set_xlabel("Contribution margin")
    title(
        ax,
        "Fraud control is the strongest mitigation, not a profitability fix",
        "Deterministic contribution margin by scenario",
    )
    save(fig, "19_scenario_before_after.png")

    # 20 Threshold tradeoff
    c = curve.sort_values("review_rate")
    fig, ax = plt.subplots(figsize=(8.4, 4.7))
    style(ax)
    ax.plot(c.review_rate * 100, c.net_benefit / 1e6, color=ACCENT, marker="o", lw=2.3)
    ax.scatter(rec.review_rate * 100, rec.net_benefit / 1e6, s=120, facecolor="white", edgecolor=ACCENT, lw=2)
    ax.annotate(
        f"Score >= {rec.recommended_threshold:.0f}\n{rec.review_rate:.0%} reviewed\n${rec.net_benefit / 1e6:.2f}M net",
        (rec.review_rate * 100, rec.net_benefit / 1e6),
        xytext=(14, -8),
        textcoords="offset points",
        bbox={"boxstyle": "round,pad=.45", "fc": PANEL, "ec": "none"},
    )
    ax.set_xlabel("Orders reviewed")
    ax.set_ylabel("Net benefit")
    ax.xaxis.set_major_formatter(PercentFormatter())
    ax.yaxis.set_major_formatter(FuncFormatter(money_m))
    title(
        ax,
        "Review economics flatten well before full coverage",
        "Retrospective in-sample threshold simulation; holdout validation required",
    )
    save(fig, "20_threshold_tradeoff.png")

    print(f"done -> {OUT} ({len(list(OUT.glob('*.png')))} charts)")


if __name__ == "__main__":
    main()
