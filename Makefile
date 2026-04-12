PYTHON := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest

.PHONY: help setup test data features scoring governance scenarios montecarlo backtest viz dashboard pages snapshot schema-contracts metric-governance schema-drift validate release-gate all

help:
	@echo "Targets:"
	@echo "  setup      Create virtualenv + install requirements"
	@echo "  test       Run test suite"
	@echo "  data       Generate synthetic raw tables"
	@echo "  features   Build analytical feature tables"
	@echo "  scoring    Build scoring tables"
	@echo "  governance Build governance action register"
	@echo "  scenarios  Build scenario analysis tables"
	@echo "  montecarlo Build Monte Carlo scenario uncertainty tables"
	@echo "  backtest   Build score policy backtesting outputs"
	@echo "  viz        Build chart pack"
	@echo "  dashboard  Build executive HTML dashboard"
	@echo "  pages      Publish GitHub Pages entrypoint + named dashboard artifact"
	@echo "  snapshot   Build executive KPI snapshot artifacts"
	@echo "  schema-contracts Generate + validate schema contracts"
	@echo "  metric-governance Validate governed KPI contracts and recomputation"
	@echo "  schema-drift Generate schema drift report + history snapshot"
	@echo "  validate   Run formal validation report"
	@echo "  release-gate Enforce release state gate from validation outputs"
	@echo "  all        Run full end-to-end pipeline"

setup:
	python3 -m venv .venv
	$(PIP) install -r requirements.txt

test:
	$(PYTEST) -q

data:
	$(PYTHON) src/data_generation/generate_synthetic_marketplace_data.py --output-dir data/raw

features:
	$(PYTHON) src/features/build_analytical_feature_layer.py --raw-dir data/raw --output-dir data/processed

scoring:
	$(PYTHON) src/scoring/build_scoring_framework.py --raw-dir data/raw --processed-dir data/processed

governance:
	$(PYTHON) src/governance/build_governance_action_register.py --processed-dir data/processed --output-dir data/processed

scenarios:
	$(PYTHON) src/scenario_analysis/build_scenario_decision_analysis.py --raw-dir data/raw --processed-dir data/processed --baseline-months 6 --horizon-months 6

montecarlo:
	$(PYTHON) src/scenario_analysis/run_scenario_monte_carlo.py --processed-dir data/processed --output-dir data/processed --charts-dir outputs/charts --iterations 2000

backtest:
	$(PYTHON) src/backtesting/run_score_policy_backtest.py --raw-dir data/raw --processed-dir data/processed --output-dir data/processed --charts-dir outputs/charts

viz:
	$(PYTHON) src/visualization/build_marketplace_visualizations.py --raw-dir data/raw --processed-dir data/processed --output-dir outputs/charts

dashboard:
	$(PYTHON) src/dashboard/build_executive_dashboard.py --raw-dir data/raw --processed-dir data/processed --reports-dir reports --output-file outputs/dashboard/executive-marketplace-command-center.html

pages:
	$(PYTHON) src/dashboard/publish_github_pages.py --source-html outputs/dashboard/executive-marketplace-command-center.html --destination-html .pages/executive-marketplace-command-center.html --index-html .pages/index.html

snapshot:
	$(PYTHON) src/validation/generate_executive_snapshot.py --raw-dir data/raw --processed-dir data/processed --reports-dir reports

schema-contracts:
	$(PYTHON) src/validation/generate_schema_contracts.py --raw-dir data/raw --processed-dir data/processed --output-file config/contracts/v1/schema_contracts.json
	$(PYTHON) src/validation/validate_schema_contracts.py --schema-file config/contracts/v1/schema_contracts.json --output-file reports/schema_contract_issues.csv

metric-governance:
	$(PYTHON) src/validation/validate_metric_governance.py --raw-dir data/raw --processed-dir data/processed --reports-dir reports --contract-file config/contracts/v1/metric_governance_contract.csv --output-file reports/metric_governance_issues.csv

schema-drift:
	$(PYTHON) src/validation/generate_schema_drift_report.py --current-schema-file config/contracts/v1/schema_contracts.json --history-dir config/contracts/history --output-csv reports/schema_drift_changes.csv --output-report reports/schema_drift_report.md --snapshot-current

validate:
	$(PYTHON) src/validation/run_full_validation.py --raw-dir data/raw --processed-dir data/processed --report-dir reports --schema-file config/contracts/v1/schema_contracts.json --metric-contract-file config/contracts/v1/metric_governance_contract.csv

release-gate:
	$(PYTHON) src/validation/enforce_release_gate.py --release-file reports/validation_release_assessment.csv --required-state decision-support\ only

all:
	$(PYTHON) src/pipeline/run_full_pipeline.py --raw-dir data/raw --processed-dir data/processed --charts-dir outputs/charts --dashboard-file outputs/dashboard/executive-marketplace-command-center.html --pages-dashboard-file .pages/executive-marketplace-command-center.html --pages-index-file .pages/index.html --monte-carlo-iterations 2000 --schema-file config/contracts/v1/schema_contracts.json --metric-contract-file config/contracts/v1/metric_governance_contract.csv --schema-history-dir config/contracts/history --reports-dir reports --required-release-state decision-support\ only
