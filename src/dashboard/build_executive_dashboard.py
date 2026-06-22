from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

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


DASHBOARD_VERSION = "2026.06.06-public-release"


def _as_bool(value: object, default: bool = False) -> bool:
    if value is None or pd.isna(value):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def _json_safe(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if value is None:
        return None
    if pd.isna(value):
        return None
    return value


def _load_raw(raw_dir: Path) -> dict[str, pd.DataFrame]:
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


def _load_processed(processed_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "opf": pd.read_csv(processed_dir / "order_profitability_features.csv", parse_dates=["order_date"]),
        "order_risk": pd.read_csv(processed_dir / "order_risk_scores.csv", parse_dates=["order_date"]),
        "buyer_risk": pd.read_csv(processed_dir / "buyer_behavior_risk.csv"),
        "seller_scorecard": pd.read_csv(processed_dir / "seller_scorecard.csv"),
        "scenario_results": pd.read_csv(processed_dir / "scenario_results_summary.csv"),
        "scenario_assumptions": pd.read_csv(processed_dir / "scenario_assumptions.csv"),
        "scenario_decision": pd.read_csv(processed_dir / "scenario_decision_matrix.csv"),
        "recommended_policy": pd.read_csv(processed_dir / "backtesting_recommended_policy.csv"),
    }


def _load_official_kpis(reports_dir: Path) -> dict[str, object]:
    snap_path = reports_dir / "executive_kpi_snapshot.csv"
    if not snap_path.exists():
        return {"source": "fallback_missing_snapshot", "metrics": {}}

    snap = pd.read_csv(snap_path)
    if not {"metric", "value"}.issubset(snap.columns):
        return {"source": "fallback_invalid_snapshot_schema", "metrics": {}}

    metrics = {str(r["metric"]): float(r["value"]) for _, r in snap.iterrows() if pd.notna(r["value"])}
    return {"source": str(snap_path), "metrics": metrics}


def _load_validation_summary(reports_dir: Path) -> dict[str, object]:
    summary_path = reports_dir / "validation_summary.csv"
    release_path = reports_dir / "validation_release_assessment.csv"

    out: dict[str, object] = {
        "source": str(summary_path),
        "release_source": str(release_path),
        "release_state": "unknown",
        "publish_blocked": True,
        "critical_issues": None,
        "high_issues": None,
        "medium_issues": None,
        "low_issues": None,
        "committee_grade_ready": False,
        "public_release_ready": False,
        "rationale": "Validation summary not available.",
    }

    if summary_path.exists():
        summary = pd.read_csv(summary_path)
        if not summary.empty:
            row = summary.iloc[0].to_dict()
            out.update(
                {
                    "release_state": str(row.get("release_state", "unknown")),
                    "publish_blocked": _as_bool(row.get("publish_blocked", True), default=True),
                    "critical_issues": int(row.get("critical_issues", 0)),
                    "high_issues": int(row.get("high_issues", 0)),
                    "medium_issues": int(row.get("medium_issues", 0)),
                    "low_issues": int(row.get("low_issues", 0)),
                    "committee_grade_ready": _as_bool(row.get("committee_grade_ready", False), default=False),
                    "public_release_ready": _as_bool(row.get("public_release_ready", False), default=False),
                }
            )

    if release_path.exists():
        release = pd.read_csv(release_path)
        if not release.empty:
            row = release.iloc[0].to_dict()
            out.update(
                {
                    "rationale": str(row.get("rationale", out["rationale"])),
                    "public_release_ready": _as_bool(row.get("public_release_ready", False), default=False),
                }
            )
    return out


def _build_order_facts(raw: dict[str, pd.DataFrame], proc: dict[str, pd.DataFrame]) -> pd.DataFrame:
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


def _build_seller_meta(raw: dict[str, pd.DataFrame], proc: dict[str, pd.DataFrame]) -> pd.DataFrame:
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
    sampled_parts: list[pd.DataFrame] = []

    for _, grp in strata.groupby("_strata", sort=False):
        n = int(round(len(grp) * frac))
        n = max(1, min(len(grp), n))
        sampled_parts.append(grp.sample(n=n, random_state=sample_seed))

    sampled = pd.concat(sampled_parts, ignore_index=True)
    if len(sampled) > max_orders:
        sampled = sampled.sample(n=max_orders, random_state=sample_seed)

    return sampled.drop(columns=["_strata"]).sort_values(["m", "sid"]).reset_index(drop=True)


def _build_payload(cfg: DashboardConfig) -> dict[str, object]:
    raw = _load_raw(cfg.raw_dir)
    proc = _load_processed(cfg.processed_dir)
    official = _load_official_kpis(cfg.reports_dir)
    validation = _load_validation_summary(cfg.reports_dir)

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
            "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
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
        "validation": validation,
        "recommended_policy": proc["recommended_policy"].to_dict(orient="records"),
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
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-start: #f5f5f7;
      --bg-end: #f5f5f7;
      --top-shell-bg: rgba(255, 255, 255, 0.72);
      --top-shell-solid: #ffffff;
      --panel: #ffffff;
      --panel-soft: #f3f5f8;
      --panel-strong: #ffffff;
      --ink: #0a1628;
      --ink-2: #1d2b3e;
      --muted: #5c6b80;
      --muted-2: #8593a5;
      --brand: #5b54e0;
      --brand-soft: #eeedfd;
      --brand-ink: #4a43c9;
      --accent: #5b54e0;
      --good: #1f8a55;
      --warn: #b07407;
      --bad: #c5453b;
      --line: #e6e9ef;
      --line-strong: #d4dae3;
      --line-soft: #eef1f5;
      --table-head: #f6f8fa;
      --table-row-hover: #f6f6fe;
      --narrative-bg: #f8f9fb;
      --narrative-line: #e6e9ef;
      --badge-good-bg: #ecf6f0;
      --badge-good-line: #cbe6d6;
      --badge-warn-bg: #fbf3e4;
      --badge-warn-line: #ecd9b4;
      --badge-bad-bg: #fbecea;
      --badge-bad-line: #f0cfcb;
      --alert-warn-bg: #fbf3e4;
      --alert-warn-line: #ecd9b4;
      --alert-bad-bg: #fbecea;
      --alert-bad-line: #f0cfcb;
      --alert-info-bg: #f1f0fd;
      --alert-info-line: #ddd9f7;
      --shadow: 0 1px 2px rgba(10, 22, 40, 0.05), 0 8px 24px rgba(10, 22, 40, 0.045);
      --shadow-soft: 0 1px 2px rgba(10, 22, 40, 0.04);
      --radius: 16px;
      --radius-sm: 11px;
      --ease: cubic-bezier(0.4, 0, 0.2, 1);
      --axis: #6b7888;
      --grid: #eaedf2;
      --hover-bg: #0a1628;
      --hover-ink: #ffffff;
    }
    body[data-theme="dark"] {
      --bg-start: #0a0c10;
      --bg-end: #0a0c10;
      --top-shell-bg: rgba(16, 18, 24, 0.68);
      --top-shell-solid: #0e1117;
      --panel: #12151c;
      --panel-soft: #171b24;
      --panel-strong: #12151c;
      --ink: #edf0f5;
      --ink-2: #d6dbe4;
      --muted: #98a3b3;
      --muted-2: #6b7686;
      --brand: #8e88ff;
      --brand-soft: #1c1d2e;
      --brand-ink: #aaa4ff;
      --accent: #8e88ff;
      --good: #45c08a;
      --warn: #e0a544;
      --bad: #f0726b;
      --line: #222732;
      --line-strong: #2e374a;
      --line-soft: #1b2029;
      --table-head: #141821;
      --table-row-hover: #181a28;
      --narrative-bg: #141821;
      --narrative-line: #222732;
      --badge-good-bg: #102019;
      --badge-good-line: #1e3a2c;
      --badge-warn-bg: #221a0e;
      --badge-warn-line: #41331a;
      --badge-bad-bg: #241416;
      --badge-bad-line: #43262a;
      --alert-warn-bg: #221a0e;
      --alert-warn-line: #41331a;
      --alert-bad-bg: #241416;
      --alert-bad-line: #43262a;
      --alert-info-bg: #1a1b2b;
      --alert-info-line: #2c2d44;
      --shadow: 0 1px 2px rgba(0, 0, 0, 0.45), 0 8px 24px rgba(0, 0, 0, 0.35);
      --shadow-soft: 0 1px 2px rgba(0, 0, 0, 0.32);
      --axis: #8693a4;
      --grid: #20252f;
      --hover-bg: #20242e;
      --hover-ink: #edf0f5;
    }
    * { box-sizing: border-box; }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      padding: 0;
      margin: -1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
      border: 0;
    }
    body {
      margin: 0;
      background: var(--bg-start);
      color: var(--ink);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "SF Pro Display", "Helvetica Neue", "Geist", "Segoe UI", Arial, sans-serif;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
      -moz-osx-font-smoothing: grayscale;
      text-rendering: optimizeLegibility;
    }
    .mono, .value, .kpi .value, .decision-stat .value, .scenario-card .main, .bench .num {
      font-family: "Geist Mono", "SF Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
      font-feature-settings: "tnum" 1;
      font-variant-numeric: tabular-nums;
    }
    .skip-link {
      position: absolute;
      left: 16px;
      top: -48px;
      z-index: 100;
      background: var(--ink);
      color: var(--panel-strong);
      padding: 10px 12px;
      border-radius: 8px;
      font-weight: 700;
    }
    .skip-link:focus { top: 12px; }
    .top-shell {
      position: sticky;
      top: 0;
      z-index: 30;
      background: var(--top-shell-bg);
      -webkit-backdrop-filter: saturate(180%) blur(20px);
      backdrop-filter: saturate(180%) blur(20px);
      border-bottom: 1px solid var(--line);
    }
    @supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
      .top-shell { background: var(--top-shell-solid); }
    }
    .header {
      max-width: 1680px;
      margin: 0 auto;
      padding: 20px 28px 18px 28px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 18px;
      align-items: center;
    }
    .eyebrow {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      margin-bottom: 9px;
      font-size: 10.5px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 1.4px;
      color: var(--muted-2);
    }
    .title h1 {
      margin: 0;
      font-size: 20px;
      letter-spacing: -0.3px;
      line-height: 1.2;
      font-weight: 600;
      color: var(--ink);
      display: flex;
      align-items: flex-start;
      gap: 11px;
    }
    .title h1::before {
      content: "";
      width: 4px;
      height: 19px;
      border-radius: 3px;
      background: var(--accent);
      flex: 0 0 auto;
      margin-top: 2px;
    }
    .title p {
      margin: 6px 0 0 21px;
      color: var(--muted);
      font-size: 13px;
      max-width: 900px;
    }
    .header-meta {
      display: grid;
      justify-items: end;
      gap: 10px;
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
      border: 1px solid transparent;
      border-radius: 980px;
      background: var(--panel-soft);
      color: var(--ink-2);
      padding: 8px 15px;
      font-family: inherit;
      font-size: 13px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s var(--ease), border-color 0.2s var(--ease), color 0.2s var(--ease), transform 0.12s var(--ease);
      box-shadow: none;
    }
    button:active { transform: scale(0.97); }
    button.primary {
      background: var(--accent);
      color: #ffffff;
      border-color: var(--accent);
      font-weight: 600;
    }
    button.primary:hover { background: var(--brand-ink); border-color: var(--brand-ink); }
    button.subtle {
      background: transparent;
      color: var(--muted);
    }
    button:hover { background: var(--line); color: var(--ink); }
    button:focus-visible,
    input:focus-visible,
    select:focus-visible,
    .tab-btn:focus-visible,
    .sort-button:focus-visible,
    .skip-link:focus-visible {
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }
    .filter-shell {
      max-width: 1680px;
      margin: 0 auto;
      overflow: hidden;
      transition: max-height 0.25s ease, opacity 0.22s ease, transform 0.22s ease, margin-bottom 0.22s ease;
      max-height: 560px;
      opacity: 1;
      transform: translateY(0);
      margin-bottom: 0;
    }
    .filter-shell.collapsed {
      max-height: 0;
      opacity: 0;
      transform: translateY(-8px);
      margin-bottom: -2px;
      pointer-events: none;
    }
    .filter-bar {
      max-width: 1680px;
      margin: 0 auto;
      padding: 16px 18px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
      gap: 12px;
      align-items: end;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      box-shadow: var(--shadow-soft);
    }
    .filter {
      display: grid;
      gap: 4px;
      padding: 0;
      border-radius: 0;
      background: transparent;
      border: none;
      box-shadow: none;
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
      background: var(--panel-strong);
      color: var(--ink);
      border-radius: 8px;
      padding: 9px 11px;
      font-size: 13px;
      min-height: 40px;
    }
    .scope-bar {
      max-width: 1680px;
      margin: 0 auto;
      padding: 10px 6px 14px 6px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }
    .scope-chip {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 5px 10px;
      border-radius: 7px;
      background: var(--panel-soft);
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 11.5px;
      box-shadow: none;
    }
    .scope-chip strong {
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      font-size: 10px;
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
      margin: 16px auto 34px auto;
      padding: 0 24px 34px 24px;
    }
    .tabs {
      display: flex;
      flex-wrap: nowrap;
      gap: 2px;
      margin-bottom: 18px;
      padding: 0;
      border-radius: 0;
      background: transparent;
      border: none;
      border-bottom: 1px solid var(--line);
      box-shadow: none;
      width: 100%;
      max-width: 100%;
      overflow-x: auto;
      scrollbar-width: none;
    }
    .tabs::-webkit-scrollbar { display: none; }
    .tab-btn {
      flex: 0 0 auto;
      border-radius: 0;
      padding: 11px 14px;
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      font-size: 13px;
      font-weight: 500;
      color: var(--muted);
      box-shadow: none;
    }
    .tab-btn:hover {
      background: transparent;
      color: var(--ink);
      border-bottom-color: var(--line-strong, var(--line));
    }
    .tab-btn.active {
      background: transparent;
      border-bottom: 2px solid var(--accent);
      color: var(--ink);
      font-weight: 600;
      box-shadow: none;
    }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }
    .hero-strip {
      margin: 22px 0 18px 0;
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 28px;
      align-items: center;
    }
    .hero-message {
      background: transparent;
      border: none;
      border-radius: 0;
      box-shadow: none;
      padding: 0;
      font-size: 14px;
      line-height: 1.55;
      color: var(--ink);
    }
    .hero-message h2 {
      margin: 7px 0 0 0;
      font-size: 23px;
      line-height: 1.22;
      letter-spacing: -0.5px;
      font-weight: 600;
      max-width: 820px;
      color: var(--ink);
    }
    .hero-message p {
      margin: 8px 0 0 0;
      color: var(--muted);
      font-size: 13.5px;
      max-width: 780px;
    }
    .hero-side {
      display: grid;
      gap: 10px;
    }
    .decision-points {
      margin-top: 0;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .decision-point {
      padding: 15px 17px;
      border-radius: var(--radius-sm);
      background: var(--panel-soft);
      border: 1px solid var(--line);
    }
    .decision-point .name {
      font-size: 10.5px;
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.7px;
    }
    .decision-point .main {
      margin-top: 7px;
      font-size: 14px;
      font-weight: 500;
      line-height: 1.4;
      color: var(--ink);
    }
    .decision-board {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
    }
    .decision-stat {
      padding: 15px 17px;
      border-radius: var(--radius-sm);
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow-soft);
    }
    .decision-stat .name {
      font-size: 10.5px;
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.7px;
    }
    .decision-stat .value {
      margin-top: 8px;
      font-size: 22px;
      font-weight: 500;
      letter-spacing: -0.4px;
      color: var(--ink);
    }
    .decision-stat.good .value { color: var(--good); }
    .decision-stat.bad .value { color: var(--bad); }
    .decision-stat .hint {
      margin-top: 6px;
      color: var(--muted-2);
      font-size: 12px;
      line-height: 1.45;
    }
    .signal-grid {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .signal-card {
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--panel-strong);
      padding: 12px 15px;
      box-shadow: var(--shadow-soft);
      min-width: 136px;
      position: relative;
    }
    .signal-card::before {
      content: "";
      position: absolute;
      left: 13px;
      top: 14px;
      width: 6px;
      height: 6px;
      border-radius: 999px;
      background: var(--muted-2);
    }
    .signal-card.good::before { background: var(--good); }
    .signal-card.warn::before { background: var(--warn); }
    .signal-card.bad::before { background: var(--bad); }
    .signal-card .name {
      font-size: 10.5px;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: var(--muted);
      font-weight: 600;
      padding-left: 14px;
    }
    .signal-card .state {
      margin-top: 3px;
      font-size: 15px;
      font-weight: 600;
      letter-spacing: -0.2px;
    }
    .signal-card .hint {
      margin-top: 2px;
      font-size: 11px;
      color: var(--muted-2);
    }
    .signal-card.good .state { color: var(--good); }
    .signal-card.warn .state { color: var(--warn); }
    .signal-card.bad .state { color: var(--bad); }
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(7, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 0;
    }
    .kpi {
      grid-column: auto;
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 18px 18px 17px 18px;
      min-height: 120px;
      display: grid;
      align-content: start;
      gap: 7px;
      transition: transform 0.2s var(--ease), box-shadow 0.2s var(--ease);
    }
    .kpi.feature {
      grid-column: span 3;
    }
    .kpi-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }
    .kpi .label {
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      font-weight: 600;
      letter-spacing: 0.6px;
      min-height: 26px;
      line-height: 1.2;
    }
    .kpi .value {
      font-size: 32px;
      font-weight: 500;
      letter-spacing: -0.8px;
      line-height: 1.05;
      color: var(--ink);
    }
    .kpi.feature .value { font-size: 34px; }
    .kpi .delta {
      font-size: 12px;
      color: var(--muted);
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .kpi .delta .dir { font-weight: 600; }
    .kpi.good .delta .dir { color: var(--good); }
    .kpi.warn .delta .dir { color: var(--warn); }
    .kpi.bad .delta .dir { color: var(--bad); }
    .kpi .interpretation { display: none; }
    .kpi .context {
      font-size: 12px;
      color: var(--muted-2);
      font-weight: 400;
    }
    .tone-dot {
      width: 7px;
      height: 7px;
      border-radius: 999px;
      flex: 0 0 auto;
      background: var(--muted-2);
    }
    .kpi.good .tone-dot { background: var(--good); }
    .kpi.warn .tone-dot { background: var(--warn); }
    .kpi.bad .tone-dot { background: var(--bad); }
    .action-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
      margin-top: 10px;
    }
    .action-card {
      border: 1px solid var(--line);
      border-radius: var(--radius-sm);
      background: var(--panel-strong);
      padding: 15px 17px;
      box-shadow: var(--shadow-soft);
    }
    .action-card .name {
      font-size: 10.5px;
      color: var(--muted);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.7px;
      display: flex;
      align-items: center;
      gap: 7px;
    }
    .action-card .name::before {
      content: "";
      width: 6px;
      height: 6px;
      border-radius: 999px;
      background: var(--muted-2);
      flex: 0 0 auto;
    }
    .action-card.bad .name::before { background: var(--bad); }
    .action-card.warn .name::before { background: var(--warn); }
    .action-card.good .name::before { background: var(--good); }
    .action-card .main {
      margin-top: 8px;
      font-size: 14px;
      font-weight: 500;
      line-height: 1.4;
      color: var(--ink);
    }
    .action-card .hint {
      margin-top: 6px;
      font-size: 12px;
      color: var(--muted-2);
      line-height: 1.45;
    }
    .kpi-band {
      margin: 0 0 22px 0;
    }
    .row {
      display: grid;
      gap: 14px;
      margin-bottom: 14px;
      align-items: start;
    }
    .row-2 { grid-template-columns: 1fr 1fr; }
    .row-3 { grid-template-columns: 1fr 1fr 1fr; }
    .overview-decisions { grid-template-columns: 1.7fr 1fr; }
    .overview-decisions .action-grid { margin-top: 12px; }
    .overview-decisions .decision-board { grid-template-columns: 1fr; }
    .panel {
      background: var(--panel-strong);
      border: 1px solid var(--line);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      padding: 22px 24px;
    }
    .panel h3 {
      margin: 0 0 6px 0;
      font-size: 15px;
      font-weight: 600;
      line-height: 1.35;
      letter-spacing: -0.2px;
      color: var(--ink);
    }
    .panel .sub {
      margin: 0 0 14px 0;
      color: var(--muted);
      font-size: 12.5px;
      line-height: 1.45;
      max-width: 680px;
    }
    .plot {
      width: 100%;
      min-height: 338px;
      border-radius: 12px;
      overflow: hidden;
      border: 1px solid var(--line-soft);
      background: var(--panel-strong);
    }
    .plot.short { min-height: 270px; }
    .narrative {
      line-height: 1.6;
      color: var(--ink-2);
      font-size: 13.5px;
      background: var(--narrative-bg);
      border: 1px solid var(--narrative-line);
      border-radius: var(--radius-sm);
      padding: 16px 18px;
    }
    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    .badge {
      padding: 8px 10px;
      border-radius: 8px;
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
      border-radius: 8px;
      padding: 10px;
      font-size: 13px;
      border: 1px solid;
    }
    .alert.warn { background: var(--alert-warn-bg); border-color: var(--alert-warn-line); }
    .alert.bad { background: var(--alert-bad-bg); border-color: var(--alert-bad-line); }
    .alert.info { background: var(--alert-info-bg); border-color: var(--alert-info-line); }
    .alert-head {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 12.5px;
      font-weight: 600;
      color: var(--ink);
      margin-bottom: 10px;
    }
    .alert-head::before {
      content: "";
      width: 8px; height: 8px;
      border-radius: 999px;
      background: var(--muted-2);
    }
    .alert-head.good::before { background: var(--good); }
    .alert-head.bad::before { background: var(--bad); }
    .guard {
      display: grid;
      grid-template-columns: 1fr auto auto 56px;
      align-items: center;
      gap: 12px;
      padding: 11px 12px;
      border-bottom: 1px solid var(--line-soft);
    }
    .guard:last-child { border-bottom: 0; }
    .guard-label { font-size: 13px; color: var(--ink); }
    .guard-val { font-size: 13px; color: var(--ink); font-weight: 500; }
    .guard-limit { font-size: 12px; color: var(--muted-2); }
    .guard-state {
      justify-self: end;
      font-size: 11px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.4px;
      color: var(--good);
    }
    .guard.warn .guard-state, .guard.warn .guard-val { color: var(--warn); }
    .guard.bad .guard-state, .guard.bad .guard-val { color: var(--bad); }
    .bench-grid {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 8px;
      margin-top: 10px;
    }
    .bench {
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 9px;
      background: var(--panel-soft);
    }
    .bench .name { font-size: 11.5px; color: var(--muted); }
    .bench .num { margin-top: 6px; font-size: 19px; font-weight: 500; letter-spacing: -0.3px; color: var(--ink); }
    .bench-hint { margin-top: 3px; font-size: 11px; color: var(--muted-2); }
    .table-tools {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 8px;
    }
    .table-tools input, .table-tools select {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
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
      cursor: default;
      user-select: none;
      background: var(--table-head);
      position: sticky;
      top: 0;
      z-index: 1;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.35px;
    }
    .sort-button {
      border: 0;
      background: transparent;
      color: inherit;
      padding: 0;
      min-height: 24px;
      font: inherit;
      font-weight: inherit;
      text-transform: inherit;
      letter-spacing: inherit;
      cursor: pointer;
    }
    tbody td {
      border-bottom: 1px solid var(--line-soft);
      padding: 9px 8px;
      color: var(--ink);
      vertical-align: top;
    }
    tbody tr:nth-child(even) {
      background: rgba(245, 248, 252, 0.5);
    }
    tbody tr:hover { background: var(--table-row-hover); }
    .table-wrap {
      max-height: 420px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 10px;
      background: var(--panel-strong);
    }
    .table-pill {
      display: inline-flex;
      align-items: center;
      padding: 5px 8px;
      border-radius: 8px;
      font-size: 11px;
      font-weight: 700;
      border: 1px solid;
      white-space: nowrap;
    }
    .table-pill.good { color: var(--good); background: var(--badge-good-bg); border-color: var(--badge-good-line); }
    .table-pill.warn { color: var(--warn); background: var(--badge-warn-bg); border-color: var(--badge-warn-line); }
    .table-pill.bad { color: var(--bad); background: var(--badge-bad-bg); border-color: var(--badge-bad-line); }
    .action-text {
      font-size: 12px;
      line-height: 1.4;
      color: var(--muted);
      max-width: 250px;
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
      gap: 10px;
      margin-bottom: 12px;
    }
    .scenario-card {
      padding: 12px;
      border-radius: 8px;
      border: 1px solid var(--line);
      background: var(--panel-strong);
      box-shadow: var(--shadow-soft);
    }
    .scenario-card .name { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; }
    .scenario-card .main { margin-top: 6px; font-size: 22px; font-weight: 500; letter-spacing: -0.4px; color: var(--ink); }
    .scenario-card .hint { margin-top: 5px; font-size: 12px; color: var(--muted-2); }
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
      background: var(--panel-strong);
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
      border-radius: 8px;
      background: var(--panel-soft);
    }
    @media (max-width: 1280px) {
      .hero-strip { grid-template-columns: 1fr; }
      .decision-points,
      .decision-board,
      .action-grid { grid-template-columns: 1fr; }
      .signal-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); justify-content: stretch; }
      .kpi-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); }
      .kpi, .kpi.feature { grid-column: span 2; }
      .row-3 { grid-template-columns: 1fr; }
      .row-2 { grid-template-columns: 1fr; }
      .scenario-cards { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 860px) {
      .title h1 { font-size: 28px; }
      .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .kpi, .kpi.feature { grid-column: span 1; }
      .filter-bar { grid-template-columns: repeat(2, minmax(140px, 1fr)); }
      .header { grid-template-columns: 1fr; }
      .header-meta { justify-items: start; }
      .actions { justify-content: flex-start; }
      .signal-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); justify-content: stretch; }
      .bench-grid { grid-template-columns: 1fr; }
      .action-grid { grid-template-columns: 1fr; }
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
      .filter-shell {
        max-height: none !important;
        opacity: 1 !important;
        transform: none !important;
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
  <a class="skip-link" href="#mainContent">Skip to dashboard content</a>
  <div class="top-shell">
    <div class="header">
      <div class="title">
        <div class="eyebrow">Synthetic marketplace · decision support</div>
        <h1>Profitability, Fraud &amp; Seller Quality</h1>
        <p>Is GMV growth converting into protected, profitable value — and where should leadership intervene next?</p>
      </div>
      <div class="header-meta">
        <div class="actions">
          <button type="button" id="filtersToggle" class="subtle">Filters</button>
          <button type="button" id="themeToggle" class="subtle">Dark</button>
          <button type="button" id="printDashboard" class="subtle">Print</button>
          <button type="button" id="methodologyOpen" class="subtle">Methodology</button>
          <button type="button" id="resetFiltersTop">Reset</button>
        </div>
      </div>
    </div>

    <div class="filter-shell" id="filterShell">
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
          <button type="button" id="applyFilters" class="primary">Apply Filters</button>
          <button type="button" id="resetFilters">Reset</button>
        </div>
      </div>
    </div>
    <div class="scope-bar" id="scopeBar" aria-live="polite"></div>
  </div>

  <main class="container" id="mainContent">
    <div class="hero-strip">
      <div class="hero-message">
        <div class="eyebrow">Executive read</div>
        <h2 id="heroHeadline"></h2>
        <p id="heroMessage"></p>
      </div>
      <div class="hero-side">
        <div class="signal-grid" id="signalCards"></div>
      </div>
    </div>

    <section class="kpi-band" aria-label="Key performance indicators">
      <div class="kpi-grid" id="kpiGrid"></div>
    </section>

    <nav class="tabs" aria-label="Dashboard sections">
      <button type="button" class="tab-btn active" data-tab="overview" aria-pressed="true">Overview</button>
      <button type="button" class="tab-btn" data-tab="profitability" aria-pressed="false">Profitability</button>
      <button type="button" class="tab-btn" data-tab="risk" aria-pressed="false">Risk &amp; Fraud</button>
      <button type="button" class="tab-btn" data-tab="seller" aria-pressed="false">Seller Quality</button>
      <button type="button" class="tab-btn" data-tab="ops" aria-pressed="false">Operations &amp; CX</button>
      <button type="button" class="tab-btn" data-tab="scenario" aria-pressed="false">Scenarios</button>
      <button type="button" class="tab-btn" data-tab="methodology" aria-pressed="false">Methodology</button>
    </nav>

    <section id="tab-overview" class="tab-panel active">
      <div class="row row-2 overview-decisions">
        <div class="panel">
          <h3>What to do now</h3>
          <p class="sub">The immediate decision lens for the current scope, ahead of topline GMV.</p>
          <div class="decision-points" id="decisionPoints"></div>
          <div class="action-grid" id="actionQueue"></div>
        </div>
        <div class="panel">
          <h3>Trajectory</h3>
          <p class="sub">Recent-period momentum — or standing against the portfolio when a scope is filtered.</p>
          <div class="decision-board" id="decisionBoard"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Executive narrative</h3>
          <p class="sub">Plain-language read of the current scope and what is driving margin.</p>
          <div class="narrative" id="executiveNarrative"></div>
          <div class="bench-grid" id="benchmarkCards"></div>
        </div>
        <div class="panel">
          <h3>Alerts requiring attention</h3>
          <p class="sub">Threshold breaches across leakage, fraud, and operational reliability.</p>
          <div class="alert-list" id="alertsPanel"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Is topline growth converting into protected marketplace value?</h3>
          <p class="sub">Use to detect when GMV expansion is not translating into risk-adjusted value.</p>
          <div id="plotGrowthOverview" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Where is commission economics being lost?</h3>
          <p class="sub">Use to choose the largest controllable leakage pool first.</p>
          <div id="plotWaterfallOverview" class="plot"></div>
        </div>
      </div>
    </section>

    <section id="tab-profitability" class="tab-panel">
      <div class="row row-2">
        <div class="panel">
          <h3>When does apparent growth diverge from risk-adjusted growth?</h3>
          <p class="sub">Use to pause growth pushes in months where the spread widens.</p>
          <div id="plotGrowth" class="plot"></div>
        </div>
        <div class="panel">
          <h3>How much net value depends on subsidy intensity?</h3>
          <p class="sub">Use to tighten promo policy where subsidy share rises without protected value.</p>
          <div id="plotNetSubsidy" class="plot"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Which category-months show structural margin weakness?</h3>
          <p class="sub">Use to identify persistent value-destructive category patterns.</p>
          <div id="plotCategoryHeatmap" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Which leakage component is eroding contribution margin?</h3>
          <p class="sub">Use to separate price/promo leakage from fraud and service leakage.</p>
          <div id="plotWaterfall" class="plot"></div>
        </div>
      </div>
    </section>

    <section id="tab-risk" class="tab-panel">
      <div class="row row-2">
        <div class="panel">
          <h3>Are disputes and chargebacks entering a risk-pressure burst?</h3>
          <p class="sub">Use to detect co-movement before fraud losses become structural.</p>
          <div id="plotRiskTrend" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Which payment-risk signals deserve tighter review friction?</h3>
          <p class="sub">Use to prioritize top-right signal clusters for manual review or controls.</p>
          <div id="plotDisputeChargeback" class="plot"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Which channel and payment combinations form suspicious hotspots?</h3>
          <p class="sub">Use to route hotspot combinations to control policy experiments.</p>
          <div id="plotSuspiciousMatrix" class="plot"></div>
        </div>
        <div class="panel">
          <h3>How large is the buyer and order risk tail?</h3>
          <p class="sub">Use to size the operational burden of critical risk containment.</p>
          <div id="plotRiskDistribution" class="plot"></div>
        </div>
      </div>
    </section>

    <section id="tab-seller" class="tab-panel">
      <div class="row row-2">
        <div class="panel">
          <h3>How heavy is the seller quality risk tail?</h3>
          <p class="sub">Use to estimate coaching, audit, and enforcement workload.</p>
          <div id="plotSellerQualityDist" class="plot short"></div>
        </div>
        <div class="panel">
          <h3>Which sellers are economically fragile before growth is added?</h3>
          <p class="sub">Use to avoid scaling sellers that need subsidy or leakage containment first.</p>
          <div id="plotMarginFragilityDist" class="plot short"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Do high-volume sellers carry a disproportionate dispute burden?</h3>
          <p class="sub">Use to decide whether account management should target top sellers or the long tail.</p>
          <div id="plotSellerCohort" class="plot short"></div>
        </div>
        <div class="panel">
          <h3>Which sellers sit in the high-volume, weak-quality quadrant?</h3>
          <p class="sub">Use to prioritize escalations where operational impact is material.</p>
          <div id="plotSellerMatrix" class="plot"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Who is at the top of the seller governance queue?</h3>
          <p class="sub">Use to assign account-level actions by priority score and expected impact.</p>
          <div id="plotTopSellers" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Which weak sellers require an owner and next action?</h3>
          <p class="sub">Use for execution tracking by risk, operations, and seller management teams.</p>
          <div class="table-tools">
            <label class="sr-only" for="sellerSearch">Search sellers</label>
            <input id="sellerSearch" type="text" placeholder="Search seller id">
            <label class="sr-only" for="sellerRowsPerPage">Seller rows per page</label>
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
                  <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-sort="sid">Seller</button></th>
                  <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-sort="gvt">Gov Tier</button></th>
                  <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-sort="gvs">Gov Score</button></th>
                  <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-sort="sqs">Quality Score</button></th>
                  <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-sort="gmv">GMV</button></th>
                  <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-sort="orders">Orders</button></th>
                  <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-sort="refund_rate">Refund Rate</button></th>
                  <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-sort="dispute_rate">Dispute Rate</button></th>
                  <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-sort="delay_rate">Delay Rate</button></th>
                  <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-sort="ract">Recommended Action</button></th>
                </tr>
              </thead>
              <tbody id="sellerTableBody"></tbody>
            </table>
          </div>
          <div class="pager">
            <button type="button" id="sellerPrev">Prev</button>
            <span id="sellerPageInfo" aria-live="polite"></span>
            <button type="button" id="sellerNext">Next</button>
          </div>
        </div>
      </div>
    </section>

    <section id="tab-ops" class="tab-panel">
      <div class="row row-2">
        <div class="panel">
          <h3>How does refund rate vary with delivery delay?</h3>
          <p class="sub">Use to quantify the association between logistics reliability and margin leakage.</p>
          <div id="plotRefundDelay" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Are delay, cancellation, and on-time performance deteriorating together?</h3>
          <p class="sub">Use to identify periods where CX failure compounds margin leakage.</p>
          <div id="plotOpsTrend" class="plot"></div>
        </div>
      </div>
      <div class="row row-2">
        <div class="panel">
          <h3>Where does delay become a dispute-rate problem?</h3>
          <p class="sub">Use to set operational SLA thresholds for dispute containment.</p>
          <div id="plotDisputeDelay" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Which categories combine promo dependency with operational risk?</h3>
          <p class="sub">Use to avoid funding demand in defect-heavy categories.</p>
          <div id="plotPromoCategory" class="plot"></div>
        </div>
      </div>
    </section>

    <section id="tab-scenario" class="tab-panel">
      <div class="scenario-cards" id="scenarioCards"></div>
      <div class="row row-2">
        <div class="panel">
          <h3>Which scenario assumption produces the smallest growth trade-off?</h3>
          <p class="sub">Use to compare GMV drag against quality-ratio lift.</p>
          <div id="plotScenarioComparison" class="plot"></div>
        </div>
        <div class="panel">
          <h3>Which scenario assumption produces the largest contribution-margin improvement?</h3>
          <p class="sub">Use to rank interventions by expected CM improvement.</p>
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
                <th scope="col">Scenario</th>
                <th scope="col">Priority Score</th>
                <th scope="col">GMV Delta</th>
                <th scope="col">Quality Delta</th>
                <th scope="col">CM Delta</th>
                <th scope="col">Leakage Avoided</th>
                <th scope="col">Recommended Action</th>
              </tr>
            </thead>
            <tbody id="scenarioDecisionBody"></tbody>
          </table>
        </div>
      </div>
    </section>

    <section id="tab-methodology" class="tab-panel method-tab">
      <div class="panel">
        <h3>Methodology & Definitions</h3>
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
          <li>All results are synthetic and demonstrate the workflow, not real marketplace performance.</li>
          <li>Rates and thresholds are diagnostic, not causal proof of fraud or misconduct.</li>
          <li>Scenario center is strategic what-if support, not a probabilistic forecast model.</li>
          <li>Threshold policy results are retrospective and in-sample; validate on a later holdout period before deployment.</li>
          <li>Realized contribution margin and expected margin after risk are different proxies and should not be read as a calibrated forecast gap.</li>
          <li>Validation checks include reconciliation, referential integrity, leakage coherence, and no-leakage feature design.</li>
        </ul>
      </div>
    </section>
  </main>

  <aside class="drawer" id="methodologyDrawer" role="dialog" aria-modal="true" aria-hidden="true" aria-labelledby="methodologyDrawerTitle" inert>
    <header>
      <strong id="methodologyDrawerTitle">Methodology Quick Reference</strong>
      <button type="button" id="methodologyClose">Close</button>
    </header>
    <div class="body">
      <p><b>Purpose:</b> Demonstrate a reproducible decision-support workflow for marketplace growth quality, margin resilience, fraud exposure, and seller quality risk.</p>
      <p><b>Interpretation guardrail:</b> topline GMV is not sufficient; leadership decisions should use risk-adjusted value and leakage decomposition.</p>
      <p><b>Threshold policy:</b> the recommended review threshold is retrospective and in-sample; validate it on a later holdout period before deployment.</p>
      <p><b>Data coverage:</b> use filter scope indicators and empty states to avoid overgeneralizing narrow slices.</p>
      <p id="drawerCoverage"></p>
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
    validation: EMBEDDED.validation || {},
    policyRows: EMBEDDED.recommended_policy || [],
    theme: 'light',
    filtersOpen: false,
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
  let methodologyReturnFocus = null;

  function cssVar(name) {
    return getComputedStyle(document.body).getPropertyValue(name).trim();
  }

  function themeTokens() {
    return {
      panel: cssVar('--panel'),
      panelStrong: cssVar('--panel-strong'),
      ink: cssVar('--ink'),
      muted: cssVar('--muted'),
      axis: cssVar('--axis'),
      grid: cssVar('--grid'),
      hoverBg: cssVar('--hover-bg'),
      hoverInk: cssVar('--hover-ink'),
    };
  }

  function chartPalette() {
    const dark = APP.theme === 'dark';
    const accent = dark ? '#8e88ff' : '#5b54e0';
    const accentSoft = dark ? '#5b54e0' : '#b3afef';
    const steel = dark ? '#8693a4' : '#94a0b3';
    const ink = dark ? '#c6cdd9' : '#42506a';
    const good = dark ? '#45c08a' : '#1f8a55';
    const bad = dark ? '#f0726b' : '#c5453b';
    const warn = dark ? '#e0a544' : '#b07407';
    return {
      // semantic aliases kept for backward compatibility across chart functions
      blue: accent,
      blueSoft: accentSoft,
      navy: ink,
      green: good,
      teal: dark ? '#5fb0c4' : '#2f7d92',
      orange: warn,
      gold: warn,
      red: bad,
      rose: dark ? '#e08aa0' : '#c06478',
      neutral: steel,
      neutralDark: ink,
      accent, accentSoft, steel, ink, good, bad, warn,
    };
  }

  // Muted diverging scale (loss -> neutral -> profit) for margin-style heatmaps.
  function divergingScale() {
    const dark = APP.theme === 'dark';
    return dark
      ? [[0, '#b5524c'], [0.5, '#2a2f3a'], [1, '#3f9e74']]
      : [[0, '#c5453b'], [0.5, '#eef1f5'], [1, '#1f8a55']];
  }
  // Single-hue sequential (low -> high intensity) for risk hotspots.
  function sequentialScale() {
    const dark = APP.theme === 'dark';
    return dark
      ? [[0, '#1b2330'], [0.5, '#5b54e0'], [1, '#f0726b']]
      : [[0, '#eef0fb'], [0.5, '#9a93e8'], [1, '#c5453b']];
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
      margin: { l: 56, r: 20, t: 48, b: 84 },
      font: { family: 'Geist, -apple-system, BlinkMacSystemFont, Segoe UI, Arial, sans-serif', size: 12.5, color: t.ink },
      colorway: [t.axis, cssVar('--accent')],
      legend: {
        orientation: 'h',
        y: -0.24,
        x: 0,
        xanchor: 'left',
        font: { color: t.muted, size: 12 },
        bgcolor: 'rgba(0,0,0,0)',
      },
      title: { text: '', x: 0, xanchor: 'left', font: { size: 1, color: t.panel } },
      hoverlabel: {
        bgcolor: t.hoverBg,
        bordercolor: t.hoverBg,
        font: { color: t.hoverInk, family: 'Geist Mono, SF Mono, ui-monospace, monospace', size: 12 }
      }
    };
  }

  function themedLayout(layout) {
    const t = themeTokens();
    const merged = { ...baseLayout(), ...layout };
    if (merged.title && (merged.title.text || merged.title.text === '')) {
      const txt = merged.title.text;
      merged.title = {
        text: txt,
        x: 0,
        xanchor: 'left',
        y: 0.98,
        yanchor: 'top',
        font: { size: 13, color: t.muted, family: 'Geist, -apple-system, Segoe UI, Arial, sans-serif' },
        ...(typeof merged.title === 'object' ? {} : {}),
      };
      merged.title.text = txt;
      merged.title.font = { size: 13, color: t.muted, family: 'Geist, -apple-system, Segoe UI, Arial, sans-serif' };
    }
    const axisKeys = ['xaxis', 'xaxis2', 'xaxis3', 'yaxis', 'yaxis2', 'yaxis3'];
    for (const key of axisKeys) {
      if (!merged[key]) continue;
      const isX = key.startsWith('x');
      merged[key] = {
        automargin: true,
        tickfont: { color: t.axis, size: 11.5 },
        titlefont: { color: t.muted, size: 12 },
        linecolor: t.grid,
        zerolinecolor: t.grid,
        gridcolor: t.grid,
        showgrid: !isX,
        showline: false,
        ticks: '',
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

  function setFiltersOpen(open) {
    APP.filtersOpen = !!open;
    const shell = document.getElementById('filterShell');
    const button = document.getElementById('filtersToggle');
    if (shell) shell.classList.toggle('collapsed', !APP.filtersOpen);
    if (button) {
      button.textContent = APP.filtersOpen ? 'Hide Filters' : 'Show Filters';
      button.setAttribute('aria-expanded', APP.filtersOpen ? 'true' : 'false');
    }
  }

  function num(v) { return Number(v || 0); }
  function pct(v, d = 1) { return `${(num(v) * 100).toFixed(d)}%`; }
  const MINUS = '−';
  function money(v) {
    const n = num(v);
    const sign = n < 0 ? MINUS : '';
    const a = Math.abs(n);
    if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
    if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(2)}M`;
    if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(1)}K`;
    return `${sign}$${a.toFixed(0)}`;
  }
  function _signed(v, d, unit) {
    const r = Number(v.toFixed(d));
    const sign = r > 0 ? '+' : r < 0 ? MINUS : '';
    return `${sign}${Math.abs(r).toFixed(d)}${unit}`;
  }
  function ppSigned(v, d = 2) { return _signed(v, d, 'pp'); }
  function pctSigned(v, d = 1) { return _signed(v, d, '%'); }
  function fixed(v, d = 1) { return Number(v || 0).toFixed(d); }
  function cap(s) { const t = String(s || '').trim(); return t ? t.charAt(0).toUpperCase() + t.slice(1) : t; }
  function governedMetric(key, fallback = 0) {
    const has = Object.prototype.hasOwnProperty.call(APP.officialKpis, key);
    return has ? num(APP.officialKpis[key]) : num(fallback);
  }
  function tierClassFromSeverity(s) {
    if (s === 'good') return 'good';
    if (s === 'bad') return 'bad';
    return 'warn';
  }
  function tierClassFromRiskTier(tier) {
    if (tier === 'Low') return 'good';
    if (tier === 'Moderate') return 'warn';
    return 'bad';
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

  function scopeSummaryChips(filters, state) {
    const chips = [];
    chips.push(`<span class="scope-chip"><strong>Coverage</strong> ${filters.dateFrom} to ${filters.dateTo}</span>`);

    const dimensions = [
      ['Region', filters.region],
      ['Category', filters.category],
      ['Seller tier', filters.sellerTier],
      ['Seller type', filters.sellerType],
      ['Acquisition', filters.acquisition],
      ['Buyer type', filters.buyerType],
      ['Risk tier', filters.riskTier],
    ];
    for (const [label, value] of dimensions) {
      if (value !== '__ALL__') chips.push(`<span class="scope-chip"><strong>${label}</strong> ${value}</span>`);
    }

    chips.push(`<span class="scope-chip"><strong>Orders</strong> ${state.kpi.orders.toLocaleString()}</span>`);
    chips.push(`<span class="scope-chip"><strong>Sellers</strong> ${state.sellerArr.length.toLocaleString()}</span>`);
    return chips.join('');
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

  function isScopeFiltered() {
    const f = currentFilters();
    if (f.region !== '__ALL__' || f.category !== '__ALL__' || f.sellerTier !== '__ALL__' ||
        f.sellerType !== '__ALL__' || f.acquisition !== '__ALL__' || f.buyerType !== '__ALL__' ||
        f.riskTier !== '__ALL__') return true;
    if (f.dateFrom !== EMBEDDED.meta.coverage_start || f.dateTo !== EMBEDDED.meta.coverage_end) return true;
    return false;
  }

  function windowStats(months) {
    let gmv = 0, net = 0, riskAdj = 0, commission = 0, subsidy = 0, margin = 0, orders = 0, refundOrders = 0, disputesCount = 0;
    for (const x of months) {
      gmv += x.gmv; net += x.net; riskAdj += x.riskAdj; commission += x.commission;
      subsidy += x.subsidy; margin += x.margin; orders += x.orders;
      refundOrders += (x.refundOrders || 0); disputesCount += (x.disputesCount || 0);
    }
    return {
      gmv, net, riskAdj, margin, orders,
      takeRate: gmv ? commission / gmv : 0,
      refundRate: orders ? refundOrders / orders : 0,
      disputeRate: orders ? disputesCount / orders : 0,
      subsidyShare: gmv ? subsidy / gmv : 0,
      qualityRatio: net ? riskAdj / net : 0,
      cmRate: net ? margin / net : 0,
    };
  }

  // Period-over-period momentum within the current scope: most recent window vs the
  // window before it. This is the always-meaningful comparison shown by default, so the
  // dashboard never opens on dead "0.00pp vs baseline" values.
  function periodTrend(state) {
    const m = state.monthArr;
    if (m.length < 2) return null;
    const w = m.length >= 6 ? 3 : Math.max(1, Math.floor(m.length / 2));
    const recent = m.slice(-w);
    const prior = m.slice(-2 * w, -w);
    if (!prior.length) return null;
    const r = windowStats(recent), p = windowStats(prior);
    const ppl = (a, b) => (a - b) * 100;
    const chg = (a, b) => (b ? (a - b) / Math.abs(b) * 100 : 0);
    return {
      window: w,
      label: `vs prior ${w} mo`,
      takeRate: ppl(r.takeRate, p.takeRate),
      refundRate: ppl(r.refundRate, p.refundRate),
      disputeRate: ppl(r.disputeRate, p.disputeRate),
      subsidyShare: ppl(r.subsidyShare, p.subsidyShare),
      qualityRatio: ppl(r.qualityRatio, p.qualityRatio),
      cmRate: ppl(r.cmRate, p.cmRate),
      gmvPct: chg(r.gmv, p.gmv),
      riskAdjPct: chg(r.riskAdj, p.riskAdj),
      marginPct: chg(r.margin, p.margin),
      recent: r, prior: p,
    };
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
        month.set(m, { m, gmv: 0, net: 0, riskAdj: 0, commission: 0, subsidy: 0, refund: 0, dispute: 0, chargebackLoss: 0, margin: 0, orders: 0, refundOrders: 0, disputesCount: 0, chargebacksCount: 0, cancels: 0, onTimeEligible: 0, onTimeCount: 0, delaySum: 0, delayEligible: 0 });
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
      mm.refundOrders += hasRef;
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
      expectedMargin: governedMetric('expected_margin_after_risk', b.expectedMargin),
      refundRate: governedMetric('refund_rate', b.refundRate),
      disputeRate: governedMetric('dispute_rate', b.disputeRate),
      chargebackRate: governedMetric('chargeback_rate', 0),
      subsidyShare: governedMetric('subsidy_share', b.subsidyShare),
      riskAdj: governedMetric('risk_adjusted_value', b.riskAdj),
      criticalSellers: governedMetric('critical_sellers', b.criticalSellers),
    };
    const filtered = APP.filtered;
    const trend = APP.trend;
    const protectedShare = official.net ? official.riskAdj / official.net : 0;
    const sliceProtectedShare = k.net ? k.riskAdj / k.net : 0;
    const dispShare = filtered ? sliceProtectedShare : protectedShare;
    const dispCmRate = filtered ? (k.net ? k.margin / k.net : 0) : (official.net ? official.margin / official.net : 0);

    // Rate metrics: when a scope is filtered, compare it to the governed portfolio;
    // otherwise surface trailing-window momentum so the default view is never dead.
    const rateDelta = (scopeVal, portfolioVal, trendVal, goodIsDown) => {
      if (filtered) return `${ppSigned((scopeVal - portfolioVal) * 100)} vs portfolio`;
      if (trend) return `${ppSigned(trendVal)} ${trend.label}`;
      return goodIsDown ? 'Lower is better' : 'Higher is better';
    };

    const cards = [
      {
        label: 'GMV',
        value: filtered ? money(k.gmv) : money(official.gmv),
        delta: filtered
          ? `${pct(official.gmv ? k.gmv / official.gmv : 0)} of portfolio`
          : (trend ? `${pctSigned(trend.gmvPct)} ${trend.label}` : 'Full-period total'),
        context: `Gross merchandise value`,
        tone: 'flat',
      },
      {
        label: 'Protected Value',
        value: filtered ? money(k.riskAdj) : money(official.riskAdj),
        delta: `${pct(dispShare)} of net protected`,
        context: `Risk-adjusted GMV retained`,
        tone: dispShare >= 0.95 ? 'good' : dispShare >= 0.90 ? 'warn' : 'bad',
      },
      {
        label: 'Contribution Margin',
        value: filtered ? money(k.margin) : money(official.margin),
        delta: `CM rate ${pct(dispCmRate)}`,
        context: `Realized margin after risk`,
        tone: (filtered ? k.margin : official.margin) >= 0 ? 'good' : 'bad',
      },
      {
        label: 'Take Rate',
        value: pct(filtered ? k.takeRate : official.takeRate),
        delta: rateDelta(k.takeRate, official.takeRate, trend ? trend.takeRate : 0, false),
        context: `Commission yield on GMV`,
        tone: (filtered ? k.takeRate : official.takeRate) >= 0.10 ? 'good' : (filtered ? k.takeRate : official.takeRate) >= 0.08 ? 'warn' : 'bad',
      },
      {
        label: 'Refund Rate',
        value: pct(filtered ? k.refundRate : official.refundRate),
        delta: rateDelta(k.refundRate, official.refundRate, trend ? trend.refundRate : 0, true),
        context: `Orders refunded`,
        tone: (filtered ? k.refundRate : official.refundRate) <= 0.12 ? 'good' : (filtered ? k.refundRate : official.refundRate) <= 0.18 ? 'warn' : 'bad',
      },
      {
        label: 'Dispute Rate',
        value: pct(filtered ? k.disputeRate : official.disputeRate),
        delta: rateDelta(k.disputeRate, official.disputeRate, trend ? trend.disputeRate : 0, true),
        context: `Orders disputed`,
        tone: (filtered ? k.disputeRate : official.disputeRate) <= 0.10 ? 'good' : (filtered ? k.disputeRate : official.disputeRate) <= 0.15 ? 'warn' : 'bad',
      },
      {
        label: 'Subsidy Share',
        value: pct(filtered ? k.subsidyShare : official.subsidyShare),
        delta: rateDelta(k.subsidyShare, official.subsidyShare, trend ? trend.subsidyShare : 0, true),
        context: `GMV funded by promotions`,
        tone: (filtered ? k.subsidyShare : official.subsidyShare) <= 0.03 ? 'good' : (filtered ? k.subsidyShare : official.subsidyShare) <= 0.05 ? 'warn' : 'bad',
      },
    ];
    const grid = document.getElementById('kpiGrid');
    grid.innerHTML = cards.map(c => `
      <div class="kpi ${c.tone}">
        <div class="kpi-head">
          <div class="label">${c.label}</div>
          <span class="tone-dot"></span>
        </div>
        <div class="value">${c.value}</div>
        <div class="delta"><span class="dir">${c.delta}</span></div>
        <div class="context">${c.context}</div>
      </div>
    `).join('');
  }

  function renderHero(state, baseline) {
    const k = state.kpi;
    const filtered = APP.filtered;
    const trend = APP.trend;
    const qualRatio = k.net ? k.riskAdj / k.net : 0;
    const baseQual = baseline.kpi.net ? baseline.kpi.riskAdj / baseline.kpi.net : 0;
    // Quality movement: vs portfolio when a scope is filtered, otherwise trailing momentum.
    const qualityDelta = filtered ? (qualRatio - baseQual) * 100 : (trend ? trend.qualityRatio : 0);
    const cmpLabel = filtered ? 'vs the portfolio' : (trend ? `over the last ${trend.window} months` : 'across the full period');
    const growthHealth = qualityDelta >= 1 ? 'good' : qualityDelta >= -0.3 ? 'warn' : 'bad';
    const marginHealth = k.margin >= 0 ? 'good' : 'bad';
    const disputeWarn = baseline.kpi.disputeRate + 0.01;
    const disputeBad = baseline.kpi.disputeRate + 0.025;
    const riskHealth = k.disputeRate <= disputeWarn ? 'good' : k.disputeRate <= disputeBad ? 'warn' : 'bad';
    const opsGood = baseline.rates.onTimeRate + 0.02;
    const opsWarn = Math.max(0.0, baseline.rates.onTimeRate - 0.015);
    const opsHealth = state.rates.onTimeRate >= opsGood ? 'good' : state.rates.onTimeRate >= opsWarn ? 'warn' : 'bad';
    const worstIssue = marginHealth === 'bad' ? 'margin leakage' : riskHealth === 'bad' ? 'fraud and dispute pressure' : growthHealth === 'bad' ? 'fragile growth quality' : 'protecting current quality while scaling';
    const subject = filtered ? 'This scope is' : 'The marketplace is';
    const headline = `${subject} ${growthHealth === 'good' ? 'expanding with stronger economic quality' : growthHealth === 'warn' ? 'growing with mixed quality signals' : 'growing with deteriorating quality protection'}.`;
    const moveWord = qualityDelta >= 0.05 ? 'up' : qualityDelta <= -0.05 ? 'down' : 'flat';
    const moveClause = moveWord === 'flat'
      ? `Risk-adjusted value holds at ${pct(qualRatio)} of net ${cmpLabel}.`
      : `Risk-adjusted value sits at ${pct(qualRatio)} of net, ${moveWord} ${Math.abs(qualityDelta).toFixed(1)}pp ${cmpLabel}.`;
    const message = `${moveClause} The immediate lens is ${worstIssue}, not topline GMV alone.`;
    document.getElementById('heroHeadline').textContent = headline;
    document.getElementById('heroMessage').textContent = message;

    const decisionPoints = [
      {
        name: 'Primary action',
        main: marginHealth === 'bad' ? 'Contain leakage before funding more volume.' : riskHealth === 'bad' ? 'Tighten fraud and dispute controls in this slice.' : 'Protect current quality while scaling volume.',
      },
      {
        name: 'Main exposure',
        main: `Realized leakage stands at ${money(state.leakage.total)} across subsidy, refund, dispute, and chargeback loss.`,
      },
      {
        name: 'Operational read',
        main: `On-time performance is ${pct(state.rates.onTimeRate)} with average delay at ${fixed(state.rates.avgDelay, 1)} days.`,
      },
    ];
    document.getElementById('decisionPoints').innerHTML = decisionPoints.map(d => `
      <div class="decision-point">
        <div class="name">${d.name}</div>
        <div class="main">${d.main}</div>
      </div>
    `).join('');

    const policy = APP.policyRows[0] || {};
    const validation = APP.validation || {};
    const scenario = [...APP.scenarioDecision].sort((a, b) => b.decision_priority_score - a.decision_priority_score)[0] || {};
    const actionQueue = [
      {
        name: 'Decision 1',
        main: cap(scenario.recommended_decision) || 'Prioritize the highest protected-margin scenario.',
        hint: scenario.scenario ? `Top scenario: ${String(scenario.scenario).replaceAll('_', ' ')} | CM impact ${money(scenario.contribution_margin_change_vs_baseline)}` : 'Scenario decision matrix unavailable.',
        cls: 'good',
      },
      {
        name: 'Decision 2',
        main: cap(policy.policy_guidance) || 'Escalate high-risk orders to manual review.',
        hint: policy.recommended_threshold !== undefined ? `Retrospective threshold ${fixed(policy.recommended_threshold, 0)} | in-sample net benefit ${money(policy.net_benefit)}` : 'Policy simulation unavailable.',
        cls: 'warn',
      },
      {
        name: 'Validation scope',
        main: validation.publish_blocked ? 'Do not publish until validation blockers are cleared.' : 'Configured checks pass for public decision-support demonstration.',
        hint: `State: ${validation.release_state || 'unknown'} | critical ${validation.critical_issues ?? 'n/a'} | high ${validation.high_issues ?? 'n/a'}`,
        cls: validation.publish_blocked ? 'bad' : 'good',
      },
    ];
    document.getElementById('actionQueue').innerHTML = actionQueue.map(a => `
      <div class="action-card ${a.cls}">
        <div class="name">${a.name}</div>
        <div class="main">${a.main}</div>
        <div class="hint">${a.hint}</div>
      </div>
    `).join('');

    const qualHint = filtered ? `${ppSigned(qualityDelta, 1)} vs portfolio` : (trend ? `${ppSigned(qualityDelta, 1)} ${trend.label}` : `${pct(qualRatio)} of net`);
    const signals = [
      { name: 'Growth Quality', state: growthHealth === 'good' ? 'Healthy' : growthHealth === 'warn' ? 'Watchlist' : 'Fragile', hint: qualHint, cls: growthHealth },
      { name: 'Margin Discipline', state: marginHealth === 'good' ? 'Stable' : 'At Risk', hint: `Realized CM ${money(k.margin)}`, cls: marginHealth },
      { name: 'Fraud Pressure', state: riskHealth === 'good' ? 'Contained' : riskHealth === 'warn' ? 'Elevated' : 'Severe', hint: `Dispute rate ${pct(k.disputeRate)}`, cls: riskHealth },
      { name: 'Fulfillment', state: opsHealth === 'good' ? 'Reliable' : opsHealth === 'warn' ? 'Unstable' : 'Weak', hint: `On-time ${pct(state.rates.onTimeRate)}`, cls: opsHealth },
    ];
    document.getElementById('signalCards').innerHTML = signals.map(s => `
      <div class="signal-card ${s.cls}">
        <div class="name">${s.name}</div>
        <div class="state">${s.state}</div>
        <div class="hint">${s.hint}</div>
      </div>
    `).join('');

    const signedVal = (v, kind) => kind === 'pct' ? pctSigned(v) : ppSigned(v, 1);
    const toneOf = (v, goodIsUp) => (Math.abs(v) < 0.05 ? 'flat' : ((v >= 0) === goodIsUp ? 'good' : 'bad'));
    let board;
    if (filtered) {
      board = [
        { name: 'GMV vs portfolio', value: pct(baseline.kpi.gmv ? k.gmv / baseline.kpi.gmv : 0), hint: 'Share of marketplace GMV in this scope.', tone: 'flat' },
        { name: 'Quality vs portfolio', value: ppSigned((qualRatio - baseQual) * 100, 1), hint: 'Protected-value ratio against the full portfolio.', tone: toneOf((qualRatio - baseQual) * 100, true) },
        { name: 'CM rate vs portfolio', value: ppSigned(((k.net ? k.margin / k.net : 0) - (baseline.kpi.net ? baseline.kpi.margin / baseline.kpi.net : 0)) * 100, 1), hint: 'Contribution-margin rate against the portfolio.', tone: toneOf(((k.net ? k.margin / k.net : 0) - (baseline.kpi.net ? baseline.kpi.margin / baseline.kpi.net : 0)) * 100, true) },
      ];
    } else if (trend) {
      board = [
        { name: 'GMV momentum', value: signedVal(trend.gmvPct, 'pct'), hint: `Recent ${trend.window} months vs the prior ${trend.window}.`, tone: toneOf(trend.gmvPct, true) },
        { name: 'Protected-value momentum', value: signedVal(trend.riskAdjPct, 'pct'), hint: 'Risk-adjusted GMV trajectory.', tone: toneOf(trend.riskAdjPct, true) },
        { name: 'Quality-ratio shift', value: signedVal(trend.qualityRatio, 'pp'), hint: 'Protected share of net value, recent vs prior.', tone: toneOf(trend.qualityRatio, true) },
      ];
    } else {
      board = [
        { name: 'Protected share', value: pct(qualRatio), hint: 'Risk-adjusted value over net value.', tone: 'flat' },
        { name: 'Leakage load', value: money(state.leakage.total), hint: 'Subsidy, refund, dispute and chargeback erosion.', tone: 'flat' },
        { name: 'Realized CM', value: money(k.margin), hint: 'Contribution margin after risk.', tone: k.margin >= 0 ? 'good' : 'bad' },
      ];
    }
    document.getElementById('decisionBoard').innerHTML = board.map(d => `
      <div class="decision-stat ${d.tone || 'flat'}">
        <div class="name">${d.name}</div>
        <div class="value">${d.value}</div>
        <div class="hint">${d.hint}</div>
      </div>
    `).join('');
  }

  function renderNarrativeAndAlerts(state, baseline) {
    const k = state.kpi;
    const filtered = APP.filtered;
    const trend = APP.trend;
    const qualRatio = k.net ? k.riskAdj / k.net : 0;
    const baseQual = baseline.kpi.net ? baseline.kpi.riskAdj / baseline.kpi.net : 0;
    const qualityDelta = filtered ? (qualRatio - baseQual) * 100 : (trend ? trend.qualityRatio : 0);
    const cmStatus = k.margin >= 0 ? 'positive' : 'negative';
    const scopeWord = filtered ? 'selected scope' : 'marketplace';
    const flat = Math.abs(qualityDelta) < 0.05;
    const movePhrase = filtered
      ? (flat
          ? `Against the full portfolio, quality protection is essentially in line.`
          : `Against the full portfolio, quality protection is ${qualityDelta >= 0 ? 'ahead by' : 'behind by'} ${Math.abs(qualityDelta).toFixed(1)}pp.`)
      : (trend
          ? (flat
              ? `Over the last ${trend.window} months, quality protection held steady.`
              : `Over the last ${trend.window} months, quality protection ${qualityDelta > 0 ? 'improved by' : 'slipped by'} ${Math.abs(qualityDelta).toFixed(1)}pp.`)
          : `Quality protection holds at ${pct(qualRatio)} of net value.`);
    const narrative = `The ${scopeWord} covers ${k.orders.toLocaleString()} orders and ${money(k.gmv)} of GMV. Protected value stands at ${money(k.riskAdj)} — ${pct(qualRatio)} of net value — while realized contribution margin is ${cmStatus} at ${money(k.margin)}. Refunds, disputes and subsidy dependence remain the main drag. ${movePhrase}`;
    document.getElementById('executiveNarrative').textContent = narrative;

    const disputeLimit = Math.max(0.20, baseline.kpi.disputeRate + 0.025);
    const refundLimit = Math.max(0.17, baseline.kpi.refundRate + 0.015);
    const subsidyLimit = Math.max(0.035, baseline.kpi.subsidyShare + 0.008);
    const onTimeFloor = Math.max(0.0, baseline.rates.onTimeRate - 0.03);
    const guards = [
      { label: 'Dispute rate', value: pct(k.disputeRate), limit: `≤ ${pct(disputeLimit)}`, breach: k.disputeRate > disputeLimit, sev: 'bad' },
      { label: 'Refund rate', value: pct(k.refundRate), limit: `≤ ${pct(refundLimit)}`, breach: k.refundRate > refundLimit, sev: 'warn' },
      { label: 'Subsidy share', value: pct(k.subsidyShare), limit: `≤ ${pct(subsidyLimit)}`, breach: k.subsidyShare > subsidyLimit, sev: 'warn' },
      { label: 'On-time fulfillment', value: pct(state.rates.onTimeRate), limit: `≥ ${pct(onTimeFloor)}`, breach: state.rates.onTimeRate < onTimeFloor, sev: 'bad' },
    ];
    const breaches = guards.filter(g => g.breach).length;
    const head = breaches
      ? `<div class="alert-head bad">${breaches} of ${guards.length} guardrails breached</div>`
      : `<div class="alert-head good">All ${guards.length} guardrails within range</div>`;
    const rows = guards.map(g => `
      <div class="guard ${g.breach ? g.sev : 'good'}">
        <span class="guard-label">${g.label}</span>
        <span class="guard-val mono">${g.value}</span>
        <span class="guard-limit mono">${g.limit}</span>
        <span class="guard-state">${g.breach ? 'Breach' : 'OK'}</span>
      </div>`).join('');
    document.getElementById('alertsPanel').innerHTML = head + rows;

    const cmGap = k.expectedMargin - k.margin;
    const bench = [
      { name: 'Expected vs realized CM', num: money(cmGap), hint: 'Margin lost to realized risk' },
      { name: 'Leakage / net value', num: pct(k.net ? state.leakage.total / k.net : 0), hint: 'Erosion as share of net' },
      { name: 'Avg delivery delay', num: `${fixed(state.rates.avgDelay, 1)} d`, hint: 'Across delayed orders' },
    ];
    document.getElementById('benchmarkCards').innerHTML = bench.map(b => `<div class="bench"><div class="name">${b.name}</div><div class="num">${b.num}</div><div class="bench-hint">${b.hint}</div></div>`).join('');
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
    const c = chartPalette();
    plotOrEmpty(divId, [
      { x: m.map(x => x.m), y: m.map(x => x.gmv), mode: 'lines+markers', name: 'GMV', line: { color: c.steel, width: 2.4 }, marker: { size: 5 } },
      { x: m.map(x => x.m), y: m.map(x => x.riskAdj), mode: 'lines+markers', name: 'Risk-Adjusted GMV', line: { color: c.accent, width: 3 }, marker: { size: 5 } }
    ], {
      margin: { l: 56, r: 20, t: 30, b: 84 },
      yaxis: { title: 'Value ($)' },
      xaxis: { title: 'Month', tickangle: -35 }
    }, m.length > 0);
  }

  function renderWaterfall(state, divId) {
    const l = state.leakage;
    const c = chartPalette();
    const t = themeTokens();
    const measures = ['relative', 'relative', 'relative', 'relative', 'relative', 'total'];
    const x = ['Commission', 'Subsidy', 'Refunds', 'Disputes', 'Chargeback', 'Contribution<br>Margin'];
    const y = [l.commission, -l.subsidy, -l.refund, -l.dispute, -l.chargebackLoss, 0];
    const cm = l.commission - l.subsidy - l.refund - l.dispute - l.chargebackLoss;
    const labels = [l.commission, -l.subsidy, -l.refund, -l.dispute, -l.chargebackLoss, cm].map(money);
    plotOrEmpty(divId, [{
      type: 'waterfall',
      measure: measures,
      x,
      y,
      width: 0.62,
      text: labels,
      textposition: 'outside',
      textfont: { family: 'Geist Mono, SF Mono, ui-monospace, monospace', size: 11, color: t.muted },
      cliponaxis: false,
      connector: { line: { color: t.axis, width: 1, dash: 'dot' } },
      increasing: { marker: { color: c.steel } },
      decreasing: { marker: { color: c.bad } },
      totals: { marker: { color: cm >= 0 ? c.accent : c.bad } },
      hovertemplate: '%{x}<br>%{text}<extra></extra>'
    }], {
      margin: { l: 56, r: 20, t: 30, b: 64 },
      yaxis: { title: 'Value ($)', zeroline: true, zerolinewidth: 1.4 },
      xaxis: { tickfont: { size: 11 } }
    }, state.kpi.orders > 0);
  }

  function renderNetSubsidy(state) {
    const m = state.monthArr;
    const c = chartPalette();
    plotOrEmpty('plotNetSubsidy', [
      { x: m.map(x => x.m), y: m.map(x => x.net), type: 'bar', name: 'Net Value', marker: { color: c.blueSoft } },
      { x: m.map(x => x.m), y: m.map(x => (x.gmv ? x.subsidy / x.gmv : 0) * 100), type: 'scatter', mode: 'lines+markers', name: 'Subsidy Share (%)', yaxis: 'y2', line: { color: c.orange, width: 2.5 } }
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
      colorscale: divergingScale(),
      zmid: 0,
      colorbar: { title: 'Margin Rate', outlinewidth: 0, thickness: 12 }
    }], {
      title: { text: 'Category-Month Margin Quality Is Uneven and Persistent' },
      xaxis: { tickangle: -35 },
      yaxis: { automargin: true }
    }, true);
  }

  function renderRiskTrend(state) {
    const m = state.monthArr;
    const c = chartPalette();
    plotOrEmpty('plotRiskTrend', [
      { x: m.map(x => x.m), y: m.map(x => x.orders ? x.disputesCount / x.orders : 0), mode: 'lines+markers', name: 'Dispute Rate', line: { width: 3, color: c.red }, marker: { size: 5 } },
      { x: m.map(x => x.m), y: m.map(x => x.orders ? x.chargebacksCount / x.orders : 0), mode: 'lines+markers', name: 'Chargeback Rate', line: { width: 2.4, color: c.steel }, marker: { size: 5 } }
    ], {
      title: { text: 'Dispute and Chargeback Rates Co-Move in Risk Bursts', font: { size: 15 } },
      yaxis: { title: 'Rate' },
      xaxis: { tickangle: -35 }
    }, m.length > 0);
  }

  function renderDisputeChargebackScatter(state) {
    const arr = state.paySignalArr;
    const c = chartPalette();
    plotOrEmpty('plotDisputeChargeback', [{
      x: arr.map(x => x.chargebackRate),
      y: arr.map(x => x.disputeRate),
      text: arr.map(x => `${x.signal}<br>Orders: ${x.orders.toLocaleString()}`),
      mode: 'markers',
      marker: {
        size: arr.map(x => 8 + Math.sqrt(x.orders) * 0.35),
        color: arr.map(x => x.orders),
        colorscale: sequentialScale(),
        showscale: true,
        colorbar: { title: 'Orders', outlinewidth: 0, thickness: 12 },
        line: { color: APP.theme === 'dark' ? '#12151c' : '#ffffff', width: 0.8 }
      },
      hovertemplate: '%{text}<br>Chargeback: %{x:.2%}<br>Dispute: %{y:.2%}<extra></extra>'
    }], {
      title: { text: 'Higher Payment-Risk Signals Cluster in Elevated Dispute/Chargeback Zone' },
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
      colorscale: sequentialScale(),
      colorbar: { title: '(Disputes + Chargebacks) / Orders', outlinewidth: 0, thickness: 12 }
    }], {
      title: { text: 'Suspicious Pattern Hotspots by Channel and Payment Method' },
      xaxis: { tickangle: -30 },
      yaxis: { automargin: true }
    }, true);
  }

  function renderRiskDistribution(state) {
    const rt = state.riskTierCount;
    const bt = state.buyerTierCount;
    const orderTiers = ['Low', 'Moderate', 'High', 'Critical'];
    const buyerTiers = ['Low', 'Moderate', 'High', 'Critical'];
    const cd = chartPalette();
    plotOrEmpty('plotRiskDistribution', [
      { x: orderTiers, y: orderTiers.map(t => rt[t] || 0), type: 'bar', name: 'Order Risk Tier Count', marker: { color: cd.accent } },
      { x: buyerTiers, y: buyerTiers.map(t => bt[t] || 0), type: 'bar', name: 'Buyer Risk Tier Count', marker: { color: cd.steel } }
    ], {
      barmode: 'group',
      title: { text: 'Critical Risk Tail Exists in Both Buyer and Order Distributions', font: { size: 15 } },
      yaxis: { title: 'Count' }
    }, state.kpi.orders > 0);
  }

  function renderSellerQuality(state) {
    const sellers = state.sellerArr;
    const c = chartPalette();
    plotOrEmpty('plotSellerQualityDist', [{
      type: 'histogram',
      x: sellers.map(s => s.sqs),
      nbinsx: 30,
      marker: { color: c.blueSoft },
      name: 'Seller Quality Score'
    }], {
      title: { text: 'Seller Quality Score Tail Indicates Governance Workload', font: { size: 15 } },
      xaxis: { title: 'Seller Quality Score (Higher = Riskier)' },
      yaxis: { title: 'Seller Count' }
    }, sellers.length > 0);

    plotOrEmpty('plotMarginFragilityDist', [{
      type: 'histogram',
      x: sellers.map(s => s.mfs),
      nbinsx: 30,
      marker: { color: c.accent },
      name: 'Margin Fragility'
    }], {
      title: { text: 'Margin Fragility Concentration Indicates Structural Economic Risk', font: { size: 15 } },
      xaxis: { title: 'Margin Fragility Score' },
      yaxis: { title: 'Seller Count' }
    }, sellers.length > 0);
  }

  function renderSellerCohort(state) {
    const order = ['Top 10% GMV Sellers', 'Mid 40% GMV Sellers', 'Long-Tail 50% Sellers'];
    const c = [...state.sellerCohorts].sort((a, b) => order.indexOf(a.cohort) - order.indexOf(b.cohort));
    plotOrEmpty('plotSellerCohort', [{
      type: 'bar',
      x: c.map(x => x.cohort),
      y: c.map(x => x.disputeRate),
      marker: { color: chartPalette().steel },
      hovertemplate: '%{x}<br>Dispute rate: %{y:.2%}<extra></extra>'
    }], {
      title: { text: 'Dispute Burden Persists Across Seller Volume Cohorts', font: { size: 15 } },
      yaxis: { title: 'Dispute Rate', tickformat: '.1%' }
    }, c.length > 0);
  }

  function renderSellerMatrix(state) {
    const s = state.sellerArr;
    const dk = APP.theme === 'dark';
    const tiers = ['Low', 'Moderate', 'High', 'Critical'];
    const colors = dk
      ? { Low: '#3a3f63', Moderate: '#6862c4', High: '#8e88ff', Critical: '#f0726b' }
      : { Low: '#cdcaf2', Moderate: '#9a93e8', High: '#5b54e0', Critical: '#c5453b' };
    const mLine = dk ? '#12151c' : '#ffffff';
    const traces = tiers.map(t => {
      const d = s.filter(x => x.gvt === t);
      return {
        x: d.map(x => x.gmv),
        y: d.map(x => x.sqs),
        mode: 'markers',
        type: 'scatter',
        name: t,
        text: d.map(x => `Seller ${x.sid}<br>GMV: ${money(x.gmv)}<br>Quality: ${fixed(x.sqs,1)}<br>Gov: ${fixed(x.gvs,1)}`),
        marker: { size: d.map(x => 8 + Math.sqrt(x.orders) * 0.4), color: colors[t], opacity: 0.72, line: { color: mLine, width: 0.7 } },
        hovertemplate: '%{text}<extra></extra>'
      };
    });
    plotOrEmpty('plotSellerMatrix', traces, {
      title: { text: 'High-Volume, Weak-Quality Sellers Form the Primary Governance Risk Quadrant' },
      xaxis: { title: 'Seller GMV ($)', type: 'log' },
      yaxis: { title: 'Seller Quality Score' },
      shapes: [{ type: 'line', x0: 1, x1: Math.max(1, ...s.map(x => x.gmv)), y0: 55, y1: 55, line: { color: chartPalette().steel, dash: 'dot' } }]
    }, s.length > 0);
  }

  function renderTopSellers(state) {
    const top = [...state.sellerArr].sort((a, b) => b.gvs - a.gvs).slice(0, 20).reverse();
    const dk = APP.theme === 'dark';
    const tierColor = (t) => dk
      ? (t === 'Critical' ? '#f0726b' : t === 'High' ? '#8e88ff' : t === 'Moderate' ? '#6862c4' : '#3a3f63')
      : (t === 'Critical' ? '#c5453b' : t === 'High' ? '#5b54e0' : t === 'Moderate' ? '#9a93e8' : '#cdcaf2');
    plotOrEmpty('plotTopSellers', [{
      type: 'bar',
      orientation: 'h',
      y: top.map(x => x.sid),
      x: top.map(x => x.gvs),
      marker: { color: top.map(x => tierColor(x.gvt)) },
      text: top.map(x => fixed(x.gvs, 1)),
      textposition: 'outside',
      cliponaxis: false,
      hovertemplate: 'Seller %{y}<br>Governance score: %{x:.1f}<extra></extra>'
    }], {
      title: { text: 'Top Governance Priority Sellers Concentrate Enterprise Risk' },
      xaxis: { title: 'Governance Priority Score' },
      yaxis: { title: 'Seller ID' }
    }, top.length > 0);
  }

  function renderOpsCharts(state) {
    const delay = state.delayBucketArr;
    const c = chartPalette();
    plotOrEmpty('plotRefundDelay', [{
      x: delay.map(x => x.bucket),
      y: delay.map(x => x.refundRate),
      mode: 'lines+markers',
      line: { color: c.red, width: 3 },
      hovertemplate: 'Delay %{x} days<br>Refund rate: %{y:.2%}<extra></extra>'
    }], {
      title: { text: 'Refund Rates Increase as Delay Days Rise', font: { size: 15 } },
      xaxis: { title: 'Delay Days (bucketed)' },
      yaxis: { title: 'Refund Rate', tickformat: '.1%' }
    }, delay.length > 0);

    const m = state.monthArr;
    plotOrEmpty('plotOpsTrend', [
      { x: m.map(x => x.m), y: m.map(x => x.delayEligible ? x.delaySum / x.delayEligible : 0), mode: 'lines+markers', name: 'Avg Delay Days', yaxis: 'y1', line: { color: c.orange, width: 2.6 } },
      { x: m.map(x => x.m), y: m.map(x => x.orders ? x.cancels / x.orders : 0), mode: 'lines+markers', name: 'Cancellation Rate', yaxis: 'y2', line: { color: c.red, width: 2.6 } },
      { x: m.map(x => x.m), y: m.map(x => x.onTimeEligible ? x.onTimeCount / x.onTimeEligible : 0), mode: 'lines+markers', name: 'On-Time Rate', yaxis: 'y2', line: { color: c.green, width: 2.6 } }
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
      line: { color: c.red, width: 3 },
      hovertemplate: 'Delay %{x} days<br>Dispute rate: %{y:.2%}<extra></extra>'
    }], {
      title: { text: 'Dispute Risk Escalates with Higher Delay Buckets', font: { size: 15 } },
      xaxis: { title: 'Delay Days (bucketed)' },
      yaxis: { title: 'Dispute Rate', tickformat: '.1%' }
    }, delay.length > 0);

    const cat = [...state.categoryArr].sort((a, b) => b.subsidyShare - a.subsidyShare).slice(0, 12);
    plotOrEmpty('plotPromoCategory', [{
      type: 'bar',
      orientation: 'h',
      y: cat.map(x => x.category),
      x: cat.map(x => x.subsidyShare),
      marker: { color: c.accent },
      hovertemplate: '%{y}<br>Promo dependency: %{x:.2%}<extra></extra>'
    }], {
      title: { text: 'Promo Dependency by Category Shows Margin Sensitivity Exposure', font: { size: 15 } },
      xaxis: { title: 'Subsidy Share of GMV', tickformat: '.1%' }
    }, cat.length > 0);
  }

  function renderSellerConcentration(state) {
    const c = state.concentration;
    const p = chartPalette();
    plotOrEmpty('plotSellerConcentration', [
      { x: c.map(x => x.sellerShare), y: c.map(x => x.gmvShare), mode: 'lines', name: 'Observed', line: { color: p.accent, width: 3 }, fill: 'tozeroy', fillcolor: APP.theme === 'dark' ? 'rgba(142,136,255,0.14)' : 'rgba(91,84,224,0.10)' },
      { x: [0, 1], y: [0, 1], mode: 'lines', name: 'Equality', line: { color: p.neutral, dash: 'dash' } }
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
        colorscale: divergingScale(),
        cmid: 0,
        showscale: true,
        colorbar: { title: 'CM Delta', outlinewidth: 0, thickness: 12 },
        line: { color: APP.theme === 'dark' ? '#12151c' : '#ffffff', width: 1 }
      },
      hovertemplate: '%{text}<br>GMV delta: %{x:.2f}%<br>Quality delta: %{y:.2f}pp<extra></extra>'
    }], {
      title: { text: 'Scenario Assumptions Compare Protected Economics with GMV Trade-offs' },
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
      marker: { color: sorted.map(r => r.contribution_margin_change_vs_baseline >= 0 ? chartPalette().good : chartPalette().bad) },
      hovertemplate: '%{x}<br>CM Delta: %{y:$,.0f}<extra></extra>'
    }], {
      title: { text: 'Margin Protection Ranking Across Strategic Scenarios' },
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
          <td><span class="table-pill ${tierClassFromRiskTier(r.gvt)}">${r.gvt}</span></td>
          <td>${fixed(r.gvs, 1)}</td>
          <td>${fixed(r.sqs, 1)}</td>
          <td>${money(r.gmv)}</td>
          <td>${r.orders.toLocaleString()}</td>
          <td>${pct(r.refund_rate)}</td>
          <td>${pct(r.dispute_rate)}</td>
          <td>${pct(r.delay_rate)}</td>
          <td><div class="action-text">${r.ract}</div></td>
        </tr>
      `).join('');
    }
    document.getElementById('sellerPageInfo').textContent = `Page ${APP.sellerPage} / ${totalPages} (${rows.length.toLocaleString()} sellers)`;
  }

  function renderRiskAndProfitabilityMandatoryCharts(state) {
    const cat = [...state.categoryArr].sort((a, b) => b.refundRate - a.refundRate).slice(0, 12);
    plotOrEmpty('plotRefundByCategory', [{
      type: 'bar',
      orientation: 'h',
      y: cat.map(x => x.category),
      x: cat.map(x => x.refundRate),
      marker: { color: chartPalette().rose },
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
    APP.filtered = isScopeFiltered();
    APP.trend = periodTrend(state);
    document.getElementById('scopeBar').innerHTML = scopeSummaryChips(filters, state);
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

  function activateTab(button) {
    document.querySelectorAll('.tab-btn').forEach(b => {
      b.classList.remove('active');
      b.setAttribute('aria-pressed', 'false');
    });
    button.classList.add('active');
    button.setAttribute('aria-pressed', 'true');
    const tab = button.getAttribute('data-tab');
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    document.getElementById(`tab-${tab}`).classList.add('active');
  }

  function applySellerSort(header) {
    const key = header.getAttribute('data-sort');
    if (APP.sellerSort.key === key) {
      APP.sellerSort.dir = APP.sellerSort.dir === 'asc' ? 'desc' : 'asc';
    } else {
      APP.sellerSort.key = key;
      APP.sellerSort.dir = key === 'sid' || key === 'gvt' || key === 'ract' ? 'asc' : 'desc';
    }
    document.querySelectorAll('#tab-seller thead .sort-button').forEach(button => {
      button.closest('th').setAttribute(
        'aria-sort',
        button === header ? (APP.sellerSort.dir === 'asc' ? 'ascending' : 'descending') : 'none'
      );
    });
    APP.sellerPage = 1;
    renderSellerTable(APP.currentState);
  }

  function setMethodologyDrawerOpen(open) {
    const drawer = document.getElementById('methodologyDrawer');
    drawer.classList.toggle('open', open);
    drawer.setAttribute('aria-hidden', open ? 'false' : 'true');
    drawer.inert = !open;
    if (open) {
      methodologyReturnFocus = document.activeElement;
      document.getElementById('methodologyClose').focus();
    } else if (methodologyReturnFocus instanceof HTMLElement) {
      methodologyReturnFocus.focus();
    }
  }

  function bindEvents() {
    document.getElementById('applyFilters').addEventListener('click', () => { APP.sellerPage = 1; renderDashboard(); });
    document.getElementById('resetFilters').addEventListener('click', resetFilters);
    document.getElementById('resetFiltersTop').addEventListener('click', resetFilters);
    document.getElementById('filtersToggle').addEventListener('click', () => {
      setFiltersOpen(!APP.filtersOpen);
    });
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
      btn.addEventListener('click', () => activateTab(btn));
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

    document.querySelectorAll('#tab-seller thead .sort-button').forEach(button => {
      button.addEventListener('click', () => applySellerSort(button));
    });

    document.getElementById('methodologyOpen').addEventListener('click', () => {
      setMethodologyDrawerOpen(true);
    });
    document.getElementById('methodologyClose').addEventListener('click', () => {
      setMethodologyDrawerOpen(false);
    });
    document.addEventListener('keydown', (event) => {
      const drawerOpen = document.getElementById('methodologyDrawer').classList.contains('open');
      if (event.key === 'Escape' && drawerOpen) {
        setMethodologyDrawerOpen(false);
      } else if (event.key === 'Tab' && drawerOpen) {
        event.preventDefault();
        document.getElementById('methodologyClose').focus();
      }
    });
  }

  function mountExtraMandatoryPanels() {
    const profitabilityPanel = document.getElementById('tab-profitability');

    const extraProfit = document.createElement('div');
    extraProfit.className = 'row row-2';
    extraProfit.innerHTML = `
      <div class="panel">
        <h3>Which categories have the highest refund rate?</h3>
        <p class="sub">Use to prioritize quality and policy intervention in value-destructive segments.</p>
        <div id="plotRefundByCategory" class="plot"></div>
      </div>
      <div class="panel">
        <h3>How concentrated is GMV in the seller base?</h3>
        <p class="sub">Use to understand whether a few sellers can amplify governance and margin shocks.</p>
        <div id="plotSellerConcentration" class="plot"></div>
      </div>
    `;
    profitabilityPanel.appendChild(extraProfit);
  }

  function init() {
    applyTheme(preferredTheme(), false);
    setFiltersOpen(false);
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
    if cfg.max_orders <= 0:
        raise ValueError("max_orders must be greater than zero.")
    payload = _build_payload(cfg)
    data_json = json.dumps(_json_safe(payload), separators=(",", ":"), ensure_ascii=True, allow_nan=False)
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
