from __future__ import annotations

import argparse
import json
from pathlib import Path

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
    "order_risk_calibrated",
    "model_calibration_parameters",
    "model_calibration_curve",
    "temporal_holdout_metrics",
    "model_monitoring_monthly",
    "model_monitoring_alerts",
    "model_release_assessment",
    "order_accounting_pnl",
    "finance_general_ledger",
    "finance_reconciliation",
    "accounting_kpi_summary",
    "experiment_assignments",
    "experiment_balance",
    "experiment_results",
    "experiment_power",
    "experiment_heterogeneity",
]

PRIMARY_KEYS: dict[str, list[str]] = {
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
    "seller_monthly_quality": ["seller_id", "month"],
    "buyer_behavior_risk": ["buyer_id"],
    "category_risk_summary": ["month", "category"],
    "seller_risk_base": ["seller_id", "current_period"],
    "order_risk_scores": ["order_id"],
    "seller_quality_scores": ["seller_id"],
    "fraud_exposure_scores": ["seller_id"],
    "margin_fragility_scores": ["seller_id"],
    "governance_priority_scores": ["seller_id"],
    "seller_scorecard": ["seller_id"],
    "top_high_priority_sellers": ["seller_id"],
    "top_high_risk_orders": ["order_id"],
    "scoring_sensitivity_summary": ["scenario"],
    "governance_action_register": ["entity_type", "entity_id"],
    "scenario_assumptions": ["scenario"],
    "scenario_results_summary": ["scenario"],
    "scenario_component_bridge": ["scenario"],
    "scenario_decision_matrix": ["scenario"],
    "scenario_monte_carlo_samples": ["iteration", "scenario"],
    "scenario_monte_carlo_summary": ["scenario"],
    "scenario_monte_carlo_decision": ["scenario"],
    "backtesting_threshold_curve": ["threshold"],
    "backtesting_action_impact": ["threshold", "efficacy_assumption"],
    "order_risk_calibrated": ["order_id"],
    "model_calibration_parameters": ["policy_version"],
    "model_calibration_curve": ["split", "calibration_bin"],
    "temporal_holdout_metrics": ["split"],
    "model_monitoring_monthly": ["month"],
    "model_monitoring_alerts": ["alert_id"],
    "model_release_assessment": ["assessment_scope"],
    "order_accounting_pnl": ["order_id"],
    "finance_general_ledger": ["journal_line_id"],
    "finance_reconciliation": ["check_name"],
    "accounting_kpi_summary": ["finance_policy_version"],
    "experiment_assignments": ["order_id"],
    "experiment_balance": ["covariate"],
    "experiment_results": ["experiment_id", "metric"],
    "experiment_power": ["experiment_id"],
    "experiment_heterogeneity": ["dimension", "segment"],
}

UNIQUE_CONSTRAINTS: dict[str, list[list[str]]] = {
    "payments": [["order_id"]],
    "logistics_events": [["order_id"]],
}

NOT_NULL_COLUMNS: dict[str, list[str]] = {
    "buyers": ["buyer_id"],
    "sellers": ["seller_id"],
    "products": ["product_id", "seller_id"],
    "orders": ["order_id", "buyer_id", "order_date"],
    "order_items": ["order_item_id", "order_id", "product_id", "seller_id"],
    "payments": ["payment_id", "order_id"],
    "refunds": ["refund_id", "order_id", "refund_date"],
    "disputes": ["dispute_id", "order_id", "dispute_date"],
    "logistics_events": ["event_id", "order_id", "seller_id"],
}

ROW_COUNT_CONSTRAINTS: dict[str, dict[str, int]] = {
    "scenario_top_risk_exposure": {"minimum": 1, "maximum": 1},
    "backtesting_recommended_policy": {"minimum": 1, "maximum": 1},
    "model_calibration_parameters": {"minimum": 1, "maximum": 1},
    "model_release_assessment": {"minimum": 1, "maximum": 1},
    "accounting_kpi_summary": {"minimum": 1, "maximum": 1},
    "experiment_power": {"minimum": 1, "maximum": 1},
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
    # CSV reads datetime-like values as strings; detect parseable date columns
    # explicitly. Under pandas 3.0 read_csv yields the new `str` dtype (not
    # `object`), so accept any string-like dtype here, guarded by parse rate.
    # Dates in this dataset are ISO-8601, so parse with that format to avoid
    # mis-parsing non-date text (which coerces cleanly to NaT).
    if series.dtype == object or pd.api.types.is_string_dtype(series):
        non_null = series.dropna()
        if len(non_null) > 0:
            parsed = pd.to_datetime(non_null, errors="coerce", utc=False, format="ISO8601")
            parse_rate = float(parsed.notna().mean())
            if parse_rate >= 0.98:
                return "datetime"
    return "string"


def _table_contract(path: Path, table_name: str) -> dict[str, object]:
    sample = pd.read_csv(path, nrows=200)
    return {
        "table_name": table_name,
        "path": str(path.as_posix()),
        "columns": list(sample.columns),
        "column_types": {c: _infer_kind(sample[c]) for c in sample.columns},
        "primary_key_candidate": PRIMARY_KEYS.get(table_name, []),
        "unique_constraints": UNIQUE_CONSTRAINTS.get(table_name, []),
        "not_null_columns": NOT_NULL_COLUMNS.get(table_name, PRIMARY_KEYS.get(table_name, [])),
        "row_count_constraint": ROW_COUNT_CONSTRAINTS.get(table_name, {}),
        "enforcement": "exact_columns",
    }


def generate_contract(raw_dir: Path, processed_dir: Path) -> dict[str, object]:
    paths = [(table, raw_dir / f"{table}.csv") for table in RAW_TABLES]
    paths.extend((table, processed_dir / f"{table}.csv") for table in PROCESSED_TABLES)

    missing = [path for _, path in paths if not path.exists()]
    if missing:
        missing_text = ", ".join(path.as_posix() for path in missing)
        raise FileNotFoundError(f"Cannot generate a complete schema contract; missing table(s): {missing_text}")

    tables = [_table_contract(path, table) for table, path in paths]

    return {
        "contract_version": "v1.1.0",
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
