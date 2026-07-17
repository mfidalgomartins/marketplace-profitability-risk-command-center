from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pypdf import PdfReader
from src.experimentation.run_controlled_experiment import (
    ExperimentConfig,
    _clustered_difference,
    _deterministic_uniform,
    build_experiment_outputs,
)
from src.experimentation.run_controlled_experiment import (
    _load_policy as load_experiment_policy,
)
from src.experimentation.run_controlled_experiment import (
    save_outputs as save_experiment_outputs,
)
from src.finance.build_accounting_pnl import (
    FinanceConfig,
    build_finance_outputs,
)
from src.finance.build_accounting_pnl import (
    _load_policy as load_finance_policy,
)
from src.finance.build_accounting_pnl import (
    save_outputs as save_finance_outputs,
)
from src.model_validation.run_temporal_validation import (
    TemporalValidationConfig,
    _average_precision,
    _population_stability_index,
    _roc_auc,
    build_temporal_validation_outputs,
)
from src.model_validation.run_temporal_validation import (
    _load_policy as load_model_policy,
)
from src.model_validation.run_temporal_validation import (
    save_outputs as save_model_outputs,
)
from src.visualization.build_accessible_report import (
    AccessibleReportConfig,
    build_accessible_report,
)
from src.warehouse.build_duckdb_warehouse import (
    WarehouseConfig,
    _safe_identifier,
    build_warehouse,
)

ROOT = Path(__file__).resolve().parents[1]


def test_temporal_validation_uses_matured_holdout_and_shadow(tmp_path: Path) -> None:
    outputs = build_temporal_validation_outputs(
        TemporalValidationConfig(
            raw_dir=ROOT / "data/raw",
            processed_dir=ROOT / "data/processed",
            policy_file=ROOT / "config/contracts/v1/model_monitoring_policy.json",
        )
    )
    calibrated = outputs["order_risk_calibrated"]
    assert set(calibrated["split"]) == {
        "development",
        "maturation_gap",
        "holdout",
        "shadow_unmatured",
    }
    metrics = outputs["temporal_holdout_metrics"]
    assert set(metrics["split"]) == {"development", "maturation_gap", "holdout"}
    assert metrics["roc_auc"].between(0, 1).all()
    release = outputs["model_release_assessment"].iloc[0]
    assert release["automated_decision_status"] == "not approved"
    assert int(release["unmatured_shadow_rows"]) > 0
    assert outputs["model_calibration_parameters"].iloc[0]["slope"] > 0
    save_model_outputs(outputs, tmp_path)
    assert (tmp_path / "model_release_assessment.csv").exists()


def test_model_metric_helpers_and_policy_validation(tmp_path: Path) -> None:
    y = np.array([0, 1, 0, 1])
    score = np.array([0.1, 0.9, 0.2, 0.8])
    assert _roc_auc(y, score) == 1.0
    assert _average_precision(y, score) == 1.0
    edges = np.array([-np.inf, 0.5, np.inf])
    reference = pd.Series([0.1, 0.2, 0.8, 0.9])
    assert _population_stability_index(reference, reference, edges) == pytest.approx(0.0)

    invalid = tmp_path / "invalid-model-policy.json"
    invalid.write_text(json.dumps({"calibration_bins": 2}), encoding="utf-8")
    with pytest.raises(ValueError, match="missing fields"):
        load_model_policy(invalid)


def test_finance_outputs_reconcile_to_order_subledger(tmp_path: Path) -> None:
    outputs = build_finance_outputs(
        FinanceConfig(
            processed_dir=ROOT / "data/processed",
            policy_file=ROOT / "config/contracts/v1/finance_policy.json",
        )
    )
    order_pnl = outputs["order_accounting_pnl"]
    general_ledger = outputs["finance_general_ledger"]
    assert order_pnl["order_id"].is_unique
    assert general_ledger["debit"].sum() == pytest.approx(general_ledger["credit"].sum())
    assert outputs["finance_reconciliation"]["status"].eq("passed").all()
    assert outputs["accounting_kpi_summary"].iloc[0]["accounting_basis"].startswith("synthetic_")
    save_finance_outputs(outputs, tmp_path)
    assert (tmp_path / "finance_general_ledger.csv").exists()


def test_finance_policy_rejects_negative_rates(tmp_path: Path) -> None:
    policy = json.loads((ROOT / "config/contracts/v1/finance_policy.json").read_text(encoding="utf-8"))
    policy["payment_variable_rate"] = -0.1
    path = tmp_path / "invalid-finance-policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="non-negative"):
        load_finance_policy(path)


def test_controlled_experiment_is_balanced_powered_and_explicitly_synthetic(
    tmp_path: Path,
) -> None:
    outputs = build_experiment_outputs(
        ExperimentConfig(
            processed_dir=ROOT / "data/processed",
            policy_file=ROOT / "config/contracts/v1/experiment_policy.json",
        )
    )
    assignments = outputs["experiment_assignments"]
    assert assignments["order_id"].is_unique
    assert set(assignments["assigned_arm"]) == {
        "business_as_usual",
        "enhanced_manual_review",
    }
    assert outputs["experiment_balance"]["absolute_standardized_mean_difference"].max() < 0.1
    assert outputs["experiment_power"].iloc[0]["power_status"] == "passed"
    results = outputs["experiment_results"]
    assert results["evidence_scope"].eq("synthetic_randomized_trial").all()
    assert results["operational_decision_status"].eq("not approved").all()
    assert _deterministic_uniform("same-order") == _deterministic_uniform("same-order")
    save_experiment_outputs(outputs, tmp_path)
    assert (tmp_path / "experiment_results.csv").exists()


def test_clustered_experiment_inference_and_policy_validation(tmp_path: Path) -> None:
    inference = _clustered_difference(
        pd.Series([0.0, 1.0, 0.0, 1.0, 1.0, 1.0]),
        pd.Series([0, 0, 0, 1, 1, 1]),
        pd.Series(["a", "a", "b", "c", "c", "d"]),
    )
    assert inference["estimate"] > 0
    assert inference["seller_cluster_count"] == 4

    policy = json.loads((ROOT / "config/contracts/v1/experiment_policy.json").read_text(encoding="utf-8"))
    policy["allocation_rate"] = 1.0
    path = tmp_path / "invalid-experiment-policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="between zero and one"):
        load_experiment_policy(path)


def _write_warehouse_fixture(raw_dir: Path, processed_dir: Path) -> None:
    raw_dir.mkdir(parents=True)
    processed_dir.mkdir(parents=True)
    pd.DataFrame([{"order_id": "O1", "order_date": "2026-01-01 10:00:00"}]).to_csv(raw_dir / "orders.csv", index=False)
    pd.DataFrame(
        [
            {
                "order_id": "O1",
                "order_date": "2026-01-01 10:00:00",
                "buyer_id": "B1",
                "seller_id": "S1",
                "category": "Home",
                "order_channel": "web",
                "payment_method": "card",
                "order_risk_score": 70.0,
                "order_risk_tier": "High",
            }
        ]
    ).to_csv(processed_dir / "order_risk_scores.csv", index=False)
    pd.DataFrame([{"order_id": "O1", "calibrated_probability": 0.5, "split": "holdout"}]).to_csv(
        processed_dir / "order_risk_calibrated.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "order_id": "O1",
                "gross_value": 100.0,
                "net_value": 90.0,
                "accounting_contribution": 5.0,
                "finance_policy_version": "1.0.0",
                "gross_commission_revenue": 10.0,
                "commission_reversal": 0.0,
                "order_date": "2026-01-01 10:00:00",
            }
        ]
    ).to_csv(processed_dir / "order_accounting_pnl.csv", index=False)
    pd.DataFrame([{"seller_id": "S1", "score": 70.0}]).to_csv(processed_dir / "seller_scorecard.csv", index=False)
    pd.DataFrame(
        [
            {
                "entity_type": "seller",
                "entity_id": "S1",
                "owner_team": "Risk",
                "sla_days": 2,
                "status": "open",
                "next_review_step": "review",
            }
        ]
    ).to_csv(processed_dir / "governance_action_register.csv", index=False)
    pd.DataFrame([{"month": "2026-01", "roc_auc": 0.7}]).to_csv(
        processed_dir / "model_monitoring_monthly.csv", index=False
    )
    pd.DataFrame([{"metric": "adverse_event_rate", "effect": -1.0}]).to_csv(
        processed_dir / "experiment_results.csv", index=False
    )
    pd.DataFrame([{"check_name": "balanced", "status": "passed"}]).to_csv(
        processed_dir / "finance_reconciliation.csv", index=False
    )


def test_duckdb_warehouse_is_idempotent_and_validated(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    _write_warehouse_fixture(raw_dir, processed_dir)
    cfg = WarehouseConfig(
        raw_dir=raw_dir,
        processed_dir=processed_dir,
        database_file=tmp_path / "warehouse.duckdb",
        manifest_file=tmp_path / "warehouse_manifest.csv",
        validation_file=tmp_path / "warehouse_validation.csv",
    )
    first_manifest, first_validation = build_warehouse(cfg)
    second_manifest, second_validation = build_warehouse(cfg)
    pd.testing.assert_frame_equal(first_manifest, second_manifest)
    pd.testing.assert_frame_equal(first_validation, second_validation)
    assert first_validation["status"].eq("passed").all()
    assert cfg.database_file.exists()
    with pytest.raises(ValueError, match="Unsafe warehouse identifier"):
        _safe_identifier("unsafe-table")


def test_accessible_pdf_contains_tagged_structure(tmp_path: Path) -> None:
    output = tmp_path / "accessible-summary.pdf"
    cfg = AccessibleReportConfig(
        processed_dir=ROOT / "data/processed",
        reports_dir=ROOT / "reports",
        output_file=output,
    )
    pdf = build_accessible_report(cfg)
    assert build_accessible_report(cfg) == pdf
    assert output.read_bytes() == pdf
    reader = PdfReader(output)
    catalog = reader.trailer["/Root"]
    assert "/StructTreeRoot" in catalog
    assert bool(catalog["/MarkInfo"]["/Marked"])
    assert str(catalog["/Lang"]) == "en"
    assert len(pdf) > 20_000
