from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist
from typing import TypedDict, cast

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ExperimentConfig:
    processed_dir: Path = Path("data/processed")
    policy_file: Path = Path("config/contracts/v1/experiment_policy.json")
    output_dir: Path = Path("data/processed")


class ExperimentPolicy(TypedDict):
    allocation_rate: float
    alpha: float
    analysis_unit: str
    assignment_salt: str
    eligibility_score_threshold: float
    eligibility_window_days: int
    experiment_id: str
    manual_review_cost: float
    minimum_detectable_effect_pp: float
    policy_version: str
    power: float
    simulated_prevention_efficacy: float
    treatment: str


def _load_policy(path: Path) -> ExperimentPolicy:
    policy = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "allocation_rate",
        "alpha",
        "analysis_unit",
        "assignment_salt",
        "eligibility_score_threshold",
        "eligibility_window_days",
        "experiment_id",
        "manual_review_cost",
        "minimum_detectable_effect_pp",
        "policy_version",
        "power",
        "simulated_prevention_efficacy",
        "treatment",
    }
    missing = sorted(required - set(policy))
    if missing:
        raise ValueError(f"Experiment policy is missing fields: {missing}")
    unit_interval_fields = [
        "allocation_rate",
        "alpha",
        "power",
        "simulated_prevention_efficacy",
    ]
    if any(not 0 < float(policy[name]) < 1 for name in unit_interval_fields):
        raise ValueError("Allocation, alpha, power, and efficacy must be between zero and one.")
    if float(policy["minimum_detectable_effect_pp"]) <= 0:
        raise ValueError("Minimum detectable effect must be positive.")
    return cast(ExperimentPolicy, policy)


def _deterministic_uniform(value: str) -> float:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:16], 16) / 16**16


def _build_assignments(
    scores: pd.DataFrame,
    calibrated: pd.DataFrame,
    profitability: pd.DataFrame,
    policy: ExperimentPolicy,
) -> pd.DataFrame:
    base = scores[
        [
            "order_id",
            "order_date",
            "seller_id",
            "category",
            "order_channel",
            "order_risk_score",
        ]
    ].merge(
        calibrated[["order_id", "calibrated_probability"]],
        on="order_id",
        how="left",
        validate="one_to_one",
    )
    base = base.merge(
        profitability[
            [
                "order_id",
                "gross_value",
                "net_value",
                "refund_amount",
                "dispute_amount",
                "chargeback_loss_proxy",
            ]
        ],
        on="order_id",
        how="left",
        validate="one_to_one",
    )
    if base.isna().any().any():
        raise ValueError("Experiment inputs contain nulls after joining at order grain.")
    base["order_date"] = pd.to_datetime(base["order_date"], errors="raise")
    cutoff = base["order_date"].max() - pd.Timedelta(days=int(policy["eligibility_window_days"]))
    eligible = base[
        (base["order_date"] >= cutoff) & (base["order_risk_score"] >= float(policy["eligibility_score_threshold"]))
    ].copy()
    if eligible.empty:
        raise ValueError("No orders meet the experiment eligibility policy.")

    experiment_id = str(policy["experiment_id"])
    salt = str(policy["assignment_salt"])
    eligible["assignment_uniform"] = eligible["order_id"].map(
        lambda value: _deterministic_uniform(f"{experiment_id}|{salt}|assignment|{value}")
    )
    eligible["treatment_flag"] = (eligible["assignment_uniform"] < float(policy["allocation_rate"])).astype(int)
    eligible["assigned_arm"] = np.where(eligible["treatment_flag"].eq(1), str(policy["treatment"]), "business_as_usual")
    eligible["baseline_adverse_flag"] = (
        (eligible["refund_amount"] > 0) | (eligible["dispute_amount"] > 0) | (eligible["chargeback_loss_proxy"] > 0)
    ).astype(int)
    eligible["baseline_adverse_loss"] = (
        eligible["refund_amount"] + eligible["dispute_amount"] + eligible["chargeback_loss_proxy"]
    ).round(2)
    eligible["prevention_uniform"] = eligible["order_id"].map(
        lambda value: _deterministic_uniform(f"{experiment_id}|{salt}|prevention|{value}")
    )
    eligible["simulated_prevention_flag"] = (
        eligible["treatment_flag"].eq(1)
        & eligible["baseline_adverse_flag"].eq(1)
        & (eligible["prevention_uniform"] < float(policy["simulated_prevention_efficacy"]))
    ).astype(int)
    eligible["observed_adverse_flag"] = eligible["baseline_adverse_flag"] - eligible["simulated_prevention_flag"]
    eligible["observed_adverse_loss"] = (
        eligible["baseline_adverse_loss"] * (1 - eligible["simulated_prevention_flag"])
        + eligible["treatment_flag"] * float(policy["manual_review_cost"])
    ).round(2)
    eligible["experiment_id"] = experiment_id
    eligible["experiment_policy_version"] = str(policy["policy_version"])
    eligible["evidence_scope"] = "synthetic_randomized_trial"
    return eligible.sort_values(["order_date", "order_id"]).reset_index(drop=True)


def _standardized_mean_difference(treatment: pd.Series, control: pd.Series) -> float:
    pooled_variance = (float(treatment.var(ddof=1)) + float(control.var(ddof=1))) / 2
    if pooled_variance <= 0 or not np.isfinite(pooled_variance):
        return 0.0
    return (float(treatment.mean()) - float(control.mean())) / math.sqrt(pooled_variance)


def _build_balance(assignments: pd.DataFrame) -> pd.DataFrame:
    treated = assignments[assignments["treatment_flag"] == 1]
    control = assignments[assignments["treatment_flag"] == 0]
    rows: list[dict[str, object]] = []
    for covariate in [
        "order_risk_score",
        "calibrated_probability",
        "gross_value",
        "net_value",
    ]:
        smd = _standardized_mean_difference(treated[covariate], control[covariate])
        rows.append(
            {
                "covariate": covariate,
                "control_mean": float(control[covariate].mean()),
                "treatment_mean": float(treated[covariate].mean()),
                "standardized_mean_difference": smd,
                "absolute_standardized_mean_difference": abs(smd),
                "balance_status": "passed" if abs(smd) < 0.1 else "review",
            }
        )
    for covariate in ["category", "order_channel"]:
        for level in sorted(assignments[covariate].astype(str).unique()):
            treatment_indicator = treated[covariate].astype(str).eq(level).astype(float)
            control_indicator = control[covariate].astype(str).eq(level).astype(float)
            smd = _standardized_mean_difference(treatment_indicator, control_indicator)
            rows.append(
                {
                    "covariate": f"{covariate}={level}",
                    "control_mean": float(control_indicator.mean()),
                    "treatment_mean": float(treatment_indicator.mean()),
                    "standardized_mean_difference": smd,
                    "absolute_standardized_mean_difference": abs(smd),
                    "balance_status": "passed" if abs(smd) < 0.1 else "review",
                }
            )
    return pd.DataFrame(rows)


def _clustered_difference(outcome: pd.Series, treatment: pd.Series, clusters: pd.Series) -> dict[str, float]:
    y = outcome.to_numpy(dtype=float)
    t = treatment.to_numpy(dtype=float)
    design = np.column_stack([np.ones(len(y)), t])
    bread = np.linalg.inv(design.T @ design)
    beta = bread @ design.T @ y
    residual = y - design @ beta
    meat = np.zeros((2, 2), dtype=float)
    unique_clusters = clusters.astype(str).unique()
    for cluster in unique_clusters:
        mask = clusters.astype(str).eq(cluster).to_numpy()
        cluster_score = design[mask].T @ residual[mask]
        meat += np.outer(cluster_score, cluster_score)
    cluster_count = len(unique_clusters)
    if cluster_count <= 1:
        raise ValueError("Cluster-robust inference requires at least two sellers.")
    sample_size, parameter_count = design.shape
    correction = (cluster_count / (cluster_count - 1)) * ((sample_size - 1) / (sample_size - parameter_count))
    variance = correction * bread @ meat @ bread
    standard_error = math.sqrt(max(float(variance[1, 1]), 0.0))
    estimate = float(beta[1])
    z_statistic = estimate / standard_error if standard_error > 0 else float("nan")
    p_value = math.erfc(abs(z_statistic) / math.sqrt(2)) if np.isfinite(z_statistic) else float("nan")
    critical = NormalDist().inv_cdf(0.975)
    return {
        "estimate": estimate,
        "clustered_standard_error": standard_error,
        "confidence_interval_lower": estimate - critical * standard_error,
        "confidence_interval_upper": estimate + critical * standard_error,
        "p_value": p_value,
        "seller_cluster_count": float(cluster_count),
    }


def _build_results(assignments: pd.DataFrame, balance: pd.DataFrame, policy: ExperimentPolicy) -> pd.DataFrame:
    treatment = assignments["treatment_flag"]
    clusters = assignments["seller_id"]
    outcome_specs = [
        ("adverse_event_rate", "observed_adverse_flag", 100.0, "percentage_points"),
        ("adverse_loss_per_order", "observed_adverse_loss", 1.0, "USD_per_order"),
    ]
    rows: list[dict[str, object]] = []
    for metric, column, scale, unit in outcome_specs:
        inference = _clustered_difference(assignments[column], treatment, clusters)
        control_mean = float(assignments.loc[treatment.eq(0), column].mean()) * scale
        treatment_mean = float(assignments.loc[treatment.eq(1), column].mean()) * scale
        rows.append(
            {
                "experiment_id": str(policy["experiment_id"]),
                "metric": metric,
                "control_mean": control_mean,
                "treatment_mean": treatment_mean,
                "intention_to_treat_effect": inference["estimate"] * scale,
                "clustered_standard_error": inference["clustered_standard_error"] * scale,
                "confidence_interval_lower": inference["confidence_interval_lower"] * scale,
                "confidence_interval_upper": inference["confidence_interval_upper"] * scale,
                "p_value": inference["p_value"],
                "unit": unit,
                "seller_cluster_count": int(inference["seller_cluster_count"]),
                "sample_size": len(assignments),
                "control_rows": int(treatment.eq(0).sum()),
                "treatment_rows": int(treatment.eq(1).sum()),
                "maximum_absolute_balance_smd": float(balance["absolute_standardized_mean_difference"].max()),
                "evidence_scope": "synthetic_randomized_trial",
                "operational_decision_status": "not approved",
            }
        )
    return pd.DataFrame(rows)


def _build_power(assignments: pd.DataFrame, policy: ExperimentPolicy) -> pd.DataFrame:
    alpha = float(policy["alpha"])
    target_power = float(policy["power"])
    delta = float(policy["minimum_detectable_effect_pp"]) / 100
    control_rate = float(assignments.loc[assignments["treatment_flag"].eq(0), "baseline_adverse_flag"].mean())
    alternative_rate = float(np.clip(control_rate - delta, 1e-6, 1 - 1e-6))
    pooled_rate = (control_rate + alternative_rate) / 2
    z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
    z_power = NormalDist().inv_cdf(target_power)
    variance_term = max(2 * pooled_rate * (1 - pooled_rate), 1e-9)
    required_per_arm = math.ceil(variance_term * (z_alpha + z_power) ** 2 / delta**2)
    observed_per_arm = int(assignments["treatment_flag"].value_counts().min())
    achieved_z = math.sqrt(observed_per_arm * delta**2 / variance_term) - z_alpha
    achieved_power = NormalDist().cdf(achieved_z)
    return pd.DataFrame(
        [
            {
                "experiment_id": str(policy["experiment_id"]),
                "alpha": alpha,
                "target_power": target_power,
                "minimum_detectable_effect_pp": float(policy["minimum_detectable_effect_pp"]),
                "control_baseline_rate": control_rate,
                "required_rows_per_arm": required_per_arm,
                "observed_minimum_rows_per_arm": observed_per_arm,
                "estimated_power_at_mde": achieved_power,
                "power_status": ("passed" if observed_per_arm >= required_per_arm else "underpowered"),
            }
        ]
    )


def _build_heterogeneity(assignments: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for dimension in ["category", "order_channel"]:
        for segment, selected in assignments.groupby(dimension, sort=True):
            control = selected[selected["treatment_flag"].eq(0)]
            treated = selected[selected["treatment_flag"].eq(1)]
            if control.empty or treated.empty:
                continue
            control_rate = float(control["observed_adverse_flag"].mean())
            treatment_rate = float(treated["observed_adverse_flag"].mean())
            rows.append(
                {
                    "dimension": dimension,
                    "segment": segment,
                    "row_count": len(selected),
                    "control_rows": len(control),
                    "treatment_rows": len(treated),
                    "control_adverse_rate": control_rate,
                    "treatment_adverse_rate": treatment_rate,
                    "intention_to_treat_effect_pp": 100 * (treatment_rate - control_rate),
                    "evidence_scope": "exploratory_synthetic_randomized_trial",
                }
            )
    return pd.DataFrame(rows)


def build_experiment_outputs(cfg: ExperimentConfig) -> dict[str, pd.DataFrame]:
    policy = _load_policy(cfg.policy_file)
    scores = pd.read_csv(cfg.processed_dir / "order_risk_scores.csv", parse_dates=["order_date"])
    calibrated = pd.read_csv(cfg.processed_dir / "order_risk_calibrated.csv")
    profitability = pd.read_csv(cfg.processed_dir / "order_profitability_features.csv")
    assignments = _build_assignments(scores, calibrated, profitability, policy)
    balance = _build_balance(assignments)
    results = _build_results(assignments, balance, policy)
    power = _build_power(assignments, policy)
    heterogeneity = _build_heterogeneity(assignments)
    return {
        "experiment_assignments": assignments,
        "experiment_balance": balance,
        "experiment_results": results,
        "experiment_power": power,
        "experiment_heterogeneity": heterogeneity,
    }


def save_outputs(outputs: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in outputs.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the deterministic synthetic controlled intervention trial.")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=Path("config/contracts/v1/experiment_policy.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    cfg = ExperimentConfig(
        processed_dir=args.processed_dir,
        policy_file=args.policy_file,
        output_dir=args.output_dir,
    )
    outputs = build_experiment_outputs(cfg)
    save_outputs(outputs, cfg.output_dir)
    print("Controlled experiment outputs generated:")
    for name, frame in outputs.items():
        print(f"  - {name}: {len(frame):,} rows")


if __name__ == "__main__":
    main()
