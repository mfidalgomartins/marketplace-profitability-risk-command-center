import json
from pathlib import Path

import pandas as pd
from src.validation.generate_schema_drift_report import (
    DRIFT_COLUMNS,
    DriftConfig,
    _render_report,
    _resolve_previous_schema,
    _snapshot_schema,
    compare_contracts,
    run_drift,
)

ROOT = Path(__file__).resolve().parents[1]


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


def test_compare_contracts_keeps_columns_when_no_drift(tmp_path: Path) -> None:
    prev = tmp_path / "prev.json"
    curr = tmp_path / "curr.json"
    tables = [
        {
            "table_name": "orders",
            "columns": ["order_id", "net_paid_amount"],
            "column_types": {"order_id": "string", "net_paid_amount": "number"},
            "primary_key_candidate": ["order_id"],
        }
    ]
    _write_contract(prev, tables)
    _write_contract(curr, tables)

    changes = compare_contracts(prev, curr)

    assert changes.empty
    assert list(changes.columns) == [
        "change_type",
        "table_name",
        "column_name",
        "previous_value",
        "current_value",
        "severity",
    ]


def test_run_drift_against_committed_history() -> None:
    cfg = DriftConfig(
        current_schema_file=ROOT / "config" / "contracts" / "v1" / "schema_contracts.json",
        history_dir=ROOT / "config" / "contracts" / "history",
    )
    changes, previous, snapshot_path = run_drift(cfg)
    assert previous is not None  # history has baseline snapshots
    assert snapshot_path is None  # snapshot_current defaults to False
    assert list(changes.columns) == DRIFT_COLUMNS


def test_resolve_previous_schema_returns_none_for_empty_history(tmp_path: Path) -> None:
    assert _resolve_previous_schema(DriftConfig(history_dir=tmp_path)) is None


def test_run_drift_can_snapshot_into_fresh_history(tmp_path: Path) -> None:
    cfg = DriftConfig(
        current_schema_file=ROOT / "config" / "contracts" / "v1" / "schema_contracts.json",
        history_dir=tmp_path,
        snapshot_current=True,
    )
    _, _, snapshot_path = run_drift(cfg)
    assert snapshot_path is not None and snapshot_path.exists()
    # Re-snapshotting identical content reuses the existing file rather than duplicating.
    again = _snapshot_schema(cfg.current_schema_file, tmp_path)
    assert again == snapshot_path


def test_render_report_variants(tmp_path: Path) -> None:
    current = ROOT / "config" / "contracts" / "v1" / "schema_contracts.json"
    # No previous snapshot -> baseline message.
    assert "Baseline initialized" in _render_report(None, current, pd.DataFrame(columns=DRIFT_COLUMNS))
    # Previous present, no changes -> no-drift message.
    assert "No schema drift" in _render_report(current, current, pd.DataFrame(columns=DRIFT_COLUMNS))
    # Previous present, with changes -> summary + change lines.
    changes = pd.DataFrame(
        [
            {
                "change_type": "type_changed",
                "table_name": "orders",
                "column_name": "gmv",
                "previous_value": "number",
                "current_value": "integer",
                "severity": "Medium",
            }
        ]
    )
    report = _render_report(current, current, changes)
    assert "Drift Summary" in report and "type_changed" in report
