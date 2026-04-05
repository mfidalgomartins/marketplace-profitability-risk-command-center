from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

import pandas as pd


@dataclass
class ContractIssue:
    table_name: str
    path: str
    issue_type: str
    detail: str


def validate_schema_contracts(schema_file: Path) -> pd.DataFrame:
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    contract = json.loads(schema_file.read_text(encoding="utf-8"))
    issues: List[ContractIssue] = []

    for t in contract.get("tables", []):
        table_name = str(t.get("table_name"))
        path = Path(str(t.get("path")))
        expected_cols = list(t.get("columns", []))
        expected_types = dict(t.get("column_types", {}))
        pk = list(t.get("primary_key_candidate", []))

        if not path.exists():
            issues.append(
                ContractIssue(
                    table_name=table_name,
                    path=str(path),
                    issue_type="missing_table_file",
                    detail="Contract path does not exist.",
                )
            )
            continue

        df = pd.read_csv(path)
        actual_cols = list(df.columns)
        if actual_cols != expected_cols:
            issues.append(
                ContractIssue(
                    table_name=table_name,
                    path=str(path),
                    issue_type="column_mismatch",
                    detail=f"Expected columns {expected_cols}, got {actual_cols}",
                )
            )

        for c, expected_kind in expected_types.items():
            if c not in df.columns:
                continue
            dtype = str(df[c].dtype)
            if expected_kind == "integer":
                ok = "int" in dtype
            elif expected_kind == "number":
                ok = ("float" in dtype) or ("int" in dtype)
            elif expected_kind == "boolean":
                ok = ("bool" in dtype) or ("int" in dtype)
            elif expected_kind == "datetime":
                parsed = pd.to_datetime(df[c], errors="coerce", utc=False)
                ok = bool(parsed.notna().mean() >= 0.98)
            else:
                ok = True
            if not ok:
                issues.append(
                    ContractIssue(
                        table_name=table_name,
                        path=str(path),
                        issue_type="type_mismatch",
                        detail=f"Column {c}: expected {expected_kind}, got dtype {dtype}",
                    )
                )

        if pk:
            missing_pk = [k for k in pk if k not in df.columns]
            if missing_pk:
                issues.append(
                    ContractIssue(
                        table_name=table_name,
                        path=str(path),
                        issue_type="missing_primary_key_columns",
                        detail=f"Missing PK columns: {missing_pk}",
                    )
                )
            else:
                dup = int(df.duplicated(subset=pk).sum())
                if dup > 0:
                    issues.append(
                        ContractIssue(
                            table_name=table_name,
                            path=str(path),
                            issue_type="primary_key_duplicates",
                            detail=f"{dup} duplicated rows on key {pk}",
                        )
                    )

    return pd.DataFrame([i.__dict__ for i in issues])


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate data tables against schema contracts.")
    parser.add_argument("--schema-file", type=Path, default=Path("schemas/v1/schema_contracts.json"))
    parser.add_argument("--output-file", type=Path, default=Path("reports/schema_contract_issues.csv"))
    args = parser.parse_args()

    issues = validate_schema_contracts(args.schema_file)
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    issues.to_csv(args.output_file, index=False)

    if issues.empty:
        print("Schema contracts: PASSED")
    else:
        print(f"Schema contracts: FAILED with {len(issues)} issue(s). See {args.output_file}")


if __name__ == "__main__":
    main()
