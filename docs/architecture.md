# Architecture

## System boundary

The repository has two deliberate runtime surfaces:

1. A deterministic batch pipeline that generates synthetic sources, governed analytical outputs, a local DuckDB catalog, validation evidence, and publication artifacts.
2. A case-management API that persists operational decisions in SQLite for local/single-instance use.

The static dashboard remains self-contained and does not call the API. This preserves its existing presentation and makes the publication artifact deployable to GitHub Pages without a backend.

No pipeline step calls an external service. All network-facing behavior is opt-in through the API process.

## Execution flow

```text
synthetic source tables
  -> point-in-time feature layer
  -> order and seller heuristic scores
  -> temporal probability calibration
       development -> maturation gap -> matured holdout -> unmatured shadow
  -> governed order P&L and double-entry journals
  -> synthetic randomized intervention analysis
  -> governance register, scenarios, Monte Carlo, and threshold backtest
  -> DuckDB raw/analytics views and curated marts
  -> KPI snapshot, schema drift, formal validation, and release gate
  -> dashboard, chart pack, analytical PDF, tagged PDF/UA, and Pages staging
```

The warehouse synchronizes after all analytical outputs exist. Schema and formal validation then examine the complete release. Public-facing artifacts are staged only after the release gate passes.

## Component responsibilities

| Component | Responsibility | Primary output |
|---|---|---|
| `src/data_generation/` | Deterministic marketplace simulation | `data/raw/*.csv` |
| `src/features/` | Order economics and matured entity history | Core processed features |
| `src/scoring/` | Leakage-safe heuristic order/seller indices | Scorecards and priority subsets |
| `src/model_validation/` | Calibration, temporal holdout, drift, alerts, model release status | Model-governance tables |
| `src/finance/` | Order subledger, double-entry journals, reconciliation | Accounting tables |
| `src/experimentation/` | Deterministic randomization, ITT, clustered inference, power | Experiment evidence |
| `src/governance/` | Ownership, SLA, and action routing | Governance action register |
| `src/scenario_analysis/` | Deterministic and stochastic stress testing | Scenario decision tables |
| `src/backtesting/` | Retrospective threshold economics | Review-capacity policy input |
| `src/warehouse/` | Idempotent DuckDB catalog and curated marts | Local DuckDB + warehouse reports |
| `src/api/` | Authenticated, auditable case workflow | SQLite operational state |
| `src/validation/` | Schema, metric, integrity, narrative, and release controls | `reports/` |
| `src/dashboard/` | Standalone HTML and Pages staging | Dashboard HTML |
| `src/visualization/` | Chart pack, analytical PDF, and tagged PDF/UA | Publication artifacts |

## Governed contracts

| Contract | Controls |
|---|---|
| `schema_contracts.json` | Columns, inferred types, keys, nullability, uniqueness, row-count constraints |
| `metric_governance_contract.csv` | Official KPI definitions, grains, formulas, and source ownership |
| `model_monitoring_policy.json` | Maturation lag, split sizes, calibration bins, shadow window, release thresholds |
| `finance_policy.json` | Account map and synthetic revenue/loss recognition assumptions |
| `experiment_policy.json` | Eligibility, allocation, MDE, power, review cost, and synthetic efficacy |

Normal runs treat contracts as immutable input. Only `make update-schema-contracts` can re-baseline the schema contract.

## Data grains

- Raw and analytical order tables: one row per `order_id`.
- Accounting subledger: one row per `order_id`; general ledger: one row per journal line.
- Seller scorecards: one row per `seller_id`; quality history: one row per `(seller_id, month)`.
- Model monitoring: one row per month; calibration curve: one row per `(split, calibration_bin)`.
- Experiment assignments: one row per eligible `order_id`; results: one row per `(experiment_id, metric)`.
- Governance actions: one row per `(entity_type, entity_id)`.
- Case state: one row per case; events and audit entries are append-only.

The batch release still assumes one seller per order. Supporting multi-seller baskets requires governed allocation at seller-order-item grain before finance, scoring, and case routing can remain coherent.

## Temporal model semantics

The 60-day maturation lag is applied twice:

- Historical score features include an entity’s outcome only after that outcome can be considered mature.
- Calibration training stops 60 days before holdout entry. The most recent 60 days are shadow-scored but excluded from outcome performance.

This yields four explicit populations: `development`, `maturation_gap`, `holdout`, and `shadow_unmatured`. The release table can recommend a shadow run but can never approve automated decisions.

## Finance semantics

Order amounts are rounded to cents before aggregation. Monthly journals post equal debit and credit lines. Release validation requires both:

- total debits equal total credits;
- general-ledger contribution equals the order subledger contribution within one cent.

The account map is a synthetic management-accounting policy, not GAAP/IFRS certification.

## Warehouse semantics

DuckDB stores source metadata and curated marts. Raw and analytical schemas are views over versioned CSV artifacts; this avoids duplicating the full 100+ MB release. Curated seller, finance, model-monitoring, and experiment marts are materialized, while the order decision mart remains a one-to-one view.

Each source is fingerprinted with SHA-256. A deterministic aggregate release id makes synchronization idempotent: unchanged sources do not rebuild the catalog. The database itself is a local runtime artifact; the manifest and validation evidence are versioned.

## API trust boundaries

```text
client
  -> trusted-host and request-size checks
  -> bearer-token digest verification
  -> role permission
  -> Pydantic request contract
  -> idempotency and optimistic-concurrency checks
  -> transactional case update + immutable event + HMAC audit entry
  -> security-header response
```

Writes fail closed when the audit key is absent or too short. Managers/admins are the only roles allowed to close pending cases. The SQLite schema prevents updates or deletes to event/audit tables.

## Failure semantics

Pipeline commands run sequentially with `check=True`; any error stops the run. Schema violations fail before publication. Formal validation converts findings into blocker/warning classes, and the release gate rejects insufficient release states.

Generated files before a failed gate are build outputs, not approved artifacts. The case API uses a transaction per command, so case state, event history, audit chain, and idempotency record commit together or roll back together.

## Reproducibility

- Data, Monte Carlo, sampling, assignment, and synthetic prevention use fixed seeds or stable hashes.
- Historical scores use fixed priors, a fixed order-value reference, and matured-only history.
- Generated text/HTML uses source dates instead of wall-clock timestamps.
- Both PDFs use stable metadata; the accessible summary uses a content-derived PDF identifier.
- DuckDB source release ids derive from ordered SHA-256 fingerprints.
- CI rebuilds governed artifacts and compares them with Git.

## Production scale path

The implemented boundaries are designed for replacement without changing business contracts:

- Move CSV views to partitioned Parquet or managed warehouse tables.
- Run the same ordered steps in Airflow, Dagster, or a cloud scheduler with persisted run metadata.
- Replace SQLite with managed PostgreSQL and apply the existing migration/transaction semantics.
- Replace local bearer provisioning with OIDC/JWT verification and centralized policy.
- Add real prospective shadow data, controller-approved accounting rules, and a pre-registered live experiment.
- Route alerts, audit anomalies, and case SLA breaches into operational monitoring.
