# Feature Dictionary: Marketplace Analytical Layer

## Table: `order_profitability_features`
Purpose: order-level unit economics with expected risk adjustments using only order-time fields plus trailing (prior) entity behavior.

- `order_id`: unique order key from `orders.order_id`.
- `order_date`: order timestamp from `orders.order_date`.
- `buyer_id`: buyer key from `orders.buyer_id`.
- `seller_id`: seller key from `order_items.seller_id` (fallback logistics seller).
- `category`: primary order category from highest-gross item (`order_items` + `products`).
- `gross_value`: order gross value from `orders.gross_order_value`.
- `net_value`: order net paid value from `orders.net_paid_amount`.
- `subsidy_amount`: platform promo subsidy from `orders.subsidy_amount`.
- `commission_fee`: summed item commission from `order_items.commission_fee`.
- `refund_amount`: realized refund amount from `refunds.refund_amount` aggregated by order.
- `dispute_amount`: realized dispute amount from `disputes.dispute_amount` aggregated by order.
- `chargeback_loss_proxy`: realized chargeback loss proxy from payment chargeback flag times net order value.
- `realized_contribution_margin_proxy`: `commission_fee - subsidy_amount - refund_amount - dispute_amount - chargeback_loss_proxy`.
- `estimated_margin_after_risk`: `order_margin_proxy - expected_refund_loss - expected_dispute_loss - expected_chargeback_loss`.
- `risk_adjusted_order_value`: `net_value - expected_total_risk_loss`.
- `profitability_flag`: `profitable` if `estimated_margin_after_risk > 0`, else `fragile`.

## Table: `seller_monthly_quality`
Purpose: seller-month quality and fragility monitor for governance and account management.

- `seller_id`: seller key.
- `month`: calendar month (`YYYY-MM`) from `order_date`.
- `orders`: order count.
- `GMV`: summed `gross_value`.
- `net_value`: summed `net_value`.
- `avg_margin_proxy`: mean order margin proxy (`order_items.margin_proxy` summed at order).
- `refund_rate`: share of orders with refund > 0.
- `dispute_rate`: share of orders with dispute > 0.
- `chargeback_rate`: share of orders with `payments.chargeback_flag=1`.
- `cancellation_rate`: share of orders with `logistics_events.cancellation_flag=1`.
- `delay_rate`: delayed deliveries / delivery-eligible orders.
- `on_time_rate`: on-time deliveries / delivery-eligible orders.
- `promo_dependency_rate`: `sum(subsidy_amount) / sum(GMV)`.
- `repeat_buyer_rate`: share of orders from buyers with prior order history with the same seller.
- `seller_quality_proxy`: weighted 0-100 quality proxy.
- `fragility_flag`: `fragile` vs `stable` threshold rule.

## Table: `buyer_behavior_risk`
Purpose: leakage-safe buyer snapshot for risk routing based on trailing behavior only.

- `buyer_id`: buyer key.
- `trailing_order_count`: trailing-window order count.
- `refund_frequency`: smoothed refund frequency.
- `dispute_frequency`: smoothed dispute frequency.
- `chargeback_frequency`: smoothed chargeback frequency.
- `average_order_value`: trailing average order gross value.
- `promo_usage_rate`: share of trailing orders with promo usage.
- `abnormal_behavior_flags`: interpretable rule flags (pipe-separated).
- `order_risk_proxy`: 0-100 risk score from weighted frequencies.

## Table: `category_risk_summary`
Purpose: category-month risk and margin-fragility diagnostics for pricing, promo, and risk policy.

- `month`: calendar month (`YYYY-MM`).
- `category`: primary order category.
- `GMV`: summed `gross_value`.
- `net_value`: summed `net_value`.
- `refund_rate`: order-level refund incidence by category-month.
- `dispute_rate`: order-level dispute incidence by category-month.
- `subsidy_rate`: `sum(subsidy_amount) / sum(GMV)`.
- `margin_fragility_index`: 0-100 weighted index using refund/dispute/chargeback/subsidy/negative-margin signals.

## Table: `seller_risk_base`
Purpose: current-period seller profile for scoring and intervention prioritization.

- `seller_id`: seller key.
- `current_period`: snapshot period (`YYYY-MM`) using latest available order month.
- `quality_inputs`: JSON payload of quality-related inputs.
- `fraud_inputs`: JSON payload of fraud-related inputs.
- `profitability_inputs`: JSON payload of profitability-related inputs.
- `operational_inputs`: JSON payload of logistics/ops inputs.
- `concentration_inputs`: JSON payload of concentration/dependency inputs.
