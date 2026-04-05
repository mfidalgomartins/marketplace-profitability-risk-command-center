from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import pandas as pd


@dataclass(frozen=True)
class ExecutiveSnapshotConfig:
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    reports_dir: Path = Path("reports")


def _load(cfg: ExecutiveSnapshotConfig) -> Dict[str, pd.DataFrame]:
    return {
        "orders": pd.read_csv(cfg.raw_dir / "orders.csv", parse_dates=["order_date"]),
        "order_items": pd.read_csv(cfg.raw_dir / "order_items.csv"),
        "refunds": pd.read_csv(cfg.raw_dir / "refunds.csv"),
        "disputes": pd.read_csv(cfg.raw_dir / "disputes.csv"),
        "payments": pd.read_csv(cfg.raw_dir / "payments.csv"),
        "opf": pd.read_csv(cfg.processed_dir / "order_profitability_features.csv", parse_dates=["order_date"]),
        "seller_scorecard": pd.read_csv(cfg.processed_dir / "seller_scorecard.csv"),
        "scenario_decision": pd.read_csv(cfg.processed_dir / "scenario_decision_matrix.csv"),
    }


def _build_snapshot_tables(t: Dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, str]:
    orders = t["orders"]
    items = t["order_items"]
    refunds = t["refunds"]
    disputes = t["disputes"]
    payments = t["payments"]
    opf = t["opf"]
    seller_scorecard = t["seller_scorecard"]
    scenario_decision = t["scenario_decision"]

    gmv = float(opf["gross_value"].sum())
    net_value = float(opf["net_value"].sum())
    risk_adjusted_value = float(opf["risk_adjusted_order_value"].sum())
    take_rate = float(opf["commission_fee"].sum() / gmv) if gmv else 0.0
    subsidy_share = float(opf["subsidy_amount"].sum() / gmv) if gmv else 0.0
    realized_cm = float(opf["realized_contribution_margin_proxy"].sum())
    expected_cm = float(opf["estimated_margin_after_risk"].sum())

    refund_rate = float(orders["order_id"].isin(refunds["order_id"]).mean())
    dispute_rate = float(orders["order_id"].isin(disputes["order_id"]).mean())
    chargeback_rate = float(payments["chargeback_flag"].mean())

    seller_gmv = (
        items.groupby("seller_id", as_index=False)["gross_item_value"]
        .sum()
        .sort_values("gross_item_value", ascending=False)
    )
    top10_seller_share = (
        float(seller_gmv.head(10)["gross_item_value"].sum() / seller_gmv["gross_item_value"].sum())
        if len(seller_gmv) > 0
        else 0.0
    )
    critical_sellers = int((seller_scorecard["governance_priority_tier"] == "Critical").sum())

    best_scenario = scenario_decision.sort_values("decision_priority_score", ascending=False).iloc[0]
    best_scenario_text = (
        f"{best_scenario['scenario']} | score={best_scenario['decision_priority_score']:.2f} | "
        f"CM delta={best_scenario['contribution_margin_change_vs_baseline']:.0f} | "
        f"leakage avoided={best_scenario['leakage_avoided_vs_baseline']:.0f}"
    )

    metrics = pd.DataFrame(
        [
            {"metric": "gmv", "value": gmv, "display": f"${gmv:,.2f}"},
            {"metric": "net_value", "value": net_value, "display": f"${net_value:,.2f}"},
            {"metric": "risk_adjusted_value", "value": risk_adjusted_value, "display": f"${risk_adjusted_value:,.2f}"},
            {"metric": "take_rate", "value": take_rate, "display": f"{take_rate*100:.2f}%"},
            {"metric": "subsidy_share", "value": subsidy_share, "display": f"{subsidy_share*100:.2f}%"},
            {"metric": "realized_contribution_margin_proxy", "value": realized_cm, "display": f"${realized_cm:,.2f}"},
            {"metric": "expected_margin_after_risk", "value": expected_cm, "display": f"${expected_cm:,.2f}"},
            {"metric": "refund_rate", "value": refund_rate, "display": f"{refund_rate*100:.2f}%"},
            {"metric": "dispute_rate", "value": dispute_rate, "display": f"{dispute_rate*100:.2f}%"},
            {"metric": "chargeback_rate", "value": chargeback_rate, "display": f"{chargeback_rate*100:.2f}%"},
            {"metric": "top10_seller_gmv_share", "value": top10_seller_share, "display": f"{top10_seller_share*100:.2f}%"},
            {"metric": "critical_sellers", "value": float(critical_sellers), "display": str(critical_sellers)},
        ]
    )

    coverage_start = opf["order_date"].min().date().isoformat()
    coverage_end = opf["order_date"].max().date().isoformat()
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    markdown = "\n".join(
        [
            "# Executive KPI Snapshot",
            "",
            f"- Generated at: `{generated_at}`",
            f"- Coverage: `{coverage_start}` to `{coverage_end}`",
            f"- Orders: `{len(opf):,}`",
            "",
            "## Core KPIs",
            *(f"- `{r.metric}`: **{r.display}**" for r in metrics.itertuples(index=False)),
            "",
            "## Scenario Priority (Current Run)",
            f"- Top-ranked scenario: `{best_scenario_text}`",
            "",
            "## Notes",
            "- `realized_contribution_margin_proxy` uses realized refund/dispute/chargeback leakage.",
            "- `expected_margin_after_risk` is model-based expected-risk margin from the feature layer.",
        ]
    )
    return metrics, markdown


def generate_snapshot(cfg: ExecutiveSnapshotConfig) -> tuple[Path, Path]:
    tables = _load(cfg)
    metrics, markdown = _build_snapshot_tables(tables)

    cfg.reports_dir.mkdir(parents=True, exist_ok=True)
    csv_path = cfg.reports_dir / "executive_kpi_snapshot.csv"
    md_path = cfg.reports_dir / "executive_kpi_snapshot.md"

    metrics.to_csv(csv_path, index=False)
    md_path.write_text(markdown + "\n", encoding="utf-8")
    return csv_path, md_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate executive KPI snapshot artifacts from latest processed outputs.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    args = parser.parse_args()

    cfg = ExecutiveSnapshotConfig(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        reports_dir=args.reports_dir,
    )
    csv_path, md_path = generate_snapshot(cfg)
    print(f"Executive snapshot generated: {csv_path}")
    print(f"Executive snapshot generated: {md_path}")


if __name__ == "__main__":
    main()
