from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class ContractIssue:
    table_name: str
    path: str
    issue_type: str
    detail: str


ISSUE_COLUMNS = ["table_name", "path", "issue_type", "detail"]


def validate_schema_contracts(schema_file: Path) -> pd.DataFrame:
    if not schema_file.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_file}")

    contract = json.loads(schema_file.read_text(encoding="utf-8"))
    issues: list[ContractIssue] = []
    tables = contract.get("tables")
    if not isinstance(tables, list) or not tables:
        return pd.DataFrame(
            [
                ContractIssue(
                    table_name="__contract__",
                    path=str(schema_file),
                    issue_type="invalid_contract",
                    detail="Contract must contain a non-empty tables list.",
                ).__dict__
            ]
        )

    invalid_entries = [position for position, table in enumerate(tables) if not isinstance(table, dict)]
    for position in invalid_entries:
        issues.append(
            ContractIssue(
                table_name="__contract__",
                path=str(schema_file),
                issue_type="invalid_table_contract",
                detail=f"Table contract at position {position} must be an object.",
            )
        )

    valid_tables = [table for table in tables if isinstance(table, dict)]
    table_names = [str(table.get("table_name")) for table in valid_tables]
    duplicate_tables = sorted({name for name in table_names if table_names.count(name) > 1})
    for table_name in duplicate_tables:
        issues.append(
            ContractIssue(
                table_name=table_name,
                path=str(schema_file),
                issue_type="duplicate_table_contract",
                detail="Table is defined more than once in the contract.",
            )
        )

    for t in valid_tables:
        table_name = str(t.get("table_name"))
        path = Path(str(t.get("path")))
        expected_cols = list(t.get("columns", []))
        expected_types = dict(t.get("column_types", {}))
        pk = list(t.get("primary_key_candidate", []))
        not_null_columns = list(t.get("not_null_columns", pk))
        unique_constraints = [list(columns) for columns in t.get("unique_constraints", [])]
        row_count_constraint = dict(t.get("row_count_constraint", {}))

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
        minimum_rows = row_count_constraint.get("minimum")
        maximum_rows = row_count_constraint.get("maximum")
        if minimum_rows is not None and len(df) < int(minimum_rows):
            issues.append(
                ContractIssue(
                    table_name=table_name,
                    path=str(path),
                    issue_type="row_count_below_minimum",
                    detail=f"Expected at least {int(minimum_rows)} row(s), found {len(df)}.",
                )
            )
        if maximum_rows is not None and len(df) > int(maximum_rows):
            issues.append(
                ContractIssue(
                    table_name=table_name,
                    path=str(path),
                    issue_type="row_count_above_maximum",
                    detail=f"Expected at most {int(maximum_rows)} row(s), found {len(df)}.",
                )
            )

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
                # Judge datetime validity on populated values only: a date column
                # may legitimately have nulls (e.g. undelivered orders), and that
                # must match how the contract generator infers the kind.
                non_null = df[c].dropna()
                if len(non_null) == 0:
                    ok = True
                else:
                    parsed = pd.to_datetime(non_null, errors="coerce", utc=False, format="ISO8601")
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

        for c in not_null_columns:
            if c not in df.columns:
                continue
            null_count = int(df[c].isna().sum())
            if null_count:
                issues.append(
                    ContractIssue(
                        table_name=table_name,
                        path=str(path),
                        issue_type="not_null_violation",
                        detail=f"Column {c}: {null_count} null value(s)",
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
                null_pk = int(df[pk].isna().any(axis=1).sum())
                if null_pk > 0:
                    issues.append(
                        ContractIssue(
                            table_name=table_name,
                            path=str(path),
                            issue_type="primary_key_nulls",
                            detail=f"{null_pk} row(s) contain nulls in key {pk}",
                        )
                    )
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

        for columns in unique_constraints:
            missing_columns = [column for column in columns if column not in df.columns]
            if missing_columns:
                issues.append(
                    ContractIssue(
                        table_name=table_name,
                        path=str(path),
                        issue_type="missing_unique_constraint_columns",
                        detail=f"Missing unique-constraint columns: {missing_columns}",
                    )
                )
                continue
            duplicate_count = int(df.duplicated(subset=columns).sum())
            if duplicate_count:
                issues.append(
                    ContractIssue(
                        table_name=table_name,
                        path=str(path),
                        issue_type="unique_constraint_violation",
                        detail=f"{duplicate_count} duplicated row(s) on constraint {columns}",
                    )
                )

    if issues:
        return pd.DataFrame([i.__dict__ for i in issues])
    return pd.DataFrame(columns=ISSUE_COLUMNS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate data tables against schema contracts.")
    parser.add_argument("--schema-file", type=Path, default=Path("config/contracts/v1/schema_contracts.json"))
    parser.add_argument("--output-file", type=Path, default=Path("reports/schema_contract_issues.csv"))
    args = parser.parse_args()

    issues = validate_schema_contracts(args.schema_file)
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    issues.to_csv(args.output_file, index=False)

    if issues.empty:
        print("Schema contracts: PASSED")
    else:
        print(f"Schema contracts: FAILED with {len(issues)} issue(s). See {args.output_file}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
