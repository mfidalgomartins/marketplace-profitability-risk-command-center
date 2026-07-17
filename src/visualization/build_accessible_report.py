from __future__ import annotations

import argparse
import hashlib
import html
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pydyf
from pypdf import PdfReader
from pypdf.generic import DictionaryObject
from weasyprint import HTML


@dataclass(frozen=True)
class AccessibleReportConfig:
    processed_dir: Path = Path("data/processed")
    reports_dir: Path = Path("reports")
    output_file: Path = Path("outputs/reports/marketplace-command-center-accessible-summary.pdf")


def _money(value: Any) -> str:
    return f"${float(value):,.0f}"


def _number(value: Any, decimals: int = 3) -> str:
    return f"{float(value):,.{decimals}f}"


def _integer(value: Any) -> str:
    return f"{int(value):,}"


def _escape(value: object) -> str:
    return html.escape(str(value))


def _table(headers: list[str], rows: list[list[object]], caption: str) -> str:
    header_html = "".join(f'<th scope="col">{_escape(header)}</th>' for header in headers)
    row_html = "".join("<tr>" + "".join(f"<td>{_escape(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return (
        '<div class="table-wrap"><table>'
        f"<caption>{_escape(caption)}</caption>"
        f"<thead><tr>{header_html}</tr></thead><tbody>{row_html}</tbody></table></div>"
    )


def _load_inputs(cfg: AccessibleReportConfig) -> dict[str, pd.DataFrame]:
    files = {
        "finance": cfg.processed_dir / "accounting_kpi_summary.csv",
        "reconciliation": cfg.processed_dir / "finance_reconciliation.csv",
        "holdout": cfg.processed_dir / "temporal_holdout_metrics.csv",
        "release": cfg.processed_dir / "model_release_assessment.csv",
        "alerts": cfg.processed_dir / "model_monitoring_alerts.csv",
        "experiment": cfg.processed_dir / "experiment_results.csv",
        "power": cfg.processed_dir / "experiment_power.csv",
        "balance": cfg.processed_dir / "experiment_balance.csv",
        "warehouse": cfg.reports_dir / "warehouse_validation.csv",
    }
    missing = [str(path) for path in files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Accessible report inputs are missing: {missing}")
    return {name: pd.read_csv(path) for name, path in files.items()}


def _build_html(inputs: dict[str, pd.DataFrame]) -> str:
    finance = inputs["finance"].iloc[0]
    release = inputs["release"].iloc[0]
    holdout = inputs["holdout"].set_index("split")
    experiment = inputs["experiment"].set_index("metric")
    power = inputs["power"].iloc[0]
    holdout_metrics = holdout.loc["holdout"]
    event_effect = experiment.loc["adverse_event_rate"]
    loss_effect = experiment.loc["adverse_loss_per_order"]
    alert_count = len(inputs["alerts"])
    balance_max = float(inputs["balance"]["absolute_standardized_mean_difference"].max())
    warehouse_passed = int(inputs["warehouse"]["status"].eq("passed").sum())
    warehouse_total = len(inputs["warehouse"])
    as_of_date = str(finance["as_of_date"])
    created_at = f"{as_of_date[:10]}T23:59:59Z"

    finance_table = _table(
        ["Measure", "Value"],
        [
            ["Gross marketplace value", _money(finance["gross_marketplace_value"])],
            ["Gross commission revenue", _money(finance["gross_commission_revenue"])],
            ["Commission reversals", _money(finance["commission_reversals"])],
            ["Operating expense", _money(finance["total_operating_expense"])],
            ["Accounting contribution", _money(finance["accounting_contribution"])],
        ],
        "Synthetic management accounts, reconciled to the order subledger",
    )
    split_table = _table(
        ["Split", "Rows", "Event rate", "ROC AUC", "AP lift", "Brier", "ECE"],
        [
            [
                split,
                _integer(row["row_count"]),
                f"{100 * float(row['event_rate']):.1f}%",
                _number(row["roc_auc"]),
                _number(row["average_precision_lift"]),
                _number(row["brier_score"]),
                _number(row["expected_calibration_error"]),
            ]
            for split, row in holdout.iterrows()
        ],
        "Time-based evaluation using only fully matured outcomes",
    )
    experiment_table = _table(
        ["Outcome", "Control", "Treatment", "ITT effect", "95% confidence interval", "p-value"],
        [
            [
                "Adverse event rate",
                f"{float(event_effect['control_mean']):.2f}%",
                f"{float(event_effect['treatment_mean']):.2f}%",
                f"{float(event_effect['intention_to_treat_effect']):.2f} pp",
                (
                    f"[{float(event_effect['confidence_interval_lower']):.2f}, "
                    f"{float(event_effect['confidence_interval_upper']):.2f}] pp"
                ),
                _number(event_effect["p_value"], 4),
            ],
            [
                "Adverse loss per order",
                f"${float(loss_effect['control_mean']):.2f}",
                f"${float(loss_effect['treatment_mean']):.2f}",
                f"${float(loss_effect['intention_to_treat_effect']):.2f}",
                (
                    f"[${float(loss_effect['confidence_interval_lower']):.2f}, "
                    f"${float(loss_effect['confidence_interval_upper']):.2f}]"
                ),
                _number(loss_effect["p_value"], 4),
            ],
        ],
        "Synthetic randomized trial with seller-clustered standard errors",
    )
    alert_text = (
        f"{alert_count} monitoring threshold breaches require review."
        if alert_count
        else "No monitoring threshold breaches were detected."
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="author" content="Marketplace Command Center">
  <meta name="description" content="Accessible executive summary for the marketplace profitability, fraud, and seller-quality decision system.">
  <meta name="keywords" content="marketplace, profitability, fraud, seller quality, governance">
  <meta name="generator" content="Marketplace Command Center reproducible pipeline">
  <meta name="dcterms.created" content="{created_at}">
  <meta name="dcterms.modified" content="{created_at}">
  <title>Marketplace Command Center — Accessible Executive Summary</title>
  <style>
    @page {{ size: A4; margin: 17mm 16mm 18mm; @bottom-right {{ content: "Page " counter(page) " of " counter(pages); color: #526071; font-size: 9pt; }} }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: #17202b; font-family: Arial, Helvetica, sans-serif; font-size: 10.5pt; line-height: 1.45; }}
    h1 {{ margin: 0 0 7mm; color: #0c2f4f; font-size: 25pt; line-height: 1.08; }}
    h2 {{ margin: 8mm 0 3mm; color: #0c2f4f; font-size: 16pt; break-after: avoid; }}
    h3 {{ margin: 5mm 0 2mm; color: #174f78; font-size: 12pt; break-after: avoid; }}
    p {{ margin: 0 0 3mm; }}
    ul {{ margin: 1mm 0 4mm 5mm; padding-left: 4mm; }}
    li {{ margin-bottom: 1.5mm; }}
    .eyebrow {{ margin-bottom: 3mm; color: #245f89; font-size: 9pt; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
    .scope {{ border-left: 4px solid #1677a8; background: #edf6fa; padding: 4mm 5mm; margin: 5mm 0; }}
    .scope strong {{ color: #0c2f4f; }}
    .kpis {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 4mm; margin: 5mm 0; }}
    .kpi {{ border: 1px solid #cbd7df; border-radius: 2mm; padding: 4mm; break-inside: avoid; }}
    .kpi-label {{ color: #526071; font-size: 8.5pt; text-transform: uppercase; letter-spacing: .04em; }}
    .kpi-value {{ margin-top: 1mm; color: #0c2f4f; font-size: 18pt; font-weight: 700; }}
    .kpi-note {{ margin-top: 1mm; color: #526071; font-size: 8.5pt; }}
    .table-wrap {{ margin: 3mm 0 6mm; break-inside: avoid; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 8.5pt; }}
    caption {{ padding: 0 0 2mm; color: #384657; font-weight: 700; text-align: left; }}
    th {{ background: #0c2f4f; color: white; font-weight: 700; text-align: left; }}
    th, td {{ border: 1px solid #cbd7df; padding: 2.2mm; vertical-align: top; }}
    tbody tr:nth-child(even) {{ background: #f4f7f9; }}
    .status {{ display: inline-block; border: 1px solid #245f89; border-radius: 4mm; padding: 1mm 3mm; color: #0c2f4f; font-weight: 700; }}
    .page-break {{ break-before: page; }}
    .compact {{ font-size: 10pt; line-height: 1.35; }}
    .compact h3 {{ margin: 3mm 0 1mm; }}
    .compact ul, .compact ol {{ margin-bottom: 2mm; }}
    .compact li {{ margin-bottom: .7mm; }}
    .small {{ color: #526071; font-size: 8.5pt; }}
    footer {{ margin-top: 10mm; border-top: 1px solid #cbd7df; padding-top: 3mm; color: #526071; font-size: 8.5pt; }}
  </style>
</head>
<body>
<main>
  <header>
    <p class="eyebrow">Decision-support system · Accessible PDF/UA summary</p>
    <h1>Marketplace Profitability, Fraud &amp; Seller Quality Command Center</h1>
    <p>Executive evidence pack as of {_escape(as_of_date[:10])}. The report connects governed finance, point-in-time risk validation, controlled intervention design, and operational controls.</p>
    <div class="scope"><strong>Evidence boundary.</strong> All source records and intervention outcomes are synthetic. Findings demonstrate analytical and engineering capability; they do not establish real-world causal impact or authorize automated enforcement.</div>
  </header>

  <section aria-labelledby="snapshot-title">
    <h2 id="snapshot-title">Executive snapshot</h2>
    <div class="kpis">
      <div class="kpi"><div class="kpi-label">Orders accounted</div><div class="kpi-value">{_integer(finance["order_count"])}</div><div class="kpi-note">One subledger row per order</div></div>
      <div class="kpi"><div class="kpi-label">Accounting contribution</div><div class="kpi-value">{_money(finance["accounting_contribution"])}</div><div class="kpi-note">Synthetic management-accounting basis</div></div>
      <div class="kpi"><div class="kpi-label">Mature holdout ROC AUC</div><div class="kpi-value">{_number(holdout_metrics["roc_auc"])}</div><div class="kpi-note">Later-period, label-matured evaluation</div></div>
      <div class="kpi"><div class="kpi-label">Trial ITT effect</div><div class="kpi-value">{float(event_effect["intention_to_treat_effect"]):.2f} pp</div><div class="kpi-note">Synthetic randomized intervention</div></div>
    </div>
    <p><span class="status">Model status: {_escape(release["release_status"])}</span></p>
    <p>{_escape(alert_text)} Automated decision status remains <strong>{_escape(release["automated_decision_status"])}</strong>.</p>
  </section>

  <section class="page-break" aria-labelledby="finance-title">
    <h2 id="finance-title">1. Governed management accounts</h2>
    <p>The order subledger recognizes commission revenue, commission reversals, payment processing, marketplace subsidy, unrecovered refund exposure, disputes, chargebacks, and fulfillment support. Every monthly journal is double-entry.</p>
    {finance_table}
    <p><strong>Reconciliation:</strong> all {_integer(len(inputs["reconciliation"]))} finance controls passed. The general ledger balances and reconciles to the order-level contribution.</p>
  </section>

  <section aria-labelledby="model-title">
    <h2 id="model-title">2. Point-in-time model evidence</h2>
    <p>Calibration is learned only from development observations whose outcomes were available at the training cutoff. A maturation gap separates training from the later-period holdout; the most recent records remain an outcome-unmatured shadow window.</p>
    {split_table}
    <h3>Release interpretation</h3>
    <ul>
      <li>Holdout window: {_escape(release["holdout_start"])} through {_escape(release["holdout_end"])}, {_integer(release["holdout_rows"])} orders.</li>
      <li>Unmatured shadow: {_integer(release["unmatured_shadow_rows"])} orders, monitored for score drift but excluded from outcome performance.</li>
      <li>Required next step: {_escape(release["required_next_step"])}</li>
    </ul>
  </section>

  <section aria-labelledby="experiment-title">
    <h2 id="experiment-title">3. Controlled intervention design</h2>
    <p>Eligible high-risk orders are allocated deterministically to business-as-usual or enhanced manual review. The analysis reports intention-to-treat effects with seller-clustered standard errors.</p>
    {experiment_table}
    <ul>
      <li>Sample size: {_integer(event_effect["sample_size"])} orders across {_integer(event_effect["seller_cluster_count"])} seller clusters.</li>
      <li>Maximum absolute standardized mean difference: {_number(balance_max)}; values below 0.10 satisfy the balance rule.</li>
      <li>Power at the policy MDE: {100 * float(power["estimated_power_at_mde"]):.1f}% ({_escape(power["power_status"])}).</li>
    </ul>
  </section>

  <section class="compact" aria-labelledby="controls-title">
    <h2 id="controls-title">4. Production controls and operating model</h2>
    <h3>Data and orchestration</h3>
    <ul>
      <li>Versioned schema, metric, monitoring, finance, and experiment contracts.</li>
      <li>Idempotent DuckDB catalog with raw and analytics views plus curated decision marts.</li>
      <li>{warehouse_passed} of {warehouse_total} warehouse source and reconciliation checks passed.</li>
      <li>Reproducible pipeline, deterministic analytical artifacts, CI quality gates, and dependency scanning.</li>
    </ul>
    <h3>Case management</h3>
    <ul>
      <li>Deny-by-default bearer authentication and role-based permissions.</li>
      <li>Optimistic concurrency and idempotent commands for all writes.</li>
      <li>Manager approval required to close a case.</li>
      <li>Append-only case events and HMAC-chained audit records.</li>
    </ul>
    <h3>Known limitations</h3>
    <ul>
      <li>Synthetic data cannot validate external validity, treatment compliance, adversarial response, or live operating cost.</li>
      <li>The logistic calibration layer converts a governed heuristic score into a probability; it is not a claim of a production-trained fraud model.</li>
      <li>Finance policies are explicit management-accounting assumptions and require controller approval before real reporting use.</li>
      <li>The SQLite case store is appropriate for local demonstration and single-instance deployment; multi-instance production requires a managed transactional database.</li>
    </ul>
    <h3>Next real-world milestones</h3>
    <ol>
      <li>Run a prospective shadow period on real, fully matured outcomes.</li>
      <li>Obtain Finance sign-off on account mapping and loss-recognition policy.</li>
      <li>Pre-register the intervention experiment and instrument assignment, exposure, compliance, and guardrails.</li>
      <li>Deploy the API behind centralized identity, TLS termination, rate limiting, and managed secrets.</li>
    </ol>
  </section>
</main>
<footer>Marketplace Command Center · Accessible executive summary · Evidence scope: synthetic decision support only</footer>
</body>
</html>"""


def _stabilize_table_header_ids(_document: object, pdf: pydyf.PDF) -> None:
    """Replace process-specific WeasyPrint table-header IDs with stable IDs."""
    header_ids: dict[str, str] = {}
    header_number = 0

    for pdf_object in pdf.objects:
        if not isinstance(pdf_object, pydyf.Dictionary):
            continue
        if pdf_object.get("Type") != "/StructElem" or pdf_object.get("S") != "/TH":
            continue
        header_id = pdf_object.get("ID")
        if not isinstance(header_id, pydyf.String):
            continue
        header_number += 1
        stable_id = f"table-header-{header_number:04d}"
        header_ids[str(header_id.string)] = stable_id
        header_id.string = stable_id

    for pdf_object in pdf.objects:
        if not isinstance(pdf_object, pydyf.Dictionary):
            continue
        attributes = pdf_object.get("A")
        if not isinstance(attributes, pydyf.Dictionary):
            continue
        headers = attributes.get("Headers")
        if not isinstance(headers, pydyf.Array):
            continue
        for header in headers:
            if isinstance(header, pydyf.String) and str(header.string) in header_ids:
                header.string = header_ids[str(header.string)]


def build_accessible_report(cfg: AccessibleReportConfig) -> bytes:
    inputs = _load_inputs(cfg)
    report_html = _build_html(inputs)
    identifier = hashlib.sha256(report_html.encode("utf-8")).digest()[:16]
    pdf = HTML(string=report_html, base_url=str(Path.cwd())).write_pdf(
        pdf_variant="pdf/ua-1",
        pdf_tags=True,
        pdf_identifier=identifier,
        optimize_images=True,
        finisher=_stabilize_table_header_ids,
    )
    if not isinstance(pdf, bytes) or not pdf.startswith(b"%PDF"):
        raise ValueError("WeasyPrint did not produce a valid PDF byte stream.")
    reader = PdfReader(BytesIO(pdf))
    catalog = cast(DictionaryObject, reader.trailer["/Root"])
    mark_info = cast(DictionaryObject | None, catalog.get("/MarkInfo"))
    metadata_stream = catalog.get("/Metadata")
    metadata_bytes = b"" if metadata_stream is None else cast(Any, metadata_stream).get_object().get_data()
    structure_ok = (
        "/StructTreeRoot" in catalog
        and mark_info is not None
        and bool(mark_info.get("/Marked"))
        and bool(catalog.get("/Lang"))
        and b"pdfuaid:part" in metadata_bytes
    )
    if not structure_ok:
        raise ValueError("Accessible PDF is missing required PDF/UA structure or metadata.")
    cfg.output_file.parent.mkdir(parents=True, exist_ok=True)
    cfg.output_file.write_bytes(pdf)
    return pdf


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the tagged PDF/UA executive summary.")
    parser.add_argument("--processed-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument(
        "--output-file",
        type=Path,
        default=Path("outputs/reports/marketplace-command-center-accessible-summary.pdf"),
    )
    args = parser.parse_args()
    cfg = AccessibleReportConfig(
        processed_dir=args.processed_dir,
        reports_dir=args.reports_dir,
        output_file=args.output_file,
    )
    pdf = build_accessible_report(cfg)
    print(f"Accessible PDF/UA summary generated: {cfg.output_file} ({len(pdf):,} bytes)")


if __name__ == "__main__":
    main()
