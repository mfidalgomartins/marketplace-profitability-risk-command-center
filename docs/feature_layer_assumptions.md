# Feature Layer Assumptions, Caveats, and Usage Notes

## Why each analytical table exists

1. `order_profitability_features`
- Converts raw order economics into a risk-adjusted order lens.
- Supports contribution analysis, margin leakage diagnostics, and profitability segmentation.

2. `seller_monthly_quality`
- Provides a stable governance panel for seller performance by month.
- Enables ranking, tiering, and intervention decisions without black-box scoring.

3. `buyer_behavior_risk`
- Produces a leakage-safe snapshot of buyer behavioral risk using trailing windows only.
- Supports rule tuning, review routing, and customer risk stratification.

4. `category_risk_summary`
- Captures category-month differences in risk, subsidy dependence, and fragility.
- Supports merchandising, pricing, and promotion policy choices.

5. `seller_risk_base`
- Consolidates seller inputs into structured domains (quality/fraud/profitability/ops/concentration).
- Serves as the upstream base for formal governance prioritization and scorecards.

## No-leakage design choices

- Expected order risk losses are estimated from:
  - order-time attributes (`payment_risk_signal`, channel, category, promo flag)
  - trailing historical seller/buyer priors computed with strict chronological shift
- Buyer risk table uses only trailing-window behavior up to snapshot date.
- Seller risk base uses trailing-window metrics only for the current snapshot period.

## Engineered metric assumptions

- Smoothed frequency metrics use additive priors to reduce volatility for low-volume entities.
- Risk-severity assumptions:
  - expected refund loss severity: 85% of commission exposure
  - expected dispute loss severity: 70% of commission exposure
  - expected chargeback loss severity: 22% of order net value
- `profitability_flag` is a binary operational proxy, not a full accounting contribution margin.
- `realized_contribution_margin_proxy` uses realized leakage channels and is governance-aligned with scenario economics.
- `seller_quality_proxy` and `margin_fragility_index` are interpretable weighted composites and should be calibrated over time.
- Delay/on-time operational thresholds:
  - `delay_rate` uses delays of 3 or more days among delivery-eligible orders
  - `on_time_rate` treats delays of 1 day or less as on-time

## Caveats

- `payment_risk_signal` comes from synthetic generation and may be stronger than production calibration.
- Category assignment at order level uses primary item (highest gross line), which simplifies multi-category baskets.
- `seller_risk_base` JSON inputs are for portability/auditability; downstream scoring can normalize into wide columns.
- This layer is intended for decision support and model feature baselining, not statutory financial reporting.

## Traceability

- Every feature is computed directly from `data/raw/*.csv` in:
  - `src/features/build_analytical_feature_layer.py`
- Output tables are deterministic and reproducible with the same raw inputs.
