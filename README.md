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

## Repository Structure
```text
marketplace-profitability-fraud-seller-quality-command-center/
├── .github/workflows/
├── data/
│   ├── raw/
│   └── processed/
├── docs/
├── notebooks/
├── outputs/
│   ├── charts/
│   └── dashboard/
├── reports/
├── schemas/
│   └── v1/
├── src/
│   ├── data_generation/
│   ├── features/
│   ├── backtesting/
│   ├── scoring/
│   ├── governance/
│   ├── scenario_analysis/
│   ├── visualization/
│   ├── dashboard/
│   ├── pipeline/
│   └── validation/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
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

See full methodology in [methodology.md](methodology.md).

## Scoring Framework (Summary)
All scores are 0-100 and tiered (`Low`, `Moderate`, `High`, `Critical`):
- `seller_quality_score`: seller defect and operational reliability risk
- `order_risk_score`: order-level fraud/dispute routing risk
- `fraud_exposure_score`: seller-level fraud concentration risk
- `margin_fragility_score`: subsidy/leakage-driven economic fragility
- `governance_priority_score`: unified intervention priority

Each score includes:
- main risk driver
- recommended action (for example `seller coaching required`, `hold payouts`, `tighten promo eligibility`, `escalate for manual review`)

## Dashboard Overview
Official generated artifact:
- `outputs/dashboard/marketplace_command_center_dashboard.html`

Optional non-official sampled artifact:
- `outputs/dashboard/marketplace_command_center_dashboard_demo.html`

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

## Key Findings (Current Run)
Run-level findings are generated automatically during pipeline execution:
- `reports/executive_kpi_snapshot.md`
- `reports/executive_kpi_snapshot.csv`

This avoids stale hard-coded metrics in repository documentation and keeps executive claims aligned with current artifacts.

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

## Exceptional Upgrades Implemented
1. **Action backtesting module** (`src/backtesting/run_score_policy_backtest.py`) with threshold curves, intervention economics, and policy recommendation table.
2. **Monte Carlo uncertainty engine** (`src/scenario_analysis/run_scenario_monte_carlo.py`) with P05/P50/P95 outcome bands and probability-of-improvement outputs.
3. **Schema contracts and drift checks** (`src/validation/generate_schema_contracts.py`, `src/validation/validate_schema_contracts.py`) integrated into pipeline and CI.
4. **Official dashboard governance path** with optional sampled demo build isolated from the official release artifact.
5. **Containerized reproducibility** via `Dockerfile` and `docker-compose.yml`.
6. **Extended automated tests** covering backtesting, uncertainty tables, and schema contracts.
7. **Schema drift history reporting** (`src/validation/generate_schema_drift_report.py`) with version snapshots.
8. **Executive preview artifact pack** (`src/visualization/generate_executive_preview_pack.py`) plus CI artifact upload.
9. **Governance action register** (`src/governance/build_governance_action_register.py`) with owner-team and SLA fields.
10. **Realized margin alignment** across feature/scenario/dashboard layers via `realized_contribution_margin_proxy`.
11. **Automatic executive KPI snapshot** (`src/validation/generate_executive_snapshot.py`) to eliminate stale hard-coded memo metrics.
12. **Hardened schema type contracts** with datetime parse validation rather than string-only dtype checks.
13. **Packaging and test reliability hardening** (`pytest.ini`, `src/__init__.py`) so `pytest -q` works without manual `PYTHONPATH` overrides.
14. **Release-state enforcement** (`reports/validation_release_assessment.csv`) with blocker-aware publish gating.
15. **Metric governance contracts** (`schemas/v1/metric_governance_contract.csv`) with recomputation checks and governed KPI range enforcement.
16. **Hard release gate script** (`src/validation/enforce_release_gate.py`) integrated into pipeline/CI so weak states cannot pass silently.

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
  --metric-contract-file schemas/v1/metric_governance_contract.csv \
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

.venv/bin/python src/scenario_analysis/run_scenario_monte_carlo.py \
  --processed-dir data/processed \
  --output-dir data/processed \
  --charts-dir outputs/charts \
  --iterations 2000

.venv/bin/python src/backtesting/run_score_policy_backtest.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --output-dir data/processed \
  --charts-dir outputs/charts

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

# Optional non-official sampled dashboard
.venv/bin/python src/dashboard/build_executive_dashboard.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --reports-dir reports \
  --output-file outputs/dashboard/marketplace_command_center_dashboard_demo.html \
  --max-orders 25000 \
  --sample-seed 42

.venv/bin/python src/validation/generate_schema_contracts.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --output-file schemas/v1/schema_contracts.json

.venv/bin/python src/validation/validate_schema_contracts.py \
  --schema-file schemas/v1/schema_contracts.json \
  --output-file reports/schema_contract_issues.csv

.venv/bin/python src/validation/generate_schema_drift_report.py \
  --current-schema-file schemas/v1/schema_contracts.json \
  --history-dir schemas/history \
  --output-csv reports/schema_drift_changes.csv \
  --output-report reports/schema_drift_report.md \
  --snapshot-current

.venv/bin/python src/validation/run_full_validation.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --report-dir reports \
  --schema-file schemas/v1/schema_contracts.json \
  --metric-contract-file schemas/v1/metric_governance_contract.csv

.venv/bin/python src/validation/validate_metric_governance.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --reports-dir reports \
  --contract-file schemas/v1/metric_governance_contract.csv \
  --output-file reports/metric_governance_issues.csv

.venv/bin/python src/validation/enforce_release_gate.py \
  --release-file reports/validation_release_assessment.csv \
  --required-state "decision-support only"

.venv/bin/python src/visualization/generate_executive_preview_pack.py \
  --charts-dir outputs/charts \
  --output-image outputs/charts/00_executive_preview_pack.png \
  --output-manifest outputs/charts/00_executive_preview_pack.md
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

## 5) Docker Reproducibility
```bash
docker compose run --rm pipeline
docker compose run --rm test
```

## Future Improvements
1. Add anomaly-detection layer on channel-payment-risk clusters.
2. Add incremental build mode for near-real-time refresh patterns.
3. Add browser-rendered dashboard screenshot snapshots in CI (currently chart-preview pack only).
4. Add optional external benchmark profile pack to calibrate synthetic assumptions.
5. Add policy-outcome tracking on realized interventions (post-deployment feedback loop).

## Documentation Index
- [methodology.md](methodology.md)
- [data_dictionary.md](data_dictionary.md)
- [executive_summary.md](executive_summary.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [docs/portfolio_readiness.md](docs/portfolio_readiness.md)
- [docs/dashboard_architecture.md](docs/dashboard_architecture.md)
- [docs/release_readiness_governance.md](docs/release_readiness_governance.md)
- [docs/scoring_framework.md](docs/scoring_framework.md)
- [docs/scenario_decision_analysis.md](docs/scenario_decision_analysis.md)

## GitHub Polish Notes
- CI workflow is included at `.github/workflows/ci.yml` (tests + validation smoke check).
- Generated heavy dashboard HTML is ignored by default for lean repository commits (`.gitignore`), but reproducible from source scripts.
