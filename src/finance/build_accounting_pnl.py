from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FinanceConfig:
    processed_dir: Path = Path("data/processed")
    policy_file: Path = Path("config/contracts/v1/finance_policy.json")
    output_dir: Path = Path("data/processed")


class FinancePolicy(TypedDict):
    accounting_basis: str
    accounts: dict[str, str]
    commission_refund_reversal_rate: float
    dispute_platform_loss_rate: float
    fulfillment_support_rate: float
    payment_fixed_fee: float
    payment_variable_rate: float
    policy_version: str
    refund_unrecovered_rate: float


def _load_policy(path: Path) -> FinancePolicy:
    policy = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "accounting_basis",
        "accounts",
        "commission_refund_reversal_rate",
        "dispute_platform_loss_rate",
        "fulfillment_support_rate",
        "payment_fixed_fee",
        "payment_variable_rate",
        "policy_version",
        "refund_unrecovered_rate",
    }
    missing = sorted(required - set(policy))
    if missing:
        raise ValueError(f"Finance policy is missing fields: {missing}")
    rates = [
        "commission_refund_reversal_rate",
        "dispute_platform_loss_rate",
        "fulfillment_support_rate",
        "payment_variable_rate",
        "refund_unrecovered_rate",
    ]
    if any(float(policy[name]) < 0 for name in rates):
        raise ValueError("Finance policy rates must be non-negative.")
    if float(policy["payment_fixed_fee"]) < 0:
        raise ValueError("Payment fixed fee must be non-negative.")
    return cast(FinancePolicy, policy)


def _build_order_subledger(source: pd.DataFrame, policy: FinancePolicy) -> pd.DataFrame:
    source_columns = [
        "order_id",
        "order_date",
        "gross_value",
        "net_value",
        "subsidy_amount",
        "commission_fee",
        "refund_amount",
        "dispute_amount",
        "chargeback_loss_proxy",
    ]
    missing = sorted(set(source_columns) - set(source.columns))
    if missing:
        raise ValueError(f"Profitability source is missing fields: {missing}")
    if source["order_id"].duplicated().any():
        raise ValueError("Profitability source must have one row per order.")

    ledger = source[source_columns].copy()
    ledger["order_date"] = pd.to_datetime(ledger["order_date"], errors="raise")
    value_columns = source_columns[2:]
    if ledger[value_columns].isna().any().any() or (ledger[value_columns] < 0).any().any():
        raise ValueError("Finance inputs must be non-null and non-negative.")

    refund_share = np.divide(
        ledger["refund_amount"],
        ledger["gross_value"],
        out=np.zeros(len(ledger), dtype=float),
        where=ledger["gross_value"].to_numpy(dtype=float) > 0,
    )
    refund_share = np.clip(refund_share, 0.0, 1.0)
    ledger["gross_commission_revenue"] = ledger["commission_fee"]
    ledger["commission_reversal"] = (
        ledger["commission_fee"] * refund_share * float(policy["commission_refund_reversal_rate"])
    )
    ledger["net_commission_revenue"] = ledger["gross_commission_revenue"] - ledger["commission_reversal"]
    ledger["payment_processing_expense"] = (
        float(policy["payment_fixed_fee"]) + float(policy["payment_variable_rate"]) * ledger["net_value"]
    )
    ledger["marketplace_subsidy_expense"] = ledger["subsidy_amount"]
    ledger["unrecovered_refund_expense"] = float(policy["refund_unrecovered_rate"]) * ledger["refund_amount"]
    ledger["dispute_loss_expense"] = float(policy["dispute_platform_loss_rate"]) * ledger["dispute_amount"]
    ledger["chargeback_loss_expense"] = ledger["chargeback_loss_proxy"]
    ledger["fulfillment_support_expense"] = float(policy["fulfillment_support_rate"]) * ledger["commission_fee"]

    monetary_columns = [
        "gross_value",
        "net_value",
        "gross_commission_revenue",
        "commission_reversal",
        "net_commission_revenue",
        "payment_processing_expense",
        "marketplace_subsidy_expense",
        "unrecovered_refund_expense",
        "dispute_loss_expense",
        "chargeback_loss_expense",
        "fulfillment_support_expense",
    ]
    ledger[monetary_columns] = ledger[monetary_columns].round(2)
    ledger["net_commission_revenue"] = (ledger["gross_commission_revenue"] - ledger["commission_reversal"]).round(2)
    expense_columns = [
        "payment_processing_expense",
        "marketplace_subsidy_expense",
        "unrecovered_refund_expense",
        "dispute_loss_expense",
        "chargeback_loss_expense",
        "fulfillment_support_expense",
    ]
    ledger["accounting_contribution"] = (ledger["net_commission_revenue"] - ledger[expense_columns].sum(axis=1)).round(
        2
    )
    ledger["accounting_basis"] = str(policy["accounting_basis"])
    ledger["finance_policy_version"] = str(policy["policy_version"])
    return ledger.sort_values(["order_date", "order_id"]).reset_index(drop=True)


def _build_general_ledger(order_ledger: pd.DataFrame, policy: FinancePolicy) -> pd.DataFrame:
    accounts = policy["accounts"]
    entries = [
        ("commission_revenue", "gross_commission_revenue", "1100", "4000"),
        ("commission_reversal", "commission_reversal", "4010", "1100"),
        ("marketplace_subsidy", "marketplace_subsidy_expense", "5000", "1100"),
        ("payment_processing", "payment_processing_expense", "5010", "1100"),
        ("unrecovered_refund", "unrecovered_refund_expense", "5020", "1100"),
        ("dispute_loss", "dispute_loss_expense", "5030", "1100"),
        ("chargeback_loss", "chargeback_loss_expense", "5040", "1100"),
        ("fulfillment_support", "fulfillment_support_expense", "5050", "1100"),
    ]
    monthly = order_ledger.assign(accounting_month=order_ledger["order_date"].dt.to_period("M").astype(str))
    rows: list[dict[str, object]] = []
    for month, selected in monthly.groupby("accounting_month", sort=True):
        posting_date = pd.Period(month, freq="M").end_time.date().isoformat()
        for sequence, (entry_name, amount_column, debit_account, credit_account) in enumerate(entries, start=1):
            amount = round(float(selected[amount_column].sum()), 2)
            journal_id = f"GL-{month.replace('-', '')}-{sequence:02d}"
            for line_number, (account, debit, credit) in enumerate(
                [(debit_account, amount, 0.0), (credit_account, 0.0, amount)], start=1
            ):
                rows.append(
                    {
                        "journal_id": journal_id,
                        "journal_line_id": f"{journal_id}-{line_number}",
                        "accounting_month": month,
                        "posting_date": posting_date,
                        "entry_type": entry_name,
                        "account_code": account,
                        "account_name": accounts[account],
                        "debit": debit,
                        "credit": credit,
                        "currency": "USD",
                        "finance_policy_version": str(policy["policy_version"]),
                    }
                )
    return pd.DataFrame(rows)


def _build_reconciliation(order_ledger: pd.DataFrame, general_ledger: pd.DataFrame) -> pd.DataFrame:
    income_accounts = {"4000"}
    contra_revenue_accounts = {"4010"}
    expense_accounts = {"5000", "5010", "5020", "5030", "5040", "5050"}
    total_debits = round(float(general_ledger["debit"].sum()), 2)
    total_credits = round(float(general_ledger["credit"].sum()), 2)
    income = float(general_ledger.loc[general_ledger["account_code"].isin(income_accounts), "credit"].sum())
    contra_revenue = float(
        general_ledger.loc[general_ledger["account_code"].isin(contra_revenue_accounts), "debit"].sum()
    )
    expenses = float(general_ledger.loc[general_ledger["account_code"].isin(expense_accounts), "debit"].sum())
    gl_contribution = round(income - contra_revenue - expenses, 2)
    subledger_contribution = round(float(order_ledger["accounting_contribution"].sum()), 2)
    checks = [
        (
            "general_ledger_balanced",
            total_debits,
            total_credits,
            round(total_debits - total_credits, 2),
            0.0,
        ),
        (
            "pnl_reconciles_to_order_subledger",
            gl_contribution,
            subledger_contribution,
            round(gl_contribution - subledger_contribution, 2),
            0.01,
        ),
    ]
    rows = []
    for check_name, actual, expected, difference, tolerance in checks:
        rows.append(
            {
                "check_name": check_name,
                "actual_value": actual,
                "expected_value": expected,
                "difference": difference,
                "tolerance": tolerance,
                "status": "passed" if abs(difference) <= tolerance else "failed",
            }
        )
    reconciliation = pd.DataFrame(rows)
    if reconciliation["status"].eq("failed").any():
        raise ValueError("Finance reconciliation failed.")
    return reconciliation


def build_finance_outputs(cfg: FinanceConfig) -> dict[str, pd.DataFrame]:
    policy = _load_policy(cfg.policy_file)
    source = pd.read_csv(cfg.processed_dir / "order_profitability_features.csv", parse_dates=["order_date"])
    order_ledger = _build_order_subledger(source, policy)
    general_ledger = _build_general_ledger(order_ledger, policy)
    reconciliation = _build_reconciliation(order_ledger, general_ledger)
    summary = pd.DataFrame(
        [
            {
                "as_of_date": order_ledger["order_date"].max().isoformat(),
                "currency": "USD",
                "order_count": len(order_ledger),
                "gross_marketplace_value": round(float(order_ledger["gross_value"].sum()), 2),
                "gross_commission_revenue": round(float(order_ledger["gross_commission_revenue"].sum()), 2),
                "commission_reversals": round(float(order_ledger["commission_reversal"].sum()), 2),
                "total_operating_expense": round(
                    float(
                        order_ledger[
                            [
                                "payment_processing_expense",
                                "marketplace_subsidy_expense",
                                "unrecovered_refund_expense",
                                "dispute_loss_expense",
                                "chargeback_loss_expense",
                                "fulfillment_support_expense",
                            ]
                        ]
                        .sum(axis=1)
                        .sum()
                    ),
                    2,
                ),
                "accounting_contribution": round(float(order_ledger["accounting_contribution"].sum()), 2),
                "accounting_basis": str(policy["accounting_basis"]),
                "finance_policy_version": str(policy["policy_version"]),
            }
        ]
    )
    return {
        "order_accounting_pnl": order_ledger,
        "finance_general_ledger": general_ledger,
        "finance_reconciliation": reconciliation,
        "accounting_kpi_summary": summary,
    }


def save_outputs(outputs: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, frame in outputs.items():
        frame.to_csv(output_dir / f"{name}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build governed marketplace management accounts.")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--policy-file", type=Path, default=Path("config/contracts/v1/finance_policy.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/processed"))
    args = parser.parse_args()
    cfg = FinanceConfig(
        processed_dir=args.processed_dir,
        policy_file=args.policy_file,
        output_dir=args.output_dir,
    )
    outputs = build_finance_outputs(cfg)
    save_outputs(outputs, cfg.output_dir)
    print("Accounting outputs generated:")
    for name, frame in outputs.items():
        print(f"  - {name}: {len(frame):,} rows")


if __name__ == "__main__":
    main()
