# Scenario & Decision Analysis Memo

## Objective
Provide forward-looking strategic decision support for marketplace leadership by stress-testing profitability and risk under plausible operating-policy changes.

This layer is intentionally not a forecasting model. It is a controlled scenario engine that applies transparent business levers to recent run-rate economics.

## Method
- Baseline window: most recent 6 months of observed orders.
- Forward horizon: 6 months (scales baseline run-rate).
- Scenario mechanics: multiplicative factors applied to GMV, net conversion, subsidy/refund/dispute/chargeback rates, risk-adjustment gap, and top-risk seller exposure.
- Governance overlays include bad actor removal intensity (share of bad-actor exposure removed).
- Governance overlays include bad actor correction effectiveness (share of bad-actor leakage reduced via controls).

## Scenario Set
- `baseline`: status-quo continuation.
- `seller_quality_improvement`: stronger seller coaching + SLA enforcement, small GMV drag.
- `subsidy_tightening`: tighter promo eligibility, stronger margin discipline, more GMV drag.
- `fraud_control_improvement`: stricter risk controls and manual-review expansion, lower fraud leakage, mild conversion drag.
- `downside_high_risk_deterioration`: risky cohorts grow faster and quality worsens.

## Output Tables
- `data/processed/scenario_assumptions.csv`
- `data/processed/scenario_results_summary.csv`
- `data/processed/scenario_component_bridge.csv`
- `data/processed/scenario_top_risk_exposure.csv`
- `data/processed/scenario_decision_matrix.csv`

## Current Run Highlights
Use the current generated artifacts for run-specific values:
- `data/processed/scenario_results_summary.csv`
- `data/processed/scenario_decision_matrix.csv`
- `data/processed/scenario_top_risk_exposure.csv`
- `reports/executive_kpi_snapshot.md`

Interpretation should be based on the latest generated outputs, not hard-coded memo values.

## Business Interpretation
- Growth quality is fragile when risk-heavy cohorts scale faster than controls.
- Fraud controls and seller quality interventions produce the highest near-term economic protection in this synthetic marketplace.
- Subsidy tightening helps economics, but can over-correct demand if applied too broadly.
- Leadership should evaluate performance using both topline and risk-adjusted value, not GMV alone.

## Risks of Overconfidence
- Scenario factors are assumption-driven and may not hold under policy feedback effects.
- GMV elasticity and seller/buyer adaptation are simplified.
- Bad-actor correction/removal effects are modeled as fixed intensities, not dynamic behavior.
- No macro or competitor response is modeled.
- This is deterministic scenario planning, not a probabilistic forecast distribution.

## Decision Guidance
- First: execute fraud-control and seller-quality programs in high-risk tiers.
- Second: apply subsidy tightening selectively (category/channel/segment gates).
- Third: set explicit guardrails on top-risk seller exposure and payout controls.
- Fourth: track weekly quality-adjusted KPIs (`risk_adjusted_gmv`, leakage rate, CM proxy) as governance triggers.
