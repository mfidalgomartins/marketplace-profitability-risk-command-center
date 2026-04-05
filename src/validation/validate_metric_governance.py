from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import pandas as pd


@dataclass
class MetricGovernanceIssue:
    metric_name: str
    check_name: str
    severity: str
    metric_value: str
    threshold: str
    detail: str


@dataclass(frozen=True)
class MetricGovernanceConfig:
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    reports_dir: Path = Path("reports")
    contract_file: Path = Path("schemas/v1/metric_governance_contract.csv")
    output_file: Path = Path("reports/metric_governance_issues.csv")


def _compute_metric_references(raw_dir: Path, processed_dir: Path) -> Dict[str, float]:
    orders = pd.read_csv(raw_dir / "orders.csv")
    opf = pd.read_csv(processed_dir / "order_profitability_features.csv")
    seller_scorecard = pd.read_csv(processed_dir / "seller_scorecard.csv")

    gmv = float(opf["gross_value"].sum())
    net_value = float(opf["net_value"].sum())
    out = {
        "gmv": gmv,
        "net_value": net_value,
        "risk_adjusted_value": float(opf["risk_adjusted_order_value"].sum()),
        "take_rate": float(opf["commission_fee"].sum() / gmv) if gmv else 0.0,
        "subsidy_share": float(opf["subsidy_amount"].sum() / gmv) if gmv else 0.0,
        "realized_contribution_margin_proxy": float(opf["realized_contribution_margin_proxy"].sum()),
        "refund_rate": float((opf["refund_amount"] > 0).mean()),
        "dispute_rate": float((opf["dispute_amount"] > 0).mean()),
        "critical_sellers": float((seller_scorecard["governance_priority_tier"] == "Critical").sum()),
    }

    # Relationship checks are material governance checks even if not explicitly in snapshot contract.
    out["relationship__risk_adjusted_le_net"] = float(out["risk_adjusted_value"] <= out["net_value"] + 1e-9)
    out["relationship__net_le_gmv"] = float(out["net_value"] <= out["gmv"] + 1e-9)
    out["relationship__rates_within_unit_interval"] = float(
        0.0 <= out["refund_rate"] <= 1.0 and 0.0 <= out["dispute_rate"] <= 1.0
    )
    out["relationship__opf_order_grain"] = float(len(opf) == int(opf["order_id"].nunique()))
    out["relationship__raw_order_count_positive"] = float(len(orders) > 0)
    return out


def validate_metric_governance(cfg: MetricGovernanceConfig) -> pd.DataFrame:
    issues: List[MetricGovernanceIssue] = []

    if not cfg.contract_file.exists():
        issues.append(
            MetricGovernanceIssue(
                metric_name="contract",
                check_name="contract_file_exists",
                severity="Critical",
                metric_value="missing",
                threshold="present",
                detail=f"Metric governance contract missing: {cfg.contract_file}",
            )
        )
        return pd.DataFrame([i.__dict__ for i in issues])

    snapshot_path = cfg.reports_dir / "executive_kpi_snapshot.csv"
    if not snapshot_path.exists():
        issues.append(
            MetricGovernanceIssue(
                metric_name="executive_kpi_snapshot",
                check_name="snapshot_file_exists",
                severity="Critical",
                metric_value="missing",
                threshold="present",
                detail=f"Governed KPI snapshot missing: {snapshot_path}",
            )
        )
        return pd.DataFrame([i.__dict__ for i in issues])

    contract = pd.read_csv(cfg.contract_file)
    snapshot = pd.read_csv(snapshot_path)
    if not {"metric", "value"}.issubset(snapshot.columns):
        issues.append(
            MetricGovernanceIssue(
                metric_name="executive_kpi_snapshot",
                check_name="snapshot_schema",
                severity="Critical",
                metric_value="invalid columns",
                threshold="metric,value",
                detail="Executive KPI snapshot schema is invalid for governance checks.",
            )
        )
        return pd.DataFrame([i.__dict__ for i in issues])

    snapshot_map = {str(r["metric"]): float(r["value"]) for _, r in snapshot.iterrows() if pd.notna(r["value"])}
    recomputed = _compute_metric_references(cfg.raw_dir, cfg.processed_dir)

    for _, row in contract.iterrows():
        metric = str(row["metric_name"])
        min_value = float(row["min_value"])
        max_value = float(row["max_value"])
        tol = float(row["recompute_tolerance"])
        sev_range = str(row["severity_on_range"])
        sev_recompute = str(row["severity_on_recompute"])

        if metric not in snapshot_map:
            issues.append(
                MetricGovernanceIssue(
                    metric_name=metric,
                    check_name="snapshot_metric_exists",
                    severity="High",
                    metric_value="missing",
                    threshold="present",
                    detail=f"Metric `{metric}` missing from executive snapshot.",
                )
            )
            continue

        observed = float(snapshot_map[metric])
        if observed < min_value or observed > max_value:
            issues.append(
                MetricGovernanceIssue(
                    metric_name=metric,
                    check_name="metric_range_check",
                    severity=sev_range,
                    metric_value=f"{observed:.12g}",
                    threshold=f"[{min_value:.12g}, {max_value:.12g}]",
                    detail=f"Metric `{metric}` is outside governed range.",
                )
            )

        if metric in recomputed:
            expected = recomputed[metric]
            rel_diff = abs(observed - expected) / max(1.0, abs(expected))
            if rel_diff > tol:
                issues.append(
                    MetricGovernanceIssue(
                        metric_name=metric,
                        check_name="recompute_consistency_check",
                        severity=sev_recompute,
                        metric_value=f"relative_diff={rel_diff:.6e}",
                        threshold=f"<= {tol:.6e}",
                        detail=f"Metric `{metric}` does not reconcile to governed recomputation.",
                    )
                )

    # Additional relationship checks.
    relationship_checks = [
        ("relationship__risk_adjusted_le_net", "Critical", "risk_adjusted_value <= net_value"),
        ("relationship__net_le_gmv", "Critical", "net_value <= gmv"),
        ("relationship__rates_within_unit_interval", "High", "refund_rate and dispute_rate in [0,1]"),
        ("relationship__opf_order_grain", "Critical", "order_profitability_features at unique order grain"),
        ("relationship__raw_order_count_positive", "Critical", "raw orders row count > 0"),
    ]
    for key, sev, thr in relationship_checks:
        if recomputed.get(key, 0.0) < 0.5:
            issues.append(
                MetricGovernanceIssue(
                    metric_name=key,
                    check_name="relationship_check",
                    severity=sev,
                    metric_value="False",
                    threshold=thr,
                    detail=f"Metric governance relationship failed: {thr}.",
                )
            )

    if issues:
        return pd.DataFrame([i.__dict__ for i in issues])
    return pd.DataFrame(columns=["metric_name", "check_name", "severity", "metric_value", "threshold", "detail"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate governed KPI metrics and reconciliation contracts.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--contract-file", type=Path, default=Path("schemas/v1/metric_governance_contract.csv"))
    parser.add_argument("--output-file", type=Path, default=Path("reports/metric_governance_issues.csv"))
    args = parser.parse_args()

    cfg = MetricGovernanceConfig(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        reports_dir=args.reports_dir,
        contract_file=args.contract_file,
        output_file=args.output_file,
    )
    issues = validate_metric_governance(cfg)
    cfg.output_file.parent.mkdir(parents=True, exist_ok=True)
    issues.to_csv(cfg.output_file, index=False)

    if issues.empty:
        print("Metric governance: PASSED")
    else:
        print(f"Metric governance: FAILED with {len(issues)} issue(s). See {cfg.output_file}")


if __name__ == "__main__":
    main()
