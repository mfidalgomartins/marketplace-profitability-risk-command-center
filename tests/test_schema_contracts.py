import json
from pathlib import Path

import pandas as pd
import pytest
from src.validation import validate_schema_contracts as vsc_module
from src.validation.validate_schema_contracts import validate_schema_contracts

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "config" / "contracts" / "v1" / "schema_contracts.json"


def _write_schema(path: Path, table: dict) -> None:
    path.write_text(
        json.dumps({"contract_version": "v1.0.0", "schema_family": "marketplace_command_center", "tables": [table]}),
        encoding="utf-8",
    )


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
    assert list(issues.columns) == ["table_name", "path", "issue_type", "detail"]


def test_validate_raises_for_missing_schema(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        validate_schema_contracts(tmp_path / "nope.json")


def test_validate_flags_missing_table_file(tmp_path: Path) -> None:
    schema = tmp_path / "schema.json"
    _write_schema(schema, {"table_name": "orders", "path": str(tmp_path / "absent.csv"), "columns": ["order_id"]})
    issues = validate_schema_contracts(schema)
    assert set(issues["issue_type"]) == {"missing_table_file"}


def test_validate_flags_column_type_and_key_problems(tmp_path: Path) -> None:
    data = tmp_path / "orders.csv"
    # gmv is text (type mismatch vs "number"); order_id duplicated (PK dup);
    # column order differs from the contract (column mismatch).
    pd.DataFrame({"order_id": ["A", "A"], "gmv": ["x", "y"], "extra": [1, 2]}).to_csv(data, index=False)
    schema = tmp_path / "schema.json"
    _write_schema(
        schema,
        {
            "table_name": "orders",
            "path": str(data),
            "columns": ["order_id", "gmv"],
            "column_types": {"order_id": "string", "gmv": "number"},
            "primary_key_candidate": ["order_id"],
        },
    )
    issues = validate_schema_contracts(schema)
    found = set(issues["issue_type"])
    assert "column_mismatch" in found
    assert "type_mismatch" in found
    assert "primary_key_duplicates" in found


def test_validate_flags_nulls_and_unique_constraint_violations(tmp_path: Path) -> None:
    data = tmp_path / "payments.csv"
    pd.DataFrame(
        {
            "payment_id": ["P1", None, "P3"],
            "order_id": ["O1", "O1", "O2"],
        }
    ).to_csv(data, index=False)
    schema = tmp_path / "schema.json"
    _write_schema(
        schema,
        {
            "table_name": "payments",
            "path": str(data),
            "columns": ["payment_id", "order_id"],
            "column_types": {"payment_id": "string", "order_id": "string"},
            "primary_key_candidate": ["payment_id"],
            "not_null_columns": ["payment_id", "order_id"],
            "unique_constraints": [["order_id"]],
        },
    )
    issues = validate_schema_contracts(schema)
    found = set(issues["issue_type"])
    assert "not_null_violation" in found
    assert "primary_key_nulls" in found
    assert "unique_constraint_violation" in found


def test_validate_flags_row_count_constraints(tmp_path: Path) -> None:
    data = tmp_path / "policy.csv"
    pd.DataFrame({"threshold": [50, 60]}).to_csv(data, index=False)
    schema = tmp_path / "schema.json"
    _write_schema(
        schema,
        {
            "table_name": "policy",
            "path": str(data),
            "columns": ["threshold"],
            "column_types": {"threshold": "integer"},
            "row_count_constraint": {"minimum": 1, "maximum": 1},
        },
    )

    issues = validate_schema_contracts(schema)
    assert "row_count_above_maximum" in set(issues["issue_type"])


def test_datetime_column_with_nulls_validates_cleanly(tmp_path: Path) -> None:
    # A date column may legitimately have missing values (e.g. undelivered
    # orders); validation must judge it on populated values only.
    data = tmp_path / "logistics.csv"
    pd.DataFrame({"delivered_date": ["2024-03-01", None, "2024-03-05", None]}).to_csv(data, index=False)
    schema = tmp_path / "schema.json"
    _write_schema(
        schema,
        {
            "table_name": "logistics",
            "path": str(data),
            "columns": ["delivered_date"],
            "column_types": {"delivered_date": "datetime"},
        },
    )
    issues = validate_schema_contracts(schema)
    assert issues.empty


def test_validate_flags_missing_primary_key_columns(tmp_path: Path) -> None:
    data = tmp_path / "t.csv"
    pd.DataFrame({"a": [1, 2]}).to_csv(data, index=False)
    schema = tmp_path / "schema.json"
    _write_schema(
        schema,
        {"table_name": "t", "path": str(data), "columns": ["a"], "primary_key_candidate": ["missing_id"]},
    )
    issues = validate_schema_contracts(schema)
    assert "missing_primary_key_columns" in set(issues["issue_type"])


def test_validate_schema_contracts_cli_writes_report(tmp_path: Path, monkeypatch, capsys) -> None:
    out = tmp_path / "issues.csv"
    monkeypatch.setattr(
        "sys.argv",
        ["validate_schema_contracts.py", "--schema-file", str(SCHEMA_FILE), "--output-file", str(out)],
    )
    vsc_module.main()
    assert out.exists()
    assert "PASSED" in capsys.readouterr().out


def test_validate_schema_contracts_cli_exits_nonzero_on_failure(tmp_path: Path, monkeypatch) -> None:
    schema = tmp_path / "schema.json"
    _write_schema(schema, {"table_name": "missing", "path": str(tmp_path / "missing.csv"), "columns": []})
    out = tmp_path / "issues.csv"
    monkeypatch.setattr(
        "sys.argv",
        ["validate_schema_contracts.py", "--schema-file", str(schema), "--output-file", str(out)],
    )
    with pytest.raises(SystemExit) as exc_info:
        vsc_module.main()
    assert exc_info.value.code == 1
    assert out.exists()
