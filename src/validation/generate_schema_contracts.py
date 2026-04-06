from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import pandas as pd


RAW_TABLES = [
    "buyers",
    "sellers",
    "products",
    "orders",
    "order_items",
    "payments",
    "refunds",
    "disputes",
    "logistics_events",
]

PROCESSED_TABLES = [
    "order_profitability_features",
    "seller_monthly_quality",
    "buyer_behavior_risk",
    "category_risk_summary",
    "seller_risk_base",
    "order_risk_scores",
    "seller_quality_scores",
    "fraud_exposure_scores",
    "margin_fragility_scores",
    "governance_priority_scores",
    "seller_scorecard",
    "order_scorecard",
    "top_high_priority_sellers",
    "top_high_risk_orders",
    "scoring_sensitivity_summary",
    "governance_action_register",
    "scenario_assumptions",
    "scenario_results_summary",
    "scenario_component_bridge",
    "scenario_top_risk_exposure",
    "scenario_decision_matrix",
    "scenario_monte_carlo_samples",
    "scenario_monte_carlo_summary",
    "scenario_monte_carlo_decision",
    "backtesting_threshold_curve",
    "backtesting_action_impact",
    "backtesting_recommended_policy",
]

PRIMARY_KEYS = {
    "buyers": ["buyer_id"],
    "sellers": ["seller_id"],
    "products": ["product_id"],
    "orders": ["order_id"],
    "order_items": ["order_item_id"],
    "payments": ["payment_id"],
    "refunds": ["refund_id"],
    "disputes": ["dispute_id"],
    "logistics_events": ["event_id"],
    "order_profitability_features": ["order_id"],
    "buyer_behavior_risk": ["buyer_id"],
    "order_risk_scores": ["order_id"],
    "seller_quality_scores": ["seller_id"],
    "fraud_exposure_scores": ["seller_id"],
    "margin_fragility_scores": ["seller_id"],
    "governance_priority_scores": ["seller_id"],
    "seller_scorecard": ["seller_id"],
    "order_scorecard": ["order_id"],
    "governance_action_register": ["entity_type", "entity_id"],
}


def _infer_kind(series: pd.Series) -> str:
    dtype = str(series.dtype)
    if "int" in dtype:
        return "integer"
    if "float" in dtype:
        return "number"
    if "bool" in dtype:
        return "boolean"
    if "datetime" in dtype:
        return "datetime"
    # CSV reads datetime-like values as strings; detect parseable date columns explicitly.
    if series.dtype == object:
        non_null = series.dropna()
        if len(non_null) > 0:
            parsed = pd.to_datetime(non_null, errors="coerce", utc=False)
            parse_rate = float(parsed.notna().mean())
            if parse_rate >= 0.98:
                return "datetime"
    return "string"


def _table_contract(path: Path, table_name: str) -> Dict[str, object]:
    sample = pd.read_csv(path, nrows=200)
    return {
        "table_name": table_name,
        "path": str(path.as_posix()),
        "columns": list(sample.columns),
        "column_types": {c: _infer_kind(sample[c]) for c in sample.columns},
        "primary_key_candidate": PRIMARY_KEYS.get(table_name, []),
        "enforcement": "exact_columns",
    }


def generate_contract(raw_dir: Path, processed_dir: Path) -> Dict[str, object]:
    tables: List[Dict[str, object]] = []

    for t in RAW_TABLES:
        p = raw_dir / f"{t}.csv"
        if p.exists():
            tables.append(_table_contract(p, t))

    for t in PROCESSED_TABLES:
        p = processed_dir / f"{t}.csv"
        if p.exists():
            tables.append(_table_contract(p, t))

    return {
        "contract_version": "v1.0.0",
        "schema_family": "marketplace_command_center",
        "tables": tables,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate schema contract file from current data artifacts.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-file", type=Path, default=Path("config/contracts/v1/schema_contracts.json"))
    args = parser.parse_args()

    contract = generate_contract(args.raw_dir, args.processed_dir)
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(json.dumps(contract, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Schema contracts written: {args.output_file}")


if __name__ == "__main__":
    main()
