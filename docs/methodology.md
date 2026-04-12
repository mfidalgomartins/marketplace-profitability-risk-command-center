# Methodology (Concise)

## Purpose
Decision-support for marketplace leadership with three priorities:
- interpretability over black-box models
- risk-aware economics over topline-only growth
- reproducible, auditable outputs

## Data Generation (Synthetic)
- 24-month horizon, multi-category marketplace.
- Heterogeneous seller quality, promo sensitivity, and region/channel risk.
- Post-order events (refunds, disputes, chargebacks) tied to operational and risk signals.

## Core Metrics
- GMV, Net Value, Take Rate, Subsidy Share.
- Contribution Margin Proxy (commission minus subsidy/refund/dispute/chargeback loss proxy).
- Risk-Adjusted GMV (expected loss adjusted).
- Refund/Dispute/Chargeback/Cancellation/On-time rates.

## Feature Layer (Core Tables)
- `order_profitability_features`
- `seller_monthly_quality`
- `buyer_behavior_risk`
- `category_risk_summary`
- `seller_risk_base`

No-leakage logic is enforced for historical rates and risk features.

## Scoring Summary
All scores are 0-100 (Low/Moderate/High/Critical).
- `seller_quality_score`: refund/dispute/chargeback + operational reliability.
- `order_risk_score`: payment signal/method + channel/category + prior buyer/seller risk.
- `fraud_exposure_score`: dispute/chargeback concentration + risky order share.
- `margin_fragility_score`: negative margin share + subsidy dependence + leakage exposure.
- `governance_priority_score`: blended seller quality, fraud exposure, margin fragility, concentration.

Scores include a main driver and recommended action for operational routing.

## Scenarios
Deterministic what-if scenarios (not forecasts):
- baseline
- seller quality improvement
- subsidy tightening
- fraud control improvement
- downside risk deterioration

## Validation (Summary)
Formal checks before conclusions:
- reconciliation and coherence (orders/refunds/disputes/payments)
- schema contract validation
- metric governance guardrails
- scenario arithmetic consistency
- narrative overclaiming scan

Artifacts are generated during pipeline execution and kept out of GitHub for cleanliness.
