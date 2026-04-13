from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

import pandas as pd


@dataclass(frozen=True)
class GovernanceConfig:
    processed_dir: Path = Path("data/processed")
    output_dir: Path = Path("data/processed")
    max_seller_actions: int = 150
    max_order_actions: int = 250


def _load_tables(processed_dir: Path) -> Dict[str, pd.DataFrame]:
    return {
        "seller_scorecard": pd.read_csv(processed_dir / "seller_scorecard.csv"),
        "order_risk_scores": pd.read_csv(processed_dir / "order_risk_scores.csv"),
        "opf": pd.read_csv(processed_dir / "order_profitability_features.csv"),
    }


def _owner_from_seller_driver(driver: str) -> str:
    if driver == "fraud_exposure":
        return "Risk Operations"
    if driver == "margin_fragility":
        return "Finance and Pricing"
    if driver == "seller_quality":
        return "Seller Operations"
    return "Marketplace Governance"


def _owner_from_order_driver(driver: str) -> str:
    if driver in {"payment_signal", "payment_method", "buyer_history"}:
        return "Risk Operations"
    if driver in {"seller_history", "category_risk"}:
        return "Risk and Seller Operations"
    return "Marketplace Operations"


def _sla_days(tier: str) -> int:
    if tier == "Critical":
        return 2
    if tier == "High":
        return 7
    if tier == "Moderate":
        return 14
    return 30


def _build_seller_actions(
    seller_scorecard: pd.DataFrame,
    opf: pd.DataFrame,
    max_seller_actions: int,
) -> pd.DataFrame:
    seller_leakage = (
        opf.groupby("seller_id", as_index=False)
        .agg(
            seller_gmv=("gross_value", "sum"),
            seller_net=("net_value", "sum"),
            seller_risk_adjusted=("risk_adjusted_order_value", "sum"),
            seller_expected_margin=("estimated_margin_after_risk", "sum"),
            seller_realized_margin=("realized_contribution_margin_proxy", "sum"),
            seller_refunds=("refund_amount", "sum"),
            seller_disputes=("dispute_amount", "sum"),
            seller_chargeback_loss=("chargeback_loss_proxy", "sum"),
            seller_subsidy=("subsidy_amount", "sum"),
        )
        .assign(
            seller_total_leakage=lambda d: d["seller_refunds"]
            + d["seller_disputes"]
            + d["seller_chargeback_loss"]
            + d["seller_subsidy"]
        )
    )

    candidates = (
        seller_scorecard.merge(seller_leakage, on="seller_id", how="left")
        .fillna(
            {
                "seller_gmv": 0.0,
                "seller_net": 0.0,
                "seller_risk_adjusted": 0.0,
                "seller_expected_margin": 0.0,
                "seller_realized_margin": 0.0,
                "seller_refunds": 0.0,
                "seller_disputes": 0.0,
                "seller_chargeback_loss": 0.0,
                "seller_subsidy": 0.0,
                "seller_total_leakage": 0.0,
            }
        )
        .copy()
    )
    candidates = candidates.sort_values(
        ["governance_priority_score", "seller_total_leakage", "gmv"],
        ascending=[False, False, False],
    ).head(max_seller_actions)

    out = pd.DataFrame(
        {
            "entity_type": "seller",
            "entity_id": candidates["seller_id"].astype(str),
            "priority_score": candidates["governance_priority_score"].astype(float),
            "risk_tier": candidates["governance_priority_tier"].astype(str),
            "main_risk_driver": candidates["main_risk_driver"].astype(str),
            "recommended_action": candidates["recommended_action"].astype(str),
            "owner_team": candidates["main_risk_driver"].map(_owner_from_seller_driver),
            "sla_days": candidates["governance_priority_tier"].map(_sla_days).astype(int),
            "estimated_leakage_proxy": candidates["seller_total_leakage"].astype(float),
            "estimated_margin_proxy": candidates["seller_realized_margin"].astype(float),
            "gross_value": candidates["seller_gmv"].astype(float),
            "net_value": candidates["seller_net"].astype(float),
            "risk_adjusted_value": candidates["seller_risk_adjusted"].astype(float),
            "record_source": "seller_scorecard + order_profitability_features",
        }
    )
    return out


def _build_order_actions(
    order_risk_scores: pd.DataFrame,
    opf: pd.DataFrame,
    max_order_actions: int,
) -> pd.DataFrame:
    order_base = order_risk_scores.merge(
        opf[
            [
                "order_id",
                "gross_value",
                "net_value",
                "risk_adjusted_order_value",
                "estimated_margin_after_risk",
                "realized_contribution_margin_proxy",
                "subsidy_amount",
                "refund_amount",
                "dispute_amount",
                "chargeback_loss_proxy",
            ]
        ],
        on="order_id",
        how="left",
    ).fillna(0.0)

    order_base["order_total_leakage"] = (
        order_base["subsidy_amount"]
        + order_base["refund_amount"]
        + order_base["dispute_amount"]
        + order_base["chargeback_loss_proxy"]
    )

    candidates = order_base.sort_values(
        ["order_risk_score", "order_total_leakage", "net_value"],
        ascending=[False, False, False],
    ).head(max_order_actions)

    out = pd.DataFrame(
        {
            "entity_type": "order",
            "entity_id": candidates["order_id"].astype(str),
            "priority_score": candidates["order_risk_score"].astype(float),
            "risk_tier": candidates["order_risk_tier"].astype(str),
            "main_risk_driver": candidates["order_risk_main_driver"].astype(str),
            "recommended_action": candidates["recommended_action"].astype(str),
            "owner_team": candidates["order_risk_main_driver"].map(_owner_from_order_driver),
            "sla_days": candidates["order_risk_tier"].map(_sla_days).astype(int),
            "estimated_leakage_proxy": candidates["order_total_leakage"].astype(float),
            "estimated_margin_proxy": candidates["realized_contribution_margin_proxy"].astype(float),
            "gross_value": candidates["gross_value"].astype(float),
            "net_value": candidates["net_value"].astype(float),
            "risk_adjusted_value": candidates["risk_adjusted_order_value"].astype(float),
            "record_source": "order_risk_scores + order_profitability_features",
        }
    )
    return out


def build_action_register(cfg: GovernanceConfig) -> pd.DataFrame:
    tables = _load_tables(cfg.processed_dir)

    seller_actions = _build_seller_actions(
        seller_scorecard=tables["seller_scorecard"],
        opf=tables["opf"],
        max_seller_actions=cfg.max_seller_actions,
    )
    order_actions = _build_order_actions(
        order_risk_scores=tables["order_risk_scores"],
        opf=tables["opf"],
        max_order_actions=cfg.max_order_actions,
    )

    register = pd.concat([seller_actions, order_actions], ignore_index=True)
    ordered_idx = register.sort_values(
        ["priority_score", "estimated_leakage_proxy"],
        ascending=[False, False],
    ).index
    rank_map = {idx: rank for rank, idx in enumerate(ordered_idx, start=1)}
    register["priority_rank"] = register.index.map(rank_map).astype(int)
    register["status"] = "open"
    register["next_review_step"] = (
        "assign owner and execute recommended action within SLA"
    )
    register = register.sort_values(["priority_rank"], ascending=[True]).reset_index(drop=True)
    return register


def save_action_register(register: pd.DataFrame, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "governance_action_register.csv"
    register.to_csv(output_path, index=False)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build governance action register for seller and order interventions.")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--max-seller-actions", type=int, default=150)
    parser.add_argument("--max-order-actions", type=int, default=250)
    args = parser.parse_args()

    cfg = GovernanceConfig(
        processed_dir=args.processed_dir,
        output_dir=args.output_dir,
        max_seller_actions=args.max_seller_actions,
        max_order_actions=args.max_order_actions,
    )

    register = build_action_register(cfg)
    out = save_action_register(register, cfg.output_dir)
    print(f"Governance action register generated: {out} ({len(register):,} rows)")


if __name__ == "__main__":
    main()
