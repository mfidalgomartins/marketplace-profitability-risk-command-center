import json
from pathlib import Path

from src.validation.validate_schema_contracts import validate_schema_contracts


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "schemas" / "v1" / "schema_contracts.json"


def test_schema_contract_file_exists_and_has_expected_core_tables() -> None:
    assert SCHEMA_FILE.exists()

    contract = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
    assert contract["schema_family"] == "marketplace_command_center"
    assert contract["contract_version"].startswith("v1.")

    table_names = {t["table_name"] for t in contract["tables"]}
    required = {
        "buyers",
        "orders",
        "order_items",
        "order_profitability_features",
        "order_risk_scores",
        "seller_scorecard",
        "scenario_results_summary",
        "backtesting_threshold_curve",
        "scenario_monte_carlo_summary",
        "governance_action_register",
    }
    assert required.issubset(table_names)


def test_schema_contracts_validate_cleanly() -> None:
    issues = validate_schema_contracts(SCHEMA_FILE)
    assert issues.empty
