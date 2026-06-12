# Marketplace Profitability, Fraud & Seller Quality Command Center

Reproducible marketplace analytics that connects unit economics, fraud exposure, seller quality, operational leakage, scenario testing, and governed release validation.

**[Open the live dashboard](https://mfidalgomartins.github.io/marketplace-profitability-risk-command-center/)** · **[Open the analytical report](outputs/reports/marketplace-command-center-report.pdf)**

![Growth quality view from the marketplace command center](outputs/graphs/01_growth_quality_gap.png)

## Decisions Supported

- Distinguish topline GMV growth from protected value and contribution margin.
- Route high-risk orders and weak-quality sellers into finite intervention queues.
- Quantify leakage from subsidy, refunds, disputes, chargebacks, and delivery failure.
- Compare intervention assumptions through deterministic scenarios and Monte Carlo ranges.
- Block publication when governed KPI, schema, reconciliation, or narrative checks fail.

## Data Scope

The committed dataset is synthetic and deterministic. It covers **March 2024 to February 2026** and contains:

| Entity | Rows |
|---|---:|
| Orders | 156,121 |
| Order items | 226,097 |
| Sellers | 1,200 |
| Buyers | 9,000 |
| Products | 20,326 |
| Refund events | 27,835 |
| Dispute events | 22,146 |

Synthetic event probabilities vary by seller quality, category, region, channel, payment method, subsidy use, and delivery performance. Current economics assume one seller per order; the validation gate blocks publication if that grain changes.

## Analytical Pipeline

```text
synthetic raw data
  -> analytical feature layer
  -> order and seller scoring
  -> governance action register
  -> deterministic scenarios + Monte Carlo ranges
  -> retrospective threshold policy simulation
  -> governed KPIs, validation, dashboard, charts, and PDF report
```

Key design decisions:

- Historical buyer and seller risk inputs exclude current-order outcomes.
- Contribution margin is a conservative gross-leakage proxy, not accounting P&L.
- Scores are interpretable 0-100 indices with drivers and recommended actions, not calibrated probabilities.
- Threshold economics are retrospective and in-sample; deployment requires later-period holdout validation.
- Scenarios are assumption-driven stress tests, not forecasts or causal estimates.

See [methodology](docs/methodology.md) and the [data dictionary](docs/data_dictionary.md) for definitions, joins, grains, and limitations.

## Published Outputs

| Output | Purpose |
|---|---|
| [Live dashboard](https://mfidalgomartins.github.io/marketplace-profitability-risk-command-center/) | Interactive executive review surface |
| [Analytical PDF report](outputs/reports/marketplace-command-center-report.pdf) | Board-style narrative, evidence, and action priorities |
| [`outputs/graphs/`](outputs/graphs/) | Publication chart pack |
| [`data/processed/governance_action_register.csv`](data/processed/governance_action_register.csv) | Seller and order intervention queue |
| [`data/processed/scenario_decision_matrix.csv`](data/processed/scenario_decision_matrix.csv) | Scenario trade-off ranking |
| [`reports/validation_report.md`](reports/validation_report.md) | Release readiness and validation coverage |

## Run Locally

Requires Python 3.12+.

```bash
make setup
make all
make test
```

`make all` regenerates the raw and processed data, governed reports, dashboard, publication charts, PDF report, and GitHub Pages staging files.

Run the same pipeline in Docker:

```bash
docker build -t marketplace-command-center .
docker run --rm -v "$PWD:/app" marketplace-command-center
```

## Repository Structure

```text
config/contracts/   governed metric and schema contracts
data/raw/           deterministic synthetic source tables
data/processed/     analytical, scoring, scenario, and action outputs
docs/               methodology, data dictionary, and executive framing
outputs/dashboard/  standalone interactive dashboard
outputs/graphs/     publication chart pack
outputs/reports/    analytical PDF report
reports/            KPI snapshots and validation evidence
src/                pipeline, feature, scoring, scenario, and publishing code
tests/              analytical, governance, release-gate, and publishing tests
```

## Validation And Limits

The current release passes the configured technical and analytical gates with state `decision-support only`. The validation layer checks key uniqueness, joins, reconciliations, metric contracts, scenario arithmetic, directional score separation, dashboard feeds, and narrative overclaiming.

The outputs are suitable for demonstrating an analytics operating model and reviewing implementation choices. They are **not** suitable for financial reporting, production fraud decisions, seller enforcement, forecasting, or causal inference without real data, calibrated models, and external validation.

## License

[MIT](LICENSE)
