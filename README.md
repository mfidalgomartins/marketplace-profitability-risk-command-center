# Marketplace Profitability, Fraud & Seller Quality Command Center

This project is an executive analytics control tower for digital marketplaces. It was built to answer a practical leadership question: is growth economically healthy, or is GMV being inflated by subsidy dependence, weak seller behavior, fraud exposure, and operational deterioration.

Live dashboard: [mfidalgomartins.github.io/marketplace-profitability-risk-command-center](https://mfidalgomartins.github.io/marketplace-profitability-risk-command-center/)

Most marketplace reporting overweights topline volume. That creates blind spots: loss-making cohorts can look like growth winners, high-volume sellers can quietly degrade CX, and disputes or chargebacks can scale before governance reacts. This repository focuses on those blind spots and turns them into decision-ready outputs.

## What this system delivers
The pipeline generates realistic multi-entity marketplace data, builds governed analytical tables, calculates interpretable risk and quality scores, runs scenario analysis, and publishes an offline executive dashboard with validation evidence.

The design is intentionally end-to-end: profitability, fraud risk, seller quality, operations, and governance are treated as one system instead of separate analyses.

## Decisions it supports
- Where growth is healthy vs fragile after risk and leakage adjustments.
- Which seller cohorts require coaching, tighter controls, payout holds, or escalation.
- Where subsidy policy should be tightened without damaging high-quality growth.
- Which category, region, or channel issues should be prioritized first by risk, finance, and operations.

## Architecture at a glance
1. Synthetic data generation and raw layer.
2. Feature and KPI engineering layer.
3. Scoring and governance action layer.
4. Scenario and decision analysis layer.
5. Visualization and executive dashboard layer.
6. Validation and release-gate layer.

## Repository layout
```text
.
├── src/
├── data/
├── reports/
├── outputs/
├── docs/
├── tests/
├── config/
├── notebooks/
├── requirements.txt
├── Makefile
└── README.md
```

## Core outputs
- `outputs/dashboard/executive-marketplace-command-center.html`
- `outputs/charts/*.png`
- `data/processed/*.csv`
- `reports/validation_report.md`
- `reports/executive_kpi_snapshot.csv`

## Why this project stands out
It is not a chart pack. It is a governed decision-support workflow with explicit scoring logic, operational action mapping, scenario trade-off analysis, and validation controls designed to reduce false confidence.

## Run
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make all
.venv/bin/pytest -q
```
Dashboard artifact: `outputs/dashboard/executive-marketplace-command-center.html`
GitHub Pages entrypoint: `docs/index.html` and `docs/executive-marketplace-command-center.html` (auto-deployed via `.github/workflows/pages.yml`).

## Limits and scope
- Data is synthetic and assumption-driven.
- Margin is an analytical proxy, not accounting P&L.
- Scenarios are for strategic stress testing, not production forecasting.

Tools: Python, SQL, pandas, NumPy, Plotly, Matplotlib, pytest, Make, Docker.
