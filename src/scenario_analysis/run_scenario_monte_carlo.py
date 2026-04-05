from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns


@dataclass(frozen=True)
class MonteCarloConfig:
    processed_dir: Path = Path("data/processed")
    output_dir: Path = Path("data/processed")
    charts_dir: Path = Path("outputs/charts")
    iterations: int = 2000
    seed: int = 42


def _load(cfg: MonteCarloConfig) -> Dict[str, pd.DataFrame]:
    return {
        "assumptions": pd.read_csv(cfg.processed_dir / "scenario_assumptions.csv"),
        "results": pd.read_csv(cfg.processed_dir / "scenario_results_summary.csv"),
        "exposure": pd.read_csv(cfg.processed_dir / "scenario_top_risk_exposure.csv"),
    }


def _draw_factor(rng: np.random.Generator, base: float, sigma: float, lower: float = 0.01) -> float:
    x = base * (1.0 + rng.normal(0.0, sigma))
    return float(max(lower, x))


def _simulate(cfg: MonteCarloConfig, assumptions: pd.DataFrame, baseline_row: pd.Series, exposure: pd.Series) -> pd.DataFrame:
    rng = np.random.default_rng(cfg.seed)

    baseline_gmv = float(baseline_row["gmv"])
    baseline_net_to_gmv = float(baseline_row["net_value"] / baseline_row["gmv"]) if float(baseline_row["gmv"]) else 0.0
    baseline_commission_rate = float(baseline_row["commission_revenue"] / baseline_row["gmv"]) if float(baseline_row["gmv"]) else 0.0
    baseline_subsidy_rate = float(baseline_row["subsidy"] / baseline_row["gmv"]) if float(baseline_row["gmv"]) else 0.0
    baseline_refund_rate = float(baseline_row["refunds"] / baseline_row["net_value"]) if float(baseline_row["net_value"]) else 0.0
    baseline_dispute_rate = float(baseline_row["disputes"] / baseline_row["net_value"]) if float(baseline_row["net_value"]) else 0.0
    baseline_chargeback_rate = (
        float(baseline_row["chargeback_loss"] / baseline_row["net_value"]) if float(baseline_row["net_value"]) else 0.0
    )
    baseline_risk_gap_rate = (
        float((baseline_row["net_value"] - baseline_row["risk_adjusted_gmv"]) / baseline_row["net_value"])
        if float(baseline_row["net_value"])
        else 0.0
    )

    rows: List[dict[str, float | int | str]] = []
    for it in range(cfg.iterations):
        macro_scale = 1.0 + rng.normal(0.0, 0.015)

        for r in assumptions.itertuples(index=False):
            gmv_factor = _draw_factor(rng, r.gmv_factor * macro_scale, sigma=0.03)
            net_to_gmv_factor = _draw_factor(rng, r.net_to_gmv_factor, sigma=0.015)
            subsidy_rate_factor = _draw_factor(rng, r.subsidy_rate_factor, sigma=0.05)
            refund_rate_factor = _draw_factor(rng, r.refund_rate_factor, sigma=0.06)
            dispute_rate_factor = _draw_factor(rng, r.dispute_rate_factor, sigma=0.07)
            chargeback_rate_factor = _draw_factor(rng, r.chargeback_rate_factor, sigma=0.08)
            risk_gap_factor = _draw_factor(rng, r.risk_gap_factor, sigma=0.06)
            top_risk_exposure_factor = _draw_factor(rng, r.top_risk_exposure_factor, sigma=0.06)

            gmv = baseline_gmv * gmv_factor
            net = gmv * baseline_net_to_gmv * net_to_gmv_factor
            commission = gmv * baseline_commission_rate

            subsidy = gmv * baseline_subsidy_rate * subsidy_rate_factor
            refunds = net * baseline_refund_rate * refund_rate_factor
            disputes = net * baseline_dispute_rate * dispute_rate_factor
            chargeback = net * baseline_chargeback_rate * chargeback_rate_factor

            leakage_total = subsidy + refunds + disputes + chargeback
            contribution_margin = commission - leakage_total
            risk_adjusted = net * (1.0 - baseline_risk_gap_rate * risk_gap_factor)

            top_risk_downside = (
                net
                * float(exposure["top_risk_net_share"])
                * float(exposure["top_risk_leak_rate"])
                * top_risk_exposure_factor
            )

            rows.append(
                {
                    "iteration": it,
                    "scenario": r.scenario,
                    "scenario_type": r.scenario_type,
                    "gmv": gmv,
                    "net_value": net,
                    "risk_adjusted_gmv": risk_adjusted,
                    "commission_revenue": commission,
                    "subsidy": subsidy,
                    "refunds": refunds,
                    "disputes": disputes,
                    "chargeback_loss": chargeback,
                    "total_leakage": leakage_total,
                    "contribution_margin_proxy": contribution_margin,
                    "top_risk_seller_downside_exposure": top_risk_downside,
                }
            )

    return pd.DataFrame(rows)


def _summarize(samples: pd.DataFrame) -> pd.DataFrame:
    out_rows: List[dict[str, float | str]] = []
    metrics = [
        "gmv",
        "net_value",
        "risk_adjusted_gmv",
        "total_leakage",
        "contribution_margin_proxy",
        "top_risk_seller_downside_exposure",
    ]

    baseline = samples[samples["scenario"] == "baseline"][["iteration", "contribution_margin_proxy", "total_leakage"]].rename(
        columns={
            "contribution_margin_proxy": "baseline_cm",
            "total_leakage": "baseline_leakage",
        }
    )

    for scenario, grp in samples.groupby("scenario", sort=False):
        row: dict[str, float | str] = {"scenario": scenario, "scenario_type": str(grp["scenario_type"].iloc[0])}
        for m in metrics:
            row[f"{m}_mean"] = float(grp[m].mean())
            row[f"{m}_p05"] = float(grp[m].quantile(0.05))
            row[f"{m}_p50"] = float(grp[m].quantile(0.50))
            row[f"{m}_p95"] = float(grp[m].quantile(0.95))
            row[f"{m}_std"] = float(grp[m].std(ddof=0))

        merged = grp[["iteration", "contribution_margin_proxy", "total_leakage"]].merge(baseline, on="iteration", how="left")
        row["prob_cm_positive"] = float((grp["contribution_margin_proxy"] > 0).mean())
        row["prob_cm_better_than_baseline"] = float((merged["contribution_margin_proxy"] > merged["baseline_cm"]).mean())
        row["prob_leakage_better_than_baseline"] = float((merged["total_leakage"] < merged["baseline_leakage"]).mean())
        out_rows.append(row)

    out = pd.DataFrame(out_rows)
    out["expected_cm_delta_vs_baseline"] = (
        out["contribution_margin_proxy_mean"] - float(out.loc[out["scenario"] == "baseline", "contribution_margin_proxy_mean"].iloc[0])
    )
    out = out.sort_values("expected_cm_delta_vs_baseline", ascending=False)
    return out


def _decision_table(summary: pd.DataFrame) -> pd.DataFrame:
    df = summary.copy()
    baseline_mean = float(df.loc[df["scenario"] == "baseline", "contribution_margin_proxy_mean"].iloc[0])
    baseline_abs = max(abs(baseline_mean), 1.0)

    df["decision_score_uncertain"] = (
        0.45 * (df["expected_cm_delta_vs_baseline"] / baseline_abs)
        + 0.35 * df["prob_cm_better_than_baseline"]
        + 0.20 * df["prob_leakage_better_than_baseline"]
    ) * 100.0
    return df.sort_values("decision_score_uncertain", ascending=False)[
        [
            "scenario",
            "scenario_type",
            "decision_score_uncertain",
            "expected_cm_delta_vs_baseline",
            "prob_cm_positive",
            "prob_cm_better_than_baseline",
            "prob_leakage_better_than_baseline",
            "contribution_margin_proxy_p05",
            "contribution_margin_proxy_p50",
            "contribution_margin_proxy_p95",
        ]
    ]


def _plot(summary: pd.DataFrame, output_path: Path) -> None:
    sns.set_theme(style="whitegrid", context="talk")
    df = summary.sort_values("contribution_margin_proxy_p50", ascending=False)

    fig, ax = plt.subplots(figsize=(13, 7))
    x = np.arange(len(df))
    y = df["contribution_margin_proxy_p50"] / 1_000_000
    yerr_low = (df["contribution_margin_proxy_p50"] - df["contribution_margin_proxy_p05"]) / 1_000_000
    yerr_high = (df["contribution_margin_proxy_p95"] - df["contribution_margin_proxy_p50"]) / 1_000_000

    ax.errorbar(
        x,
        y,
        yerr=np.vstack([yerr_low, yerr_high]),
        fmt="o",
        capsize=5,
        color="#0b5ed7",
    )
    ax.axhline(0.0, color="#7c8ea8", linestyle="--", linewidth=1.2)
    ax.set_xticks(x)
    ax.set_xticklabels(df["scenario"], rotation=25, ha="right")
    ax.set_ylabel("Contribution Margin Proxy ($M)")
    ax.set_title("Scenario Uncertainty Bands Show Range of Margin Outcomes (P05-P50-P95)")

    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)


def run_monte_carlo(cfg: MonteCarloConfig) -> dict[str, pd.DataFrame]:
    data = _load(cfg)
    baseline = data["results"][data["results"]["scenario"] == "baseline"].iloc[0]
    exposure = data["exposure"].iloc[0]

    samples = _simulate(
        cfg=cfg,
        assumptions=data["assumptions"],
        baseline_row=baseline,
        exposure=exposure,
    )
    summary = _summarize(samples)
    decision = _decision_table(summary)
    return {
        "scenario_monte_carlo_samples": samples,
        "scenario_monte_carlo_summary": summary,
        "scenario_monte_carlo_decision": decision,
    }


def save_outputs(outputs: dict[str, pd.DataFrame], cfg: MonteCarloConfig) -> None:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    for name, df in outputs.items():
        df.to_csv(cfg.output_dir / f"{name}.csv", index=False)

    _plot(
        summary=outputs["scenario_monte_carlo_summary"],
        output_path=cfg.charts_dir / "18_scenario_monte_carlo_ranges.png",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Monte Carlo scenario uncertainty analysis.")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--charts-dir", type=Path, default=Path("outputs/charts"))
    parser.add_argument("--iterations", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    cfg = MonteCarloConfig(
        processed_dir=args.processed_dir,
        output_dir=args.output_dir,
        charts_dir=args.charts_dir,
        iterations=args.iterations,
        seed=args.seed,
    )

    outputs = run_monte_carlo(cfg)
    save_outputs(outputs, cfg)

    print("Monte Carlo scenario outputs generated:")
    for name, df in outputs.items():
        print(f"  - {name}: {len(df):,} rows")
    print("  - chart: 18_scenario_monte_carlo_ranges.png")


if __name__ == "__main__":
    main()
