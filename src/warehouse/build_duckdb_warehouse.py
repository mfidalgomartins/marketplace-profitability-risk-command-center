from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


@dataclass(frozen=True)
class WarehouseConfig:
    raw_dir: Path = Path("data/raw")
    processed_dir: Path = Path("data/processed")
    database_file: Path = Path("outputs/warehouse/marketplace.duckdb")
    manifest_file: Path = Path("reports/warehouse_load_manifest.csv")
    validation_file: Path = Path("reports/warehouse_validation.csv")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise ValueError(f"Unsafe warehouse identifier: {value}")
    return value


def _scalar(connection: duckdb.DuckDBPyConnection, query: str) -> Any:
    row = connection.execute(query).fetchone()
    if row is None:
        raise ValueError("Warehouse scalar query returned no row.")
    return row[0]


def _discover_sources(cfg: WarehouseConfig) -> pd.DataFrame:
    project_root = Path.cwd().resolve()
    rows: list[dict[str, object]] = []
    for schema_name, directory in [
        ("raw", cfg.raw_dir),
        ("analytics", cfg.processed_dir),
    ]:
        for path in sorted(directory.glob("*.csv")):
            resolved_path = path.resolve()
            try:
                source_path = resolved_path.relative_to(project_root).as_posix()
            except ValueError:
                source_path = resolved_path.as_posix()
            rows.append(
                {
                    "source_schema": schema_name,
                    "source_table": _safe_identifier(path.stem),
                    "source_path": source_path,
                    "source_bytes": path.stat().st_size,
                    "source_sha256": _sha256_file(path),
                }
            )
    if not rows:
        raise ValueError("No CSV sources were found for the warehouse.")
    manifest = pd.DataFrame(rows).sort_values(["source_schema", "source_table"]).reset_index(drop=True)
    release_payload = manifest.to_json(orient="records", date_format="iso")
    manifest["warehouse_release_id"] = hashlib.sha256(release_payload.encode("utf-8")).hexdigest()[:16]
    manifest["load_status"] = "synchronized"
    return manifest


def _existing_release_id(connection: duckdb.DuckDBPyConnection) -> str | None:
    try:
        row = connection.execute("SELECT warehouse_release_id FROM warehouse_meta.current_release LIMIT 1").fetchone()
    except duckdb.CatalogException:
        return None
    return str(row[0]) if row else None


def _register_source_views(connection: duckdb.DuckDBPyConnection, manifest: pd.DataFrame) -> None:
    for schema_name in ["raw", "analytics", "curated", "warehouse_meta"]:
        connection.execute(f"CREATE SCHEMA IF NOT EXISTS {schema_name}")
    for record in manifest.to_dict(orient="records"):
        schema_name = _safe_identifier(str(record["source_schema"]))
        table_name = _safe_identifier(str(record["source_table"]))
        connection.execute("SET schema = ?", [schema_name])
        source = connection.read_csv(str(record["source_path"]), header=True, sample_size=-1)
        source.create_view(table_name, replace=True)
    connection.execute("SET schema = 'main'")


def _refresh_curated_layer(connection: duckdb.DuckDBPyConnection) -> None:
    connection.execute(
        """
        CREATE OR REPLACE VIEW curated.order_decision_mart AS
        SELECT
            risk.order_id,
            risk.order_date,
            risk.buyer_id,
            risk.seller_id,
            risk.category,
            risk.order_channel,
            risk.payment_method,
            risk.order_risk_score,
            risk.order_risk_tier,
            calibrated.calibrated_probability,
            calibrated.split AS validation_split,
            pnl.gross_value,
            pnl.net_value,
            pnl.accounting_contribution,
            pnl.finance_policy_version
        FROM analytics.order_risk_scores AS risk
        INNER JOIN analytics.order_risk_calibrated AS calibrated USING (order_id)
        INNER JOIN analytics.order_accounting_pnl AS pnl USING (order_id)
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TABLE curated.seller_command_mart AS
        SELECT
            scorecard.*,
            actions.owner_team,
            actions.sla_days,
            actions.status AS action_status,
            actions.next_review_step
        FROM analytics.seller_scorecard AS scorecard
        LEFT JOIN analytics.governance_action_register AS actions
          ON actions.entity_type = 'seller'
         AND actions.entity_id = scorecard.seller_id
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TABLE curated.monthly_finance_mart AS
        SELECT
            strftime(order_date, '%Y-%m') AS accounting_month,
            count(*) AS order_count,
            round(sum(gross_value), 2) AS gross_marketplace_value,
            round(sum(gross_commission_revenue), 2) AS gross_commission_revenue,
            round(sum(commission_reversal), 2) AS commission_reversal,
            round(sum(accounting_contribution), 2) AS accounting_contribution
        FROM analytics.order_accounting_pnl
        GROUP BY 1
        ORDER BY 1
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TABLE curated.model_monitoring_mart AS
        SELECT * FROM analytics.model_monitoring_monthly ORDER BY month
        """
    )
    connection.execute(
        """
        CREATE OR REPLACE TABLE curated.experiment_results_mart AS
        SELECT * FROM analytics.experiment_results ORDER BY metric
        """
    )


def _refresh_metadata(connection: duckdb.DuckDBPyConnection, manifest: pd.DataFrame) -> None:
    release_id = str(manifest["warehouse_release_id"].iloc[0])
    connection.register("source_manifest_frame", manifest)
    connection.execute("CREATE OR REPLACE TABLE warehouse_meta.source_manifest AS SELECT * FROM source_manifest_frame")
    connection.unregister("source_manifest_frame")
    as_of_date = _scalar(connection, "SELECT max(order_date) FROM raw.orders")
    connection.execute(
        """
        CREATE OR REPLACE TABLE warehouse_meta.current_release AS
        SELECT
            ?::VARCHAR AS warehouse_release_id,
            ?::TIMESTAMP AS source_as_of_timestamp,
            ?::INTEGER AS source_table_count,
            'csv_views_plus_curated_marts'::VARCHAR AS storage_strategy
        """,
        [release_id, as_of_date, len(manifest)],
    )


def _run_validations(connection: duckdb.DuckDBPyConnection, manifest: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for record in manifest.to_dict(orient="records"):
        schema_name = _safe_identifier(str(record["source_schema"]))
        table_name = _safe_identifier(str(record["source_table"]))
        qualified_name = f"{schema_name}.{table_name}"
        connection.execute("SET schema = ?", [schema_name])
        count_row = connection.table(table_name).count("*").fetchone()
        if count_row is None:
            raise ValueError(f"Warehouse source view returned no count: {qualified_name}")
        row_count = int(count_row[0])
        rows.append(
            {
                "check_name": f"source_readable__{qualified_name}",
                "actual_value": row_count,
                "expected_value": ">=0",
                "status": "passed" if row_count >= 0 else "failed",
            }
        )
    connection.execute("SET schema = 'main'")
    order_source_count = int(_scalar(connection, "SELECT count(*) FROM analytics.order_risk_scores"))
    order_mart_count = int(_scalar(connection, "SELECT count(*) FROM curated.order_decision_mart"))
    finance_failures = int(
        _scalar(connection, "SELECT count(*) FROM analytics.finance_reconciliation WHERE status <> 'passed'")
    )
    seller_mart_count = int(_scalar(connection, "SELECT count(*) FROM curated.seller_command_mart"))
    curated_checks = [
        (
            "order_decision_mart_preserves_order_grain",
            order_mart_count,
            str(order_source_count),
            order_mart_count == order_source_count,
        ),
        (
            "finance_reconciliation_passes",
            finance_failures,
            "0",
            finance_failures == 0,
        ),
        (
            "seller_command_mart_populated",
            seller_mart_count,
            ">0",
            seller_mart_count > 0,
        ),
    ]
    for check_name, actual, expected, passed in curated_checks:
        rows.append(
            {
                "check_name": check_name,
                "actual_value": actual,
                "expected_value": expected,
                "status": "passed" if passed else "failed",
            }
        )
    validation = pd.DataFrame(rows)
    if validation["status"].eq("failed").any():
        failures = validation.loc[validation["status"].eq("failed"), "check_name"].tolist()
        raise ValueError(f"Warehouse validation failed: {failures}")
    return validation


def build_warehouse(cfg: WarehouseConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    manifest = _discover_sources(cfg)
    cfg.database_file.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(cfg.database_file))
    try:
        release_id = str(manifest["warehouse_release_id"].iloc[0])
        if _existing_release_id(connection) != release_id:
            connection.execute("BEGIN TRANSACTION")
            try:
                _register_source_views(connection, manifest)
                _refresh_curated_layer(connection)
                _refresh_metadata(connection, manifest)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        validation = _run_validations(connection, manifest)
    finally:
        connection.close()

    cfg.manifest_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.validation_file.parent.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(cfg.manifest_file, index=False)
    validation.to_csv(cfg.validation_file, index=False)
    return manifest, validation


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the idempotent DuckDB analytical warehouse.")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--database-file",
        type=Path,
        default=Path("outputs/warehouse/marketplace.duckdb"),
    )
    parser.add_argument(
        "--manifest-file",
        type=Path,
        default=Path("reports/warehouse_load_manifest.csv"),
    )
    parser.add_argument(
        "--validation-file",
        type=Path,
        default=Path("reports/warehouse_validation.csv"),
    )
    args = parser.parse_args()
    cfg = WarehouseConfig(
        raw_dir=args.raw_dir,
        processed_dir=args.processed_dir,
        database_file=args.database_file,
        manifest_file=args.manifest_file,
        validation_file=args.validation_file,
    )
    manifest, validation = build_warehouse(cfg)
    print(f"DuckDB warehouse synchronized: {len(manifest):,} sources, {len(validation):,} validation checks.")


if __name__ == "__main__":
    main()
