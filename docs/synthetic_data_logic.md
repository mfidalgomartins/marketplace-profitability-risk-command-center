# Synthetic Data Design: Business Logic and Embedded Risk Patterns

## Purpose
This synthetic dataset is designed to emulate an internal marketplace risk-and-profitability environment where headline growth can hide margin erosion and trust deterioration.

## Simulation logic

### 1. Marketplace shape and concentration
- Seller demand allocation uses a heavy-tailed distribution so volume is concentrated among a small set of sellers.
- Top sellers receive differentiated commission plans and often operate with thinner margins, creating realistic scale-vs-profitability trade-offs.

### 2. Seller heterogeneity
- Sellers are generated with latent quality and risk factors that affect cancellations, delays, refund propensity, dispute rates, and payment exposure.
- A small set of sellers is forced into a high-volume + weak-quality regime to create realistic executive escalation cases.

### 3. Buyer heterogeneity
- Buyers belong to latent behavior segments: `repeat_good`, `standard`, `price_hunter`, `suspicious`, and `repeat_bad`.
- Segments drive order frequency, payment-risk characteristics, refund behavior, and dispute behavior.

### 4. Category economics and promotion behavior
- Categories carry different base price bands, promo sensitivity, cost structures, and fraud risk.
- Promo-heavy categories (for example grocery and fashion) show stronger subsidy usage and lower margin durability.

### 5. Growth and seasonality
- Monthly demand weights apply mild growth across 24 months with expected seasonal peaks (Q4) and softer January levels.

### 6. Payment and fraud pathways
- Payment risk is a function of buyer segment, seller risk, category risk, region, channel, method, and selected suspicious combinations.
- Chargebacks are linked to disputes, especially unauthorized and not-received patterns.

### 7. Logistics to CX/risk linkage
- Delays and cancellations depend on seller quality, fulfillment model, region mismatch, and seasonal stress.
- Refund and dispute probabilities increase with logistics problems, creating causal pathways for later diagnostics.

## Embedded patterns expected to be detected

### A. Concentration effects
- Top 10 sellers contribute a large GMV share (seed 42 snapshot: ~16.8%).

### B. High-volume value destruction
- A subset of high-GMV sellers has weak quality and poor economics.
- Seed 42 snapshot: multiple high-volume sellers have negative margin proxy and elevated refund/dispute rates.

### C. Promo-sensitive category differences
- Grocery/fashion/beauty have materially higher promo usage than low-promo categories.

### D. Suspicious cluster behavior
- Social-commerce + electronics/digital goods + risky payment mix exhibits elevated chargeback rates relative to marketplace baseline.

### E. Region differences
- Refund/dispute rates vary by region due to region-specific risk and operational frictions.

### F. Logistics-driven leakage
- Orders with larger delays exhibit significantly higher refund/dispute incidence than low-delay orders.

### G. Minority risky buyers
- A small minority of buyers display sustained high refund/dispute intensity (repeat-bad behavior), while another segment remains repeat-good.

## Intentional growth vs quality trade-offs
- Growth can rise while risk-adjusted value degrades via subsidy-heavy expansion and low-margin high-volume sellers.
- Aggressive promotion lifts conversion and GMV but increases subsidy load and downstream leakage.
- Fast growth in risk-prone channels may improve topline while elevating disputes and chargebacks.
- Seller concentration improves scale efficiency but raises dependency and governance risk when top sellers underperform on quality.
