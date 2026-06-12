# Methodology

## Purpose
Demonstrate a reproducible marketplace decision-support workflow with three priorities:
- interpretability over black-box models
- risk-aware economics over topline-only growth
- reproducible, auditable outputs

## Synthetic Data
- 24-month horizon, multi-category marketplace.
- Heterogeneous seller quality, promo sensitivity, and region/channel risk.
- Post-order events (refunds, disputes, chargebacks) tied to operational and risk signals.
- One seller per order. The validation layer blocks publication if multi-seller orders appear because current economics are modeled at order grain.

## Core Metrics
- GMV, Net Value, Take Rate, Subsidy Share.
- Realized Contribution Margin Proxy: commission minus subsidy, refund value, dispute value, and chargeback loss proxy.
- Expected Margin After Risk: pre-outcome margin proxy minus modeled expected risk loss.
- Risk-Adjusted Value: net value minus modeled expected risk loss.
- Refund/Dispute/Chargeback/Cancellation/On-time rates.

Realized contribution margin is intentionally conservative and is not directly comparable with expected margin after risk. The two measures answer different questions: realized gross leakage versus pre-outcome underwriting exposure.

## Feature Layer (Core Tables)
- `order_profitability_features`
- `seller_monthly_quality`
- `buyer_behavior_risk`
- `category_risk_summary`
- `seller_risk_base`

Historical buyer and seller event rates use only prior orders. Current-order outcomes are excluded from score inputs.

## Scoring Summary
All scores are 0-100 heuristic indices (Low/Moderate/High/Critical).
- `seller_quality_score`: refund/dispute/chargeback + operational reliability.
- `order_risk_score`: payment signal/method + channel/category + prior buyer/seller risk.
- `fraud_exposure_score`: dispute/chargeback concentration + risky order share.
- `margin_fragility_score`: negative margin share + subsidy dependence + leakage exposure.
- `governance_priority_score`: blended seller quality, fraud exposure, margin fragility, concentration.

Scores include a main driver and recommended action for operational routing. They are not calibrated event probabilities.

## Scenarios
Deterministic what-if scenarios:
- baseline
- seller quality improvement
- subsidy tightening
- fraud control improvement
- downside risk deterioration

Monte Carlo outputs apply uncertainty ranges around the same assumptions. Neither deterministic nor Monte Carlo scenarios are forecasts.

## Threshold Policy Simulation
The threshold analysis evaluates historical score/outcome combinations and assumed intervention economics. It is retrospective and in-sample. The recommended threshold is a capacity-planning starting point, not a deployable policy without later-period holdout validation.

## Validation
Checks run before dashboard publication:
- reconciliation and coherence (orders/refunds/disputes/payments)
- schema contract validation
- complete metric governance coverage for official dashboard KPIs
- scenario arithmetic consistency
- score directional separation
- single-seller order-grain enforcement
- narrative overclaiming scan

Passing validation means the repository is suitable for public decision-support demonstration. It does not make the synthetic analysis production-ready or committee-grade.

## Publication Outputs
- The standalone dashboard is generated from the current processed tables and validation outputs.
- The publication chart pack is rebuilt into `outputs/graphs/`.
- The analytical PDF report is rebuilt into `outputs/reports/marketplace-command-center-report.pdf`.
- GitHub Pages is staged only after the configured release gate passes.
