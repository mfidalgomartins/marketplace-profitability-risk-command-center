# Marketplace Profitability, Fraud & Seller Quality Command Center

## Project Overview
This project is a portfolio-grade marketplace analytics system built to answer one leadership question:

**Is marketplace growth healthy and durable, or is topline being inflated by fraud exposure, seller defects, subsidy dependence, and hidden margin leakage?**

The repository includes synthetic data generation, analytical feature engineering, scoring, scenario analysis, executive visualization, a self-contained offline dashboard, and a formal QA validation framework.

## Business Problem
Marketplace leadership teams often rely on GMV as the primary growth signal. GMV alone can mask structural risks:
- high-volume sellers with poor operational quality
- subsidy-funded growth with weak underlying economics
- rising refunds, disputes, and chargebacks
- concentration risk among top sellers
- logistics deterioration driving CX and margin erosion

This project builds a decision-support operating model that combines growth, profitability, fraud, seller quality, and operational reliability in one control-tower workflow.

## Repository Scope
To keep GitHub clean and reviewable, generated runtime artifacts are not versioned:
- `data/raw/*.csv`
- `data/processed/*.csv`
- `outputs/*`
- `reports/*`

All of these are reproducible from source scripts and pipeline entrypoints in this repository.

## Why It Matters
If leadership tracks only GMV, they can miss:
- hidden contribution margin destruction
- risk concentration in a small seller cohort
- fraud leakage that scales with growth
- poor-quality growth that is not economically sustainable

The system is designed for Finance, Risk, Operations, and Seller Management to align on common metrics, interventions, and priorities.

## Repository Structure (Lean)
```text
marketplace-profitability-risk-command-center/
├── README.md
├── requirements.txt
├── .gitignore
├── src/
├── data/
├── docs/
├── tests/
├── outputs/
├── config/
├── reports/
├── Makefile
├── Dockerfile
└── pytest.ini
```

## Datasets
### Raw Tables
- `buyers.csv`
- `sellers.csv`
- `products.csv`
- `orders.csv`
- `order_items.csv`
- `payments.csv`
- `refunds.csv`
- `disputes.csv`
- `logistics_events.csv`

### Processed Analytical Tables
- `order_profitability_features.csv`
- `seller_monthly_quality.csv`
- `buyer_behavior_risk.csv`
- `category_risk_summary.csv`
- `seller_risk_base.csv`
- `order_risk_scores.csv`
- `seller_quality_scores.csv`
- `fraud_exposure_scores.csv`
- `margin_fragility_scores.csv`
- `governance_priority_scores.csv`
- `governance_action_register.csv`
- `seller_scorecard.csv`
- `scenario_results_summary.csv`
- `scenario_decision_matrix.csv`
- additional score/scenario support outputs

## Methodology (Summary)
1. **Synthetic marketplace generation** with realistic heterogeneity, risk clusters, seasonality, and concentration.
2. **Feature engineering** for order economics, seller quality, buyer risk, and category fragility using leakage-aware logic.
3. **Scoring framework** with interpretable 0-100 risk scores and operationally mapped actions.
4. **Scenario analysis** with deterministic policy scenarios plus Monte Carlo uncertainty ranges.
5. **Policy backtesting** for order-risk thresholds, precision/recall trade-offs, and intervention net-benefit.
6. **Visualization + dashboard** for executive decision workflows with governed KPI anchoring.
7. **Formal validation + schema contracts** across coherence, reconciliation, arithmetic, and schema drift.
8. **Release-readiness governance gate** with explicit states (`technically valid`, `analytically acceptable`, `decision-support only`, `screening-grade only`, `not committee-grade`, `publish-blocked`).

See full methodology in [docs/methodology.md](docs/methodology.md).

## Scoring Framework (Summary)
Interpretable 0-100 scores (Low/Moderate/High/Critical) for seller and order risk. Each score includes a main driver and a recommended action for operations.

## Dashboard Overview
Official generated artifact:
- `outputs/dashboard/marketplace_command_center_dashboard.html`

Core dashboard sections:
1. Executive Overview
2. Profitability
3. Risk & Fraud
4. Seller Quality
5. Operations & CX
6. Scenario Center
7. Methodology & Definitions

Interactive capabilities:
- sticky filters (date, region, category, seller/buyer/risk dimensions)
- KPI cards and alerts
- hover tooltips
- searchable/sortable/paginated seller table
- scenario what-if comparison
- offline self-contained deployment

## Evidence Outputs
Run-level evidence is generated on demand (not versioned in GitHub):
- `reports/executive_kpi_snapshot.csv`
- `reports/validation_report.md`

## Recommendations
1. **Prioritize fraud-control uplift first** in high-risk channels/payment patterns.
2. **Enforce seller quality and SLA interventions** for high-volume weak-quality sellers.
3. **Tighten subsidy eligibility selectively** by category/channel rather than broad cuts.
4. **Operationally target delay-heavy cohorts** to reduce refund/dispute spillover.
5. **Use governance score + concentration together** for payout controls and escalation.

## Governance Action Register
Pipeline now generates `data/processed/governance_action_register.csv`:
- unified seller + order intervention queue
- owner team assignment (`Risk Operations`, `Seller Operations`, `Finance and Pricing`, etc.)
- SLA days by risk tier
- leakage and margin exposure fields for execution prioritization

## Limitations
- Data is synthetic and assumption-driven, not observed production telemetry.
- Scenario analysis is strategic decision support, not probabilistic forecasting.
- Causal claims should not be inferred from descriptive diagnostics.

## Notable Capabilities
1. **Governed KPI snapshot** for dashboard anchoring (`src/validation/generate_executive_snapshot.py`).
2. **Interpretable scoring** for seller and order risk (`src/scoring/build_scoring_framework.py`).
3. **Scenario stress tests** for decision support (`src/scenario_analysis/build_scenario_decision_analysis.py`).

## How To Run
## 1) Environment Setup
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 1.1) Fastest Path (One Command)
```bash
make all
```

Equivalent direct entrypoint:
```bash
.venv/bin/python src/pipeline/run_full_pipeline.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --charts-dir outputs/charts \
  --dashboard-file outputs/dashboard/marketplace_command_center_dashboard.html \
  --metric-contract-file config/contracts/v1/metric_governance_contract.csv \
  --required-release-state "decision-support only" \
  --reports-dir reports
```

## 2) Full Pipeline Build
```bash
.venv/bin/python src/data_generation/generate_synthetic_marketplace_data.py --output-dir data/raw

.venv/bin/python src/features/build_analytical_feature_layer.py \
  --raw-dir data/raw \
  --output-dir data/processed

.venv/bin/python src/scoring/build_scoring_framework.py \
  --raw-dir data/raw \
  --processed-dir data/processed

.venv/bin/python src/governance/build_governance_action_register.py \
  --processed-dir data/processed \
  --output-dir data/processed

.venv/bin/python src/scenario_analysis/build_scenario_decision_analysis.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --baseline-months 6 \
  --horizon-months 6

.venv/bin/python src/visualization/build_marketplace_visualizations.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --output-dir outputs/charts

.venv/bin/python src/validation/generate_executive_snapshot.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --reports-dir reports

.venv/bin/python src/dashboard/build_executive_dashboard.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --reports-dir reports \
  --output-file outputs/dashboard/marketplace_command_center_dashboard.html

.venv/bin/python src/validation/generate_schema_contracts.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --output-file config/contracts/v1/schema_contracts.json

.venv/bin/python src/validation/validate_schema_contracts.py \
  --schema-file config/contracts/v1/schema_contracts.json \
  --output-file reports/schema_contract_issues.csv

.venv/bin/python src/validation/run_full_validation.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --report-dir reports \
  --schema-file config/contracts/v1/schema_contracts.json \
  --metric-contract-file config/contracts/v1/metric_governance_contract.csv

.venv/bin/python src/validation/enforce_release_gate.py \
  --release-file reports/validation_release_assessment.csv \
  --required-state "decision-support only"

```

## 3) Tests
Run tests after generating artifacts (fresh clones do not include generated `data/` tables by design):
```bash
make all
```

Then:
```bash
.venv/bin/pytest -q
```

or
```bash
make test
```

## 4) Open Dashboard
Open `outputs/dashboard/marketplace_command_center_dashboard.html` in a browser.

## Future Improvements
1. Add anomaly-detection layer on channel-payment-risk clusters.
2. Add incremental build mode for near-real-time refresh patterns.
3. Add browser-rendered dashboard screenshot snapshots in CI.
4. Add optional external benchmark profile pack to calibrate synthetic assumptions.
5. Add policy-outcome tracking on realized interventions (post-deployment feedback loop).

## Documentation Index
- [docs/methodology.md](docs/methodology.md)
- [docs/data_dictionary.md](docs/data_dictionary.md)
- [docs/executive_summary.md](docs/executive_summary.md)

## GitHub Polish Notes
- CI workflow is included at `.github/workflows/ci.yml` (tests + validation smoke check).
- Generated heavy dashboard HTML is ignored by default for lean repository commits (`.gitignore`), but reproducible from source scripts.
