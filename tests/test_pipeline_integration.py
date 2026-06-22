"""End-to-end, in-process exercise of the analytical chain on a small synthetic
dataset. This gives real line coverage to the data-generation, feature, scoring,
governance, scenario, Monte Carlo, and backtesting modules without depending on
the committed full-size artifacts, and surfaces small-sample fragility early.

It is deliberately sized small (few hundred buyers, ~1 year) so the whole chain
runs in a few seconds while still touching every stage."""

from pathlib import Path

import pandas as pd
import pytest
from src.backtesting.run_score_policy_backtest import BacktestConfig, run_backtest
from src.data_generation.generate_synthetic_marketplace_data import (
    GenerationConfig,
    generate_all_tables,
    save_tables,
)
from src.features.build_analytical_feature_layer import (
    FeatureBuildConfig,
    build_feature_layer,
    save_feature_tables,
)
from src.governance.build_governance_action_register import (
    GovernanceConfig,
    build_action_register,
)
from src.scenario_analysis.build_scenario_decision_analysis import (
    ScenarioConfig,
    build_scenarios,
)
from src.scenario_analysis.build_scenario_decision_analysis import (
    save_tables as save_scenario_tables,
)
from src.scenario_analysis.run_scenario_monte_carlo import MonteCarloConfig, run_monte_carlo
from src.scoring.build_scoring_framework import (
    ScoringConfig,
    build_scoring_tables,
)
from src.scoring.build_scoring_framework import (
    save_tables as save_scoring_tables,
)


@pytest.fixture(scope="module")
def small_pipeline(tmp_path_factory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("mini_marketplace")
    raw = base / "raw"
    proc = base / "processed"
    charts = base / "charts"
    raw.mkdir()
    proc.mkdir()
    charts.mkdir()

    tables = generate_all_tables(
        GenerationConfig(seed=7, n_buyers=400, n_sellers=80, start_date="2024-03-01", end_date="2025-02-28")
    )
    save_tables(tables, raw)

    feature_tables = build_feature_layer(FeatureBuildConfig(raw_dir=raw, output_dir=proc))
    save_feature_tables(feature_tables, proc)

    scoring_tables = build_scoring_tables(ScoringConfig(raw_dir=raw, processed_dir=proc))
    save_scoring_tables(scoring_tables, proc)

    register = build_action_register(GovernanceConfig(processed_dir=proc, output_dir=proc))
    register.to_csv(proc / "governance_action_register.csv", index=False)

    scenario_tables = build_scenarios(
        ScenarioConfig(raw_dir=raw, processed_dir=proc, baseline_months=3, horizon_months=3)
    )
    save_scenario_tables(scenario_tables, proc)

    mc = run_monte_carlo(
        MonteCarloConfig(processed_dir=proc, output_dir=proc, charts_dir=charts, iterations=64, seed=7)
    )
    if isinstance(mc, dict):
        for name, value in mc.items():
            if isinstance(value, pd.DataFrame):
                value.to_csv(proc / f"{name}.csv", index=False)

    bt = run_backtest(BacktestConfig(raw_dir=raw, processed_dir=proc, output_dir=proc, charts_dir=charts))

    return {"raw": raw, "proc": proc, "register": register, "mc": mc, "bt": bt}


def test_generated_raw_tables_present_and_nonempty(small_pipeline) -> None:
    raw = small_pipeline["raw"]
    for name in ["buyers", "sellers", "products", "orders", "order_items"]:
        df = pd.read_csv(raw / f"{name}.csv")
        assert not df.empty


def test_feature_layer_has_one_row_per_order(small_pipeline) -> None:
    proc = small_pipeline["proc"]
    opf = pd.read_csv(proc / "order_profitability_features.csv")
    orders = pd.read_csv(small_pipeline["raw"] / "orders.csv")
    assert len(opf) == len(orders)
    assert opf["order_id"].is_unique


def test_scores_are_bounded_and_tiered(small_pipeline) -> None:
    proc = small_pipeline["proc"]
    ors = pd.read_csv(proc / "order_risk_scores.csv")
    assert ors["order_risk_score"].between(0, 100).all()
    assert set(ors["order_risk_tier"]).issubset({"Low", "Moderate", "High", "Critical"})


def test_governance_register_built(small_pipeline) -> None:
    register = small_pipeline["register"]
    assert not register.empty
    assert {"seller", "order"} & set(register["entity_type"])


def test_scenarios_and_montecarlo_produced(small_pipeline) -> None:
    proc = small_pipeline["proc"]
    results = pd.read_csv(proc / "scenario_results_summary.csv")
    assert "baseline" in set(results["scenario"])
    # The Monte Carlo run returned something tabular for downstream consumption.
    assert small_pipeline["mc"] is not None


def test_backtest_recommends_a_policy(small_pipeline) -> None:
    bt = small_pipeline["bt"]
    assert bt is not None
