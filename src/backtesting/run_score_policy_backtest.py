from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


@dataclass(frozen=True)
class BacktestConfig:
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    output_dir: Path = Path("data/processed")
    charts_dir: Path = Path("outputs/charts")
    thresholds: tuple[int, ...] = tuple(range(30, 96, 5))
    manual_review_cost: float = 1.20
    friction_rate: float = 0.003
    base_efficacy: float = 0.35
    efficacy_scenarios: tuple[float, ...] = (0.20, 0.35, 0.50)


def _load(cfg: BacktestConfig) -> dict[str, pd.DataFrame]:
    return {
        "order_risk": pd.read_csv(cfg.processed_dir / "order_risk_scores.csv"),
        "opf": pd.read_csv(cfg.processed_dir / "order_profitability_features.csv"),
        "payments": pd.read_csv(cfg.raw_dir / "payments.csv"),
    }


def _build_base(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    order_risk = tables["order_risk"]
    opf = tables["opf"]
    payments = tables["payments"]

    base = (
        order_risk[
            [
                "order_id",
                "order_risk_score",
                "order_risk_tier",
                "order_risk_main_driver",
                "recommended_action",
            ]
        ]
        .merge(
            opf[
                [
                    "order_id",
                    "net_value",
                    "refund_amount",
                    "dispute_amount",
                    "risk_adjusted_order_value",
                    "estimated_margin_after_risk",
                ]
            ],
            on="order_id",
            how="left",
        )
        .merge(payments[["order_id", "chargeback_flag"]], on="order_id", how="left")
    )

    base["chargeback_flag"] = base["chargeback_flag"].fillna(0).astype(int)
    base["chargeback_loss_proxy"] = base["chargeback_flag"] * base["net_value"]
    base["bad_event_flag"] = (
        (base["refund_amount"] > 0) | (base["dispute_amount"] > 0) | (base["chargeback_flag"] == 1)
    ).astype(int)
    base["event_loss_proxy"] = (
        base["refund_amount"] + base["dispute_amount"] + base["chargeback_loss_proxy"]
    )
    return base


def _curve_for_thresholds(
    base: pd.DataFrame,
    thresholds: Iterable[int],
    manual_review_cost: float,
    friction_rate: float,
    efficacy: float,
) -> pd.DataFrame:
    rows: List[dict[str, float | int]] = []

    total_orders = len(base)
    total_bad = int(base["bad_event_flag"].sum())
    base_bad_rate = float(total_bad / total_orders) if total_orders else 0.0

    for threshold in thresholds:
        reviewed = base["order_risk_score"] >= threshold
        n_reviewed = int(reviewed.sum())
        tp = int((reviewed & (base["bad_event_flag"] == 1)).sum())
        fp = int((reviewed & (base["bad_event_flag"] == 0)).sum())

        precision = float(tp / n_reviewed) if n_reviewed else 0.0
        recall = float(tp / total_bad) if total_bad else 0.0
        review_rate = float(n_reviewed / total_orders) if total_orders else 0.0
        lift = float(precision / base_bad_rate) if base_bad_rate > 0 else 0.0

        bad_reviewed_loss = float(base.loc[reviewed & (base["bad_event_flag"] == 1), "event_loss_proxy"].sum())
        good_reviewed_net = float(base.loc[reviewed & (base["bad_event_flag"] == 0), "net_value"].sum())

        expected_avoided_loss = bad_reviewed_loss * efficacy
        review_cost = n_reviewed * manual_review_cost
        conversion_friction_cost = good_reviewed_net * friction_rate
        net_benefit = expected_avoided_loss - review_cost - conversion_friction_cost

        rows.append(
            {
                "threshold": threshold,
                "reviewed_orders": n_reviewed,
                "review_rate": review_rate,
                "true_positives": tp,
                "false_positives": fp,
                "precision": precision,
                "recall": recall,
                "lift_vs_base_bad_rate": lift,
                "expected_avoided_loss": expected_avoided_loss,
                "review_cost": review_cost,
                "conversion_friction_cost": conversion_friction_cost,
                "net_benefit": net_benefit,
                "efficacy_assumption": efficacy,
            }
        )

    return pd.DataFrame(rows).sort_values("threshold")


def _build_recommended_policy(curve: pd.DataFrame) -> pd.DataFrame:
    practical = curve[curve["review_rate"] <= 0.35].copy()
    if practical.empty:
        practical = curve.copy()

    best = practical.sort_values(["net_benefit", "precision", "threshold"], ascending=[False, False, False]).iloc[0]
    return pd.DataFrame(
        [
            {
                "recommended_threshold": int(best["threshold"]),
                "review_rate": float(best["review_rate"]),
                "precision": float(best["precision"]),
                "recall": float(best["recall"]),
                "expected_avoided_loss": float(best["expected_avoided_loss"]),
                "review_cost": float(best["review_cost"]),
                "conversion_friction_cost": float(best["conversion_friction_cost"]),
                "net_benefit": float(best["net_benefit"]),
                "policy_guidance": "Escalate orders above threshold to manual review; calibrate monthly with realized outcomes.",
            }
        ]
    )


def _plot(curve: pd.DataFrame, output_path: Path) -> None:
    sns.set_theme(style="whitegrid", context="talk")
    fig, axes = plt.subplots(1, 2, figsize=(16, 6))

    axes[0].plot(curve["threshold"], curve["precision"], marker="o", label="Precision")
    axes[0].plot(curve["threshold"], curve["recall"], marker="o", label="Recall")
    axes[0].plot(curve["threshold"], curve["review_rate"], marker="o", label="Review Rate")
    axes[0].set_title("Higher Risk Thresholds Improve Precision but Reduce Recall and Coverage")
    axes[0].set_xlabel("Order Risk Score Threshold")
    axes[0].set_ylabel("Rate")
    axes[0].legend()

    axes[1].plot(curve["threshold"], curve["net_benefit"] / 1_000_000, marker="o", color="#0b5ed7")
    best = curve.sort_values("net_benefit", ascending=False).iloc[0]
    axes[1].scatter([best["threshold"]], [best["net_benefit"] / 1_000_000], color="#b42318", s=80, zorder=3)
    axes[1].set_title("Intervention Net Benefit Peaks at an Intermediate Threshold")
    axes[1].set_xlabel("Order Risk Score Threshold")
    axes[1].set_ylabel("Net Benefit ($M)")
    axes[1].annotate(
        f"Best: {int(best['threshold'])}",
        xy=(best["threshold"], best["net_benefit"] / 1_000_000),
        xytext=(6, 8),
        textcoords="offset points",
        fontsize=10,
    )

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def run_backtest(cfg: BacktestConfig) -> dict[str, pd.DataFrame]:
    tables = _load(cfg)
    base = _build_base(tables)

    base_curve = _curve_for_thresholds(
        base=base,
        thresholds=cfg.thresholds,
        manual_review_cost=cfg.manual_review_cost,
        friction_rate=cfg.friction_rate,
        efficacy=cfg.base_efficacy,
    )

    impact_rows: List[pd.DataFrame] = []
    for eff in cfg.efficacy_scenarios:
        c = _curve_for_thresholds(
            base=base,
            thresholds=cfg.thresholds,
            manual_review_cost=cfg.manual_review_cost,
            friction_rate=cfg.friction_rate,
            efficacy=eff,
        )
        impact_rows.append(c)
    impact = pd.concat(impact_rows, ignore_index=True)

    recommended = _build_recommended_policy(base_curve)
    return {
        "backtesting_threshold_curve": base_curve,
        "backtesting_action_impact": impact,
        "backtesting_recommended_policy": recommended,
    }


def save_outputs(outputs: dict[str, pd.DataFrame], cfg: BacktestConfig) -> None:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    for name, df in outputs.items():
        df.to_csv(cfg.output_dir / f"{name}.csv", index=False)

    _plot(
        curve=outputs["backtesting_threshold_curve"],
        output_path=cfg.charts_dir / "17_order_risk_backtesting_thresholds.png",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run score-policy backtesting and intervention impact simulation.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--charts-dir", type=Path, default=Path("outputs/charts"))
    parser.add_argument("--manual-review-cost", type=float, default=1.20)
    parser.add_argument("--friction-rate", type=float, default=0.003)
    parser.add_argument("--base-efficacy", type=float, default=0.35)
    args = parser.parse_args()

    cfg = BacktestConfig(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        output_dir=args.output_dir,
        charts_dir=args.charts_dir,
        manual_review_cost=args.manual_review_cost,
        friction_rate=args.friction_rate,
        base_efficacy=args.base_efficacy,
    )

    outputs = run_backtest(cfg)
    save_outputs(outputs, cfg)

    print("Backtesting outputs generated:")
    for name, df in outputs.items():
        print(f"  - {name}: {len(df):,} rows")
    print("  - chart: 17_order_risk_backtesting_thresholds.png")


if __name__ == "__main__":
    main()
