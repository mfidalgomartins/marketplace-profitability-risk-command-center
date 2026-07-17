from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TemporalValidationConfig:
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    policy_file: Path = Path("config/contracts/v1/model_monitoring_policy.json")
    output_dir: Path = Path("data/processed")


class ReleaseThresholds(TypedDict):
    maximum_brier_score: float
    maximum_expected_calibration_error: float
    maximum_population_stability_index: float
    minimum_average_precision_lift: float
    minimum_roc_auc: float


class ModelMonitoringPolicy(TypedDict):
    calibration_bins: int
    holdout_days: int
    minimum_development_rows: int
    minimum_holdout_rows: int
    outcome_maturation_lag_days: int
    policy_version: str
    release_thresholds: ReleaseThresholds
    shadow_window_months: int


OUTPUT_COLUMNS = {
    "model_monitoring_alerts": [
        "alert_id",
        "month",
        "metric",
        "observed_value",
        "threshold",
        "severity",
        "recommended_action",
    ]
}


def _load_policy(path: Path) -> ModelMonitoringPolicy:
    policy = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "calibration_bins",
        "holdout_days",
        "minimum_development_rows",
        "minimum_holdout_rows",
        "outcome_maturation_lag_days",
        "release_thresholds",
        "shadow_window_months",
    }
    missing = sorted(required - set(policy))
    if missing:
        raise ValueError(f"Model monitoring policy is missing fields: {missing}")
    if int(policy["calibration_bins"]) < 3:
        raise ValueError("calibration_bins must be at least 3.")
    if int(policy["holdout_days"]) <= 0 or int(policy["outcome_maturation_lag_days"]) < 0:
        raise ValueError("Holdout days must be positive and maturation lag must be non-negative.")
    return cast(ModelMonitoringPolicy, policy)


def _build_base(cfg: TemporalValidationConfig) -> pd.DataFrame:
    scores = pd.read_csv(cfg.processed_dir / "order_risk_scores.csv", parse_dates=["order_date"])
    opf = pd.read_csv(cfg.processed_dir / "order_profitability_features.csv")
    payments = pd.read_csv(cfg.raw_dir / "payments.csv")
    base = scores[["order_id", "order_date", "order_risk_score"]].merge(
        opf[["order_id", "refund_amount", "dispute_amount"]],
        on="order_id",
        how="left",
        validate="one_to_one",
    )
    base = base.merge(
        payments[["order_id", "chargeback_flag"]],
        on="order_id",
        how="left",
        validate="one_to_one",
    )
    if base[["refund_amount", "dispute_amount", "chargeback_flag"]].isna().any().any():
        raise ValueError("Outcome fields contain nulls after the validation join.")
    base["adverse_flag"] = (
        (base["refund_amount"] > 0) | (base["dispute_amount"] > 0) | base["chargeback_flag"].eq(1)
    ).astype(int)
    return base.sort_values(["order_date", "order_id"]).reset_index(drop=True)


def _roc_auc(y_true: np.ndarray, score: np.ndarray) -> float:
    positives = int(y_true.sum())
    negatives = int(len(y_true) - positives)
    if positives == 0 or negatives == 0:
        return float("nan")
    ranks = pd.Series(score).rank(method="average").to_numpy()
    positive_rank_sum = float(ranks[y_true == 1].sum())
    return (positive_rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def _average_precision(y_true: np.ndarray, score: np.ndarray) -> float:
    positives = int(y_true.sum())
    if positives == 0:
        return float("nan")
    order = np.argsort(-score, kind="mergesort")
    ordered = y_true[order]
    precision = np.cumsum(ordered) / np.arange(1, len(ordered) + 1)
    return float(precision[ordered == 1].sum() / positives)


def _fit_logistic_calibrator(score: np.ndarray, outcome: np.ndarray) -> tuple[float, float, float, float]:
    score_mean = float(score.mean())
    score_std = float(score.std(ddof=0))
    if score_std <= 0:
        raise ValueError("Development scores have zero variance; calibration is not identifiable.")
    standardized = (score - score_mean) / score_std
    design = np.column_stack([np.ones(len(score)), standardized])
    event_rate = float(np.clip(outcome.mean(), 1e-6, 1 - 1e-6))
    beta = np.array([np.log(event_rate / (1 - event_rate)), 0.0], dtype=float)
    ridge = np.diag([1e-10, 1e-8])

    for _ in range(100):
        probability = 1.0 / (1.0 + np.exp(-np.clip(design @ beta, -35.0, 35.0)))
        weights = np.clip(probability * (1 - probability), 1e-8, None)
        information = design.T @ (weights[:, None] * design) + ridge
        score_vector = design.T @ (outcome - probability)
        step = np.linalg.solve(information, score_vector)
        beta += step
        if float(np.max(np.abs(step))) < 1e-10:
            break

    if beta[1] <= 0:
        raise ValueError("Fitted calibration slope is not positive.")
    return float(beta[0]), float(beta[1]), score_mean, score_std


def _calibrated_probability(
    score: np.ndarray,
    intercept: float,
    slope: float,
    score_mean: float,
    score_std: float,
) -> np.ndarray:
    linear = intercept + slope * ((score - score_mean) / score_std)
    return 1.0 / (1.0 + np.exp(-np.clip(linear, -35.0, 35.0)))


def _quantile_edges(values: pd.Series, bins: int) -> np.ndarray:
    edges = np.unique(values.quantile(np.linspace(0, 1, bins + 1)).to_numpy(dtype=float))
    if len(edges) < 4:
        raise ValueError("Insufficient unique values to create monitoring bins.")
    edges[0] = -np.inf
    edges[-1] = np.inf
    return edges


def _calibration_table(base: pd.DataFrame, edges: np.ndarray) -> pd.DataFrame:
    work = base.copy()
    work["calibration_bin"] = pd.cut(work["calibrated_probability"], bins=edges, labels=False, include_lowest=True)
    rows = (
        work.groupby(["split", "calibration_bin"], observed=True)
        .agg(
            row_count=("order_id", "size"),
            predicted_probability=("calibrated_probability", "mean"),
            observed_event_rate=("adverse_flag", "mean"),
            minimum_probability=("calibrated_probability", "min"),
            maximum_probability=("calibrated_probability", "max"),
        )
        .reset_index()
    )
    rows["absolute_calibration_error"] = (rows["predicted_probability"] - rows["observed_event_rate"]).abs()
    rows["calibration_bin"] = rows["calibration_bin"].astype(int) + 1
    return rows


def _expected_calibration_error(table: pd.DataFrame, split: str) -> float:
    selected = table[table["split"] == split]
    if selected.empty:
        return float("nan")
    return float(np.average(selected["absolute_calibration_error"], weights=selected["row_count"]))


def _population_stability_index(reference: pd.Series, current: pd.Series, edges: np.ndarray) -> float:
    reference_share = (
        pd.cut(reference, bins=edges, labels=False, include_lowest=True).value_counts(normalize=True).sort_index()
    )
    current_share = (
        pd.cut(current, bins=edges, labels=False, include_lowest=True).value_counts(normalize=True).sort_index()
    )
    indexes = range(len(edges) - 1)
    ref = np.array([float(reference_share.get(index, 0.0)) for index in indexes])
    cur = np.array([float(current_share.get(index, 0.0)) for index in indexes])
    epsilon = 1e-6
    return float(np.sum((cur - ref) * np.log((cur + epsilon) / (ref + epsilon))))


def _split_metrics(base: pd.DataFrame, calibration: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for split, selected in base.groupby("split", sort=False):
        y_true = selected["adverse_flag"].to_numpy(dtype=int)
        score = selected["order_risk_score"].to_numpy(dtype=float)
        probability = selected["calibrated_probability"].to_numpy(dtype=float)
        event_rate = float(y_true.mean())
        average_precision = _average_precision(y_true, score)
        rows.append(
            {
                "split": split,
                "start_date": selected["order_date"].min().isoformat(),
                "end_date": selected["order_date"].max().isoformat(),
                "row_count": len(selected),
                "event_rate": event_rate,
                "score_mean": float(score.mean()),
                "predicted_probability_mean": float(probability.mean()),
                "roc_auc": _roc_auc(y_true, score),
                "average_precision": average_precision,
                "average_precision_lift": float(average_precision / event_rate) if event_rate else float("nan"),
                "brier_score": float(np.mean((probability - y_true) ** 2)),
                "expected_calibration_error": _expected_calibration_error(calibration, str(split)),
            }
        )
    return pd.DataFrame(rows)


def _monthly_monitoring(
    base: pd.DataFrame,
    development: pd.DataFrame,
    score_edges: np.ndarray,
    calibration_edges: np.ndarray,
    evaluation_end: pd.Timestamp,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    work = base.copy()
    work["month"] = work["order_date"].dt.to_period("M").astype(str)
    for month, selected in work.groupby("month", sort=True):
        matured = selected[selected["order_date"] <= evaluation_end]
        y_true = matured["adverse_flag"].to_numpy(dtype=int)
        probability = matured["calibrated_probability"].to_numpy(dtype=float)
        if matured.empty:
            roc_auc = average_precision = brier_score = calibration_error = float("nan")
            event_rate = float("nan")
        else:
            month_calibration = _calibration_table(matured.assign(split="month"), calibration_edges)
            roc_auc = _roc_auc(y_true, matured["order_risk_score"].to_numpy(dtype=float))
            average_precision = _average_precision(y_true, matured["order_risk_score"].to_numpy(dtype=float))
            brier_score = float(np.mean((probability - y_true) ** 2))
            calibration_error = _expected_calibration_error(month_calibration, "month")
            event_rate = float(y_true.mean())
        rows.append(
            {
                "month": month,
                "row_count": len(selected),
                "matured_row_count": len(matured),
                "outcome_status": "matured" if len(matured) == len(selected) else "partially_or_unmatured",
                "event_rate": event_rate,
                "score_mean": float(selected["order_risk_score"].mean()),
                "predicted_probability_mean": float(selected["calibrated_probability"].mean()),
                "roc_auc": roc_auc,
                "average_precision": average_precision,
                "brier_score": brier_score,
                "expected_calibration_error": calibration_error,
                "population_stability_index": _population_stability_index(
                    development["order_risk_score"], selected["order_risk_score"], score_edges
                ),
            }
        )
    return pd.DataFrame(rows)


def _monitoring_alerts(monthly: pd.DataFrame, policy: ModelMonitoringPolicy) -> pd.DataFrame:
    thresholds = policy["release_thresholds"]
    shadow_months = int(policy["shadow_window_months"])
    recent = monthly[monthly["matured_row_count"] > 0].tail(shadow_months)
    checks = [
        (
            "population_stability_index",
            float(thresholds["maximum_population_stability_index"]),
            "above",
            "Investigate population shift and segment-level score movement.",
        ),
        (
            "roc_auc",
            float(thresholds["minimum_roc_auc"]),
            "below",
            "Review discrimination by segment and retrain only after root-cause analysis.",
        ),
        (
            "expected_calibration_error",
            float(thresholds["maximum_expected_calibration_error"]),
            "above",
            "Recalibrate probabilities on a later fully matured window.",
        ),
        (
            "brier_score",
            float(thresholds["maximum_brier_score"]),
            "above",
            "Review probability calibration and outcome-definition stability.",
        ),
    ]
    rows: list[dict[str, object]] = []
    for record in recent.to_dict(orient="records"):
        for metric, threshold, direction, action in checks:
            observed = float(record[metric])
            if not np.isfinite(observed):
                continue
            breached = observed > threshold if direction == "above" else observed < threshold
            if breached:
                rows.append(
                    {
                        "alert_id": f"MON-{record['month']}-{metric}",
                        "month": record["month"],
                        "metric": metric,
                        "observed_value": observed,
                        "threshold": threshold,
                        "severity": "high" if metric in {"roc_auc", "population_stability_index"} else "medium",
                        "recommended_action": action,
                    }
                )
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS["model_monitoring_alerts"])


def build_temporal_validation_outputs(cfg: TemporalValidationConfig) -> dict[str, pd.DataFrame]:
    policy = _load_policy(cfg.policy_file)
    base = _build_base(cfg)
    maximum_date = base["order_date"].max()
    maturation_lag = pd.Timedelta(days=int(policy["outcome_maturation_lag_days"]))
    evaluation_end = maximum_date - maturation_lag
    holdout_start = evaluation_end - pd.Timedelta(days=int(policy["holdout_days"]))
    development_end = holdout_start - maturation_lag
    base["split"] = np.select(
        [
            base["order_date"] <= development_end,
            base["order_date"] < holdout_start,
            base["order_date"] <= evaluation_end,
        ],
        ["development", "maturation_gap", "holdout"],
        default="shadow_unmatured",
    )
    development = base[base["split"] == "development"].copy()
    holdout = base[base["split"] == "holdout"].copy()

    if len(development) < int(policy["minimum_development_rows"]):
        raise ValueError("Development split does not meet the minimum row requirement.")
    if len(holdout) < int(policy["minimum_holdout_rows"]):
        raise ValueError("Holdout split does not meet the minimum row requirement.")

    intercept, slope, score_mean, score_std = _fit_logistic_calibrator(
        development["order_risk_score"].to_numpy(dtype=float),
        development["adverse_flag"].to_numpy(dtype=int),
    )
    base["calibrated_probability"] = _calibrated_probability(
        base["order_risk_score"].to_numpy(dtype=float), intercept, slope, score_mean, score_std
    )
    development = base[base["split"] == "development"].copy()
    holdout = base[base["split"] == "holdout"].copy()

    calibration_edges = _quantile_edges(development["calibrated_probability"], int(policy["calibration_bins"]))
    matured_evaluation = base[base["order_date"] <= evaluation_end].copy()
    calibration = _calibration_table(matured_evaluation, calibration_edges)
    split_metrics = _split_metrics(matured_evaluation, calibration)
    score_edges = _quantile_edges(development["order_risk_score"], int(policy["calibration_bins"]))
    monthly = _monthly_monitoring(base, development, score_edges, calibration_edges, evaluation_end)
    alerts = _monitoring_alerts(monthly, policy)

    holdout_metrics = split_metrics.set_index("split").loc["holdout"]
    thresholds = policy["release_thresholds"]
    gates = {
        "roc_auc_gate_passed": float(holdout_metrics["roc_auc"]) >= float(thresholds["minimum_roc_auc"]),
        "average_precision_lift_gate_passed": float(holdout_metrics["average_precision_lift"])
        >= float(thresholds["minimum_average_precision_lift"]),
        "brier_gate_passed": float(holdout_metrics["brier_score"]) <= float(thresholds["maximum_brier_score"]),
        "calibration_gate_passed": float(holdout_metrics["expected_calibration_error"])
        <= float(thresholds["maximum_expected_calibration_error"]),
    }
    gates["monitoring_gate_passed"] = not alerts["severity"].eq("high").any()
    all_passed = all(gates.values())
    release = pd.DataFrame(
        [
            {
                "assessment_scope": "simulated later-period shadow holdout",
                "as_of_date": maximum_date.isoformat(),
                "development_end": development_end.isoformat(),
                "holdout_start": holdout["order_date"].min().isoformat(),
                "holdout_end": holdout["order_date"].max().isoformat(),
                "holdout_rows": len(holdout),
                "unmatured_shadow_rows": int((base["split"] == "shadow_unmatured").sum()),
                **gates,
                "release_status": "shadow-ready" if all_passed else "recalibration-required",
                "automated_decision_status": "not approved",
                "required_next_step": "Prospective validation on real, fully matured outcomes before automated decisions.",
            }
        ]
    )
    parameters = pd.DataFrame(
        [
            {
                "calibration_method": "logistic_intercept_slope",
                "outcome": "refund_or_dispute_or_chargeback",
                "development_start": development["order_date"].min().isoformat(),
                "development_end": development["order_date"].max().isoformat(),
                "intercept": intercept,
                "slope": slope,
                "score_mean": score_mean,
                "score_standard_deviation": score_std,
                "outcome_maturation_lag_days": int(policy["outcome_maturation_lag_days"]),
                "policy_version": policy["policy_version"],
            }
        ]
    )
    calibrated = base[
        ["order_id", "order_date", "order_risk_score", "calibrated_probability", "adverse_flag", "split"]
    ].copy()
    calibrated["calibration_policy_version"] = policy["policy_version"]

    return {
        "order_risk_calibrated": calibrated,
        "model_calibration_parameters": parameters,
        "model_calibration_curve": calibration,
        "temporal_holdout_metrics": split_metrics,
        "model_monitoring_monthly": monthly,
        "model_monitoring_alerts": alerts,
        "model_release_assessment": release,
    }


def save_outputs(outputs: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in outputs.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run temporal validation, calibration, and model monitoring.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--policy-file",
        type=Path,
        default=Path("config/contracts/v1/model_monitoring_policy.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    cfg = TemporalValidationConfig(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        policy_file=args.policy_file,
        output_dir=args.output_dir,
    )
    outputs = build_temporal_validation_outputs(cfg)
    save_outputs(outputs, cfg.output_dir)
    print("Temporal model validation generated:")
    for name, frame in outputs.items():
        print(f"  - {name}: {len(frame):,} rows")


if __name__ == "__main__":
    main()
