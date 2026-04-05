import json
from pathlib import Path

from src.validation.generate_schema_drift_report import compare_contracts


def _write_contract(path: Path, tables: list[dict]) -> None:
    payload = {
        "contract_version": "v1.0.0",
        "schema_family": "marketplace_command_center",
        "tables": tables,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_compare_contracts_detects_added_removed_and_type_changes(tmp_path: Path) -> None:
    prev = tmp_path / "prev.json"
    curr = tmp_path / "curr.json"

    _write_contract(
        prev,
        [
            {
                "table_name": "orders",
                "columns": ["order_id", "net_paid_amount"],
                "column_types": {"order_id": "string", "net_paid_amount": "number"},
                "primary_key_candidate": ["order_id"],
            },
            {
                "table_name": "buyers",
                "columns": ["buyer_id"],
                "column_types": {"buyer_id": "string"},
                "primary_key_candidate": ["buyer_id"],
            },
        ],
    )
    _write_contract(
        curr,
        [
            {
                "table_name": "orders",
                "columns": ["order_id", "net_paid_amount", "risk_tier"],
                "column_types": {"order_id": "string", "net_paid_amount": "integer", "risk_tier": "string"},
                "primary_key_candidate": ["order_id"],
            },
            {
                "table_name": "payments",
                "columns": ["payment_id"],
                "column_types": {"payment_id": "string"},
                "primary_key_candidate": ["payment_id"],
            },
        ],
    )

    changes = compare_contracts(prev, curr)
    change_types = set(changes["change_type"].tolist())

    assert "table_added" in change_types
    assert "table_removed" in change_types
    assert "column_added" in change_types
    assert "type_changed" in change_types
