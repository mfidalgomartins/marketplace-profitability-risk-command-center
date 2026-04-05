from pathlib import Path

import pandas as pd

from src.validation.validate_metric_governance import MetricGovernanceConfig, validate_metric_governance


ROOT = Path(__file__).resolve().parents[1]


def test_metric_governance_contract_exists_and_has_core_metrics() -> None:
    contract_path = ROOT / "schemas" / "v1" / "metric_governance_contract.csv"
    assert contract_path.exists()

    contract = pd.read_csv(contract_path)
    required = {
        "gmv",
        "net_value",
        "risk_adjusted_value",
        "take_rate",
        "subsidy_share",
        "realized_contribution_margin_proxy",
        "refund_rate",
        "dispute_rate",
        "critical_sellers",
    }
    assert required.issubset(set(contract["metric_name"]))


def test_metric_governance_validator_passes_on_current_outputs() -> None:
    cfg = MetricGovernanceConfig(
        raw_dir=ROOT / "data" / "raw",
        processed_dir=ROOT / "data" / "processed",
        reports_dir=ROOT / "reports",
        contract_file=ROOT / "schemas" / "v1" / "metric_governance_contract.csv",
        output_file=ROOT / "reports" / "metric_governance_issues.csv",
    )
    issues = validate_metric_governance(cfg)
    assert issues.empty

