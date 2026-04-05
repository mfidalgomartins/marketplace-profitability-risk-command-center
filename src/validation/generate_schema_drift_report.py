from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class DriftConfig:
    current_schema_file: Path = Path("schemas/v1/schema_contracts.json")
    previous_schema_file: Optional[Path] = None
    history_dir: Path = Path("schemas/history")
    output_csv: Path = Path("reports/schema_drift_changes.csv")
    output_report: Path = Path("reports/schema_drift_report.md")
    snapshot_current: bool = True


def _load_contract(path: Path) -> Dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: Dict[str, dict] = {}
    for table in payload.get("tables", []):
        out[str(table["table_name"])] = {
            "columns": list(table.get("columns", [])),
            "types": dict(table.get("column_types", {})),
            "pk": list(table.get("primary_key_candidate", [])),
            "path": str(table.get("path", "")),
        }
    return out


def _resolve_previous_schema(cfg: DriftConfig) -> Optional[Path]:
    if cfg.previous_schema_file is not None:
        return cfg.previous_schema_file if cfg.previous_schema_file.exists() else None

    if not cfg.history_dir.exists():
        return None

    candidates = sorted(cfg.history_dir.glob("schema_contract_*.json"))
    if not candidates:
        return None
    return candidates[-1]


def _add_change(
    rows: List[dict],
    change_type: str,
    table_name: str,
    column_name: str,
    previous_value: str,
    current_value: str,
    severity: str,
) -> None:
    rows.append(
        {
            "change_type": change_type,
            "table_name": table_name,
            "column_name": column_name,
            "previous_value": previous_value,
            "current_value": current_value,
            "severity": severity,
        }
    )


def compare_contracts(previous_schema: Path, current_schema: Path) -> pd.DataFrame:
    prev = _load_contract(previous_schema)
    curr = _load_contract(current_schema)

    rows: List[dict] = []
    prev_tables = set(prev.keys())
    curr_tables = set(curr.keys())

    for t in sorted(curr_tables - prev_tables):
        _add_change(rows, "table_added", t, "", "", "present", "Medium")
    for t in sorted(prev_tables - curr_tables):
        _add_change(rows, "table_removed", t, "", "present", "", "High")

    for t in sorted(prev_tables & curr_tables):
        p = prev[t]
        c = curr[t]
        p_cols = p["columns"]
        c_cols = c["columns"]
        p_col_set = set(p_cols)
        c_col_set = set(c_cols)

        for col in sorted(c_col_set - p_col_set):
            _add_change(rows, "column_added", t, col, "", "present", "Low")
        for col in sorted(p_col_set - c_col_set):
            _add_change(rows, "column_removed", t, col, "present", "", "High")

        for col in sorted(p_col_set & c_col_set):
            p_type = str(p["types"].get(col, ""))
            c_type = str(c["types"].get(col, ""))
            if p_type != c_type:
                _add_change(rows, "type_changed", t, col, p_type, c_type, "Medium")

        if p_cols != c_cols:
            _add_change(rows, "column_order_changed", t, "", str(p_cols), str(c_cols), "Low")

        if p["pk"] != c["pk"]:
            _add_change(rows, "primary_key_changed", t, "", str(p["pk"]), str(c["pk"]), "High")

    return pd.DataFrame(rows)


def _render_report(previous_schema: Optional[Path], current_schema: Path, changes: pd.DataFrame) -> str:
    lines: List[str] = []
    lines.append("# Schema Drift Report")
    lines.append("")
    lines.append(f"- Current schema: `{current_schema}`")
    lines.append(f"- Previous schema: `{previous_schema}`" if previous_schema else "- Previous schema: `none`")
    lines.append("")

    if previous_schema is None:
        lines.append("No previous schema snapshot available. Baseline initialized.")
        lines.append("")
        return "\n".join(lines)

    if changes.empty:
        lines.append("No schema drift detected between compared contract versions.")
        lines.append("")
        return "\n".join(lines)

    lines.append("## Drift Summary")
    for sev in ["High", "Medium", "Low"]:
        cnt = int((changes["severity"] == sev).sum())
        lines.append(f"- `{sev}`: {cnt}")
    lines.append("")

    lines.append("## Changes")
    for _, row in changes.sort_values(["severity", "change_type", "table_name"]).iterrows():
        lines.append(
            f"- `{row['severity']}` | `{row['change_type']}` | table=`{row['table_name']}`"
            + (f" | column=`{row['column_name']}`" if str(row["column_name"]) else "")
        )
    lines.append("")
    return "\n".join(lines)


def _snapshot_schema(current_schema: Path, history_dir: Path) -> Path:
    history_dir.mkdir(parents=True, exist_ok=True)
    current_text = current_schema.read_text(encoding="utf-8")

    existing = sorted(history_dir.glob("schema_contract_*.json"))
    if existing:
        latest = existing[-1]
        if latest.read_text(encoding="utf-8") == current_text:
            return latest

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dst = history_dir / f"schema_contract_{stamp}.json"
    dst.write_text(current_text, encoding="utf-8")
    return dst


def run_drift(cfg: DriftConfig) -> Tuple[pd.DataFrame, Optional[Path], Optional[Path]]:
    if not cfg.current_schema_file.exists():
        raise FileNotFoundError(f"Current schema contract not found: {cfg.current_schema_file}")

    previous = _resolve_previous_schema(cfg)
    if previous is None:
        changes = pd.DataFrame(
            columns=["change_type", "table_name", "column_name", "previous_value", "current_value", "severity"]
        )
    else:
        changes = compare_contracts(previous, cfg.current_schema_file)

    snapshot_path = None
    if cfg.snapshot_current:
        snapshot_path = _snapshot_schema(cfg.current_schema_file, cfg.history_dir)
    return changes, previous, snapshot_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate schema drift report from schema contracts.")
    parser.add_argument("--current-schema-file", type=Path, default=Path("schemas/v1/schema_contracts.json"))
    parser.add_argument("--previous-schema-file", type=Path, default=None)
    parser.add_argument("--history-dir", type=Path, default=Path("schemas/history"))
    parser.add_argument("--output-csv", type=Path, default=Path("reports/schema_drift_changes.csv"))
    parser.add_argument("--output-report", type=Path, default=Path("reports/schema_drift_report.md"))
    parser.add_argument("--snapshot-current", action="store_true")
    args = parser.parse_args()

    cfg = DriftConfig(
        current_schema_file=args.current_schema_file,
        previous_schema_file=args.previous_schema_file,
        history_dir=args.history_dir,
        output_csv=args.output_csv,
        output_report=args.output_report,
        snapshot_current=bool(args.snapshot_current),
    )

    changes, previous, snapshot_path = run_drift(cfg)

    cfg.output_csv.parent.mkdir(parents=True, exist_ok=True)
    changes.to_csv(cfg.output_csv, index=False)
    cfg.output_report.write_text(_render_report(previous, cfg.current_schema_file, changes), encoding="utf-8")

    print(f"Schema drift changes: {len(changes)} row(s) -> {cfg.output_csv}")
    print(f"Schema drift report written: {cfg.output_report}")
    if snapshot_path is not None:
        print(f"Schema snapshot written: {snapshot_path}")


if __name__ == "__main__":
    main()
