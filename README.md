# Marketplace Profitability, Fraud & Seller Quality Command Center

A reproducible marketplace decision system spanning management P&L, point-in-time risk validation, controlled intervention design, seller governance, an analytical warehouse, and an auditable case-management API.

![CI](https://github.com/mfidalgomartins/marketplace-profitability-risk-command-center/actions/workflows/ci.yml/badge.svg) ![GitHub Pages](https://github.com/mfidalgomartins/marketplace-profitability-risk-command-center/actions/workflows/pages.yml/badge.svg)

**[Live dashboard](https://mfidalgomartins.github.io/marketplace-profitability-risk-command-center/)** · **[Analytical report](outputs/reports/marketplace-command-center-report.pdf)**

![Growth quality view from the marketplace command center](outputs/graphs/01_growth_quality_gap.png)

## Flagship deliverables

### [Interactive dashboard](https://mfidalgomartins.github.io/marketplace-profitability-risk-command-center/)

The primary review surface for a seller-quality committee: portfolio KPIs ranked by argument (gross → protected → margin), scope filters that recompute every panel against a trailing baseline instead of a static snapshot, a guardrail checklist for dispute/refund/subsidy/on-time thresholds, and a scenario comparison view for threshold trade-offs. Single self-contained HTML file, no server required.

### [Analytical report](outputs/reports/marketplace-command-center-report.pdf)

The narrative counterpart to the dashboard: leakage waterfall, seller governance distribution, model calibration and holdout evidence, and the scenario ranges behind the recommended policy — typeset as a single production PDF, not a slide deck. It states the model's failed release gate in the same voice as its passing ones.

| | Dashboard | Report |
|---|---|---|
| Format | Self-contained HTML (Plotly) | Typeset PDF |
| Use | Live filtering, scope drill-down | Fixed evidence pack for distribution |
| Audience | Working session, ad hoc queries | Committee review, offline reading |

## What this project demonstrates

- Accounting-grade synthetic management accounts: one order subledger row per order, double-entry monthly journals, and cent-level reconciliation.
- Leakage-safe scoring: fixed ex ante priors, a 60-day outcome-maturation lag, and no current- or future-outcome leakage into historical scores.
- Model governance: logistic probability calibration, a maturation gap, a fully matured later-period holdout, an unmatured shadow window, monthly drift metrics, alerts, and explicit release gates.
- Experimentation: deterministic random allocation, covariate balance, power analysis, intention-to-treat estimates, seller-clustered standard errors, and segment diagnostics.
- Data engineering: an idempotent DuckDB catalog over raw and analytical CSVs with curated order, seller, finance, model-monitoring, and experiment marts.
- Operations: a FastAPI case workflow with deny-by-default bearer authentication, RBAC, optimistic concurrency, idempotent commands, manager approval, immutable events, and an HMAC-chained audit log.
- Publication: a standalone responsive dashboard, 20-chart evidence pack, and one production analytical report.

## Current evidence boundary

All data and intervention outcomes are synthetic. The system is suitable for portfolio demonstration and decision-support prototyping; it is not authorized for financial reporting, fraud enforcement, seller sanctions, or causal claims.

The current later-period holdout contains 42,688 fully matured orders. Calibration passes its Brier and expected-calibration-error gates, but ROC AUC is 0.582 against a 0.600 policy threshold. The governed status is therefore `recalibration-required`, and automated decisions remain `not approved`. Keeping this failed gate visible is intentional: the repository demonstrates model-risk control, not a manufactured “green” result.

## Data scope

The deterministic dataset covers March 2024 through February 2026.

| Entity | Rows |
|---|---:|
| Orders | 156,121 |
| Order items | 226,097 |
| Sellers | 1,200 |
| Buyers | 9,000 |
| Products | 20,326 |
| Refund events | 27,835 |
| Dispute events | 22,146 |

Current economics assume one seller per order. The release gate blocks publication if this grain changes without a governed allocation model.

## Execution flow

```text
synthetic sources
  -> order-grain features and matured historical rates
  -> heuristic order/seller scores
  -> temporal calibration, holdout, drift, and alerts
  -> order subledger, double-entry ledger, and reconciliation
  -> randomized intervention analysis
  -> governance queue, scenarios, Monte Carlo, and threshold backtest
  -> DuckDB source views and curated marts
  -> schema/metric/integrity/release validation
  -> dashboard, charts, analytical PDF, and Pages artifact
```

The threshold backtest remains retrospective and in-sample. It is a capacity-planning input, separate from the later-period holdout and the synthetic randomized trial.

See [architecture](docs/architecture.md), [methodology](docs/methodology.md), [data dictionary](docs/data_dictionary.md), and [API operating guide](docs/api.md).

![Seller portfolio matrix and risk tier separation from the evidence pack](outputs/graphs/09_seller_portfolio_matrix.png)

## Primary outputs

| Output | Purpose |
|---|---|
| [Dashboard](outputs/dashboard/executive-marketplace-command-center.html) | Interactive executive review surface; existing visual design preserved |
| [Analytical PDF](outputs/reports/marketplace-command-center-report.pdf) | Full narrative and visual evidence pack |
| [`order_accounting_pnl.csv`](data/processed/order_accounting_pnl.csv) | Order-level management-accounting subledger |
| [`model_release_assessment.csv`](data/processed/model_release_assessment.csv) | Holdout gates and automation guardrail |
| [`experiment_results.csv`](data/processed/experiment_results.csv) | Synthetic randomized-trial ITT estimates |
| [`governance_action_register.csv`](data/processed/governance_action_register.csv) | Owned seller/order intervention queue |
| [`warehouse_validation.csv`](reports/warehouse_validation.csv) | DuckDB source and curated-mart checks |
| [`validation_report.md`](reports/validation_report.md) | Formal release evidence and limitations |

The DuckDB database is a reproducible local runtime artifact at `outputs/warehouse/marketplace.duckdb` and is intentionally not versioned. Run `make warehouse` to synchronize it.

## Run locally

Requires Python 3.12+.

```bash
make setup
make all
make verify
```

`make all` rebuilds the complete governed pipeline. Normal runs validate the committed schema contract but cannot rewrite it. Intentional schema changes use `make update-schema-contracts`, followed by review of the contract and drift report.

Useful focused targets:

```bash
make model-validation
make finance
make experiment
make warehouse
make api
```

The API starts in fail-closed mode: health endpoints remain available, but protected routes require configured token hashes and a 32-byte-or-longer audit HMAC key. See [docs/api.md](docs/api.md) before running `make api`.

Run the batch pipeline in Docker:

```bash
docker build -t marketplace-command-center .
docker run --rm -v "$PWD:/app" marketplace-command-center
```

## Repository structure

```text
config/contracts/   schema, metric, model, finance, and experiment policies
data/raw/           deterministic synthetic sources
data/processed/     analytical, accounting, model, experiment, and governance outputs
docs/               architecture, methodology, data, API, and executive documentation
outputs/dashboard/  standalone interactive dashboard
outputs/graphs/     publication chart pack
outputs/reports/    single production analytical PDF report
reports/            KPI, warehouse, validation, and release evidence
src/api/            secured case-management service and SQL migration
src/warehouse/      idempotent DuckDB catalog and curated marts
src/                batch analytics, governance, validation, and publication modules
tests/              unit, integration, API, accounting, experiment, warehouse, and artifact tests
```

## Quality and release status

CI rebuilds governed artifacts and runs formatting, lint, static types, Bandit, dependency audit, compilation, and tests with an 85% coverage floor. The current local suite passes 155 tests at 88.73% total source coverage.

Formal validation currently reports 0 critical issues, 0 high issues, and 1 medium model-monitoring warning. The public artifact state is `decision-support only`; committee-grade and automated-decision flags remain false.

## License

[MIT](LICENSE)

The analytical PDF embeds [PT Serif](https://github.com/google/fonts/tree/main/ofl/ptserif) under the [SIL Open Font License 1.1](assets/fonts/OFL.txt).
