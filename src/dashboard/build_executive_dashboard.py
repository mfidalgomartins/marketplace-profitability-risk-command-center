from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
from plotly.offline import get_plotlyjs


@dataclass(frozen=True)
class DashboardConfig:
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    reports_dir: Path = Path("reports")
    output_file: Path = Path("outputs/dashboard/executive-marketplace-command-center.html")
    max_orders: int = 15000
    sample_seed: int = 42


DASHBOARD_VERSION = "2026.04.02-governed-kpi"


def _load_raw(raw_dir: Path) -> Dict[str, pd.DataFrame]:
    return {
        "buyers": pd.read_csv(raw_dir / "buyers.csv", parse_dates=["signup_date"]),
        "sellers": pd.read_csv(raw_dir / "sellers.csv", parse_dates=["onboarding_date"]),
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
        "order_risk": pd.read_csv(processed_dir / "order_risk_scores.csv", parse_dates=["order_date"]),
        "buyer_risk": pd.read_csv(processed_dir / "buyer_behavior_risk.csv"),
        "seller_scorecard": pd.read_csv(processed_dir / "seller_scorecard.csv"),
        "scenario_results": pd.read_csv(processed_dir / "scenario_results_summary.csv"),
        "scenario_assumptions": pd.read_csv(processed_dir / "scenario_assumptions.csv"),
        "scenario_decision": pd.read_csv(processed_dir / "scenario_decision_matrix.csv"),
    }


def _load_official_kpis(reports_dir: Path) -> Dict[str, object]:
    snap_path = reports_dir / "executive_kpi_snapshot.csv"
    if not snap_path.exists():
        return {"source": "fallback_missing_snapshot", "metrics": {}}

    snap = pd.read_csv(snap_path)
    if not {"metric", "value"}.issubset(snap.columns):
        return {"source": "fallback_invalid_snapshot_schema", "metrics": {}}

    metrics = {str(r["metric"]): float(r["value"]) for _, r in snap.iterrows() if pd.notna(r["value"])}
    return {"source": str(snap_path), "metrics": metrics}


def _build_order_facts(raw: Dict[str, pd.DataFrame], proc: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    opf = proc["opf"].copy()
    orders = raw["orders"]
    buyers = raw["buyers"]
    sellers = raw["sellers"]
    order_risk = proc["order_risk"]
    buyer_risk = proc["buyer_risk"]
    payments = raw["payments"]
    logistics = raw["logistics"]
    scorecard = proc["seller_scorecard"]

    base = (
        opf.merge(
            orders[["order_id", "order_channel", "payment_method"]],
            on="order_id",
            how="left",
        )
        .merge(
            buyers[["buyer_id", "region", "acquisition_channel", "customer_type"]],
            on="buyer_id",
            how="left",
        )
        .merge(
            sellers[["seller_id", "seller_tier", "seller_type", "seller_region"]],
            on="seller_id",
            how="left",
        )
        .merge(
            order_risk[["order_id", "order_risk_score", "order_risk_tier"]],
            on="order_id",
            how="left",
        )
        .merge(
            buyer_risk[["buyer_id", "order_risk_proxy"]],
            on="buyer_id",
            how="left",
        )
        .merge(
            payments[["order_id", "chargeback_flag", "payment_risk_signal", "payment_attempts"]],
            on="order_id",
            how="left",
        )
        .merge(
            logistics[
                [
                    "order_id",
                    "delay_days",
                    "cancellation_flag",
                    "delivered_date",
                    "promised_delivery_date",
                ]
            ],
            on="order_id",
            how="left",
        )
        .merge(
            scorecard[
                [
                    "seller_id",
                    "governance_priority_score",
                    "governance_priority_tier",
                    "seller_quality_score",
                    "margin_fragility_score",
                    "recommended_action",
                ]
            ],
            on="seller_id",
            how="left",
        )
    )

    eligible = (
        base["cancellation_flag"].fillna(0).eq(0)
        & base["delivered_date"].notna()
        & base["promised_delivery_date"].notna()
    )
    on_time = np.where(
        eligible,
        (base["delivered_date"] <= base["promised_delivery_date"]).astype(int),
        np.nan,
    )

    realized_margin = base.get(
        "realized_contribution_margin_proxy",
        base["commission_fee"]
        - base["subsidy_amount"]
        - base["refund_amount"]
        - base["dispute_amount"]
        - (base["chargeback_flag"].fillna(0).astype(int) * base["net_value"]),
    )

    fact = pd.DataFrame(
        {
            "d": base["order_date"].dt.strftime("%Y-%m-%d"),
            "m": base["order_date"].dt.to_period("M").astype(str),
            "sid": base["seller_id"].astype(str),
            "reg": base["region"].fillna("Unknown"),
            "cat": base["category"].fillna("Unknown"),
            "st": base["seller_tier"].fillna("Unknown"),
            "sst": base["seller_type"].fillna("Unknown"),
            "acq": base["acquisition_channel"].fillna("Unknown"),
            "bt": base["customer_type"].fillna("Unknown"),
            "rt": base["order_risk_tier"].fillna("Unknown"),
            "gv": base["gross_value"].astype(float).round(2),
            "nv": base["net_value"].astype(float).round(2),
            "rv": base["risk_adjusted_order_value"].astype(float).round(2),
            "sub": base["subsidy_amount"].astype(float).round(2),
            "com": base["commission_fee"].astype(float).round(2),
            "ref": base["refund_amount"].astype(float).round(2),
            "dsp": base["dispute_amount"].astype(float).round(2),
            "mar": base["estimated_margin_after_risk"].astype(float).round(2),
            "rcm": pd.Series(realized_margin).astype(float).round(2),
            "cb": base["chargeback_flag"].fillna(0).astype(int),
            "pr": base["payment_risk_signal"].fillna("Unknown"),
            "dd": base["delay_days"].fillna(0).astype(float).round(2),
            "can": base["cancellation_flag"].fillna(0).astype(int),
            "ot": pd.Series(on_time).where(pd.notna(on_time), None).tolist(),
            "ch": base["order_channel"].fillna("Unknown"),
            "pm": base["payment_method"].fillna("Unknown"),
            "brs": base["order_risk_proxy"].fillna(0).astype(float).round(2),
        }
    )
    return fact


def _build_seller_meta(raw: Dict[str, pd.DataFrame], proc: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    sellers = raw["sellers"]
    scorecard = proc["seller_scorecard"]
    out = scorecard.merge(
        sellers[["seller_id", "seller_tier", "seller_type", "seller_region"]],
        on="seller_id",
        how="left",
    )
    out = out.rename(
        columns={
            "seller_id": "sid",
            "seller_tier": "st",
            "seller_type": "sst",
            "seller_region": "sreg",
            "governance_priority_score": "gvs",
            "governance_priority_tier": "gvt",
            "seller_quality_score": "sqs",
            "fraud_exposure_score": "fes",
            "margin_fragility_score": "mfs",
            "recommended_action": "ract",
            "gmv": "gmv",
            "orders": "orders",
            "net_value": "nv",
        }
    )
    out["sid"] = out["sid"].astype(str)
    return out[
        [
            "sid",
            "st",
            "sst",
            "sreg",
            "gvs",
            "gvt",
            "sqs",
            "fes",
            "mfs",
            "gmv",
            "orders",
            "nv",
            "ract",
        ]
    ].copy()


def _sample_fact_rows(fact: pd.DataFrame, max_orders: int, sample_seed: int) -> pd.DataFrame:
    if max_orders <= 0 or len(fact) <= max_orders:
        return fact

    # Preserve broad distribution across time/category/risk while shrinking payload for demo mode.
    strata = fact.assign(_strata=fact["m"].astype(str) + "|" + fact["cat"].astype(str) + "|" + fact["rt"].astype(str))
    frac = max_orders / len(strata)
    sampled_parts: List[pd.DataFrame] = []

    for _, grp in strata.groupby("_strata", sort=False):
        n = int(round(len(grp) * frac))
        n = max(1, min(len(grp), n))
        sampled_parts.append(grp.sample(n=n, random_state=sample_seed))

    sampled = pd.concat(sampled_parts, ignore_index=True)
    if len(sampled) > max_orders:
        sampled = sampled.sample(n=max_orders, random_state=sample_seed)

    return sampled.drop(columns=["_strata"]).sort_values(["m", "sid"]).reset_index(drop=True)


def _build_payload(cfg: DashboardConfig) -> Dict[str, object]:
    raw = _load_raw(cfg.raw_dir)
    proc = _load_processed(cfg.processed_dir)
    official = _load_official_kpis(cfg.reports_dir)

    fact_all = _build_order_facts(raw, proc)
    fact = _sample_fact_rows(fact_all, max_orders=cfg.max_orders, sample_seed=cfg.sample_seed)
    seller_meta = _build_seller_meta(raw, proc)

    options = {
        "region": sorted(fact["reg"].dropna().unique().tolist()),
        "category": sorted(fact["cat"].dropna().unique().tolist()),
        "seller_tier": sorted(fact["st"].dropna().unique().tolist()),
        "seller_type": sorted(fact["sst"].dropna().unique().tolist()),
        "acquisition_channel": sorted(fact["acq"].dropna().unique().tolist()),
        "buyer_type": sorted(fact["bt"].dropna().unique().tolist()),
        "risk_tier": sorted(fact["rt"].dropna().unique().tolist()),
    }

    scenario_results = proc["scenario_results"].copy()
    scenario_assumptions = proc["scenario_assumptions"].copy()
    scenario_decision = proc["scenario_decision"].copy()

    payload = {
        "meta": {
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            "dashboard_version": DASHBOARD_VERSION,
            "coverage_start": str(fact["d"].min()),
            "coverage_end": str(fact["d"].max()),
            "orders": int(len(fact)),
            "source_orders": int(len(fact_all)),
            "is_sampled": bool(len(fact) < len(fact_all)),
            "sellers": int(seller_meta["sid"].nunique()),
            "buyers": int(raw["buyers"]["buyer_id"].nunique()),
            "official_dashboard_output": "outputs/dashboard/executive-marketplace-command-center.html",
            "official_kpi_source": str(official["source"]),
        },
        "filters": options,
        "orders": fact.to_dict(orient="records"),
        "seller_meta": seller_meta.to_dict(orient="records"),
        "official_kpis": official["metrics"],
        "scenarios": scenario_results.to_dict(orient="records"),
        "scenario_assumptions": scenario_assumptions.to_dict(orient="records"),
        "scenario_decision": scenario_decision.to_dict(orient="records"),
    }
    return payload


def _dashboard_html(data_json: str, plotly_js: str) -> str:
    template = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Marketplace Profitability, Fraud & Seller Quality Command Center</title>
  <style>
    :root {
      --bg-start: #ecf2fb;
      --bg-end: #f7f9fc;
      --top-shell-bg: rgba(247, 249, 252, 0.93);
      --panel: #ffffff;
      --panel-soft: #f8fbff;
      --ink: #0f172a;
      --muted: #52607a;
      --brand: #0b5ed7;
      --brand-soft: #e7f0ff;
      --brand-ink: #0b4db2;
      --good: #1a7f37;
      --warn: #b85e00;
      --bad: #b42318;
      --line: #d7deea;
      --line-soft: #eaf0f8;
      --table-head: #f4f7fc;
      --table-row-hover: #f6faff;
      --narrative-bg: #f7faff;
      --narrative-line: #d7e3fa;
      --badge-good-bg: #eaf8ef;
      --badge-good-line: #bde3cb;
      --badge-warn-bg: #fff5e9;
      --badge-warn-line: #f0cf9f;
      --badge-bad-bg: #fff0f0;
      --badge-bad-line: #f5c2c2;
      --alert-warn-bg: #fff8ea;
      --alert-warn-line: #f5d29c;
      --alert-bad-bg: #fff0f0;
      --alert-bad-line: #f5c2c2;
      --alert-info-bg: #edf5ff;
      --alert-info-line: #c6ddff;
      --shadow: 0 10px 26px rgba(15, 23, 42, 0.08);
      --radius: 14px;
      --axis: #51617a;
      --grid: #d9e1ee;
      --hover-bg: #12274a;
      --hover-ink: #ffffff;
    }
    body[data-theme="dark"] {
      --bg-start: #0f1722;
      --bg-end: #0b1119;
      --top-shell-bg: rgba(12, 18, 28, 0.92);
      --panel: #121b29;
      --panel-soft: #162233;
      --ink: #e5edf8;
      --muted: #9db0cb;
      --brand: #5aa0ff;
      --brand-soft: #182942;
      --brand-ink: #8cbaff;
      --line: #2a3a51;
      --line-soft: #223248;
      --table-head: #162233;
      --table-row-hover: #1a2a3f;
      --narrative-bg: #13233a;
      --narrative-line: #284666;
      --badge-good-bg: #183628;
      --badge-good-line: #24543a;
      --badge-warn-bg: #3b2b12;
      --badge-warn-line: #6d501f;
      --badge-bad-bg: #3b1f25;
      --badge-bad-line: #6a2c39;
      --alert-warn-bg: #332611;
      --alert-warn-line: #6d4f1d;
      --alert-bad-bg: #371d23;
      --alert-bad-line: #6d2f3b;
      --alert-info-bg: #182942;
      --alert-info-line: #2f4f79;
      --shadow: 0 12px 28px rgba(0, 0, 0, 0.34);
      --axis: #b6c7de;
      --grid: #2f425d;
      --hover-bg: #0d1522;
      --hover-ink: #e8eef7;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: linear-gradient(170deg, var(--bg-start) 0%, var(--bg-end) 100%);
      color: var(--ink);
      font-family: "IBM Plex Sans", "Source Sans 3", "Avenir Next", "Segoe UI", Arial, sans-serif;
      line-height: 1.45;
    }
    .top-shell {
      position: sticky;
      top: 0;
      z-index: 50;
      background: var(--top-shell-bg);
      backdrop-filter: blur(6px);
      border-bottom: 1px solid var(--line);
    }
    .header {
      max-width: 1680px;
      margin: 0 auto;
      padding: 16px 22px 12px 22px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      align-items: center;
    }
    .title h1 {
      margin: 0;
      font-size: 28px;
      letter-spacing: 0.1px;
      line-height: 1.2;
    }
    .title p {
      margin: 4px 0 0 0;
      color: var(--muted);
      font-size: 13px;
      max-width: 980px;
    }
    .header-meta {
      display: grid;
      justify-items: end;
      gap: 6px;
      color: var(--muted);
      font-size: 12px;
    }
    .actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    button, .btn {
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel);
      color: var(--ink);
      padding: 8px 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.12s ease-in-out;
    }
    button.primary {
      background: var(--brand);
      color: #f8fbff;
      border-color: var(--brand);
    }
    button.subtle {
      background: var(--panel-soft);
    }
    button:hover { filter: brightness(0.98); }
    .filter-bar {
      max-width: 1680px;
      margin: 0 auto;
      padding: 0 22px 16px 22px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
      gap: 10px;
      align-items: end;
    }
    .filter {
      display: grid;
      gap: 4px;
    }
    .filter label {
      font-size: 11px;
      color: var(--muted);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .filter input, .filter select {
      border: 1px solid var(--line);
      background: var(--panel);
      color: var(--ink);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 13px;
      min-height: 40px;
    }
    .filter-actions {
      grid-column: 1 / -1;
      display: flex;
      gap: 8px;
      justify-content: flex-end;
      flex-wrap: wrap;
    }
    .container {
      max-width: 1680px;
      margin: 18px auto 30px auto;
      padding: 0 22px 30px 22px;
    }
    .tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 14px;
    }
    .tab-btn {
      border-radius: 999px;
      padding: 8px 14px;
      background: var(--panel);
      border: 1px solid var(--line);
      font-size: 13px;
      color: var(--ink);
    }
    .tab-btn.active {
      background: var(--brand-soft);
      border-color: var(--brand);
      color: var(--brand-ink);
    }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    .hero-strip {
      margin: 0 0 12px 0;
      display: grid;
      grid-template-columns: 1.3fr 1fr;
      gap: 10px;
    }
    .hero-message {
      background: linear-gradient(135deg, var(--panel) 0%, var(--panel-soft) 100%);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 14px 16px;
      font-size: 14px;
      line-height: 1.55;
      color: var(--ink);
    }
    .signal-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
    }
    .signal-card {
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--panel);
      padding: 10px;
    }
    .signal-card .name {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--muted);
      font-weight: 700;
    }
    .signal-card .state {
      margin-top: 4px;
      font-size: 15px;
      font-weight: 700;
    }
    .signal-card .hint {
      margin-top: 3px;
      font-size: 11px;
      color: var(--muted);
    }
    .signal-card.good .state { color: var(--good); }
    .signal-card.warn .state { color: var(--warn); }
    .signal-card.bad .state { color: var(--bad); }
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }
    .kpi {
      background: var(--panel);
      border: 1px solid var(--line);
      border-top: 4px solid var(--brand);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 13px;
      min-height: 96px;
    }
    .kpi.good { border-top-color: var(--good); }
    .kpi.warn { border-top-color: var(--warn); }
    .kpi.bad { border-top-color: var(--bad); }
    .kpi .label {
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 700;
      letter-spacing: 0.4px;
    }
    .kpi .value {
      margin-top: 8px;
      font-size: 25px;
      font-weight: 700;
      letter-spacing: -0.2px;
    }
    .kpi .delta {
      margin-top: 4px;
      font-size: 12px;
      color: var(--muted);
    }
    .row {
      display: grid;
      gap: 12px;
      margin-bottom: 12px;
    }
    .row-2 { grid-template-columns: 1fr 1fr; }
    .row-3 { grid-template-columns: 1fr 1fr 1fr; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 14px;
    }
    .panel h3 {
      margin: 0 0 8px 0;
      font-size: 17px;
      line-height: 1.3;
    }
    .panel .sub {
      margin: 0 0 10px 0;
      color: var(--muted);
      font-size: 12px;
    }
    .plot {
      width: 100%;
      min-height: 340px;
      border-radius: 10px;
      overflow: hidden;
    }
    .plot.short { min-height: 280px; }
    .narrative {
      line-height: 1.6;
      color: var(--ink);
      font-size: 14px;
      background: var(--narrative-bg);
      border: 1px solid var(--narrative-line);
      border-radius: 12px;
      padding: 12px;
    }
    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    .badge {
      padding: 8px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid;
    }
    .badge.good { color: var(--good); background: var(--badge-good-bg); border-color: var(--badge-good-line); }
    .badge.warn { color: var(--warn); background: var(--badge-warn-bg); border-color: var(--badge-warn-line); }
    .badge.bad { color: var(--bad); background: var(--badge-bad-bg); border-color: var(--badge-bad-line); }
    .alert-list {
      display: grid;
      gap: 8px;
    }
    .alert {
      border-radius: 10px;
      padding: 10px;
      font-size: 13px;
      border: 1px solid;
    }
    .alert.warn { background: var(--alert-warn-bg); border-color: var(--alert-warn-line); }
    .alert.bad { background: var(--alert-bad-bg); border-color: var(--alert-bad-line); }
    .alert.info { background: var(--alert-info-bg); border-color: var(--alert-info-line); }
    .bench-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-top: 10px;
    }
    .bench {
      padding: 10px;
      border: 1px dashed var(--line);
      border-radius: 10px;
      background: var(--panel-soft);
    }
    .bench .name { font-size: 12px; color: var(--muted); }
    .bench .num { margin-top: 5px; font-size: 20px; font-weight: 700; }
    .table-tools {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
    }
    .table-tools input, .table-tools select {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 7px 10px;
      font-size: 13px;
      background: var(--panel);
      color: var(--ink);
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 12px;
    }
    thead th {
      text-align: left;
      border-bottom: 1px solid var(--line);
      padding: 9px 8px;
      color: var(--ink);
      cursor: pointer;
      user-select: none;
      background: var(--table-head);
      position: sticky;
      top: 0;
      z-index: 1;
    }
    tbody td {
      border-bottom: 1px solid var(--line-soft);
      padding: 8px;
      color: var(--ink);
    }
    tbody tr:hover { background: var(--table-row-hover); }
    .table-wrap {
      max-height: 420px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 10px;
    }
    .pager {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 8px;
      margin-top: 8px;
    }
    .scenario-cards {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 10px;
    }
    .scenario-card {
      padding: 10px;
      border-radius: 12px;
      border: 1px solid var(--line);
      background: var(--panel);
    }
    .scenario-card .name { font-size: 12px; color: var(--muted); }
    .scenario-card .main { margin-top: 4px; font-size: 21px; font-weight: 700; }
    .scenario-card .hint { margin-top: 4px; font-size: 12px; color: var(--muted); }
    .method-tab h4 {
      margin: 14px 0 6px 0;
    }
    .method-tab ul { margin: 0; padding-left: 20px; }
    .method-tab li { margin: 4px 0; }
    .drawer {
      position: fixed;
      right: -520px;
      top: 0;
      height: 100vh;
      width: 520px;
      background: var(--panel);
      border-left: 1px solid var(--line);
      box-shadow: -16px 0 32px rgba(0, 0, 0, 0.12);
      z-index: 80;
      transition: right 0.25s ease;
      display: grid;
      grid-template-rows: auto 1fr;
    }
    .drawer.open { right: 0; }
    .drawer header {
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .drawer .body {
      padding: 14px 16px;
      overflow: auto;
      font-size: 13px;
      line-height: 1.6;
      color: var(--ink);
    }
    .empty {
      min-height: 240px;
      display: grid;
      place-items: center;
      color: var(--muted);
      font-size: 13px;
      border: 1px dashed var(--line);
      border-radius: 12px;
      background: var(--panel-soft);
    }
    @media (max-width: 1280px) {
      .hero-strip { grid-template-columns: 1fr; }
      .signal-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .kpi-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .row-3 { grid-template-columns: 1fr; }
      .row-2 { grid-template-columns: 1fr; }
      .scenario-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 860px) {
      .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .filter-bar { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
      .signal-grid { grid-template-columns: 1fr; }
      .bench-grid { grid-template-columns: 1fr; }
      .drawer { width: 100vw; right: -100vw; }
    }
    @media print {
      :root {
        --panel: #ffffff;
        --panel-soft: #ffffff;
        --ink: #111827;
        --muted: #4b5563;
        --line: #d1d5db;
        --line-soft: #e5e7eb;
      }
      body {
        background: #ffffff;
        color: #111827;
      }
      .top-shell {
        position: static;
        border-bottom: none;
        background: #ffffff;
        backdrop-filter: none;
      }
      .tabs,
      .drawer,
      .actions button,
      #methodologyOpen,
      #themeToggle,
      #resetFiltersTop,
      #applyFilters,
      #resetFilters,
      .table-tools,
      .pager {
        display: none !important;
      }
      .filter-bar {
        grid-template-columns: repeat(3, minmax(0, 1fr));
        padding-bottom: 8px;
      }
      .filter input, .filter select {
        border: none;
        background: transparent;
        color: #111827;
        padding: 0;
        min-height: auto;
      }
      .container {
        max-width: none;
        margin: 0;
        padding: 0;
      }
      .tab-panel {
        display: block !important;
        page-break-before: always;
      }
      #tab-overview {
        page-break-before: auto;
      }
      .panel, .kpi, .scenario-card, .hero-message, .signal-card {
        box-shadow: none;
        break-inside: avoid;
      }
      .plot {
        min-height: 260px;
      }
      .table-wrap {
        max-height: none;
        overflow: visible;
      }
      thead th {
        position: static;
      }
      .row, .kpi-grid, .hero-strip, .signal-grid, .scenario-cards {
        gap: 8px;
      }
    }
  </style>
</head>
<body data-theme="light">
  <div class="top-shell">
    <div class="header">
      <div class="title">
        <h1>Marketplace Profitability, Fraud & Seller Quality Command Center</h1>
        <p>Executive control tower for marketplace health, margin protection, fraud exposure, and seller governance actions.</p>
      </div>
      <div class="header-meta">
        <div class="actions">
          <button id="themeToggle" class="subtle">Dark Mode</button>
          <button id="printDashboard" class="subtle">Print</button>
          <button id="methodologyOpen">Methodology</button>
          <button class="primary" id="resetFiltersTop">Reset Filters</button>
        </div>
      </div>
    </div>

    <div class="filter-bar">
      <div class="filter"><label for="fDateFrom">Date From</label><input id="fDateFrom" type="date"></div>
      <div class="filter"><label for="fDateTo">Date To</label><input id="fDateTo" type="date"></div>
      <div class="filter"><label for="fRegion">Region</label><select id="fRegion"></select></div>
      <div class="filter"><label for="fCategory">Category</label><select id="fCategory"></select></div>
      <div class="filter"><label for="fSellerTier">Seller Tier</label><select id="fSellerTier"></select></div>
      <div class="filter"><label for="fSellerType">Seller Type</label><select id="fSellerType"></select></div>
      <div class="filter"><label for="fAcquisition">Acquisition Channel</label><select id="fAcquisition"></select></div>
      <div class="filter"><label for="fBuyerType">Buyer Type</label><select id="fBuyerType"></select></div>
      <div class="filter"><label for="fRiskTier">Risk Tier</label><select id="fRiskTier"></select></div>
      <div class="filter-actions">
        <button id="applyFilters" class="primary">Apply Filters</button>
        <button id="resetFilters">Reset</button>
      </div>
    </div>
  </div>

  <main class="container">
    <div class="tabs">
      <button class="tab-btn active" data-tab="overview">Executive Overview</button>
      <button class="tab-btn" data-tab="profitability">Profitability</button>
      <button class="tab-btn" data-tab="risk">Risk & Fraud</button>
      <button class="tab-btn" data-tab="seller">Seller Quality</button>
      <button class="tab-btn" data-tab="ops">Operations & CX</button>
      <button class="tab-btn" data-tab="scenario">Scenario Center</button>
      <button class="tab-btn" data-tab="methodology">Methodology & Definitions</button>
    </div>
    <div class="hero-strip">
      <div class="hero-message" id="heroMessage"></div>
      <div class="signal-grid" id="signalCards"></div>
    </div>

    <section id="tab-overview" class="tab-panel active">
      <div class="kpi-grid" id="kpiGrid"></div>
      <div class="row row-2">
        <div class="panel">
          <h3>Executive Narrative: Growth Must Be Qualified by Risk and Economic Quality</h3>
          <p class="sub">Narrative updates with filters and compares selected scope to baseline performance.</p>
          <div class="narrative" id="executiveNarrative"></div>
          <div class="badges" id="healthBadges"></div>
          <div class="bench-grid" id="benchmarkCards"></div>
        </div>
        <div class="panel">
          <h3>Key Alerts: Immediate Leadership Attention Items</h3>
          <p class="sub">Threshold-based alerts surface leakage, fraud, and operational deterioration risk.</p>
          <div class="alert-list" id="alertsPanel"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Topline vs Quality-Adjusted Marketplace Value</h3>
          <p class="sub">GMV can expand while risk-adjusted value stagnates or deteriorates.</p>
          <div id="plotGrowthOverview" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Risk Leakage Bridge Shows Where Commission Economics Are Lost</h3>
          <p class="sub">Leakage decomposition helps leadership prioritize economic-control interventions.</p>
          <div id="plotWaterfallOverview" class="plot"></div>
        </div>
      </div>
    </section>

    <section id="tab-profitability" class="tab-panel">
      <div class="row row-2">
        <div class="panel">
          <h3>Topline Growth vs Risk-Adjusted Growth Divergence</h3>
          <p class="sub">When spread widens, apparent growth quality is deteriorating.</p>
          <div id="plotGrowth" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Net Value Depends on Subsidy Intensity in Key Periods</h3>
          <p class="sub">Subsidy share trend highlights policy-driven growth dependence.</p>
          <div id="plotNetSubsidy" class="plot"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Category Profitability Heatmap Surfaces Structural Margin Weakness</h3>
          <p class="sub">Persistent negative/weak zones indicate systemic economics issues.</p>
          <div id="plotCategoryHeatmap" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Leakage Bridge: Subsidy, Refund, Dispute, and Chargeback Erosion</h3>
          <p class="sub">Contribution margin proxy must be interpreted with leakage decomposition.</p>
          <div id="plotWaterfall" class="plot"></div>
        </div>
      </div>
    </section>

    <section id="tab-risk" class="tab-panel">
      <div class="row row-2">
        <div class="panel">
          <h3>Dispute and Chargeback Trends Show Periodic Risk Pressure Bursts</h3>
          <p class="sub">Monitoring trend co-movement helps separate fraud vs service-failure regimes.</p>
          <div id="plotRiskTrend" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Payment Risk Signals Correlate with Both Disputes and Chargebacks</h3>
          <p class="sub">Signals in the top-right quadrant deserve tighter controls and review friction.</p>
          <div id="plotDisputeChargeback" class="plot"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Suspicious Pattern Matrix Identifies High-Risk Channel/Payment Combinations</h3>
          <p class="sub">Hotspots reveal suspicious operational patterns hidden in aggregate rates.</p>
          <div id="plotSuspiciousMatrix" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Buyer and Order Risk Distributions Show Critical Tail Exposure</h3>
          <p class="sub">Critical tail management is central to fraud and dispute containment.</p>
          <div id="plotRiskDistribution" class="plot"></div>
        </div>
      </div>
    </section>

    <section id="tab-seller" class="tab-panel">
      <div class="row row-2">
        <div class="panel">
          <h3>Seller Quality Risk Distribution Is Right-Tailed and Governance-Relevant</h3>
          <p class="sub">High-quality concentration vs risky tail determines intervention burden.</p>
          <div id="plotSellerQualityDist" class="plot short"></div>
        </div>
        <div class="panel">
          <h3>Margin Fragility Distribution Highlights Economic Vulnerability in the Seller Base</h3>
          <p class="sub">Risk concentration in fragility scores points to margin governance priorities.</p>
          <div id="plotMarginFragilityDist" class="plot short"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Dispute Rate by Seller Volume Cohort Exposes High-Impact Defect Zones</h3>
          <p class="sub">Cohort benchmarking supports targeted account management interventions.</p>
          <div id="plotSellerCohort" class="plot short"></div>
        </div>
        <div class="panel">
          <h3>Seller Portfolio Matrix (Volume vs Quality) Prioritizes Governance Escalation</h3>
          <p class="sub">High-volume + weak quality sellers represent the most material downside risk.</p>
          <div id="plotSellerMatrix" class="plot"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Top Sellers by Governance Priority</h3>
          <p class="sub">Priority queue based on governance risk concentration and expected impact.</p>
          <div id="plotTopSellers" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Top Weak Sellers: Searchable, Sortable Drilldown Table</h3>
          <p class="sub">Use for execution tracking by risk, operations, and seller management teams.</p>
          <div class="table-tools">
            <input id="sellerSearch" type="text" placeholder="Search seller id">
            <select id="sellerRowsPerPage">
              <option value="20">20 rows</option>
              <option value="40">40 rows</option>
              <option value="60">60 rows</option>
            </select>
          </div>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th data-sort="sid">Seller</th>
                  <th data-sort="gvt">Gov Tier</th>
                  <th data-sort="gvs">Gov Score</th>
                  <th data-sort="sqs">Quality Score</th>
                  <th data-sort="gmv">GMV</th>
                  <th data-sort="orders">Orders</th>
                  <th data-sort="refund_rate">Refund Rate</th>
                  <th data-sort="dispute_rate">Dispute Rate</th>
                  <th data-sort="delay_rate">Delay Rate</th>
                  <th data-sort="ract">Recommended Action</th>
                </tr>
              </thead>
              <tbody id="sellerTableBody"></tbody>
            </table>
          </div>
          <div class="pager">
            <button id="sellerPrev">Prev</button>
            <span id="sellerPageInfo"></span>
            <button id="sellerNext">Next</button>
          </div>
        </div>
      </div>
    </section>

    <section id="tab-ops" class="tab-panel">
      <div class="row row-2">
        <div class="panel">
          <h3>Delivery Delay Increases Directly Elevate Refund Risk</h3>
          <p class="sub">Operational reliability is a direct economic lever, not only a service metric.</p>
          <div id="plotRefundDelay" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Operations Trend: Delay, Cancellation, and On-Time Performance</h3>
          <p class="sub">CX outcomes and margin leakage move together in weak operational periods.</p>
          <div id="plotOpsTrend" class="plot"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Dispute Rate Escalates in High-Delay Buckets</h3>
          <p class="sub">Dispute containment requires logistics enforcement in high-risk cohorts.</p>
          <div id="plotDisputeDelay" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Promo Dependency by Category Interacts with Operational Defects</h3>
          <p class="sub">Subsidized categories with weak operations create compounded margin pressure.</p>
          <div id="plotPromoCategory" class="plot"></div>
        </div>
      </div>
    </section>

    <section id="tab-scenario" class="tab-panel">
      <div class="scenario-cards" id="scenarioCards"></div>
      <div class="row row-2">
        <div class="panel">
          <h3>Scenario Trade-off Map: Growth vs Quality Discipline</h3>
          <p class="sub">Strategic choice should maximize protected margin and risk-adjusted value.</p>
          <div id="plotScenarioComparison" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Contribution Margin Protection by Scenario</h3>
          <p class="sub">Compares economic upside and downside risk exposure from intervention choices.</p>
          <div id="plotScenarioMargin" class="plot"></div>
        </div>
      </div>
      <div class="panel">
        <h3>Scenario Decision Recommendations</h3>
        <p class="sub">Decision matrix ranks strategic options by margin impact, leakage avoided, and quality-adjusted outcomes.</p>
        <div class="table-wrap" style="max-height:320px">
          <table>
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Priority Score</th>
                <th>GMV Delta</th>
                <th>Quality Delta</th>
                <th>CM Delta</th>
                <th>Leakage Avoided</th>
                <th>Recommended Action</th>
              </tr>
            </thead>
            <tbody id="scenarioDecisionBody"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section id="tab-methodology" class="tab-panel method-tab">
      <div class="panel">
        <h3>Methodology & Definitions: Transparent, Reproducible, and Decision-Oriented</h3>
        <p class="sub">This project intentionally uses interpretable metrics and scoring logic rather than opaque models.</p>
        <h4>Core Metric Definitions</h4>
        <ul>
          <li><b>GMV:</b> Sum of gross order value before post-order leakage impacts.</li>
          <li><b>Net Value:</b> Customer net paid amount after direct order-level discounts/subsidy effects.</li>
          <li><b>Take Rate:</b> Commission revenue divided by GMV.</li>
          <li><b>Contribution Margin Proxy:</b> Commission minus subsidy, refunds, disputes, and chargeback loss proxy.</li>
          <li><b>Risk-Adjusted GMV:</b> Net value adjusted for expected risk loss and defect exposure.</li>
          <li><b>Refund / Dispute / Chargeback Rates:</b> Outcome incidence-based risk diagnostics.</li>
        </ul>
        <h4>Score Definitions</h4>
        <ul>
          <li><b>seller_quality_score:</b> Service and defect risk for seller performance governance.</li>
          <li><b>order_risk_score:</b> Order-level risk routing index for fraud/dispute controls.</li>
          <li><b>fraud_exposure_score:</b> Seller-level fraud pressure concentration signal.</li>
          <li><b>margin_fragility_score:</b> Economic instability score driven by subsidy/leakage dependence.</li>
          <li><b>governance_priority_score:</b> Unified operating priority index for intervention sequencing.</li>
        </ul>
        <h4>Caveats and Validation</h4>
        <ul>
          <li>Results are synthetic but behaviorally realistic for strategic decision simulation.</li>
          <li>Rates and thresholds are diagnostic, not causal proof of fraud or misconduct.</li>
          <li>Scenario center is strategic what-if support, not a probabilistic forecast model.</li>
          <li>Validation checks include reconciliation, referential integrity, leakage coherence, and no-leakage feature design.</li>
        </ul>
      </div>
    </section>
  </main>

  <aside class="drawer" id="methodologyDrawer">
    <header>
      <strong>Methodology Quick Reference</strong>
      <button id="methodologyClose">Close</button>
    </header>
    <div class="body">
      <p><b>Purpose:</b> Provide a governance-grade operating view of marketplace growth quality, margin resilience, fraud exposure, and seller quality risk.</p>
      <p><b>Interpretation guardrail:</b> topline GMV is not sufficient; leadership decisions should use risk-adjusted value and leakage decomposition.</p>
      <p><b>Alert philosophy:</b> thresholds are intentionally conservative to bias toward early risk intervention in high-impact cohorts.</p>
      <p><b>Data coverage:</b> use filter scope indicators and empty states to avoid overgeneralizing narrow slices.</p>
      <p id="drawerCoverage"></p>
      <p><b>Use with governance routines:</b> weekly for risk operations and monthly for finance/marketplace leadership reviews.</p>
    </div>
  </aside>

  <script>
  __PLOTLY_JS__
  </script>
  <script>
  const EMBEDDED = __DATA_JSON__;

  const APP = {
    rows: EMBEDDED.orders,
    sellerMetaMap: new Map(EMBEDDED.seller_meta.map(s => [String(s.sid), s])),
    officialKpis: EMBEDDED.official_kpis || {},
    theme: 'light',
    scenarioRows: EMBEDDED.scenarios,
    scenarioDecision: EMBEDDED.scenario_decision,
    currentFiltered: [],
    currentSellerRows: [],
    sellerSort: { key: 'gvs', dir: 'desc' },
    sellerSearch: '',
    sellerPage: 1,
    sellerRowsPerPage: 20,
    baselineState: null,
    currentState: null,
  };

  function cssVar(name) {
    return getComputedStyle(document.body).getPropertyValue(name).trim();
  }

  function themeTokens() {
    return {
      panel: cssVar('--panel'),
      ink: cssVar('--ink'),
      axis: cssVar('--axis'),
      grid: cssVar('--grid'),
      hoverBg: cssVar('--hover-bg'),
      hoverInk: cssVar('--hover-ink'),
    };
  }

  function emptyLayout() {
    const t = themeTokens();
    return {
      margin: { l: 30, r: 20, t: 50, b: 40 },
      paper_bgcolor: t.panel,
      plot_bgcolor: t.panel,
      xaxis: { visible: false },
      yaxis: { visible: false },
      annotations: [{ text: 'No data available for selected filters', showarrow: false, font: { size: 13, color: t.axis } }]
    };
  }

  function baseLayout() {
    const t = themeTokens();
    return {
      paper_bgcolor: t.panel,
      plot_bgcolor: t.panel,
      margin: { l: 56, r: 22, t: 60, b: 74 },
      font: { family: 'IBM Plex Sans, Source Sans 3, Segoe UI, Arial, sans-serif', size: 13, color: t.ink },
      legend: { orientation: 'h', y: -0.32, x: 0, xanchor: 'left', font: { color: t.axis, size: 12 } },
      hoverlabel: { bgcolor: t.hoverBg, font: { color: t.hoverInk } }
    };
  }

  function themedLayout(layout) {
    const t = themeTokens();
    const merged = { ...baseLayout(), ...layout };
    const axisKeys = ['xaxis', 'xaxis2', 'xaxis3', 'yaxis', 'yaxis2', 'yaxis3'];
    for (const key of axisKeys) {
      if (!merged[key]) continue;
      merged[key] = {
        automargin: true,
        tickfont: { color: t.axis },
        titlefont: { color: t.axis },
        linecolor: t.grid,
        zerolinecolor: t.grid,
        gridcolor: t.grid,
        ...merged[key],
      };
    }
    if (merged.coloraxis && typeof merged.coloraxis === 'object') {
      merged.coloraxis = {
        ...merged.coloraxis,
        colorbar: {
          tickfont: { color: t.axis },
          title: merged.coloraxis.colorbar?.title || '',
          ...merged.coloraxis.colorbar,
        }
      };
    }
    if (Array.isArray(merged.annotations)) {
      merged.annotations = merged.annotations.map(a => ({ font: { color: t.axis }, ...a }));
    }
    return merged;
  }

  function preferredTheme() {
    const saved = window.localStorage.getItem('dashboard_theme');
    if (saved === 'light' || saved === 'dark') return saved;
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function applyTheme(theme, rerender = true) {
    const normalized = theme === 'dark' ? 'dark' : 'light';
    APP.theme = normalized;
    document.body.setAttribute('data-theme', normalized);
    window.localStorage.setItem('dashboard_theme', normalized);
    const button = document.getElementById('themeToggle');
    if (button) button.textContent = normalized === 'dark' ? 'Light Mode' : 'Dark Mode';
    if (rerender && APP.currentState) {
      renderAllCharts(APP.currentState);
      renderSellerConcentration(APP.currentState);
      renderScenarioCenter();
    }
  }

  function num(v) { return Number(v || 0); }
  function pct(v, d = 1) { return `${(num(v) * 100).toFixed(d)}%`; }
  function money(v) {
    const n = num(v);
    if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
    if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
    if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
    return `$${n.toFixed(0)}`;
  }
  function fixed(v, d = 1) { return Number(v || 0).toFixed(d); }
  function governedMetric(key, fallback = 0) {
    const has = Object.prototype.hasOwnProperty.call(APP.officialKpis, key);
    return has ? num(APP.officialKpis[key]) : num(fallback);
  }
  function tierClassFromSeverity(s) {
    if (s === 'good') return 'good';
    if (s === 'bad') return 'bad';
    return 'warn';
  }

  function sortByMonth(arr, key = 'm') {
    return arr.sort((a, b) => String(a[key]).localeCompare(String(b[key])));
  }

  function fillSelect(id, options) {
    const el = document.getElementById(id);
    el.innerHTML = '';
    const all = document.createElement('option');
    all.value = '__ALL__';
    all.textContent = 'All';
    el.appendChild(all);
    for (const opt of options) {
      const o = document.createElement('option');
      o.value = opt;
      o.textContent = opt;
      el.appendChild(o);
    }
  }

  function initializeFilters() {
    const f = EMBEDDED.filters;
    fillSelect('fRegion', f.region);
    fillSelect('fCategory', f.category);
    fillSelect('fSellerTier', f.seller_tier);
    fillSelect('fSellerType', f.seller_type);
    fillSelect('fAcquisition', f.acquisition_channel);
    fillSelect('fBuyerType', f.buyer_type);
    fillSelect('fRiskTier', f.risk_tier);

    const from = document.getElementById('fDateFrom');
    const to = document.getElementById('fDateTo');
    from.min = EMBEDDED.meta.coverage_start;
    from.max = EMBEDDED.meta.coverage_end;
    to.min = EMBEDDED.meta.coverage_start;
    to.max = EMBEDDED.meta.coverage_end;
    from.value = EMBEDDED.meta.coverage_start;
    to.value = EMBEDDED.meta.coverage_end;
  }

  function currentFilters() {
    return {
      dateFrom: document.getElementById('fDateFrom').value,
      dateTo: document.getElementById('fDateTo').value,
      region: document.getElementById('fRegion').value,
      category: document.getElementById('fCategory').value,
      sellerTier: document.getElementById('fSellerTier').value,
      sellerType: document.getElementById('fSellerType').value,
      acquisition: document.getElementById('fAcquisition').value,
      buyerType: document.getElementById('fBuyerType').value,
      riskTier: document.getElementById('fRiskTier').value
    };
  }

  function resetFilters() {
    initializeFilters();
    APP.sellerPage = 1;
    APP.sellerSearch = '';
    document.getElementById('sellerSearch').value = '';
    renderDashboard();
  }

  function applyFilterRow(r, f) {
    if (r.d < f.dateFrom || r.d > f.dateTo) return false;
    if (f.region !== '__ALL__' && r.reg !== f.region) return false;
    if (f.category !== '__ALL__' && r.cat !== f.category) return false;
    if (f.sellerTier !== '__ALL__' && r.st !== f.sellerTier) return false;
    if (f.sellerType !== '__ALL__' && r.sst !== f.sellerType) return false;
    if (f.acquisition !== '__ALL__' && r.acq !== f.acquisition) return false;
    if (f.buyerType !== '__ALL__' && r.bt !== f.buyerType) return false;
    if (f.riskTier !== '__ALL__' && r.rt !== f.riskTier) return false;
    return true;
  }

  function computeState(rows) {
    const month = new Map();
    const cat = new Map();
    const catMonth = new Map();
    const seller = new Map();
    const paySignal = new Map();
    const channelPay = new Map();
    const delayBucket = new Map();
    const riskTierCount = new Map();
    const buyerTierCount = new Map();

    let gmv = 0;
    let net = 0;
    let riskAdj = 0;
    let commission = 0;
    let subsidy = 0;
    let refund = 0;
    let dispute = 0;
    let chargebackLoss = 0;
    let margin = 0;
    let expectedMargin = 0;
    let refundOrders = 0;
    let disputeOrders = 0;
    let cancelOrders = 0;
    let onTimeEligible = 0;
    let onTimeCount = 0;
    let delaySum = 0;
    let delayEligible = 0;

    for (const r of rows) {
      const m = r.m;
      if (!month.has(m)) {
        month.set(m, { m, gmv: 0, net: 0, riskAdj: 0, commission: 0, subsidy: 0, refund: 0, dispute: 0, chargebackLoss: 0, margin: 0, orders: 0, disputesCount: 0, chargebacksCount: 0, cancels: 0, onTimeEligible: 0, onTimeCount: 0, delaySum: 0, delayEligible: 0 });
      }
      const mm = month.get(m);
      const cbLoss = r.cb ? num(r.nv) : 0;
      const hasRef = num(r.ref) > 0 ? 1 : 0;
      const hasDsp = num(r.dsp) > 0 ? 1 : 0;
      mm.gmv += num(r.gv);
      mm.net += num(r.nv);
      mm.riskAdj += num(r.rv);
      mm.commission += num(r.com);
      mm.subsidy += num(r.sub);
      mm.refund += num(r.ref);
      mm.dispute += num(r.dsp);
      mm.chargebackLoss += cbLoss;
      mm.margin += num(r.rcm);
      mm.orders += 1;
      mm.disputesCount += hasDsp;
      mm.chargebacksCount += num(r.cb);
      mm.cancels += num(r.can);
      if (r.ot !== null && r.ot !== undefined) {
        mm.onTimeEligible += 1;
        mm.onTimeCount += Number(r.ot);
      }
      if (num(r.dd) > 0) {
        mm.delaySum += num(r.dd);
        mm.delayEligible += 1;
      }

      gmv += num(r.gv);
      net += num(r.nv);
      riskAdj += num(r.rv);
      commission += num(r.com);
      subsidy += num(r.sub);
      refund += num(r.ref);
      dispute += num(r.dsp);
      chargebackLoss += cbLoss;
      margin += num(r.rcm);
      expectedMargin += num(r.mar);
      refundOrders += hasRef;
      disputeOrders += hasDsp;
      cancelOrders += num(r.can);
      if (r.ot !== null && r.ot !== undefined) {
        onTimeEligible += 1;
        onTimeCount += Number(r.ot);
      }
      if (num(r.dd) > 0) {
        delaySum += num(r.dd);
        delayEligible += 1;
      }

      if (!cat.has(r.cat)) {
        cat.set(r.cat, { category: r.cat, orders: 0, gmv: 0, net: 0, subsidy: 0, margin: 0, refundOrders: 0, disputeOrders: 0 });
      }
      const cc = cat.get(r.cat);
      cc.orders += 1;
      cc.gmv += num(r.gv);
      cc.net += num(r.nv);
      cc.subsidy += num(r.sub);
      cc.margin += num(r.rcm);
      cc.refundOrders += hasRef;
      cc.disputeOrders += hasDsp;

      const cmKey = `${r.m}|${r.cat}`;
      if (!catMonth.has(cmKey)) catMonth.set(cmKey, { month: r.m, category: r.cat, net: 0, margin: 0 });
      const cmm = catMonth.get(cmKey);
      cmm.net += num(r.nv);
      cmm.margin += num(r.rcm);

      const sid = String(r.sid);
      if (!seller.has(sid)) {
        const meta = APP.sellerMetaMap.get(sid) || {};
        seller.set(sid, {
          sid,
          gmv: 0,
          net: 0,
          orders: 0,
          refundOrders: 0,
          disputeOrders: 0,
          delayEligible: 0,
          delayCount: 0,
          cancelOrders: 0,
          sqs: num(meta.sqs),
          gvs: num(meta.gvs),
          gvt: meta.gvt || 'Unknown',
          mfs: num(meta.mfs),
          st: r.st,
          sst: r.sst,
          ract: meta.ract || 'monitor only'
        });
      }
      const ss = seller.get(sid);
      ss.gmv += num(r.gv);
      ss.net += num(r.nv);
      ss.orders += 1;
      ss.refundOrders += hasRef;
      ss.disputeOrders += hasDsp;
      if (num(r.dd) >= 2) ss.delayCount += 1;
      ss.delayEligible += 1;
      ss.cancelOrders += num(r.can);

      if (!paySignal.has(r.pr)) {
        paySignal.set(r.pr, { signal: r.pr, orders: 0, disputes: 0, chargebacks: 0 });
      }
      const ps = paySignal.get(r.pr);
      ps.orders += 1;
      ps.disputes += hasDsp;
      ps.chargebacks += num(r.cb);

      const cpKey = `${r.ch}|${r.pm}`;
      if (!channelPay.has(cpKey)) {
        channelPay.set(cpKey, { channel: r.ch, payment: r.pm, orders: 0, disputes: 0, chargebacks: 0 });
      }
      const cp = channelPay.get(cpKey);
      cp.orders += 1;
      cp.disputes += hasDsp;
      cp.chargebacks += num(r.cb);

      const db = Math.max(0, Math.min(10, Math.round(num(r.dd))));
      if (!delayBucket.has(db)) delayBucket.set(db, { bucket: db, orders: 0, refundOrders: 0, disputeOrders: 0 });
      const dd = delayBucket.get(db);
      dd.orders += 1;
      dd.refundOrders += hasRef;
      dd.disputeOrders += hasDsp;

      riskTierCount.set(r.rt, (riskTierCount.get(r.rt) || 0) + 1);

      let brTier = 'Low';
      const brs = num(r.brs);
      if (brs >= 75) brTier = 'Critical';
      else if (brs >= 55) brTier = 'High';
      else if (brs >= 30) brTier = 'Moderate';
      buyerTierCount.set(brTier, (buyerTierCount.get(brTier) || 0) + 1);
    }

    const orders = rows.length;
    const leakage = subsidy + refund + dispute + chargebackLoss;
    const takeRate = gmv ? commission / gmv : 0;
    const refundRate = orders ? refundOrders / orders : 0;
    const disputeRate = orders ? disputeOrders / orders : 0;
    const subsidyShare = gmv ? subsidy / gmv : 0;
    const onTimeRate = onTimeEligible ? onTimeCount / onTimeEligible : 0;
    const cancelRate = orders ? cancelOrders / orders : 0;
    const avgDelay = delayEligible ? delaySum / delayEligible : 0;

    const monthArr = sortByMonth(Array.from(month.values()));
    const categoryArr = Array.from(cat.values()).map(x => ({
      ...x,
      refundRate: x.orders ? x.refundOrders / x.orders : 0,
      disputeRate: x.orders ? x.disputeOrders / x.orders : 0,
      subsidyShare: x.gmv ? x.subsidy / x.gmv : 0,
      marginRate: x.net ? x.margin / x.net : 0,
    }));

    const catMonthArr = Array.from(catMonth.values()).map(x => ({
      ...x,
      marginRate: x.net ? x.margin / x.net : 0
    }));

    const sellerArr = Array.from(seller.values()).map(s => ({
      ...s,
      refund_rate: s.orders ? s.refundOrders / s.orders : 0,
      dispute_rate: s.orders ? s.disputeOrders / s.orders : 0,
      delay_rate: s.delayEligible ? s.delayCount / s.delayEligible : 0,
      cancel_rate: s.orders ? s.cancelOrders / s.orders : 0,
    }));

    sellerArr.sort((a, b) => b.gmv - a.gmv);
    sellerArr.forEach((s, i) => {
      const rankPct = (i + 1) / Math.max(1, sellerArr.length);
      s.cohort = rankPct <= 0.1 ? 'Top 10% GMV Sellers' : rankPct <= 0.5 ? 'Mid 40% GMV Sellers' : 'Long-Tail 50% Sellers';
    });
    const cohortMap = new Map();
    for (const s of sellerArr) {
      if (!cohortMap.has(s.cohort)) cohortMap.set(s.cohort, { cohort: s.cohort, orders: 0, disputes: 0 });
      const c = cohortMap.get(s.cohort);
      c.orders += s.orders;
      c.disputes += s.disputeOrders;
    }
    const sellerCohorts = Array.from(cohortMap.values()).map(c => ({ ...c, disputeRate: c.orders ? c.disputes / c.orders : 0 }));

    const concentration = [];
    let cumulative = 0;
    for (let i = 0; i < sellerArr.length; i++) {
      cumulative += sellerArr[i].gmv;
      concentration.push({
        sellerShare: (i + 1) / sellerArr.length,
        gmvShare: gmv ? cumulative / gmv : 0
      });
    }

    return {
      rows,
      kpi: {
        gmv, net, riskAdj, takeRate, margin, expectedMargin, refundRate, disputeRate, subsidyShare,
        criticalSellers: sellerArr.filter(s => s.gvt === 'Critical').length,
        orders
      },
      rates: { onTimeRate, cancelRate, avgDelay },
      leakage: { subsidy, refund, dispute, chargebackLoss, total: leakage, commission },
      monthArr,
      categoryArr,
      catMonthArr,
      sellerArr,
      sellerCohorts,
      concentration,
      paySignalArr: Array.from(paySignal.values()).map(x => ({
        ...x,
        disputeRate: x.orders ? x.disputes / x.orders : 0,
        chargebackRate: x.orders ? x.chargebacks / x.orders : 0
      })),
      channelPayArr: Array.from(channelPay.values()).map(x => ({
        ...x,
        suspiciousRate: x.orders ? (x.disputes + x.chargebacks) / x.orders : 0
      })),
      delayBucketArr: sortByMonth(Array.from(delayBucket.values()), 'bucket').map(x => ({
        ...x,
        refundRate: x.orders ? x.refundOrders / x.orders : 0,
        disputeRate: x.orders ? x.disputeOrders / x.orders : 0
      })),
      riskTierCount: Object.fromEntries(riskTierCount.entries()),
      buyerTierCount: Object.fromEntries(buyerTierCount.entries()),
    };
  }

  function buildKpiCards(state, baseline) {
    const k = state.kpi;
    const b = baseline.kpi;
    const official = {
      gmv: governedMetric('gmv', b.gmv),
      net: governedMetric('net_value', b.net),
      takeRate: governedMetric('take_rate', b.takeRate),
      margin: governedMetric('realized_contribution_margin_proxy', b.margin),
      refundRate: governedMetric('refund_rate', b.refundRate),
      disputeRate: governedMetric('dispute_rate', b.disputeRate),
      subsidyShare: governedMetric('subsidy_share', b.subsidyShare),
      riskAdj: governedMetric('risk_adjusted_value', b.riskAdj),
      criticalSellers: governedMetric('critical_sellers', b.criticalSellers),
    };
    const cards = [
      { label: 'GMV', value: money(official.gmv), delta: `Filtered scope ${money(k.gmv)} (${pct(k.gmv / (official.gmv || 1))} of official)`, tone: 'good' },
      { label: 'Net Value', value: money(official.net), delta: `Filtered scope ${money(k.net)} (${pct(k.net / (official.net || 1))} of official)`, tone: 'good' },
      { label: 'Take Rate', value: pct(official.takeRate), delta: `Filtered scope ${pct(k.takeRate)} (${((k.takeRate - official.takeRate) * 100).toFixed(2)}pp delta)`, tone: 'good' },
      { label: 'Contribution Margin Proxy', value: money(official.margin), delta: `Filtered scope ${money(k.margin)} (${money(k.margin - official.margin)} delta)`, tone: official.margin >= 0 ? 'good' : 'bad' },
      { label: 'Refund Rate', value: pct(official.refundRate), delta: `Filtered scope ${pct(k.refundRate)} (${((k.refundRate - official.refundRate) * 100).toFixed(2)}pp delta)`, tone: official.refundRate <= 0.12 ? 'good' : official.refundRate <= 0.17 ? 'warn' : 'bad' },
      { label: 'Dispute Rate', value: pct(official.disputeRate), delta: `Filtered scope ${pct(k.disputeRate)} (${((k.disputeRate - official.disputeRate) * 100).toFixed(2)}pp delta)`, tone: official.disputeRate <= 0.015 ? 'good' : official.disputeRate <= 0.03 ? 'warn' : 'bad' },
      { label: 'Subsidy Share', value: pct(official.subsidyShare), delta: `Filtered scope ${pct(k.subsidyShare)} (${((k.subsidyShare - official.subsidyShare) * 100).toFixed(2)}pp delta)`, tone: official.subsidyShare <= 0.03 ? 'good' : official.subsidyShare <= 0.05 ? 'warn' : 'bad' },
      { label: 'Risk-Adjusted GMV', value: money(official.riskAdj), delta: `Filtered scope ${money(k.riskAdj)} (${pct(k.riskAdj / (official.riskAdj || 1))} of official)`, tone: 'good' },
      { label: 'Critical Sellers', value: String(Math.round(official.criticalSellers)), delta: `${k.criticalSellers} critical sellers in active slice`, tone: official.criticalSellers <= 20 ? 'good' : official.criticalSellers <= 40 ? 'warn' : 'bad' },
    ];
    const grid = document.getElementById('kpiGrid');
    grid.innerHTML = cards.map(c => `<div class="kpi ${c.tone}"><div class="label">${c.label}</div><div class="value">${c.value}</div><div class="delta">${c.delta}</div></div>`).join('');
  }

  function renderHero(state, baseline) {
    const k = state.kpi;
    const qualRatio = k.net ? k.riskAdj / k.net : 0;
    const baseQual = baseline.kpi.net ? baseline.kpi.riskAdj / baseline.kpi.net : 0;
    const qualityDelta = (qualRatio - baseQual) * 100;
    const growthHealth = qualityDelta >= 1 ? 'good' : qualityDelta >= -0.3 ? 'warn' : 'bad';
    const marginHealth = k.margin >= 0 ? 'good' : 'bad';
    const riskHealth = k.disputeRate <= 0.015 ? 'good' : k.disputeRate <= 0.03 ? 'warn' : 'bad';

    const headline = `Decision signal: selected scope shows ${qualityDelta >= 0 ? 'improving' : 'deteriorating'} quality-adjusted growth (${qualityDelta.toFixed(2)}pp vs baseline). Prioritize ${marginHealth === 'bad' ? 'margin containment' : 'risk control'} and ${riskHealth === 'bad' ? 'dispute/chargeback actions' : 'operational discipline'} in current slice.`;
    document.getElementById('heroMessage').textContent = headline;

    const signals = [
      { name: 'Growth Quality', state: growthHealth === 'good' ? 'Healthy' : growthHealth === 'warn' ? 'Watchlist' : 'Fragile', hint: `${qualityDelta.toFixed(2)}pp vs baseline`, cls: growthHealth },
      { name: 'Margin Discipline', state: marginHealth === 'good' ? 'Stable' : 'At Risk', hint: `Realized CM ${money(k.margin)}`, cls: marginHealth },
      { name: 'Fraud Pressure', state: riskHealth === 'good' ? 'Contained' : riskHealth === 'warn' ? 'Elevated' : 'Severe', hint: `Dispute rate ${pct(k.disputeRate)}`, cls: riskHealth },
    ];
    document.getElementById('signalCards').innerHTML = signals.map(s => `
      <div class="signal-card ${s.cls}">
        <div class="name">${s.name}</div>
        <div class="state">${s.state}</div>
        <div class="hint">${s.hint}</div>
      </div>
    `).join('');
  }

  function renderNarrativeAndAlerts(state, baseline) {
    const k = state.kpi;
    const qualRatio = k.net ? k.riskAdj / k.net : 0;
    const baseQual = baseline.kpi.net ? baseline.kpi.riskAdj / baseline.kpi.net : 0;
    const qualityDelta = (qualRatio - baseQual) * 100;
    const cmStatus = k.margin >= 0 ? 'positive' : 'negative';
    const narrative = `Selected scope includes ${k.orders.toLocaleString()} orders. GMV is ${money(k.gmv)} and risk-adjusted value is ${money(k.riskAdj)} (${pct(qualRatio)} of net value). Realized contribution margin proxy is ${cmStatus} at ${money(k.margin)}. Refund and dispute rates are ${pct(k.refundRate)} and ${pct(k.disputeRate)} respectively, while subsidy share is ${pct(k.subsidyShare)}. Quality-adjusted ratio moved ${qualityDelta.toFixed(2)}pp versus baseline scope, indicating ${qualityDelta >= 0 ? 'improving' : 'deteriorating'} growth quality.`;
    document.getElementById('executiveNarrative').textContent = narrative;

    const badges = [];
    badges.push({ text: `Growth Quality: ${qualRatio >= baseQual + 0.01 ? 'Healthy' : qualRatio >= baseQual - 0.005 ? 'Watch' : 'Fragile'}`, severity: qualRatio >= baseQual + 0.01 ? 'good' : qualRatio >= baseQual - 0.005 ? 'warn' : 'bad' });
    badges.push({ text: `Margin Discipline: ${k.margin >= 0 ? 'Stable' : 'At Risk'}`, severity: k.margin >= 0 ? 'good' : 'bad' });
    const fraudWarn = Math.max(0.16, baseline.kpi.disputeRate + 0.01);
    const fraudBad = Math.max(0.20, baseline.kpi.disputeRate + 0.025);
    badges.push({ text: `Fraud Pressure: ${k.disputeRate <= fraudWarn ? 'Contained' : k.disputeRate <= fraudBad ? 'Elevated' : 'Severe'}`, severity: k.disputeRate <= fraudWarn ? 'good' : k.disputeRate <= fraudBad ? 'warn' : 'bad' });
    const opsGood = baseline.rates.onTimeRate + 0.02;
    const opsWarn = Math.max(0.0, baseline.rates.onTimeRate - 0.015);
    badges.push({ text: `Operational Reliability: ${state.rates.onTimeRate >= opsGood ? 'Strong' : state.rates.onTimeRate >= opsWarn ? 'Unstable' : 'Weak'}`, severity: state.rates.onTimeRate >= opsGood ? 'good' : state.rates.onTimeRate >= opsWarn ? 'warn' : 'bad' });
    document.getElementById('healthBadges').innerHTML = badges.map(b => `<span class="badge ${tierClassFromSeverity(b.severity)}">${b.text}</span>`).join('');

    const alerts = [];
    if (k.disputeRate > fraudBad) alerts.push({ cls: 'bad', txt: `Dispute rate is elevated at ${pct(k.disputeRate)} and exceeds governance threshold.` });
    if (k.refundRate > Math.max(0.17, baseline.kpi.refundRate + 0.015)) alerts.push({ cls: 'warn', txt: `Refund rate at ${pct(k.refundRate)} indicates potential quality and CX deterioration.` });
    if (k.subsidyShare > Math.max(0.035, baseline.kpi.subsidyShare + 0.008)) alerts.push({ cls: 'warn', txt: `Subsidy share at ${pct(k.subsidyShare)} suggests margin dependence on promotions.` });
    if (state.rates.onTimeRate < Math.max(0.0, baseline.rates.onTimeRate - 0.03)) alerts.push({ cls: 'bad', txt: `On-time fulfillment is ${pct(state.rates.onTimeRate)}; operations SLA risk likely contributes to leakage.` });
    if (k.criticalSellers > 40) alerts.push({ cls: 'info', txt: `${k.criticalSellers} critical sellers in filtered scope require active governance routing.` });
    if (!alerts.length) alerts.push({ cls: 'info', txt: 'No acute threshold breaches detected for current slice. Continue monitoring.' });
    document.getElementById('alertsPanel').innerHTML = alerts.map(a => `<div class="alert ${a.cls}">${a.txt}</div>`).join('');

    const bench = [
      { name: 'CM Rate Benchmark', num: `${((k.margin / (k.net || 1) - baseline.kpi.margin / (baseline.kpi.net || 1)) * 100).toFixed(2)}pp` },
      { name: 'Expected vs Realized CM Gap', num: money(k.expectedMargin - k.margin) },
      { name: 'Refund Rate Benchmark', num: `${((k.refundRate - baseline.kpi.refundRate) * 100).toFixed(2)}pp` },
      { name: 'Quality Ratio Benchmark', num: `${qualityDelta.toFixed(2)}pp` },
    ];
    document.getElementById('benchmarkCards').innerHTML = bench.map(b => `<div class="bench"><div class="name">${b.name}</div><div class="num">${b.num}</div></div>`).join('');
  }

  function plotOrEmpty(divId, traces, layout, hasData = true) {
    if (!hasData) {
      Plotly.react(divId, [], emptyLayout());
      return;
    }
    Plotly.react(divId, traces, themedLayout(layout), { displayModeBar: false, responsive: true });
  }

  function renderGrowth(state, divId) {
    const m = state.monthArr;
    plotOrEmpty(divId, [
      { x: m.map(x => x.m), y: m.map(x => x.gmv), mode: 'lines+markers', name: 'GMV', line: { color: '#1f77b4', width: 3 } },
      { x: m.map(x => x.m), y: m.map(x => x.riskAdj), mode: 'lines+markers', name: 'Risk-Adjusted GMV', line: { color: '#d62728', width: 3 } }
    ], {
      yaxis: { title: 'Value ($)' },
      xaxis: { title: 'Month', tickangle: -35 },
      title: { text: 'GMV Growth Outpaces Risk-Adjusted Value in Volatile Periods', font: { size: 15 } }
    }, m.length > 0);
  }

  function renderWaterfall(state, divId) {
    const l = state.leakage;
    const measures = ['relative', 'relative', 'relative', 'relative', 'relative', 'total'];
    const x = ['Commission', 'Subsidy', 'Refunds', 'Disputes', 'Chargeback Loss', 'Contribution Margin'];
    const y = [l.commission, -l.subsidy, -l.refund, -l.dispute, -l.chargebackLoss, 0];
    plotOrEmpty(divId, [{
      type: 'waterfall',
      measure: measures,
      x,
      y,
      connector: { line: { color: '#95a4bf' } },
      increasing: { marker: { color: '#1a7f37' } },
      decreasing: { marker: { color: '#b42318' } },
      totals: { marker: { color: '#0b5ed7' } }
    }], {
      yaxis: { title: 'Value ($)' },
      title: { text: 'Leakage Components Explain Contribution Margin Outcome', font: { size: 15 } }
    }, state.kpi.orders > 0);
  }

  function renderNetSubsidy(state) {
    const m = state.monthArr;
    plotOrEmpty('plotNetSubsidy', [
      { x: m.map(x => x.m), y: m.map(x => x.net), type: 'bar', name: 'Net Value', marker: { color: '#4878d0' } },
      { x: m.map(x => x.m), y: m.map(x => (x.gmv ? x.subsidy / x.gmv : 0) * 100), type: 'scatter', mode: 'lines+markers', name: 'Subsidy Share (%)', yaxis: 'y2', line: { color: '#b42318', width: 2.5 } }
    ], {
      yaxis: { title: 'Net Value ($)' },
      yaxis2: { title: 'Subsidy Share (%)', overlaying: 'y', side: 'right' },
      xaxis: { tickangle: -35 },
      title: { text: 'Net Value Expansion Frequently Requires Subsidy Support', font: { size: 15 } }
    }, m.length > 0);
  }

  function renderCategoryHeatmap(state) {
    const rows = state.catMonthArr;
    const categories = [...new Set(rows.map(r => r.category))].sort();
    const months = [...new Set(rows.map(r => r.month))].sort();
    if (!rows.length) { plotOrEmpty('plotCategoryHeatmap', [], {}, false); return; }
    const z = categories.map(c => months.map(m => {
      const hit = rows.find(r => r.category === c && r.month === m);
      return hit ? hit.marginRate : null;
    }));
    plotOrEmpty('plotCategoryHeatmap', [{
      type: 'heatmap',
      x: months,
      y: categories,
      z,
      colorscale: 'RdYlGn',
      zmid: 0,
      colorbar: { title: 'Margin Rate' }
    }], {
      title: { text: 'Category-Month Margin Quality Is Uneven and Persistent', font: { size: 15 } },
      xaxis: { tickangle: -35 },
      yaxis: { automargin: true }
    }, true);
  }

  function renderRiskTrend(state) {
    const m = state.monthArr;
    plotOrEmpty('plotRiskTrend', [
      { x: m.map(x => x.m), y: m.map(x => x.orders ? x.disputesCount / x.orders : 0), mode: 'lines+markers', name: 'Dispute Rate', line: { width: 3, color: '#d62728' } },
      { x: m.map(x => x.m), y: m.map(x => x.orders ? x.chargebacksCount / x.orders : 0), mode: 'lines+markers', name: 'Chargeback Rate', line: { width: 3, color: '#ff7f0e' } }
    ], {
      title: { text: 'Dispute and Chargeback Rates Co-Move in Risk Bursts', font: { size: 15 } },
      yaxis: { title: 'Rate' },
      xaxis: { tickangle: -35 }
    }, m.length > 0);
  }

  function renderDisputeChargebackScatter(state) {
    const arr = state.paySignalArr;
    plotOrEmpty('plotDisputeChargeback', [{
      x: arr.map(x => x.chargebackRate),
      y: arr.map(x => x.disputeRate),
      text: arr.map(x => `${x.signal}<br>Orders: ${x.orders.toLocaleString()}`),
      mode: 'markers+text',
      textposition: 'top center',
      marker: {
        size: arr.map(x => 8 + Math.sqrt(x.orders) * 0.35),
        color: arr.map(x => x.orders),
        colorscale: 'YlOrRd',
        showscale: true,
        colorbar: { title: 'Orders' },
        line: { color: '#fff', width: 0.8 }
      },
      hovertemplate: '%{text}<br>Chargeback: %{x:.2%}<br>Dispute: %{y:.2%}<extra></extra>'
    }], {
      title: { text: 'Higher Payment-Risk Signals Cluster in Elevated Dispute/Chargeback Zone', font: { size: 15 } },
      xaxis: { title: 'Chargeback Rate', tickformat: '.1%' },
      yaxis: { title: 'Dispute Rate', tickformat: '.1%' }
    }, arr.length > 0);
  }

  function renderSuspiciousMatrix(state) {
    const arr = state.channelPayArr;
    if (!arr.length) { plotOrEmpty('plotSuspiciousMatrix', [], {}, false); return; }
    const channels = [...new Set(arr.map(x => x.channel))];
    const payments = [...new Set(arr.map(x => x.payment))];
    const z = channels.map(c => payments.map(p => {
      const hit = arr.find(x => x.channel === c && x.payment === p);
      return hit ? hit.suspiciousRate : null;
    }));
    plotOrEmpty('plotSuspiciousMatrix', [{
      type: 'heatmap',
      x: payments,
      y: channels,
      z,
      colorscale: 'YlOrRd',
      colorbar: { title: '(Disputes + Chargebacks) / Orders' }
    }], {
      title: { text: 'Suspicious Pattern Hotspots by Channel and Payment Method', font: { size: 15 } },
      xaxis: { tickangle: -30 },
      yaxis: { automargin: true }
    }, true);
  }

  function renderRiskDistribution(state) {
    const rt = state.riskTierCount;
    const bt = state.buyerTierCount;
    const orderTiers = ['Low', 'Moderate', 'High', 'Critical'];
    const buyerTiers = ['Low', 'Moderate', 'High', 'Critical'];
    plotOrEmpty('plotRiskDistribution', [
      { x: orderTiers, y: orderTiers.map(t => rt[t] || 0), type: 'bar', name: 'Order Risk Tier Count', marker: { color: '#4878d0' } },
      { x: buyerTiers, y: buyerTiers.map(t => bt[t] || 0), type: 'bar', name: 'Buyer Risk Tier Count', marker: { color: '#54a24b' } }
    ], {
      barmode: 'group',
      title: { text: 'Critical Risk Tail Exists in Both Buyer and Order Distributions', font: { size: 15 } },
      yaxis: { title: 'Count' }
    }, state.kpi.orders > 0);
  }

  function renderSellerQuality(state) {
    const sellers = state.sellerArr;
    plotOrEmpty('plotSellerQualityDist', [{
      type: 'histogram',
      x: sellers.map(s => s.sqs),
      nbinsx: 30,
      marker: { color: '#4878d0' },
      name: 'Seller Quality Score'
    }], {
      title: { text: 'Seller Quality Score Tail Drives Governance Workload', font: { size: 15 } },
      xaxis: { title: 'Seller Quality Score (Higher = Riskier)' },
      yaxis: { title: 'Seller Count' }
    }, sellers.length > 0);

    plotOrEmpty('plotMarginFragilityDist', [{
      type: 'histogram',
      x: sellers.map(s => s.mfs),
      nbinsx: 30,
      marker: { color: '#f58518' },
      name: 'Margin Fragility'
    }], {
      title: { text: 'Margin Fragility Concentration Indicates Structural Economic Risk', font: { size: 15 } },
      xaxis: { title: 'Margin Fragility Score' },
      yaxis: { title: 'Seller Count' }
    }, sellers.length > 0);
  }

  function renderSellerCohort(state) {
    const c = state.sellerCohorts.sort((a, b) => b.disputeRate - a.disputeRate);
    plotOrEmpty('plotSellerCohort', [{
      type: 'bar',
      x: c.map(x => x.cohort),
      y: c.map(x => x.disputeRate),
      marker: { color: '#da7c30' },
      hovertemplate: '%{x}<br>Dispute rate: %{y:.2%}<extra></extra>'
    }], {
      title: { text: 'Dispute Burden Persists Across Seller Volume Cohorts', font: { size: 15 } },
      yaxis: { title: 'Dispute Rate', tickformat: '.1%' }
    }, c.length > 0);
  }

  function renderSellerMatrix(state) {
    const s = state.sellerArr;
    const tiers = ['Low', 'Moderate', 'High', 'Critical'];
    const colors = { Low: '#9ecae1', Moderate: '#6baed6', High: '#3182bd', Critical: '#08519c' };
    const traces = tiers.map(t => {
      const d = s.filter(x => x.gvt === t);
      return {
        x: d.map(x => x.gmv),
        y: d.map(x => x.sqs),
        mode: 'markers',
        type: 'scatter',
        name: t,
        text: d.map(x => `Seller ${x.sid}<br>GMV: ${money(x.gmv)}<br>Quality: ${fixed(x.sqs,1)}<br>Gov: ${fixed(x.gvs,1)}`),
        marker: { size: d.map(x => 8 + Math.sqrt(x.orders) * 0.4), color: colors[t], opacity: 0.68, line: { color: '#fff', width: 0.7 } },
        hovertemplate: '%{text}<extra></extra>'
      };
    });
    plotOrEmpty('plotSellerMatrix', traces, {
      title: { text: 'High-Volume, Weak-Quality Sellers Form the Primary Governance Risk Quadrant', font: { size: 15 } },
      xaxis: { title: 'Seller GMV ($)', type: 'log' },
      yaxis: { title: 'Seller Quality Score' },
      shapes: [{ type: 'line', x0: 1, x1: Math.max(1, ...s.map(x => x.gmv)), y0: 55, y1: 55, line: { color: '#6b7d99', dash: 'dot' } }]
    }, s.length > 0);
  }

  function renderTopSellers(state) {
    const top = [...state.sellerArr].sort((a, b) => b.gvs - a.gvs).slice(0, 20).reverse();
    plotOrEmpty('plotTopSellers', [{
      type: 'bar',
      orientation: 'h',
      y: top.map(x => x.sid),
      x: top.map(x => x.gvs),
      marker: { color: top.map(x => x.gvt === 'Critical' ? '#08519c' : x.gvt === 'High' ? '#3182bd' : x.gvt === 'Moderate' ? '#6baed6' : '#9ecae1') },
      text: top.map(x => fixed(x.gvs, 1)),
      textposition: 'outside',
      cliponaxis: false,
      hovertemplate: 'Seller %{y}<br>Governance score: %{x:.1f}<extra></extra>'
    }], {
      title: { text: 'Top Governance Priority Sellers Concentrate Enterprise Risk', font: { size: 15 } },
      xaxis: { title: 'Governance Priority Score' },
      yaxis: { title: 'Seller ID' }
    }, top.length > 0);
  }

  function renderOpsCharts(state) {
    const delay = state.delayBucketArr;
    plotOrEmpty('plotRefundDelay', [{
      x: delay.map(x => x.bucket),
      y: delay.map(x => x.refundRate),
      mode: 'lines+markers',
      line: { color: '#c44e52', width: 3 },
      hovertemplate: 'Delay %{x} days<br>Refund rate: %{y:.2%}<extra></extra>'
    }], {
      title: { text: 'Refund Rates Increase as Delay Days Rise', font: { size: 15 } },
      xaxis: { title: 'Delay Days (bucketed)' },
      yaxis: { title: 'Refund Rate', tickformat: '.1%' }
    }, delay.length > 0);

    const m = state.monthArr;
    plotOrEmpty('plotOpsTrend', [
      { x: m.map(x => x.m), y: m.map(x => x.delayEligible ? x.delaySum / x.delayEligible : 0), mode: 'lines+markers', name: 'Avg Delay Days', yaxis: 'y1', line: { color: '#f58518', width: 2.6 } },
      { x: m.map(x => x.m), y: m.map(x => x.orders ? x.cancels / x.orders : 0), mode: 'lines+markers', name: 'Cancellation Rate', yaxis: 'y2', line: { color: '#e45756', width: 2.6 } },
      { x: m.map(x => x.m), y: m.map(x => x.onTimeEligible ? x.onTimeCount / x.onTimeEligible : 0), mode: 'lines+markers', name: 'On-Time Rate', yaxis: 'y2', line: { color: '#54a24b', width: 2.6 } }
    ], {
      title: { text: 'Operational Reliability Volatility Maps to Economic and CX Risk', font: { size: 15 } },
      xaxis: { tickangle: -35 },
      yaxis: { title: 'Average Delay Days' },
      yaxis2: { title: 'Rate', overlaying: 'y', side: 'right', tickformat: '.0%' }
    }, m.length > 0);

    plotOrEmpty('plotDisputeDelay', [{
      x: delay.map(x => x.bucket),
      y: delay.map(x => x.disputeRate),
      mode: 'lines+markers',
      line: { color: '#d62728', width: 3 },
      hovertemplate: 'Delay %{x} days<br>Dispute rate: %{y:.2%}<extra></extra>'
    }], {
      title: { text: 'Dispute Risk Escalates with Higher Delay Buckets', font: { size: 15 } },
      xaxis: { title: 'Delay Days (bucketed)' },
      yaxis: { title: 'Dispute Rate', tickformat: '.1%' }
    }, delay.length > 0);

    const cat = [...state.categoryArr].sort((a, b) => b.subsidyShare - a.subsidyShare);
    plotOrEmpty('plotPromoCategory', [{
      type: 'bar',
      orientation: 'h',
      y: cat.map(x => x.category),
      x: cat.map(x => x.subsidyShare),
      marker: { color: '#4c9f70' },
      hovertemplate: '%{y}<br>Promo dependency: %{x:.2%}<extra></extra>'
    }], {
      title: { text: 'Promo Dependency by Category Shows Margin Sensitivity Exposure', font: { size: 15 } },
      xaxis: { title: 'Subsidy Share of GMV', tickformat: '.1%' }
    }, cat.length > 0);
  }

  function renderSellerConcentration(state) {
    const c = state.concentration;
    plotOrEmpty('plotSellerConcentration', [
      { x: c.map(x => x.sellerShare), y: c.map(x => x.gmvShare), mode: 'lines', name: 'Observed', line: { color: '#1f77b4', width: 3 } },
      { x: [0, 1], y: [0, 1], mode: 'lines', name: 'Equality', line: { color: '#8fa3c3', dash: 'dash' } }
    ], {
      title: { text: 'Seller Concentration Curve Indicates Top-Seller Dependency Risk', font: { size: 15 } },
      xaxis: { title: 'Share of Sellers', tickformat: '.0%' },
      yaxis: { title: 'Cumulative GMV Share', tickformat: '.0%' }
    }, c.length > 0);
  }

  function renderScenarioCenter() {
    const s = APP.scenarioRows;
    const cardsEl = document.getElementById('scenarioCards');
    const priority = [...s].sort((a, b) => b.decision_priority_score - a.decision_priority_score);
    cardsEl.innerHTML = priority.slice(0, 4).map(r => `
      <div class="scenario-card">
        <div class="name">${r.scenario.replaceAll('_', ' ')}</div>
        <div class="main">${(r.decision_priority_score).toFixed(1)}</div>
        <div class="hint">priority score | leakage avoided ${money(r.leakage_avoided_vs_baseline)}</div>
      </div>
    `).join('');

    plotOrEmpty('plotScenarioComparison', [{
      x: s.map(r => r.gmv_change_vs_baseline_pct),
      y: s.map(r => r.quality_ratio_change_pp_vs_baseline),
      mode: 'markers',
      text: s.map(r => r.scenario),
      marker: {
        size: s.map(r => 18 + Math.abs(r.top_risk_seller_downside_exposure) / 200000),
        color: s.map(r => r.contribution_margin_change_vs_baseline),
        colorscale: 'RdYlGn',
        showscale: true,
        colorbar: { title: 'CM Delta' },
        line: { color: '#fff', width: 1 }
      },
      hovertemplate: '%{text}<br>GMV delta: %{x:.2f}%<br>Quality delta: %{y:.2f}pp<extra></extra>'
    }], {
      title: { text: 'Fraud and Quality Controls Improve Protected Economics with Limited GMV Drag', font: { size: 15 } },
      xaxis: { title: 'GMV Change vs Baseline (%)' },
      yaxis: { title: 'Quality Ratio Change (pp)' },
      shapes: [
        { type: 'line', x0: 0, x1: 0, y0: Math.min(...s.map(x => x.quality_ratio_change_pp_vs_baseline)) - 0.3, y1: Math.max(...s.map(x => x.quality_ratio_change_pp_vs_baseline)) + 0.3, line: { color: '#8ca0c2', dash: 'dot' } },
        { type: 'line', x0: Math.min(...s.map(x => x.gmv_change_vs_baseline_pct)) - 0.4, x1: Math.max(...s.map(x => x.gmv_change_vs_baseline_pct)) + 0.4, y0: 0, y1: 0, line: { color: '#8ca0c2', dash: 'dot' } }
      ]
    }, s.length > 0);

    const sorted = [...s].sort((a, b) => b.contribution_margin_change_vs_baseline - a.contribution_margin_change_vs_baseline);
    plotOrEmpty('plotScenarioMargin', [{
      type: 'bar',
      x: sorted.map(r => r.scenario),
      y: sorted.map(r => r.contribution_margin_change_vs_baseline),
      marker: { color: sorted.map(r => r.contribution_margin_change_vs_baseline >= 0 ? '#2ca02c' : '#d62728') },
      hovertemplate: '%{x}<br>CM Delta: %{y:$,.0f}<extra></extra>'
    }], {
      title: { text: 'Margin Protection Ranking Across Strategic Scenarios', font: { size: 15 } },
      yaxis: { title: 'Contribution Margin Change vs Baseline ($)' },
      xaxis: { tickangle: -30 }
    }, sorted.length > 0);

    const tbody = document.getElementById('scenarioDecisionBody');
    const decision = [...APP.scenarioDecision].sort((a, b) => b.decision_priority_score - a.decision_priority_score);
    tbody.innerHTML = decision.map(r => `
      <tr>
        <td>${r.scenario.replaceAll('_', ' ')}</td>
        <td>${fixed(r.decision_priority_score, 1)}</td>
        <td>${fixed(r.gmv_change_vs_baseline_pct, 2)}%</td>
        <td>${fixed(r.quality_ratio_change_pp_vs_baseline, 2)}pp</td>
        <td>${money(r.contribution_margin_change_vs_baseline)}</td>
        <td>${money(r.leakage_avoided_vs_baseline)}</td>
        <td>${r.recommended_decision}</td>
      </tr>
    `).join('');
  }

  function renderSellerTable(state) {
    let rows = [...state.sellerArr];
    if (APP.sellerSearch.trim()) {
      const q = APP.sellerSearch.trim().toLowerCase();
      rows = rows.filter(r => String(r.sid).toLowerCase().includes(q));
    }
    const key = APP.sellerSort.key;
    const dir = APP.sellerSort.dir === 'asc' ? 1 : -1;
    rows.sort((a, b) => {
      const va = a[key];
      const vb = b[key];
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir;
      return String(va).localeCompare(String(vb)) * dir;
    });
    APP.currentSellerRows = rows;

    const totalPages = Math.max(1, Math.ceil(rows.length / APP.sellerRowsPerPage));
    APP.sellerPage = Math.max(1, Math.min(APP.sellerPage, totalPages));
    const start = (APP.sellerPage - 1) * APP.sellerRowsPerPage;
    const end = start + APP.sellerRowsPerPage;
    const pageRows = rows.slice(start, end);

    const tbody = document.getElementById('sellerTableBody');
    if (!pageRows.length) {
      tbody.innerHTML = `<tr><td colspan="10">No sellers match current filters/search.</td></tr>`;
    } else {
      tbody.innerHTML = pageRows.map(r => `
        <tr>
          <td>${r.sid}</td>
          <td>${r.gvt}</td>
          <td>${fixed(r.gvs, 1)}</td>
          <td>${fixed(r.sqs, 1)}</td>
          <td>${money(r.gmv)}</td>
          <td>${r.orders.toLocaleString()}</td>
          <td>${pct(r.refund_rate)}</td>
          <td>${pct(r.dispute_rate)}</td>
          <td>${pct(r.delay_rate)}</td>
          <td>${r.ract}</td>
        </tr>
      `).join('');
    }
    document.getElementById('sellerPageInfo').textContent = `Page ${APP.sellerPage} / ${totalPages} (${rows.length.toLocaleString()} sellers)`;
  }

  function renderRiskAndProfitabilityMandatoryCharts(state) {
    const cat = [...state.categoryArr].sort((a, b) => b.refundRate - a.refundRate);
    plotOrEmpty('plotRefundByCategory', [{
      type: 'bar',
      orientation: 'h',
      y: cat.map(x => x.category),
      x: cat.map(x => x.refundRate),
      marker: { color: '#d66a6a' },
      hovertemplate: '%{y}<br>Refund rate: %{x:.2%}<extra></extra>'
    }], {
      title: { text: 'Refund Rate by Category Is Concentrated in High-Defect Segments', font: { size: 15 } },
      xaxis: { tickformat: '.1%', title: 'Refund Rate' }
    }, cat.length > 0);
  }

  function renderAllCharts(state) {
    renderGrowth(state, 'plotGrowthOverview');
    renderWaterfall(state, 'plotWaterfallOverview');
    renderGrowth(state, 'plotGrowth');
    renderNetSubsidy(state);
    renderCategoryHeatmap(state);
    renderWaterfall(state, 'plotWaterfall');
    renderRiskTrend(state);
    renderDisputeChargebackScatter(state);
    renderSuspiciousMatrix(state);
    renderRiskDistribution(state);
    renderSellerQuality(state);
    renderSellerCohort(state);
    renderSellerMatrix(state);
    renderTopSellers(state);
    renderOpsCharts(state);
    renderRiskAndProfitabilityMandatoryCharts(state);
  }

  function renderDashboard() {
    const filters = currentFilters();
    const rows = [];
    for (const r of APP.rows) {
      if (applyFilterRow(r, filters)) rows.push(r);
    }
    APP.currentFiltered = rows;
    const state = computeState(rows);
    APP.currentState = state;
    buildKpiCards(state, APP.baselineState);
    renderHero(state, APP.baselineState);
    renderNarrativeAndAlerts(state, APP.baselineState);
    renderAllCharts(state);
    renderSellerTable(state);
    renderSellerConcentration(state);
  }

  function setHeaderMeta() {
    const sampleSuffix = EMBEDDED.meta.is_sampled ? ` (sampled from ${EMBEDDED.meta.source_orders.toLocaleString()})` : '';
    const el = document.getElementById('drawerCoverage');
    if (el) el.textContent = `Current scope: ${EMBEDDED.meta.coverage_start} to ${EMBEDDED.meta.coverage_end}${sampleSuffix}.`;
  }

  function bindEvents() {
    document.getElementById('applyFilters').addEventListener('click', () => { APP.sellerPage = 1; renderDashboard(); });
    document.getElementById('resetFilters').addEventListener('click', resetFilters);
    document.getElementById('resetFiltersTop').addEventListener('click', resetFilters);
    document.getElementById('themeToggle').addEventListener('click', () => {
      applyTheme(APP.theme === 'dark' ? 'light' : 'dark', true);
    });
    document.getElementById('printDashboard').addEventListener('click', () => {
      window.print();
    });

    for (const id of ['fDateFrom','fDateTo','fRegion','fCategory','fSellerTier','fSellerType','fAcquisition','fBuyerType','fRiskTier']) {
      document.getElementById(id).addEventListener('change', () => {
        APP.sellerPage = 1;
        renderDashboard();
      });
    }

    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tab = btn.getAttribute('data-tab');
        document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
        document.getElementById(`tab-${tab}`).classList.add('active');
      });
    });

    document.getElementById('sellerSearch').addEventListener('input', (e) => {
      APP.sellerSearch = e.target.value;
      APP.sellerPage = 1;
      renderSellerTable(APP.currentState);
    });
    document.getElementById('sellerRowsPerPage').addEventListener('change', (e) => {
      APP.sellerRowsPerPage = Number(e.target.value);
      APP.sellerPage = 1;
      renderSellerTable(APP.currentState);
    });
    document.getElementById('sellerPrev').addEventListener('click', () => {
      APP.sellerPage = Math.max(1, APP.sellerPage - 1);
      renderSellerTable(APP.currentState);
    });
    document.getElementById('sellerNext').addEventListener('click', () => {
      APP.sellerPage += 1;
      renderSellerTable(APP.currentState);
    });

    document.querySelectorAll('#tab-seller thead th[data-sort]').forEach(th => {
      th.addEventListener('click', () => {
        const key = th.getAttribute('data-sort');
        if (APP.sellerSort.key === key) {
          APP.sellerSort.dir = APP.sellerSort.dir === 'asc' ? 'desc' : 'asc';
        } else {
          APP.sellerSort.key = key;
          APP.sellerSort.dir = key === 'sid' || key === 'gvt' || key === 'ract' ? 'asc' : 'desc';
        }
        APP.sellerPage = 1;
        renderSellerTable(APP.currentState);
      });
    });

    document.getElementById('methodologyOpen').addEventListener('click', () => {
      document.getElementById('methodologyDrawer').classList.add('open');
    });
    document.getElementById('methodologyClose').addEventListener('click', () => {
      document.getElementById('methodologyDrawer').classList.remove('open');
    });
  }

  function mountExtraMandatoryPanels() {
    const profitabilityPanel = document.getElementById('tab-profitability');

    const extraProfit = document.createElement('div');
    extraProfit.className = 'row row-2';
    extraProfit.innerHTML = `
      <div class="panel">
        <h3>Refund Rate by Category Highlights Value-Destructive Segments</h3>
        <p class="sub">Sorted view to prioritize quality and policy intervention.</p>
        <div id="plotRefundByCategory" class="plot"></div>
      </div>
      <div class="panel">
        <h3>Seller Concentration Risk Can Amplify Governance and Margin Shocks</h3>
        <p class="sub">Dependency on top sellers increases downside exposure concentration.</p>
        <div id="plotSellerConcentration" class="plot"></div>
      </div>
    `;
    profitabilityPanel.appendChild(extraProfit);
  }

  function init() {
    applyTheme(preferredTheme(), false);
    setHeaderMeta();
    initializeFilters();
    bindEvents();
    mountExtraMandatoryPanels();
    APP.baselineState = computeState(APP.rows);
    renderDashboard();
    renderScenarioCenter();
  }

  init();
  </script>
</body>
</html>
"""
    return template.replace("__DATA_JSON__", data_json).replace("__PLOTLY_JS__", plotly_js)


def build_dashboard(cfg: DashboardConfig) -> Path:
    payload = _build_payload(cfg)
    data_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
    plotly_js = get_plotlyjs()
    html = _dashboard_html(data_json=data_json, plotly_js=plotly_js)

    cfg.output_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.output_file.write_text(html, encoding="utf-8")
    return cfg.output_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Build self-contained executive marketplace HTML dashboard.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("outputs/dashboard/executive-marketplace-command-center.html"),
    )
    parser.add_argument("--max-orders", type=int, default=15000)
    parser.add_argument("--sample-seed", type=int, default=42)
    args = parser.parse_args()

    cfg = DashboardConfig(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        reports_dir=args.reports_dir,
        output_file=args.output_file,
        max_orders=args.max_orders,
        sample_seed=args.sample_seed,
    )
    out = build_dashboard(cfg)
    print(f"Executive dashboard generated: {out}")


if __name__ == "__main__":
    main()
