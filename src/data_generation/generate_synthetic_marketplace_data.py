from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd


CATEGORY_CONFIG: Dict[str, Dict[str, object]] = {
    "Electronics": {
        "subcategories": ["Phones", "Computers", "Audio", "Accessories"],
        "base_price": 240.0,
        "price_sigma": 0.42,
        "promo_sensitivity": 0.28,
        "refund_base": 0.085,
        "fraud_risk": 0.13,
        "shipping_base": 7.5,
        "cost_ratio": 0.72,
    },
    "Fashion": {
        "subcategories": ["Women", "Men", "Shoes", "Accessories"],
        "base_price": 58.0,
        "price_sigma": 0.38,
        "promo_sensitivity": 0.41,
        "refund_base": 0.11,
        "fraud_risk": 0.06,
        "shipping_base": 4.2,
        "cost_ratio": 0.46,
    },
    "Home": {
        "subcategories": ["Furniture", "Kitchen", "Decor", "Storage"],
        "base_price": 96.0,
        "price_sigma": 0.36,
        "promo_sensitivity": 0.33,
        "refund_base": 0.072,
        "fraud_risk": 0.045,
        "shipping_base": 8.8,
        "cost_ratio": 0.58,
    },
    "Beauty": {
        "subcategories": ["Skincare", "Makeup", "Hair", "Wellness"],
        "base_price": 34.0,
        "price_sigma": 0.33,
        "promo_sensitivity": 0.36,
        "refund_base": 0.067,
        "fraud_risk": 0.05,
        "shipping_base": 3.1,
        "cost_ratio": 0.49,
    },
    "Sports": {
        "subcategories": ["Fitness", "Outdoor", "Cycling", "Team Sports"],
        "base_price": 76.0,
        "price_sigma": 0.34,
        "promo_sensitivity": 0.26,
        "refund_base": 0.056,
        "fraud_risk": 0.045,
        "shipping_base": 6.2,
        "cost_ratio": 0.57,
    },
    "Toys": {
        "subcategories": ["Educational", "Puzzles", "Action Figures", "STEM"],
        "base_price": 42.0,
        "price_sigma": 0.36,
        "promo_sensitivity": 0.31,
        "refund_base": 0.061,
        "fraud_risk": 0.04,
        "shipping_base": 4.1,
        "cost_ratio": 0.53,
    },
    "Grocery": {
        "subcategories": ["Pantry", "Snacks", "Beverages", "Household"],
        "base_price": 22.0,
        "price_sigma": 0.29,
        "promo_sensitivity": 0.47,
        "refund_base": 0.032,
        "fraud_risk": 0.028,
        "shipping_base": 2.7,
        "cost_ratio": 0.68,
    },
    "Digital Goods": {
        "subcategories": ["Software", "Gaming", "Subscriptions", "Courses"],
        "base_price": 64.0,
        "price_sigma": 0.46,
        "promo_sensitivity": 0.19,
        "refund_base": 0.048,
        "fraud_risk": 0.18,
        "shipping_base": 0.8,
        "cost_ratio": 0.38,
    },
}

PROMO_CODES = ["WELCOME10", "FLASH15", "APP20", "SAVE8", "FREESHIP", "SPRING12"]

REGIONS = ["Northeast", "South", "Midwest", "West", "Central"]


@dataclass(frozen=True)
class GenerationConfig:
    seed: int = 42
    n_buyers: int = 9000
    n_sellers: int = 1200
    start_date: str = "2024-03-01"
    end_date: str = "2026-02-28"


def _clip(v: float, low: float, high: float) -> float:
    return float(min(max(v, low), high))


def _month_starts(start_date: pd.Timestamp, end_date: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(start=start_date, end=end_date, freq="MS")


def _month_weights(month_starts: pd.DatetimeIndex) -> np.ndarray:
    n = len(month_starts)
    growth = np.linspace(0.82, 1.32, n)
    seasonal = np.ones(n)
    for i, d in enumerate(month_starts):
        if d.month in (11, 12):
            seasonal[i] *= 1.22
        elif d.month == 1:
            seasonal[i] *= 0.93
        elif d.month in (6, 7):
            seasonal[i] *= 1.06
    w = growth * seasonal
    return w / w.sum()


def generate_buyers(cfg: GenerationConfig, rng: np.random.Generator) -> Tuple[pd.DataFrame, pd.DataFrame]:
    buyer_ids = [f"B{idx:06d}" for idx in range(1, cfg.n_buyers + 1)]
    signup_dates = pd.to_datetime(
        rng.integers(
            pd.Timestamp(cfg.start_date).value // 10**9 - 180 * 24 * 3600,
            pd.Timestamp(cfg.end_date).value // 10**9,
            size=cfg.n_buyers,
        ),
        unit="s",
    ).normalize()

    region = rng.choice(REGIONS, size=cfg.n_buyers, p=[0.21, 0.28, 0.19, 0.2, 0.12])
    acquisition_channel = rng.choice(
        ["organic", "paid_search", "social", "affiliate", "referral", "direct", "email"],
        size=cfg.n_buyers,
        p=[0.25, 0.2, 0.16, 0.08, 0.12, 0.13, 0.06],
    )
    customer_type = rng.choice(
        ["consumer", "small_business", "enthusiast"],
        size=cfg.n_buyers,
        p=[0.76, 0.11, 0.13],
    )

    loyalty_base = rng.choice(["Bronze", "Silver", "Gold", "Platinum"], size=cfg.n_buyers, p=[0.46, 0.3, 0.18, 0.06])
    recent_signup = signup_dates > (pd.Timestamp(cfg.end_date) - pd.Timedelta(days=210))
    loyalty_tier = np.where(recent_signup & (loyalty_base == "Platinum"), "Gold", loyalty_base)

    segment = rng.choice(
        ["repeat_good", "standard", "price_hunter", "suspicious", "repeat_bad"],
        size=cfg.n_buyers,
        p=[0.39, 0.34, 0.16, 0.08, 0.03],
    )

    propensity = rng.lognormal(mean=-0.03, sigma=0.52, size=cfg.n_buyers)
    propensity *= np.select(
        [segment == "repeat_good", segment == "standard", segment == "price_hunter", segment == "suspicious", segment == "repeat_bad"],
        [1.27, 0.95, 1.02, 1.35, 1.62],
    )

    buyers = pd.DataFrame(
        {
            "buyer_id": buyer_ids,
            "signup_date": signup_dates,
            "region": region,
            "acquisition_channel": acquisition_channel,
            "customer_type": customer_type,
            "loyalty_tier": loyalty_tier,
        }
    )

    buyer_latent = pd.DataFrame(
        {
            "buyer_id": buyer_ids,
            "segment": segment,
            "propensity": propensity,
            "segment_risk": np.select(
                [segment == "repeat_good", segment == "standard", segment == "price_hunter", segment == "suspicious", segment == "repeat_bad"],
                [0.015, 0.03, 0.045, 0.13, 0.22],
            ),
            "refund_bias": np.select(
                [segment == "repeat_good", segment == "standard", segment == "price_hunter", segment == "suspicious", segment == "repeat_bad"],
                [0.015, 0.03, 0.05, 0.08, 0.13],
            ),
            "dispute_bias": np.select(
                [segment == "repeat_good", segment == "standard", segment == "price_hunter", segment == "suspicious", segment == "repeat_bad"],
                [0.006, 0.012, 0.022, 0.08, 0.14],
            ),
        }
    )

    return buyers, buyer_latent


def generate_sellers(cfg: GenerationConfig, rng: np.random.Generator) -> Tuple[pd.DataFrame, pd.DataFrame]:
    seller_ids = [f"S{idx:05d}" for idx in range(1, cfg.n_sellers + 1)]
    onboarding_dates = pd.to_datetime(
        rng.integers(
            (pd.Timestamp(cfg.start_date) - pd.Timedelta(days=560)).value // 10**9,
            pd.Timestamp(cfg.end_date).value // 10**9,
            size=cfg.n_sellers,
        ),
        unit="s",
    ).normalize()

    seller_region = rng.choice(REGIONS, size=cfg.n_sellers, p=[0.18, 0.3, 0.2, 0.19, 0.13])
    seller_type = rng.choice(["individual", "smb", "brand", "enterprise"], size=cfg.n_sellers, p=[0.34, 0.42, 0.16, 0.08])

    categories = list(CATEGORY_CONFIG.keys())
    category_focus = rng.choice(categories, size=cfg.n_sellers, p=[0.16, 0.18, 0.14, 0.11, 0.1, 0.08, 0.13, 0.1])

    quality_score = rng.beta(3.8, 2.2, size=cfg.n_sellers)
    volume_weight = rng.pareto(2.1, size=cfg.n_sellers) + 1.0
    volume_weight *= rng.lognormal(mean=0.0, sigma=0.7, size=cfg.n_sellers)

    top_cut = np.quantile(volume_weight, 0.87)
    bottom_cut = np.quantile(volume_weight, 0.2)
    seller_tier = np.where(
        volume_weight >= np.quantile(volume_weight, 0.97),
        "Platinum",
        np.where(
            volume_weight >= top_cut,
            "Gold",
            np.where(volume_weight <= bottom_cut, "Bronze", "Silver"),
        ),
    )

    low_margin_flag = rng.random(cfg.n_sellers) < np.select(
        [seller_tier == "Platinum", seller_tier == "Gold", seller_tier == "Silver", seller_tier == "Bronze"],
        [0.45, 0.35, 0.2, 0.12],
    )

    very_high_risk_flag = rng.random(cfg.n_sellers) < 0.025
    weak_quality_flag = quality_score < np.quantile(quality_score, 0.24)

    # Force a subset of high-volume weak-quality sellers to create realistic leadership risk cases.
    high_volume_idx = np.where(volume_weight >= np.quantile(volume_weight, 0.95))[0]
    weak_high_volume = high_volume_idx[rng.random(len(high_volume_idx)) < 0.36]
    if weak_high_volume.size > 0:
        weak_quality_flag[weak_high_volume] = True
        quality_score[weak_high_volume] *= 0.74
        very_high_risk_flag[weak_high_volume[: max(1, len(weak_high_volume) // 4)]] = True

    commission_plan = np.where(
        seller_tier == "Platinum",
        "negotiated_8_10",
        np.where(seller_tier == "Gold", "preferred_10_12", "standard_12_15"),
    )

    fulfillment_model = np.where(
        (seller_type == "enterprise") | (seller_tier == "Platinum"),
        rng.choice(["platform_fulfilled", "seller_fulfilled"], size=cfg.n_sellers, p=[0.7, 0.3]),
        rng.choice(["platform_fulfilled", "seller_fulfilled"], size=cfg.n_sellers, p=[0.28, 0.72]),
    )

    commission_rate = np.where(
        commission_plan == "negotiated_8_10",
        rng.uniform(0.08, 0.105, size=cfg.n_sellers),
        np.where(
            commission_plan == "preferred_10_12",
            rng.uniform(0.1, 0.125, size=cfg.n_sellers),
            rng.uniform(0.12, 0.155, size=cfg.n_sellers),
        ),
    )

    base_risk = rng.beta(1.7, 6.4, size=cfg.n_sellers)
    seller_risk = base_risk + very_high_risk_flag.astype(float) * rng.uniform(0.11, 0.2, size=cfg.n_sellers)
    seller_risk += weak_quality_flag.astype(float) * rng.uniform(0.03, 0.08, size=cfg.n_sellers)
    seller_risk = np.clip(seller_risk, 0.01, 0.95)

    defect_risk = np.clip(0.012 + (1.0 - quality_score) * 0.09 + weak_quality_flag.astype(float) * 0.022, 0.008, 0.28)
    delay_risk = np.clip(0.45 + (1.0 - quality_score) * 2.6 + weak_quality_flag.astype(float) * 0.9, 0.2, 6.8)

    sellers = pd.DataFrame(
        {
            "seller_id": seller_ids,
            "onboarding_date": onboarding_dates,
            "seller_region": seller_region,
            "seller_type": seller_type,
            "category_focus": category_focus,
            "seller_tier": seller_tier,
            "commission_plan": commission_plan,
            "fulfillment_model": fulfillment_model,
        }
    )

    seller_latent = pd.DataFrame(
        {
            "seller_id": seller_ids,
            "quality_score": quality_score,
            "volume_weight": volume_weight,
            "commission_rate": commission_rate,
            "seller_risk": seller_risk,
            "defect_risk": defect_risk,
            "delay_risk": delay_risk,
            "low_margin_flag": low_margin_flag,
            "very_high_risk_flag": very_high_risk_flag,
            "weak_quality_flag": weak_quality_flag,
        }
    )

    return sellers, seller_latent


def generate_products(
    sellers: pd.DataFrame,
    seller_latent: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    product_rows: List[Dict[str, object]] = []
    product_counter = 1
    category_names = list(CATEGORY_CONFIG.keys())

    latent_map = seller_latent.set_index("seller_id")

    for row in sellers.itertuples(index=False):
        seller_id = row.seller_id
        focus = row.category_focus
        seller_type = row.seller_type

        if seller_type == "individual":
            n_products = int(rng.integers(4, 13))
        elif seller_type == "smb":
            n_products = int(rng.integers(9, 24))
        elif seller_type == "brand":
            n_products = int(rng.integers(14, 36))
        else:
            n_products = int(rng.integers(20, 58))

        if row.seller_tier in ("Gold", "Platinum"):
            n_products = int(n_products * rng.uniform(1.15, 1.45))

        seller_r = latent_map.loc[seller_id]

        for _ in range(n_products):
            category = focus if rng.random() < 0.78 else rng.choice(category_names)
            cat_cfg = CATEGORY_CONFIG[category]
            subcategory = rng.choice(cat_cfg["subcategories"])

            base_price = float(cat_cfg["base_price"])
            price = float(rng.lognormal(mean=np.log(base_price), sigma=float(cat_cfg["price_sigma"])))
            if row.seller_tier == "Platinum":
                price *= rng.uniform(1.05, 1.25)
            price = round(_clip(price, 3.5, 2400.0), 2)

            base_cost_ratio = float(cat_cfg["cost_ratio"])
            cost_ratio = base_cost_ratio + (0.11 if bool(seller_r.low_margin_flag) else 0.0)
            if row.commission_plan == "negotiated_8_10":
                cost_ratio += 0.04
            cost_ratio = _clip(rng.normal(cost_ratio, 0.045), 0.37, 0.95)

            estimated_cost = round(price * cost_ratio, 2)
            shipping_cost = round(
                _clip(float(cat_cfg["shipping_base"]) * rng.uniform(0.82, 1.3), 0.5, 25.0),
                2,
            )

            product_rows.append(
                {
                    "product_id": f"P{product_counter:07d}",
                    "seller_id": seller_id,
                    "category": category,
                    "subcategory": subcategory,
                    "list_price": price,
                    "estimated_cost": estimated_cost,
                    "shipping_cost_proxy": shipping_cost,
                }
            )
            product_counter += 1

    return pd.DataFrame(product_rows)


def _compute_buyer_order_counts(
    buyers: pd.DataFrame,
    buyer_latent: pd.DataFrame,
    cfg: GenerationConfig,
    rng: np.random.Generator,
) -> pd.Series:
    start = pd.Timestamp(cfg.start_date)
    end = pd.Timestamp(cfg.end_date)

    segment_mult = {
        "repeat_good": 1.24,
        "standard": 0.96,
        "price_hunter": 1.03,
        "suspicious": 1.38,
        "repeat_bad": 1.64,
    }
    loyalty_mult = {"Bronze": 0.86, "Silver": 1.0, "Gold": 1.14, "Platinum": 1.28}

    merged = buyers[["buyer_id", "signup_date", "loyalty_tier"]].merge(
        buyer_latent[["buyer_id", "segment", "propensity"]], on="buyer_id", how="left"
    )

    active_start = merged["signup_date"].clip(lower=start)
    active_months = ((end.year - active_start.dt.year) * 12 + (end.month - active_start.dt.month) + 1).clip(lower=1)

    lam = (
        active_months
        * 0.88
        * merged["propensity"]
        * merged["segment"].map(segment_mult)
        * merged["loyalty_tier"].map(loyalty_mult)
    )

    lam = lam.clip(lower=0.25, upper=46.0)
    counts = rng.poisson(lam.to_numpy())

    # Keep minimum activity for clearly active segments and cap extremes.
    active_idx = merged["segment"].isin(["repeat_good", "repeat_bad"]).to_numpy() & (counts == 0)
    counts[active_idx] = 1
    counts = np.clip(counts, 0, 140)

    return pd.Series(counts, index=merged["buyer_id"])  # type: ignore[return-value]


def generate_transactions(
    buyers: pd.DataFrame,
    buyer_latent: pd.DataFrame,
    sellers: pd.DataFrame,
    seller_latent: pd.DataFrame,
    products: pd.DataFrame,
    cfg: GenerationConfig,
    rng: np.random.Generator,
) -> Dict[str, pd.DataFrame]:
    start = pd.Timestamp(cfg.start_date)
    end = pd.Timestamp(cfg.end_date)

    month_starts = _month_starts(start, end)
    global_month_weights = _month_weights(month_starts)

    buyer_counts = _compute_buyer_order_counts(buyers, buyer_latent, cfg, rng)

    buyers_join = buyers.merge(buyer_latent, on="buyer_id", how="left")
    sellers_join = sellers.merge(seller_latent, on="seller_id", how="left")
    sellers_lookup = sellers_join.set_index("seller_id")

    seller_prob = sellers_join["volume_weight"].to_numpy()
    seller_prob = seller_prob / seller_prob.sum()
    seller_ids = sellers_join["seller_id"].to_numpy()

    product_cols = [
        "product_id",
        "seller_id",
        "category",
        "list_price",
        "estimated_cost",
        "shipping_cost_proxy",
    ]
    products_small = products[product_cols].copy()

    products_by_seller: Dict[str, np.ndarray] = {}
    for sid, grp in products_small.groupby("seller_id"):
        products_by_seller[sid] = grp.index.to_numpy()

    acquisition_to_channel_probs = {
        "organic": [0.48, 0.47, 0.05],
        "paid_search": [0.53, 0.42, 0.05],
        "social": [0.22, 0.52, 0.26],
        "affiliate": [0.5, 0.44, 0.06],
        "referral": [0.37, 0.55, 0.08],
        "direct": [0.56, 0.4, 0.04],
        "email": [0.45, 0.5, 0.05],
    }
    order_channels = np.array(["web", "mobile_app", "social_commerce"])

    payment_methods = np.array(["credit_card", "debit_card", "digital_wallet", "bank_transfer", "prepaid_card"])

    payment_method_probs_by_segment = {
        "repeat_good": [0.42, 0.25, 0.2, 0.11, 0.02],
        "standard": [0.39, 0.25, 0.24, 0.08, 0.04],
        "price_hunter": [0.32, 0.28, 0.29, 0.05, 0.06],
        "suspicious": [0.27, 0.19, 0.29, 0.06, 0.19],
        "repeat_bad": [0.2, 0.16, 0.27, 0.04, 0.33],
    }

    region_risk_adj = {"Northeast": 0.0, "Midwest": 0.004, "West": 0.012, "Central": 0.008, "South": 0.02}
    category_risk_adj = {cat: float(cfgv["fraud_risk"]) for cat, cfgv in CATEGORY_CONFIG.items()}

    orders_rows: List[Dict[str, object]] = []
    order_items_rows: List[Dict[str, object]] = []
    payments_rows: List[Dict[str, object]] = []
    logistics_rows: List[Dict[str, object]] = []

    order_context: List[Dict[str, object]] = []

    order_counter = 1
    order_item_counter = 1
    payment_counter = 1
    event_counter = 1

    for buyer in buyers_join.itertuples(index=False):
        n_orders = int(buyer_counts.get(buyer.buyer_id, 0))
        if n_orders <= 0:
            continue

        eligible_mask = month_starts >= max(pd.Timestamp(buyer.signup_date), start).replace(day=1)
        eligible_month_idx = np.where(eligible_mask)[0]
        if eligible_month_idx.size == 0:
            continue

        month_probs = global_month_weights[eligible_month_idx]
        month_probs = month_probs / month_probs.sum()

        chosen_months_idx = rng.choice(eligible_month_idx, size=n_orders, p=month_probs)
        chosen_sellers = rng.choice(seller_ids, size=n_orders, p=seller_prob)

        for k in range(n_orders):
            month_start = month_starts[chosen_months_idx[k]]
            day = int(rng.integers(1, month_start.days_in_month + 1))
            hour = int(rng.integers(8, 23))
            minute = int(rng.integers(0, 60))
            order_date = (month_start + pd.Timedelta(days=day - 1, hours=hour, minutes=minute)).floor("min")

            seller_id = str(chosen_sellers[k])
            seller = sellers_lookup.loc[seller_id]

            seller_product_idx = products_by_seller.get(seller_id)
            if seller_product_idx is None or len(seller_product_idx) == 0:
                seller_product_idx = rng.choice(products_small.index.to_numpy(), size=3, replace=False)

            channel_probs = acquisition_to_channel_probs[str(buyer.acquisition_channel)]
            order_channel = str(rng.choice(order_channels, p=channel_probs))

            seg = str(buyer.segment)
            pm_probs = payment_method_probs_by_segment[seg]
            if order_channel == "social_commerce":
                pm_probs = [pm_probs[0] * 0.82, pm_probs[1] * 0.85, pm_probs[2] * 1.22, pm_probs[3] * 0.9, pm_probs[4] * 1.45]
                pm_probs = (np.array(pm_probs) / np.sum(pm_probs)).tolist()
            payment_method = str(rng.choice(payment_methods, p=pm_probs))

            n_items = int(rng.choice([1, 2, 3, 4], p=[0.67, 0.23, 0.08, 0.02]))
            selected_product_idx = rng.choice(seller_product_idx, size=n_items, replace=True)

            item_gross_values: List[float] = []
            item_merchant_discounts: List[float] = []
            item_rows_pending: List[Dict[str, object]] = []

            order_main_category = None

            for pidx in selected_product_idx:
                prod = products_small.loc[pidx]
                category = str(prod["category"])
                if order_main_category is None:
                    order_main_category = category

                category_cfg = CATEGORY_CONFIG[category]
                quantity = int(rng.choice([1, 1, 1, 2, 2, 3], p=[0.34, 0.26, 0.16, 0.16, 0.06, 0.02]))
                sale_price = float(prod["list_price"]) * _clip(rng.normal(0.97, 0.08), 0.58, 1.22)
                sale_price = round(_clip(sale_price, 2.5, 3200.0), 2)
                gross_item_value = round(sale_price * quantity, 2)

                promo_sens = float(category_cfg["promo_sensitivity"])
                markdown_rate = _clip(rng.normal(0.022 + promo_sens * 0.06, 0.02), 0.0, 0.24)
                merchant_discount = round(gross_item_value * markdown_rate, 2)

                item_gross_values.append(gross_item_value)
                item_merchant_discounts.append(merchant_discount)

                item_rows_pending.append(
                    {
                        "order_item_id": f"OI{order_item_counter:08d}",
                        "order_id": f"O{order_counter:08d}",
                        "product_id": str(prod["product_id"]),
                        "seller_id": seller_id,
                        "quantity": quantity,
                        "sale_price": sale_price,
                        "gross_item_value": gross_item_value,
                        "merchant_discount": merchant_discount,
                        "category": category,
                        "estimated_cost": round(float(prod["estimated_cost"]) * quantity, 2),
                        "shipping_cost_proxy": round(float(prod["shipping_cost_proxy"]) * quantity, 2),
                    }
                )
                order_item_counter += 1

            gross_order_value = round(float(np.sum(item_gross_values)), 2)
            promo_used = False
            promo_code = None

            category_cfg_main = CATEGORY_CONFIG[str(order_main_category)]
            promo_prob = float(category_cfg_main["promo_sensitivity"]) * 0.58 + 0.06
            if seg == "price_hunter":
                promo_prob += 0.12
            elif seg == "repeat_bad":
                promo_prob += 0.04
            elif seg == "repeat_good":
                promo_prob -= 0.015

            if order_channel == "mobile_app":
                promo_prob += 0.035
            if month_start.month in (11, 12):
                promo_prob += 0.07

            promo_prob = _clip(promo_prob, 0.04, 0.78)
            if rng.random() < promo_prob:
                promo_used = True
                promo_code = str(rng.choice(PROMO_CODES, p=[0.24, 0.18, 0.17, 0.2, 0.08, 0.13]))

            promo_discount_total = 0.0
            if promo_used:
                promo_rate = _clip(
                    rng.normal(0.038 + float(category_cfg_main["promo_sensitivity"]) * 0.24, 0.025),
                    0.02,
                    0.34,
                )
                if promo_code in ("FLASH15", "APP20"):
                    promo_rate += 0.018
                promo_discount_total = round(gross_order_value * promo_rate, 2)

            gross_arr = np.array(item_gross_values)
            if gross_arr.sum() > 0:
                promo_alloc = promo_discount_total * (gross_arr / gross_arr.sum())
            else:
                promo_alloc = np.zeros_like(gross_arr)

            net_total = 0.0
            seller_commission_rate = float(seller["commission_rate"])

            for i, pending in enumerate(item_rows_pending):
                promo_piece = round(float(promo_alloc[i]), 2)
                total_discount = round(float(pending["merchant_discount"]) + promo_piece, 2)
                net_item_value = round(max(0.5, float(pending["gross_item_value"]) - total_discount), 2)
                commission_fee = round(net_item_value * seller_commission_rate, 2)

                shipping_subsidy_factor = 0.22
                if str(seller["fulfillment_model"]) == "platform_fulfilled":
                    shipping_subsidy_factor += 0.16
                if buyer.region != seller.seller_region:
                    shipping_subsidy_factor += 0.11
                if pending["category"] in ("Fashion", "Grocery"):
                    shipping_subsidy_factor += 0.08
                shipping_subsidy_factor = _clip(shipping_subsidy_factor, 0.12, 0.64)

                margin_proxy = round(
                    commission_fee - promo_piece - float(pending["shipping_cost_proxy"]) * shipping_subsidy_factor,
                    2,
                )

                order_items_rows.append(
                    {
                        "order_item_id": pending["order_item_id"],
                        "order_id": pending["order_id"],
                        "product_id": pending["product_id"],
                        "seller_id": pending["seller_id"],
                        "quantity": pending["quantity"],
                        "sale_price": pending["sale_price"],
                        "gross_item_value": pending["gross_item_value"],
                        "net_item_value": net_item_value,
                        "discount_amount": total_discount,
                        "commission_fee": commission_fee,
                        "estimated_cost": pending["estimated_cost"],
                        "margin_proxy": margin_proxy,
                    }
                )
                net_total += net_item_value

            net_paid_amount = round(net_total, 2)
            subsidy_amount = round(promo_discount_total, 2)

            order_id = f"O{order_counter:08d}"
            order_counter += 1

            risk_score = 0.014
            risk_score += float(buyer.segment_risk)
            risk_score += float(seller.seller_risk) * 0.52
            risk_score += category_risk_adj[str(order_main_category)] * 0.44
            risk_score += region_risk_adj[str(buyer.region)]
            risk_score += {"credit_card": 0.016, "debit_card": 0.013, "digital_wallet": 0.028, "bank_transfer": 0.01, "prepaid_card": 0.075}[payment_method]
            risk_score += {"web": 0.0, "mobile_app": 0.01, "social_commerce": 0.045}[order_channel]
            if str(buyer.region) == "South" and str(order_main_category) in ("Electronics", "Digital Goods") and order_channel == "social_commerce":
                risk_score += 0.095
            if bool(seller.very_high_risk_flag) and payment_method in ("prepaid_card", "digital_wallet"):
                risk_score += 0.08
            if net_paid_amount > 420:
                risk_score += 0.015
            risk_score = _clip(risk_score, 0.003, 0.95)

            payment_attempts = int(1 + (rng.random() < risk_score * 0.95) + (rng.random() < risk_score * 0.34))
            payment_fail_prob = _clip(0.012 + risk_score * 0.18 + (0.012 if payment_attempts >= 3 else 0.0), 0.005, 0.45)
            payment_status = "failed" if rng.random() < payment_fail_prob else "paid"

            if risk_score < 0.075:
                payment_risk_signal = "low"
            elif risk_score < 0.145:
                payment_risk_signal = "medium"
            elif risk_score < 0.255:
                payment_risk_signal = "high"
            else:
                payment_risk_signal = "critical"

            payment_id = f"PAY{payment_counter:08d}"
            payment_counter += 1

            chargeback_flag = 0

            if payment_status == "failed":
                cancellation_flag = 1
                shipped_date = pd.NaT
                delivered_date = pd.NaT
                promised_delivery = pd.NaT
                delay_days = np.nan
                order_status = "payment_failed"
            else:
                same_region = buyer.region == seller.seller_region
                base_transit = 2.2 if same_region else 4.1
                if str(seller.fulfillment_model) == "platform_fulfilled":
                    base_transit -= 0.7

                category_ship_adj = float(CATEGORY_CONFIG[str(order_main_category)]["shipping_base"]) / 6.0
                processing_days = max(0, int(round(rng.normal(1.2 + (0.85 if str(seller.fulfillment_model) == "seller_fulfilled" else 0.2), 0.8))))

                seasonal_delay = 0.0
                if month_start.month in (11, 12):
                    seasonal_delay += 0.9
                elif month_start.month == 1:
                    seasonal_delay += 0.25

                cancel_prob = _clip(
                    0.006
                    + float(seller.defect_risk) * 0.82
                    + (0.02 if bool(seller.weak_quality_flag) else 0.0)
                    + (0.015 if month_start.month in (11, 12) else 0.0),
                    0.002,
                    0.33,
                )
                cancellation_flag = int(rng.random() < cancel_prob)

                promised_days = int(round(base_transit + category_ship_adj + processing_days + rng.normal(0.0, 0.8)))
                # Ensure promised delivery cannot precede shipping completion.
                promised_days = max(1, processing_days + 1, promised_days)
                promised_delivery = order_date + pd.Timedelta(days=promised_days)

                if cancellation_flag:
                    shipped_date = pd.NaT
                    delivered_date = pd.NaT
                    delay_days = np.nan
                    order_status = "cancelled"
                else:
                    delay_expect = (
                        float(seller.delay_risk)
                        + seasonal_delay
                        + (0.55 if not same_region else 0.0)
                        + (0.8 if bool(seller.weak_quality_flag) else 0.0)
                        + rng.normal(0.0, 0.5)
                    )
                    delay_days = max(0, int(round(delay_expect)))
                    shipped_date = order_date + pd.Timedelta(days=processing_days)
                    delivered_date = promised_delivery + pd.Timedelta(days=delay_days)
                    order_status = "completed"

            orders_rows.append(
                {
                    "order_id": order_id,
                    "buyer_id": buyer.buyer_id,
                    "order_date": order_date,
                    "payment_method": payment_method,
                    "order_channel": order_channel,
                    "promo_code_used": promo_code if promo_used else None,
                    "gross_order_value": gross_order_value,
                    "subsidy_amount": subsidy_amount,
                    "net_paid_amount": net_paid_amount,
                    "order_status": order_status,
                }
            )

            payments_rows.append(
                {
                    "payment_id": payment_id,
                    "order_id": order_id,
                    "payment_status": payment_status,
                    "payment_attempts": payment_attempts,
                    "chargeback_flag": chargeback_flag,
                    "payment_risk_signal": payment_risk_signal,
                }
            )

            logistics_rows.append(
                {
                    "event_id": f"L{event_counter:09d}",
                    "order_id": order_id,
                    "seller_id": seller_id,
                    "shipped_date": shipped_date,
                    "delivered_date": delivered_date,
                    "promised_delivery_date": promised_delivery,
                    "delay_days": delay_days,
                    "cancellation_flag": cancellation_flag,
                }
            )
            event_counter += 1

            order_context.append(
                {
                    "order_id": order_id,
                    "buyer_id": buyer.buyer_id,
                    "seller_id": seller_id,
                    "order_date": order_date,
                    "payment_id": payment_id,
                    "payment_status": payment_status,
                    "payment_risk_signal": payment_risk_signal,
                    "payment_risk_numeric": risk_score,
                    "order_main_category": order_main_category,
                    "order_channel": order_channel,
                    "net_paid_amount": net_paid_amount,
                    "order_status": order_status,
                    "delay_days": delay_days,
                    "cancellation_flag": cancellation_flag,
                    "delivered_date": delivered_date,
                    "region": buyer.region,
                    "promo_used": promo_used,
                }
            )

    orders = pd.DataFrame(orders_rows)
    order_items = pd.DataFrame(order_items_rows)
    payments = pd.DataFrame(payments_rows)
    logistics = pd.DataFrame(logistics_rows)

    refunds_rows: List[Dict[str, object]] = []
    disputes_rows: List[Dict[str, object]] = []
    refund_counter = 1
    dispute_counter = 1

    buyer_lookup = buyers_join.set_index("buyer_id")
    seller_lookup = sellers_join.set_index("seller_id")

    order_status_map = orders.set_index("order_id")["order_status"].to_dict()
    payment_chargeback_map = {r["order_id"]: 0 for r in payments_rows}

    for ctx in order_context:
        if ctx["payment_status"] != "paid":
            continue

        oid = str(ctx["order_id"])
        buyer_row = buyer_lookup.loc[str(ctx["buyer_id"])]
        seller_row = seller_lookup.loc[str(ctx["seller_id"])]
        category = str(ctx["order_main_category"])

        delay_days = 0 if pd.isna(ctx["delay_days"]) else int(ctx["delay_days"])
        cancellation_flag = int(ctx["cancellation_flag"])
        net_paid = float(ctx["net_paid_amount"])

        refund_prob = (
            float(CATEGORY_CONFIG[category]["refund_base"])
            + (0.31 if cancellation_flag else 0.0)
            + (0.065 if delay_days >= 3 else 0.0)
            + (0.115 if delay_days >= 7 else 0.0)
            + float(buyer_row["refund_bias"])
            + float(seller_row["defect_risk"]) * 0.4
            + region_risk_adj[str(ctx["region"]) ] * 0.7
            + (0.028 if bool(ctx["promo_used"]) else 0.0)
        )
        refund_prob = _clip(refund_prob, 0.01, 0.88)

        has_refund = rng.random() < refund_prob
        full_refund = False
        refund_amount = 0.0
        current_refund_date: pd.Timestamp | None = None

        if has_refund:
            full_refund_prob = 0.2 + (0.52 if cancellation_flag else 0.0) + (0.22 if delay_days >= 6 else 0.0)
            full_refund_prob += 0.12 if str(buyer_row["segment"]) == "repeat_bad" else 0.0
            full_refund_prob = _clip(full_refund_prob, 0.12, 0.96)
            full_refund = rng.random() < full_refund_prob

            if full_refund:
                refund_amount = round(net_paid, 2)
            else:
                refund_amount = round(net_paid * _clip(rng.normal(0.48, 0.18), 0.12, 0.82), 2)

            if cancellation_flag:
                reason = "order_cancelled"
                refund_date = pd.Timestamp(ctx["order_date"]) + pd.Timedelta(days=int(rng.integers(1, 5)))
            elif delay_days >= 6:
                reason = rng.choice(["late_delivery", "item_not_received"], p=[0.64, 0.36])
                base_date = pd.Timestamp(ctx["delivered_date"]) if pd.notna(ctx["delivered_date"]) else pd.Timestamp(ctx["order_date"]) + pd.Timedelta(days=6)
                refund_date = base_date + pd.Timedelta(days=int(rng.integers(1, 14)))
            elif str(buyer_row["segment"]) in ("suspicious", "repeat_bad") and float(ctx["payment_risk_numeric"]) > 0.22:
                reason = "fraud_suspected"
                base_date = pd.Timestamp(ctx["order_date"]) + pd.Timedelta(days=int(rng.integers(2, 16)))
                refund_date = base_date
            else:
                reason = rng.choice(["not_as_described", "damaged_item", "buyer_remorse"], p=[0.42, 0.29, 0.29])
                base_date = pd.Timestamp(ctx["delivered_date"]) if pd.notna(ctx["delivered_date"]) else pd.Timestamp(ctx["order_date"]) + pd.Timedelta(days=5)
                refund_date = base_date + pd.Timedelta(days=int(rng.integers(1, 21)))

            current_refund_date = pd.Timestamp(refund_date)
            refunds_rows.append(
                {
                    "refund_id": f"R{refund_counter:08d}",
                    "order_id": oid,
                    "refund_date": refund_date,
                    "refund_reason": reason,
                    "refund_amount": refund_amount,
                    "full_refund_flag": int(full_refund),
                }
            )
            refund_counter += 1

            if full_refund:
                order_status_map[oid] = "refunded"
            else:
                if order_status_map.get(oid) not in ("cancelled", "payment_failed"):
                    order_status_map[oid] = "partially_refunded"

        remaining_exposure = max(0.0, net_paid - refund_amount)
        dispute_prob = (
            0.007
            + float(ctx["payment_risk_numeric"]) * 0.48
            + float(buyer_row["dispute_bias"])
            + float(seller_row["seller_risk"]) * 0.2
            + (0.055 if delay_days >= 5 else 0.0)
            + (0.03 if has_refund and not full_refund else 0.0)
            + (0.045 if str(ctx["order_channel"]) == "social_commerce" else 0.0)
        )
        if full_refund or remaining_exposure <= 1.0:
            dispute_prob *= 0.15
        dispute_prob = _clip(dispute_prob, 0.002, 0.74)

        if rng.random() < dispute_prob:
            if float(ctx["payment_risk_numeric"]) > 0.24:
                dispute_reason = rng.choice(["unauthorized_transaction", "item_not_received", "not_as_described"], p=[0.58, 0.27, 0.15])
            elif delay_days >= 5:
                dispute_reason = rng.choice(["item_not_received", "late_delivery", "refund_not_processed"], p=[0.45, 0.33, 0.22])
            else:
                dispute_reason = rng.choice(["not_as_described", "damaged_item", "refund_not_processed"], p=[0.49, 0.31, 0.2])

            dispute_amount = round(net_paid * _clip(rng.normal(0.71, 0.23), 0.2, 1.0), 2)
            dispute_amount = round(min(dispute_amount, remaining_exposure), 2)
            if dispute_amount < 1.0:
                continue

            if dispute_reason == "unauthorized_transaction":
                status = rng.choice(["won_by_buyer", "won_by_seller", "under_review"], p=[0.73, 0.13, 0.14])
            elif dispute_reason in ("item_not_received", "late_delivery"):
                status = rng.choice(["won_by_buyer", "won_by_seller", "under_review"], p=[0.57, 0.24, 0.19])
            else:
                good_seller = float(seller_row["quality_score"]) > 0.62
                status = rng.choice(["won_by_buyer", "won_by_seller", "under_review"], p=[0.33, 0.49 if good_seller else 0.35, 0.18 if good_seller else 0.32])

            if has_refund and current_refund_date is not None:
                base_dispute_date = current_refund_date
            else:
                base_dispute_date = pd.Timestamp(ctx["order_date"]) + pd.Timedelta(days=int(rng.integers(5, 40)))
            dispute_date = base_dispute_date + pd.Timedelta(days=int(rng.integers(0, 18)))

            if str(status) == "won_by_buyer" and dispute_reason in ("unauthorized_transaction", "item_not_received"):
                cb_prob = 0.86 if dispute_reason == "unauthorized_transaction" else 0.61
                # Keep loss-channel coherence: if chargeback happens, avoid additional dispute/refund loss stacking.
                if (not has_refund) and (rng.random() < cb_prob):
                    payment_chargeback_map[oid] = 1
                    order_status_map[oid] = "chargeback"
                    continue

            disputes_rows.append(
                {
                    "dispute_id": f"D{dispute_counter:08d}",
                    "order_id": oid,
                    "dispute_date": dispute_date,
                    "dispute_reason": dispute_reason,
                    "dispute_status": str(status),
                    "dispute_amount": dispute_amount,
                }
            )
            dispute_counter += 1

    refunds = pd.DataFrame(refunds_rows)
    disputes = pd.DataFrame(disputes_rows)

    if not refunds.empty:
        refunds["refund_date"] = pd.to_datetime(refunds["refund_date"]).dt.floor("D")
    if not disputes.empty:
        disputes["dispute_date"] = pd.to_datetime(disputes["dispute_date"]).dt.floor("D")

    orders["order_status"] = orders["order_id"].map(order_status_map)

    payments["chargeback_flag"] = payments["order_id"].map(payment_chargeback_map).fillna(0).astype(int)

    # Keep date columns consistently date-like where appropriate.
    orders["order_date"] = pd.to_datetime(orders["order_date"]).dt.floor("min")
    logistics["shipped_date"] = pd.to_datetime(logistics["shipped_date"]).dt.floor("D")
    logistics["delivered_date"] = pd.to_datetime(logistics["delivered_date"]).dt.floor("D")
    logistics["promised_delivery_date"] = pd.to_datetime(logistics["promised_delivery_date"]).dt.floor("D")

    return {
        "orders": orders,
        "order_items": order_items,
        "payments": payments,
        "refunds": refunds,
        "disputes": disputes,
        "logistics_events": logistics,
    }


def generate_all_tables(cfg: GenerationConfig) -> Dict[str, pd.DataFrame]:
    rng = np.random.default_rng(cfg.seed)
    buyers, buyer_latent = generate_buyers(cfg, rng)
    sellers, seller_latent = generate_sellers(cfg, rng)
    products = generate_products(sellers, seller_latent, rng)

    tx = generate_transactions(
        buyers=buyers,
        buyer_latent=buyer_latent,
        sellers=sellers,
        seller_latent=seller_latent,
        products=products,
        cfg=cfg,
        rng=rng,
    )

    tables = {
        "buyers": buyers,
        "sellers": sellers,
        "products": products,
        **tx,
    }

    # Ensure requested schema ordering.
    tables["buyers"] = tables["buyers"][
        ["buyer_id", "signup_date", "region", "acquisition_channel", "customer_type", "loyalty_tier"]
    ]
    tables["sellers"] = tables["sellers"][
        [
            "seller_id",
            "onboarding_date",
            "seller_region",
            "seller_type",
            "category_focus",
            "seller_tier",
            "commission_plan",
            "fulfillment_model",
        ]
    ]
    tables["products"] = tables["products"][
        [
            "product_id",
            "seller_id",
            "category",
            "subcategory",
            "list_price",
            "estimated_cost",
            "shipping_cost_proxy",
        ]
    ]

    tables["orders"] = tables["orders"][
        [
            "order_id",
            "buyer_id",
            "order_date",
            "payment_method",
            "order_channel",
            "promo_code_used",
            "gross_order_value",
            "subsidy_amount",
            "net_paid_amount",
            "order_status",
        ]
    ]

    tables["order_items"] = tables["order_items"][
        [
            "order_item_id",
            "order_id",
            "product_id",
            "seller_id",
            "quantity",
            "sale_price",
            "gross_item_value",
            "net_item_value",
            "discount_amount",
            "commission_fee",
            "estimated_cost",
            "margin_proxy",
        ]
    ]

    tables["payments"] = tables["payments"][
        [
            "payment_id",
            "order_id",
            "payment_status",
            "payment_attempts",
            "chargeback_flag",
            "payment_risk_signal",
        ]
    ]

    tables["refunds"] = tables["refunds"][
        ["refund_id", "order_id", "refund_date", "refund_reason", "refund_amount", "full_refund_flag"]
    ]

    tables["disputes"] = tables["disputes"][
        ["dispute_id", "order_id", "dispute_date", "dispute_reason", "dispute_status", "dispute_amount"]
    ]

    tables["logistics_events"] = tables["logistics_events"][
        [
            "event_id",
            "order_id",
            "seller_id",
            "shipped_date",
            "delivered_date",
            "promised_delivery_date",
            "delay_days",
            "cancellation_flag",
        ]
    ]

    return tables


def save_tables(tables: Dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(output_dir / f"{name}.csv", index=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic marketplace raw datasets.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-buyers", type=int, default=9000)
    parser.add_argument("--n-sellers", type=int, default=1200)
    parser.add_argument("--start-date", type=str, default="2024-03-01")
    parser.add_argument("--end-date", type=str, default="2026-02-28")

    args = parser.parse_args()

    cfg = GenerationConfig(
        seed=args.seed,
        n_buyers=args.n_buyers,
        n_sellers=args.n_sellers,
        start_date=args.start_date,
        end_date=args.end_date,
    )

    tables = generate_all_tables(cfg)
    save_tables(tables, args.output_dir)

    print("Synthetic marketplace data generated:")
    for name, df in tables.items():
        print(f"  - {name}: {len(df):,} rows")


if __name__ == "__main__":
    main()
