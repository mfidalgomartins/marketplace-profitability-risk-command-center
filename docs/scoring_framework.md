# Scoring Framework: Marketplace Risk & Governance Operating Model

## Scope
This scoring layer produces interpretable, operationally actionable 0-100 scores for seller governance and order risk routing.

All scores use a consistent direction:
- higher score = higher risk/exposure/priority
- lower score = healthier performance

Tier scale (applied consistently):
- `Low`: 0-29.99
- `Moderate`: 30-54.99
- `High`: 55-74.99
- `Critical`: 75-100

## 1) `seller_quality_score`
Purpose: detect seller behavior and service quality risk.

### Logic
Weighted risk composite of:
- refund incidence
- dispute incidence
- chargeback incidence
- cancellation incidence
- delay incidence
- on-time failure
- weak repeat-buyer retention (penalty)

### Weights
- refund risk: 22%
- dispute risk: 20%
- chargeback risk: 16%
- cancellation risk: 10%
- delay risk: 12%
- on-time risk: 12%
- repeat-buyer risk: 8%

### Rationale
Refund/dispute/chargeback are direct trust and cost signals. Operational reliability (delay/on-time/cancel) is next most important. Repeat-buyer weakness is a smaller but meaningful quality indicator.

## 2) `order_risk_score`
Purpose: order-level fraud and dispute risk routing.

### Logic (no leakage)
Uses order-time and prior-history signals only:
- payment risk signal
- payment method risk
- channel risk
- category risk
- buyer prior bad-event rates (chronologically shifted)
- seller prior bad-event rates (chronologically shifted)
- order-value percentile

### Weights
- payment signal: 25%
- payment method: 14%
- channel risk: 12%
- category risk: 12%
- buyer history: 17%
- seller history: 15%
- order value: 5%

### Rationale
Payment and behavior context carry strongest predictive value in marketplace fraud/dispute settings. Value-size contributes but is not dominant.

## 3) `fraud_exposure_score`
Purpose: seller-level fraud/dispute exposure concentration.

### Logic
Weighted risk composite of:
- dispute rate
- chargeback rate
- high-risk order share
- critical payment-signal share
- suspicious cluster share (social commerce + digital/electronics + risky methods)

### Weights
- dispute risk: 30%
- chargeback risk: 30%
- high-risk order share: 20%
- critical payment share: 10%
- suspicious cluster share: 10%

### Rationale
Disputes and chargebacks represent direct realized/near-realized fraud pressure; supporting pattern features improve operational targeting.

## 4) `margin_fragility_score`
Purpose: quantify economic instability behind seller growth.

### Logic
Weighted risk composite of:
- negative margin order share
- subsidy dependency
- refund value leakage
- dispute value leakage
- commission compression

### Weights
- negative margin share: 30%
- subsidy dependency: 25%
- refund value risk: 20%
- dispute value risk: 15%
- commission compression: 10%

### Rationale
Persistent negative-margin behavior and subsidy dependence are first-order fragility drivers. Refund/dispute value leakage is the second-order erosion mechanism.

## 5) `governance_priority_score`
Purpose: unified intervention priority queue for leadership and risk operations.

### Logic
Weighted combination of:
- seller quality risk
- fraud exposure risk
- margin fragility risk
- concentration risk (GMV/order rank percentiles)

### Weights
- seller quality: 27%
- fraud exposure: 29%
- margin fragility: 24%
- concentration risk: 20%

### Rationale
The priority model balances direct risk (fraud), operating quality, and economic fragility, then raises priority for concentrated sellers with higher enterprise impact.

## Main risk driver and action policy
For each score, the system records:
- `main_risk_driver`: highest weighted component contribution
- `recommended_action`: tier + driver mapping to operational actions

Action vocabulary includes:
- monitor only
- seller coaching required
- tighten promo eligibility
- audit seller operations
- review fraud controls
- reduce subsidy exposure
- hold payouts
- investigate dispute cluster
- improve fulfillment SLA enforcement
- escalate for manual review

## Sensitivity discussion
Sensitivity scenarios are saved in `scoring_sensitivity_summary.csv`:
- baseline
- fraud-heavy weighting
- margin-heavy weighting
- quality-heavy weighting

Interpretation guidance:
- high top-50 overlap vs baseline means robust prioritization
- low overlap indicates ranking sensitivity and need for governance review

## Trade-offs and limitations
- Weighted scoring is transparent and controllable, but less adaptive than a fully trained model.
- Threshold-based normalization may need calibration when marketplace mix changes.
- Seller and order risk distributions depend on synthetic data regime.
- A single main driver can hide second-order risks; analysts should also inspect component breakdowns.
- Recommended actions are policy defaults; final decisions require risk operations judgment.

## Execution Layer
Scoring outputs are operationalized through:
- `data/processed/governance_action_register.csv`

This table unifies seller and order priorities into one queue with owner teams, SLA days, and exposure fields for execution governance.
