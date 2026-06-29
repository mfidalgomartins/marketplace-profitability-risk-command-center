from pathlib import Path

import pandas as pd
from src.validation import validate_metric_governance as mg_module
from src.validation.validate_metric_governance import MetricGovernanceConfig, validate_metric_governance

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROC = ROOT / "data" / "processed"
CONTRACT = ROOT / "config" / "contracts" / "v1" / "metric_governance_contract.csv"


def _contract_row(metric: str, lo: float, hi: float, tol: float = 0.01) -> dict:
    return {
        "metric_name": metric,
        "min_value": lo,
        "max_value": hi,
        "recompute_tolerance": tol,
        "severity_on_range": "High",
        "severity_on_recompute": "Critical",
    }


def test_metric_governance_contract_exists_and_has_core_metrics() -> None:
    contract_path = ROOT / "config" / "contracts" / "v1" / "metric_governance_contract.csv"
    assert contract_path.exists()

    contract = pd.read_csv(contract_path)
    required = {
        "gmv",
        "net_value",
        "risk_adjusted_value",
        "take_rate",
        "subsidy_share",
        "realized_contribution_margin_proxy",
        "expected_margin_after_risk",
        "refund_rate",
        "dispute_rate",
        "chargeback_rate",
        "top10_seller_gmv_share",
        "critical_sellers",
    }
    assert required.issubset(set(contract["metric_name"]))

    snapshot = pd.read_csv(ROOT / "reports" / "executive_kpi_snapshot.csv")
    assert set(snapshot["metric"]).issubset(set(contract["metric_name"]))


def test_metric_governance_validator_passes_on_current_outputs() -> None:
    cfg = MetricGovernanceConfig(
        raw_dir=ROOT / "data" / "raw",
        processed_dir=ROOT / "data" / "processed",
        reports_dir=ROOT / "reports",
        contract_file=ROOT / "config" / "contracts" / "v1" / "metric_governance_contract.csv",
        output_file=ROOT / "reports" / "metric_governance_issues.csv",
    )
    issues = validate_metric_governance(cfg)
    assert issues.empty


def test_missing_contract_is_critical(tmp_path: Path) -> None:
    cfg = MetricGovernanceConfig(
        raw_dir=RAW, processed_dir=PROC, reports_dir=tmp_path, contract_file=tmp_path / "absent.csv"
    )
    issues = validate_metric_governance(cfg)
    assert list(issues["check_name"]) == ["contract_file_exists"]
    assert issues.iloc[0]["severity"] == "Critical"


def test_missing_snapshot_is_critical(tmp_path: Path) -> None:
    contract = tmp_path / "contract.csv"
    pd.DataFrame([_contract_row("gmv", 0, 1e12)]).to_csv(contract, index=False)
    cfg = MetricGovernanceConfig(raw_dir=RAW, processed_dir=PROC, reports_dir=tmp_path, contract_file=contract)
    issues = validate_metric_governance(cfg)
    assert "snapshot_file_exists" in set(issues["check_name"])


def test_invalid_snapshot_schema_is_critical(tmp_path: Path) -> None:
    contract = tmp_path / "contract.csv"
    pd.DataFrame([_contract_row("gmv", 0, 1e12)]).to_csv(contract, index=False)
    # Snapshot present but with the wrong columns.
    pd.DataFrame({"wrong": [1], "cols": [2]}).to_csv(tmp_path / "executive_kpi_snapshot.csv", index=False)
    cfg = MetricGovernanceConfig(raw_dir=RAW, processed_dir=PROC, reports_dir=tmp_path, contract_file=contract)
    issues = validate_metric_governance(cfg)
    assert "snapshot_schema" in set(issues["check_name"])


def test_range_and_recompute_and_missing_metric_flagged(tmp_path: Path) -> None:
    contract = tmp_path / "contract.csv"
    pd.DataFrame(
        [
            _contract_row("gmv", 0.0, 1.0),  # real GMV is millions -> range + recompute breach
            _contract_row("not_a_real_metric", 0.0, 1.0),  # absent from snapshot -> missing
        ]
    ).to_csv(contract, index=False)
    # Snapshot supplies gmv outside the [0,1] range (and far from the real
    # recomputed millions) but omits the second metric entirely.
    pd.DataFrame({"metric": ["gmv"], "value": [5.0]}).to_csv(tmp_path / "executive_kpi_snapshot.csv", index=False)
    cfg = MetricGovernanceConfig(raw_dir=RAW, processed_dir=PROC, reports_dir=tmp_path, contract_file=contract)
    issues = validate_metric_governance(cfg)
    checks = set(issues["check_name"])
    assert "metric_range_check" in checks
    assert "recompute_consistency_check" in checks
    assert "snapshot_metric_exists" in checks


def test_metric_governance_cli_passes_on_current_outputs(tmp_path: Path, monkeypatch, capsys) -> None:
    out = tmp_path / "issues.csv"
    monkeypatch.setattr(
        "sys.argv",
        [
            "validate_metric_governance.py",
            "--raw-dir",
            str(RAW),
            "--processed-dir",
            str(PROC),
            "--reports-dir",
            str(ROOT / "reports"),
            "--contract-file",
            str(CONTRACT),
            "--output-file",
            str(out),
        ],
    )
    mg_module.main()
    assert out.exists()
    assert "PASSED" in capsys.readouterr().out
