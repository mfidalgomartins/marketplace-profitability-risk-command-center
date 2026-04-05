# Methodology

## Purpose and Analytical Standard
This project is designed as an internal decision-support methodology for marketplace leadership. The emphasis is on:
- interpretability over black-box complexity
- reproducibility over ad hoc analysis
- risk-aware economics over topline-only reporting

All outputs are generated from deterministic scripts and explicit assumptions.

## 1) Synthetic Data Generation Assumptions
Source implementation: `src/data_generation/generate_synthetic_marketplace_data.py`

## Core design assumptions
- Time horizon: 24 months (`2024-03-01` to `2026-02-28`).
- Scale: 9,000 buyers, 1,200 sellers, 156k+ orders, 226k+ order items.
- Multi-category marketplace with heterogeneous category economics and risk profiles.

## Behavioral realism embedded
- Seller quality heterogeneity (`quality_score`, `defect_risk`, `delay_risk`, `seller_risk`).
- Concentration effects among top sellers.
- Category-specific promo sensitivity and logistics characteristics.
- Region and channel risk differentials.
- Minority suspicious buyer behavior segments (including repeat-bad patterns).
- Payment risk signals and chargeback tendencies linked to channel/payment combinations.
- Logistics delays and cancellations linked to downstream refunds/disputes.

## Event generation principles
- Orders generated with seasonal demand uplift and growth trend.
- Item-level economics built first, then order-level totals reconciled.
- Refund and dispute events generated post-order with realistic reason/status distributions.
- Chargeback flags generated via payment risk dynamics.

## Known synthetic stress behavior
- Post-order leakage channels are now constrained to avoid artificial refund/dispute/chargeback double-counting beyond net paid value.
- The stress behavior is concentrated in high-risk cohorts through elevated event probabilities, not through arithmetic-overlap artifacts.

## 2) Metric Definitions

## Core economics
- **GMV** = sum(`gross_value`) at order level.
- **Net Value (NMV proxy)** = sum(`net_value`) where `net_value = net_paid_amount`.
- **Take Rate** = `sum(commission_fee) / sum(gross_value)`.
- **Subsidy Share** = `sum(subsidy_amount) / sum(gross_value)`.
- **Realized Contribution Margin Proxy** = `sum(commission_fee) - sum(subsidy_amount) - sum(refund_amount) - sum(dispute_amount) - sum(chargeback_loss_proxy)`.
- **Expected Margin After Risk** = `sum(estimated_margin_after_risk)` from order-level expected-loss modeling.
- **Risk-Adjusted GMV** = sum(`risk_adjusted_order_value`).

## Quality and risk rates
- **Refund Rate** = share of orders with `refund_amount > 0`.
- **Dispute Rate** = share of orders with `dispute_amount > 0`.
- **Chargeback Rate** = share of orders with `chargeback_flag = 1`.
- **Cancellation Rate** = share of orders with `cancellation_flag = 1`.
- **On-Time Fulfillment Rate** = `on_time_orders / delivery_eligible_orders`.
- **Delay Rate** = delayed orders / delivery-eligible orders.

## Concentration
- **Seller Concentration** measured via top-seller GMV share and cumulative concentration curve.

## 3) Engineered Feature Layer
Source implementation: `src/features/build_analytical_feature_layer.py`

## Design principles
- no leakage by construction for prior-rate features
- explicit smoothing for sparse entities
- traceability from derived fields to source columns
- stable naming conventions

## Primary analytical tables
1. `order_profitability_features`
- order-level economics and expected risk-adjusted value.

2. `seller_monthly_quality`
- seller-month operational and quality panel.

3. `buyer_behavior_risk`
- trailing-window buyer behavior summary with abnormal behavior flags.

4. `category_risk_summary`
- category-month fragility and leakage indicators.

5. `seller_risk_base`
- seller-level JSON-packed risk inputs for scoring.

## Expected loss modeling in order profitability
Expected losses are estimated from smoothed prior rates and risk priors by category/payment/channel:
- expected refund loss
- expected dispute loss
- expected chargeback loss

Then:
- `estimated_margin_after_risk = order_margin_proxy - expected_total_risk_loss`
- `risk_adjusted_order_value = net_value - expected_total_risk_loss`

## 4) Scoring Logic
Source implementation: `src/scoring/build_scoring_framework.py`

All scores are 0-100 and tiered:
- `Low` [0, 30)
- `Moderate` [30, 55)
- `High` [55, 75)
- `Critical` [75, 100]

## Score families and weighting logic
1. **seller_quality_score**
- weighted components: refund, dispute, chargeback, cancellation, delay, on-time failure, repeat-buyer weakness.

2. **order_risk_score**
- weighted components: payment signal/method, channel, category, prior buyer history, prior seller history, value percentile.

3. **fraud_exposure_score**
- weighted components: dispute rate, chargeback rate, high-risk order share, critical payment share, suspicious cluster share.

4. **margin_fragility_score**
- weighted components: negative margin share, subsidy dependency, refund value risk, dispute value risk, commission compression.

5. **governance_priority_score**
- weighted blend of quality risk, fraud risk, margin fragility, and concentration risk.

## Operating outputs
Each scored entity includes:
- risk tier
- main risk driver
- recommended action aligned to marketplace operations.

## Governance execution output
Source implementation: `src/governance/build_governance_action_register.py`

Produces `governance_action_register.csv` with:
- seller and order intervention queue
- owner team assignment
- SLA days by tier
- leakage and margin exposure fields for action sequencing

## 5) Scenario Assumptions
Source implementation: `src/scenario_analysis/build_scenario_decision_analysis.py`

Scenarios are deterministic what-if stress tests, not forecasts.

## Scenario set
1. `baseline`
2. `seller_quality_improvement`
3. `subsidy_tightening`
4. `fraud_control_improvement`
5. `downside_high_risk_deterioration`

## Mechanics
Each scenario applies factors to:
- GMV trajectory
- net-to-GMV conversion
- subsidy/refund/dispute/chargeback rates
- risk-gap factor (net vs risk-adjusted value)
- top-risk seller exposure
- bad-actor removal/correction assumptions

## Decision outputs
- scenario economics table
- component bridge
- downside exposure view
- ranked decision matrix with recommended action text

## 6) Scenario Uncertainty (Monte Carlo)
Source implementation: `src/scenario_analysis/run_scenario_monte_carlo.py`

This module extends deterministic scenarios with uncertainty-aware simulation:
- draws around key scenario factors (GMV, conversion, leakage, risk gap)
- produces distribution ranges (P05 / P50 / P95)
- estimates probability of outperforming baseline on margin and leakage

## Deliverables
- `data/processed/scenario_monte_carlo_samples.csv`
- `data/processed/scenario_monte_carlo_summary.csv`
- `data/processed/scenario_monte_carlo_decision.csv`
- `outputs/charts/18_scenario_monte_carlo_ranges.png`

## 7) Policy Backtesting
Source implementation: `src/backtesting/run_score_policy_backtest.py`

This module calibrates operational thresholds for `order_risk_score` using interpretable policy metrics:
- threshold-level precision, recall, and review-rate
- expected avoided loss under efficacy assumptions
- manual-review and conversion-friction costs
- net intervention benefit and recommended threshold

## Deliverables
- `data/processed/backtesting_threshold_curve.csv`
- `data/processed/backtesting_action_impact.csv`
- `data/processed/backtesting_recommended_policy.csv`
- `outputs/charts/17_order_risk_backtesting_thresholds.png`

## 8) Schema Contracts
Source implementations:
- `src/validation/generate_schema_contracts.py`
- `src/validation/validate_schema_contracts.py`

Contract-driven checks protect reproducibility and drift control:
- expected column list and type family per table
- primary-key candidate checks
- missing-file and schema-change detection

## Contract artifacts
- `schemas/v1/schema_contracts.json`
- `reports/schema_contract_issues.csv`

## 9) Validation Approach
Source implementation: `src/validation/run_full_validation.py`

Validation is run as a formal QA gate before final conclusions.

## Validation checks covered
1. row count sanity
2. duplicate key checks
3. null review
4. impossible value checks
5. date consistency checks
6. order-item reconciliation
7. refund/dispute/payment coherence
8. subsidy coherence checks
9. margin logic checks
10. denominator correctness checks
11. join inflation risk checks
12. leakage risk heuristics
13. tier assignment correctness
14. scenario arithmetic reconciliation
15. narrative overclaiming risk scan

## Validation deliverables
- `reports/validation_report.md`
- `reports/validation_issue_log.csv`
- `reports/validation_confidence_by_module.csv`
- `reports/validation_summary.csv`
- `reports/validation_release_assessment.csv`
- `reports/metric_governance_issues.csv`
- `reports/executive_kpi_snapshot.md`
- `reports/executive_kpi_snapshot.csv`

## Release classification model
The validation gate explicitly classifies each run into one release state:
- `technically valid`
- `analytically acceptable`
- `decision-support only`
- `screening-grade only`
- `not committee-grade`
- `publish-blocked`

`publish-blocked` is triggered by critical issues or high-severity blocker-class issues in governed modules (`metrics_logic`, `scoring`, `scenarios`, `schema_contracts`, `dashboard_feeds`).

## Metric governance contract
Source implementation: `src/validation/validate_metric_governance.py`

Contract file: `schemas/v1/metric_governance_contract.csv`

Checks enforce:
- governed KPI presence in executive snapshot
- range guardrails for finance/risk metrics
- recomputation alignment between snapshot and processed data
- relationship consistency (`risk_adjusted_value <= net_value <= gmv`)

The full-validation runner integrates this module and promotes failures into release-blocking validation issues.

## Current QA posture (latest run)
- No critical issues.
- No high-severity issues in the current synthetic run after post-order loss overlap constraints were added.

## 10) Interpretation Guardrails
- Treat outputs as strategic diagnostic support, not causal proof.
- Use score tiers for prioritization, not automatic punitive decisions.
- Use scenario outputs to compare intervention trade-offs, not to claim forecast certainty.
- Pair dashboard decisions with validation report review.
