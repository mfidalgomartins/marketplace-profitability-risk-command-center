# Data Dictionary

## Scope
This dictionary covers all primary raw and processed datasets used by the Marketplace Profitability, Fraud & Seller Quality Command Center.

## Entity Model and Join Paths
Primary join spine:
- `orders.order_id` <- `order_items.order_id`, `payments.order_id`, `refunds.order_id`, `disputes.order_id`, `logistics_events.order_id`
- `orders.buyer_id` -> `buyers.buyer_id`
- `order_items.product_id` -> `products.product_id`
- `order_items.seller_id` -> `sellers.seller_id`
- `products.seller_id` -> `sellers.seller_id`

Processed joins:
- order-grain tables join on `order_id`
- seller-grain tables join on `seller_id`
- category-month tables join on (`month`, `category`)

---

## Raw Tables

## `buyers.csv`
- Grain: one row per buyer
- Primary key: `buyer_id`
- Main joins: `orders.buyer_id`
- Key columns: `signup_date`, `region`, `acquisition_channel`, `customer_type`, `loyalty_tier`
- Major metrics enabled: buyer count, acquisition mix, regional mix

## `sellers.csv`
- Grain: one row per seller
- Primary key: `seller_id`
- Main joins: `order_items.seller_id`, `products.seller_id`, `logistics_events.seller_id`
- Key columns: `onboarding_date`, `seller_region`, `seller_type`, `category_focus`, `seller_tier`, `commission_plan`, `fulfillment_model`
- Major metrics enabled: seller mix, cohort quality and concentration analysis

## `products.csv`
- Grain: one row per product
- Primary key: `product_id`
- Main joins: `order_items.product_id`
- Key columns: `seller_id`, `category`, `subcategory`, `list_price`, `estimated_cost`, `shipping_cost_proxy`
- Major metrics enabled: category economics and cost proxies

## `orders.csv`
- Grain: one row per order
- Primary key: `order_id`
- Main joins: order-wide spine table
- Key columns: `buyer_id`, `order_date`, `payment_method`, `order_channel`, `promo_code_used`, `gross_order_value`, `subsidy_amount`, `net_paid_amount`, `order_status`
- Major metrics enabled: GMV, net value, subsidy share, channel/payment mix

## `order_items.csv`
- Grain: one row per order item
- Primary key: `order_item_id`
- Main joins: `orders`, `products`, `sellers`
- Key columns: `order_id`, `product_id`, `seller_id`, `quantity`, `sale_price`, `gross_item_value`, `net_item_value`, `discount_amount`, `commission_fee`, `estimated_cost`, `margin_proxy`
- Major metrics enabled: item-level reconciliation, commission and margin diagnostics

## `payments.csv`
- Grain: one row per order payment record
- Primary key: `payment_id`
- Main joins: `orders.order_id`
- Key columns: `payment_status`, `payment_attempts`, `chargeback_flag`, `payment_risk_signal`
- Major metrics enabled: chargeback rate, payment risk segmentation

## `refunds.csv`
- Grain: one row per refund event
- Primary key: `refund_id`
- Main joins: `orders.order_id`
- Key columns: `refund_date`, `refund_reason`, `refund_amount`, `full_refund_flag`
- Major metrics enabled: refund incidence/value and reason diagnostics

## `disputes.csv`
- Grain: one row per dispute event
- Primary key: `dispute_id`
- Main joins: `orders.order_id`
- Key columns: `dispute_date`, `dispute_reason`, `dispute_status`, `dispute_amount`
- Major metrics enabled: dispute incidence/value and status diagnostics

## `logistics_events.csv`
- Grain: one row per order logistics lifecycle
- Primary key: `event_id`
- Main joins: `orders.order_id`, `sellers.seller_id`
- Key columns: `shipped_date`, `delivered_date`, `promised_delivery_date`, `delay_days`, `cancellation_flag`
- Major metrics enabled: delay rate, cancellation rate, on-time performance

---

## Processed Tables

## `order_profitability_features.csv`
- Grain: one row per order
- Primary key: `order_id`
- Main joins: `order_risk_scores.order_id`, `orders.order_id`
- Key columns: `gross_value`, `net_value`, `subsidy_amount`, `commission_fee`, `refund_amount`, `dispute_amount`, `chargeback_loss_proxy`, `realized_contribution_margin_proxy`, `estimated_margin_after_risk`, `risk_adjusted_order_value`, `profitability_flag`
- Major metrics: GMV, net value, risk-adjusted value, margin proxy, leakage components

## `seller_monthly_quality.csv`
- Grain: one row per seller per month
- Primary key candidate: (`seller_id`, `month`)
- Main joins: seller scoring base by `seller_id`
- Key columns: `orders`, `GMV`, `net_value`, `avg_margin_proxy`, `refund_rate`, `dispute_rate`, `chargeback_rate`, `cancellation_rate`, `delay_rate`, `on_time_rate`, `promo_dependency_rate`, `repeat_buyer_rate`, `seller_quality_proxy`, `fragility_flag`
- Major metrics: seller SLA quality trends and fragility flags

## `buyer_behavior_risk.csv`
- Grain: one row per buyer snapshot
- Primary key: `buyer_id`
- Main joins: `orders.buyer_id`
- Key columns: `trailing_order_count`, `refund_frequency`, `dispute_frequency`, `chargeback_frequency`, `average_order_value`, `promo_usage_rate`, `abnormal_behavior_flags`, `order_risk_proxy`
- Major metrics: buyer-side abnormal risk monitoring

## `category_risk_summary.csv`
- Grain: one row per category per month
- Primary key candidate: (`month`, `category`)
- Main joins: category trend panels
- Key columns: `GMV`, `net_value`, `refund_rate`, `dispute_rate`, `subsidy_rate`, `margin_fragility_index`
- Major metrics: category fragility and leakage intensity

## `seller_risk_base.csv`
- Grain: one row per seller snapshot period
- Primary key candidate: (`seller_id`, `current_period`)
- Main joins: scoring layer by `seller_id`
- Key columns: `quality_inputs`, `fraud_inputs`, `profitability_inputs`, `operational_inputs`, `concentration_inputs`
- Major metrics: serialized risk inputs for score reproducibility

## `order_risk_scores.csv`
- Grain: one row per order
- Primary key: `order_id`
- Main joins: `order_profitability_features.order_id`
- Key columns: `order_risk_score`, `order_risk_tier`, `order_risk_main_driver`, `recommended_action`
- Major metrics: order-level risk routing and intervention signals

## `seller_quality_scores.csv`
- Grain: one row per seller
- Primary key: `seller_id`
- Main joins: seller scorecard
- Key columns: `seller_quality_score`, `seller_quality_tier`, `main_risk_driver`, `recommended_action`
- Major metrics: seller defect/operations governance scoring

## `fraud_exposure_scores.csv`
- Grain: one row per seller
- Primary key: `seller_id`
- Main joins: seller scorecard
- Key columns: `fraud_exposure_score`, `fraud_exposure_tier`, `main_risk_driver`, `recommended_action`
- Major metrics: seller-level fraud pressure ranking

## `margin_fragility_scores.csv`
- Grain: one row per seller
- Primary key: `seller_id`
- Main joins: seller scorecard
- Key columns: `margin_fragility_score`, `margin_fragility_tier`, `main_risk_driver`, `recommended_action`
- Major metrics: economic fragility and subsidy dependency risk

## `governance_priority_scores.csv`
- Grain: one row per seller
- Primary key: `seller_id`
- Main joins: seller scorecard
- Key columns: `governance_priority_score`, `governance_priority_tier`, `main_risk_driver`, `recommended_action`
- Major metrics: unified intervention queue

## `seller_scorecard.csv`
- Grain: one row per seller
- Primary key: `seller_id`
- Main joins: dashboard seller panels
- Key columns: governance + quality + fraud + fragility scores/tiers, `orders`, `gmv`, `net_value`
- Major metrics: consolidated seller governance lens

## `top_high_priority_sellers.csv`
- Grain: one row per prioritized seller subset
- Primary key: `seller_id` (subset)
- Main joins: operational action queue
- Key columns: governance score, quality score, fraud score, margin fragility, volume
- Major metrics: tactical governance execution list

## `top_high_risk_orders.csv`
- Grain: one row per prioritized order subset
- Primary key: `order_id` (subset)
- Main joins: manual review workflows
- Key columns: `order_risk_score`, `order_risk_tier`, main driver, action
- Major metrics: manual-review queue

## `scoring_sensitivity_summary.csv`
- Grain: one row per sensitivity scenario
- Primary key: `scenario`
- Main joins: scoring governance review
- Key columns: `avg_score`, `median_score`, `top50_overlap_vs_baseline`, `top50_overlap_rate`
- Major metrics: ranking robustness diagnostics

## `governance_action_register.csv`
- Grain: one row per actionable entity (`seller` or `order`)
- Primary key candidate: (`entity_type`, `entity_id`)
- Main joins: `seller_scorecard.seller_id` and `order_risk_scores.order_id`
- Key columns: `priority_score`, `risk_tier`, `main_risk_driver`, `recommended_action`, `owner_team`, `sla_days`, `estimated_leakage_proxy`, `estimated_margin_proxy`, `status`
- Major metrics: execution queue quality, action ownership, SLA-based intervention prioritization

## `scenario_assumptions.csv`
- Grain: one row per scenario
- Primary key: `scenario`
- Main joins: scenario outputs
- Key columns: factor multipliers and assumption narrative
- Major metrics: scenario parameter transparency

## `scenario_results_summary.csv`
- Grain: one row per scenario
- Primary key: `scenario`
- Main joins: scenario center visuals
- Key columns: GMV/net/risk-adjusted value, contribution margin proxy, leakage components, trade-off labels, decision score
- Major metrics: strategy comparison economics

## `scenario_component_bridge.csv`
- Grain: one row per scenario
- Primary key: `scenario`
- Main joins: scenario bridge analysis
- Key columns: commission, subsidy, refunds, disputes, chargeback, total leakage, CM change
- Major metrics: component-level scenario decomposition

## `scenario_top_risk_exposure.csv`
- Grain: one row per model run
- Primary key: run-level singleton
- Main joins: scenario caveat interpretation
- Key columns: `top_risk_net_share`, `top_risk_leak_rate`, bad-actor shares/count
- Major metrics: concentration of downside exposure

## `scenario_decision_matrix.csv`
- Grain: one row per scenario
- Primary key: `scenario`
- Main joins: executive decision recommendations
- Key columns: `decision_priority_score`, GMV delta, quality delta, CM delta, leakage avoided, `recommended_decision`
- Major metrics: intervention prioritization

---

## Major Metric Families by Table
- Economics: `orders`, `order_items`, `order_profitability_features`, `scenario_results_summary`
- Risk/Fraud: `payments`, `refunds`, `disputes`, `order_risk_scores`, `fraud_exposure_scores`
- Seller Governance: `seller_monthly_quality`, `seller_quality_scores`, `governance_priority_scores`, `seller_scorecard`
- Operations/CX: `logistics_events`, `seller_monthly_quality`
- Strategic Planning: scenario tables and validation reports
