"""In-process tests for the schema-contract, governance-register, and executive
snapshot builders. They run against the committed synthetic dataset and write to
temporary directories so they exercise real logic without mutating artifacts."""

from pathlib import Path

import pytest
from src.governance.build_governance_action_register import (
    GovernanceConfig,
    _owner_from_order_driver,
    _owner_from_seller_driver,
    _sla_days,
    build_action_register,
    save_action_register,
)
from src.validation import generate_schema_contracts as gsc_module
from src.validation.generate_executive_snapshot import (
    ExecutiveSnapshotConfig,
    generate_snapshot,
)
from src.validation.generate_schema_contracts import _infer_kind, generate_contract

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"


def test_infer_kind_detects_iso_date_strings() -> None:
    import pandas as pd

    # pandas 3.0 read_csv yields the new str dtype; ISO date columns must still
    # be detected as datetime (regression for the previously-dead branch).
    dates = pd.Series(["2024-03-01", "2024-04-15", "2025-01-09"], dtype="str")
    assert _infer_kind(dates) == "datetime"
    # Non-date identifiers stay strings.
    assert _infer_kind(pd.Series(["O0001", "O0002"], dtype="str")) == "string"


def test_committed_contract_types_date_columns_as_datetime() -> None:
    contract = generate_contract(RAW, PROC)
    tables = {t["table_name"]: t for t in contract["tables"]}
    assert tables["orders"]["column_types"]["order_date"] == "datetime"
    assert tables["buyers"]["column_types"]["signup_date"] == "datetime"
    # Identifier columns remain strings.
    assert tables["orders"]["column_types"]["order_id"] == "string"


def test_generate_schema_contracts_cli_writes_file(tmp_path: Path, monkeypatch, capsys) -> None:
    out = tmp_path / "schema.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "generate_schema_contracts.py",
            "--raw-dir",
            str(RAW),
            "--processed-dir",
            str(PROC),
            "--output-file",
            str(out),
        ],
    )
    gsc_module.main()
    assert out.exists()
    import json

    contract = json.loads(out.read_text(encoding="utf-8"))
    assert contract["tables"]
    assert capsys.readouterr().out.strip()


# --- schema contracts -------------------------------------------------------
def test_generate_contract_covers_raw_and_processed_tables() -> None:
    contract = generate_contract(RAW, PROC)
    assert contract["contract_version"]
    tables = {t["table_name"]: t for t in contract["tables"]}
    assert "orders" in tables
    assert "order_profitability_features" in tables
    # Each table contract exposes typed columns and a primary-key candidate.
    orders = tables["orders"]
    assert "order_id" in orders["columns"]
    assert set(orders["column_types"]) == set(orders["columns"])
    assert "order_id" in orders["primary_key_candidate"]


@pytest.mark.parametrize(
    ("values", "expected_kind"),
    [
        ([1, 2, 3], "integer"),
        ([1.5, 2.5], "number"),
        ([True, False], "boolean"),
        (["a", "b", "c"], "string"),
    ],
)
def test_infer_kind(values, expected_kind) -> None:
    import pandas as pd

    assert _infer_kind(pd.Series(values)) == expected_kind


# --- governance action register ---------------------------------------------
@pytest.mark.parametrize(
    ("tier", "expected"),
    [("Critical", 2), ("High", 7), ("Moderate", 14), ("Low", 30), ("unknown", 30)],
)
def test_sla_days(tier: str, expected: int) -> None:
    assert _sla_days(tier) == expected


def test_owner_routing_has_sensible_defaults() -> None:
    assert _owner_from_seller_driver("totally unknown driver") == "Marketplace Governance"
    assert _owner_from_order_driver("totally unknown driver") == "Marketplace Operations"


def test_build_action_register_respects_caps_and_writes(tmp_path: Path) -> None:
    cfg = GovernanceConfig(processed_dir=PROC, output_dir=tmp_path, max_seller_actions=10, max_order_actions=15)
    register = build_action_register(cfg)
    assert not register.empty
    sellers = register[register["entity_type"] == "seller"]
    orders = register[register["entity_type"] == "order"]
    assert len(sellers) <= 10
    assert len(orders) <= 15
    # Every action carries an owning team and an SLA derived from its tier.
    assert register["owner_team"].notna().all()
    assert (register["sla_days"] > 0).all()

    out = save_action_register(register, tmp_path)
    assert out.exists()


# --- executive snapshot ------------------------------------------------------
def test_generate_snapshot_writes_csv_and_markdown(tmp_path: Path) -> None:
    cfg = ExecutiveSnapshotConfig(raw_dir=RAW, processed_dir=PROC, reports_dir=tmp_path)
    csv_path, md_path = generate_snapshot(cfg)
    assert csv_path.exists() and csv_path.suffix == ".csv"
    assert md_path.exists() and md_path.suffix == ".md"
    assert md_path.read_text(encoding="utf-8").strip()
