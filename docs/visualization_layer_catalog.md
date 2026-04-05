# Visualization Layer Catalog

## Scope
Executive visualization layer for Marketplace Profitability, Fraud & Seller Quality Command Center.

All chart files are generated to `outputs/charts/` by:
`src/visualization/build_marketplace_visualizations.py`

1. `01_gmv_vs_risk_adjusted_gmv_trend.png`
- Chart objective: show whether topline GMV trend holds after risk adjustment.
- Why this chart type: dual-line time series is best for comparing two trend trajectories over the same timeline.
- Business takeaway: a persistent GMV-to-risk-adjusted gap signals hidden quality and loss pressure behind topline growth.

2. `02_net_value_and_subsidy_share_trend.png`
- Chart objective: track net marketplace value alongside subsidy dependence.
- Why this chart type: bar + line combo supports simultaneous level (net value) and rate (subsidy share) monitoring.
- Business takeaway: net growth supported by elevated subsidy share indicates policy-dependent economics.

3. `03_refund_rate_by_category.png`
- Chart objective: identify where refund incidence is concentrated by product category.
- Why this chart type: sorted horizontal bar chart ranks categories clearly and supports quick prioritization.
- Business takeaway: categories with structurally higher refund rates should receive tighter quality and fulfillment controls.

4. `04_dispute_rate_by_seller_cohort.png`
- Chart objective: compare dispute incidence across seller volume cohorts.
- Why this chart type: cohort bar comparison makes differences in structural risk easy to read.
- Business takeaway: dispute pressure is not only a long-tail issue and may exist in high-volume cohorts with larger P&L impact.

5. `05_seller_quality_distribution.png`
- Chart objective: understand the distribution and tail-risk of seller quality scores.
- Why this chart type: histogram with density overlay reveals skewness, clustering, and high-risk tails.
- Business takeaway: a right-tail concentration indicates a manageable but material set of governance-priority sellers.

6. `06_margin_fragility_distribution.png`
- Chart objective: visualize how widespread margin fragility risk is across sellers.
- Why this chart type: distribution chart highlights systemic vs concentrated fragility.
- Business takeaway: critical tail share quantifies how much of the seller base likely requires margin-discipline interventions.

7. `07_top_sellers_by_governance_priority.png`
- Chart objective: rank the most urgent sellers for risk/governance action.
- Why this chart type: sorted horizontal bars are the clearest format for top-N operational queues.
- Business takeaway: leadership can immediately target the highest-impact seller list for intervention sequencing.

8. `08_refunds_vs_delays_relationship.png`
- Chart objective: test whether logistics delay is associated with higher refunds.
- Why this chart type: delay-day line profile shows monotonic or non-linear risk escalation.
- Business takeaway: delivery delays are a likely operational driver of economic leakage and customer dissatisfaction.

9. `09_disputes_vs_chargeback_risk_relationship.png`
- Chart objective: assess alignment between dispute and chargeback outcomes by payment risk signal.
- Why this chart type: bubble scatter captures joint-risk relationship while preserving order-volume context.
- Business takeaway: payment risk signals with elevated dispute and chargeback rates justify stricter controls and review.

10. `10_promo_dependency_by_category.png`
- Chart objective: show category-level dependence on promotional subsidy.
- Why this chart type: ranked bars quickly surface policy-sensitive categories.
- Business takeaway: high promo-dependency categories are vulnerable to margin deterioration under aggressive discounting.

11. `11_seller_concentration_chart.png`
- Chart objective: quantify seller concentration in GMV.
- Why this chart type: cumulative concentration curve (Pareto-style) is the standard view for portfolio concentration risk.
- Business takeaway: concentration increases enterprise risk from a small set of sellers and raises governance urgency.

12. `12_category_profitability_heatmap.png`
- Chart objective: monitor category-month margin quality patterns over time.
- Why this chart type: heatmap highlights multi-period hotspots and persistent weak zones compactly.
- Business takeaway: recurring low-profitability pockets indicate structural category issues, not one-off noise.

13. `13_buyer_risk_distribution.png`
- Chart objective: profile buyer behavioral risk segmentation.
- Why this chart type: tiered bar distribution clearly communicates population mix across risk bands.
- Business takeaway: critical-risk buyer share can guide fraud operations capacity planning and policy strictness.

14. `14_scenario_comparison_chart.png`
- Chart objective: compare strategy scenarios on growth-quality trade-offs and margin impact.
- Why this chart type: quadrant bubble view captures directional trade-offs plus economic magnitude in one frame.
- Business takeaway: interventions that modestly reduce GMV can still improve quality and economics meaningfully.

15. `15_seller_portfolio_matrix_volume_vs_quality.png`
- Chart objective: position sellers by commercial impact (volume) and quality risk.
- Why this chart type: portfolio matrix is ideal for governance segmentation and action playbooks.
- Business takeaway: high-volume, high-risk sellers should be escalated first due to outsized downside exposure.

16. `16_risk_leakage_waterfall.png`
- Chart objective: decompose how leakage components bridge commission revenue to contribution margin.
- Why this chart type: waterfall charts are the clearest way to explain additive erosion effects.
- Business takeaway: subsidy, refunds, disputes, and chargebacks can fully absorb commission economics if unmanaged.
