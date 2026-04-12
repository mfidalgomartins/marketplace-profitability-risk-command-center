# Marketplace Profitability, Fraud & Seller Quality Command Center

**One-line description**
Executive marketplace analytics system that separates healthy growth from risk-inflated GMV by combining profitability, fraud exposure, seller quality, and operational reliability.

**Business problem**
GMV can grow while economics deteriorate. Leadership needs to know where growth is sustainable and where it is being propped up by subsidies, weak sellers, disputes, refunds, and fraud risk.

**What the system does**
- Generates a realistic multi-entity marketplace dataset.
- Builds governed analytical tables for profitability, risk, seller quality, and scenarios.
- Produces interpretable risk/governance scores with operational actions.
- Delivers an executive offline HTML dashboard and validation outputs.

**Decisions supported**
- Which seller cohorts should be coached, restricted, or escalated.
- Where subsidy policy should be tightened without damaging healthy growth.
- Which categories/regions/channels are driving margin leakage.
- Which fraud-control and operations actions have highest expected impact.

**Project architecture**
1. Data generation and raw layer.
2. Feature and metric layer.
3. Scoring and governance action layer.
4. Scenario and decision layer.
5. Visualization and dashboard layer.
6. Validation and release-gate layer.

**Repository structure**
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

**Core outputs**
- `outputs/dashboard/marketplace_command_center_dashboard.html`
- `outputs/charts/*.png`
- `data/processed/*.csv` (feature, scoring, scenario, governance outputs)
- `reports/validation_report.md`
- `reports/executive_kpi_snapshot.csv`

**Why this project is strong**
- End-to-end: economics, risk, operations, and governance in one system.
- Decision-oriented outputs, not just descriptive charts.
- Interpretable scoring with explicit business actions.
- Formal validation and release-state discipline.

**How to run**
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
make all
.venv/bin/pytest -q
```
Dashboard output: `outputs/dashboard/marketplace_command_center_dashboard.html`.

**Limitations**
- Data is synthetic and assumption-driven.
- Margin is a proxy, not accounting-grade P&L.
- Scenarios support strategy discussion; they are not production forecasts.

**Tools**
Python, SQL, pandas, NumPy, Plotly, Matplotlib, pytest, Make, Docker.
