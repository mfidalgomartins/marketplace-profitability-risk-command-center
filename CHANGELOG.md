# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Matured temporal validation with logistic calibration, a development/maturation-gap/holdout/shadow split, monthly PSI and calibration monitoring, alerts, and model release gates.
- Governed synthetic management accounts with an order subledger, monthly double-entry ledger, and cent-level reconciliation controls.
- Deterministic randomized intervention analysis with balance, power, intention-to-treat effects, seller-clustered inference, and exploratory heterogeneity.
- Idempotent DuckDB catalog with SHA-256 source releases and curated order, seller, finance, model-monitoring, and experiment marts.
- Secured FastAPI case-management service with RBAC, optimistic concurrency, idempotent commands, approval workflow, immutable events, and HMAC-chained audit verification.
- Tagged PDF/UA executive summary generated from semantic HTML and validated for structure, language, marked content, and PDF/UA metadata.
- Narrow-phone dashboard layout that preserves the existing desktop visual identity.
- Versioned model-monitoring, finance, and experiment policy contracts plus dedicated tests and formal release controls.

### Changed
- Historical buyer and seller outcomes now enter order scoring only after the 60-day maturation lag.
- Pipeline, Make targets, Docker runtime, documentation, schema contracts, validation coverage, CI artifacts, and dependency pins now cover all strategic expansion layers.
- README now leads with a flagship-deliverables section contrasting the interactive dashboard and the analytical PDF report.

## [1.0.0] - 2026-07-14

### Added
- `pyproject.toml` centralising `ruff`, `mypy`, `pytest`, `coverage`, and
  `bandit` configuration.
- `requirements-dev.txt` separating tooling from runtime dependencies.
- Developer docs: `CONTRIBUTING.md`, `SECURITY.md`, and this changelog.
- `.pre-commit-config.yaml` running the full quality gate on commit.
- In-process unit tests for the pipeline step builder, release-gate parsing,
  validation engine helpers, schema-contract/governance/snapshot builders,
  schema-drift reporting, score-policy backtesting decision logic, and the
  metric-governance validator's failure branches and CLI.
- `tests/test_pipeline_integration.py`: an in-process end-to-end run of the
  analytical chain on a small synthetic dataset.
- `make` targets: `lint`, `format`, `format-check`, `typecheck`, `security`,
  `audit`, and `verify`.
- CI now runs lint, format, type, and security gates alongside the existing
  pipeline rebuild and tests, with an enforced coverage floor.
- CLI/edge-case tests for the GitHub Pages publisher, release-gate runner,
  and the schema-contract validator/generator.
- `prefers-reduced-motion` support on the dashboard and the Pages landing page
  so animations/transitions respect the OS Reduce Motion setting (accessibility).
- `assets/fonts/`: PT Serif (SIL OFL), embedded in the PDF report for an
  editorial serif treatment of headlines, body prose, and pull quotes,
  distinct from the sans used for tables, labels, and metric cards.
- Immutable schema-contract validation during normal runs, expanded key/null/
  uniqueness enforcement, deterministic artifact checks, and dependency update
  automation.
- Temporal-integrity tests proving that current outcomes and future orders do
  not change historical order scores.
- `docs/architecture.md` documenting boundaries, grains, release semantics,
  reproducibility, and the production scale-up path.

### Changed
- Refactored `src/pipeline/run_full_pipeline.py` into a testable
  `build_pipeline_steps` / `build_parser` structure that runs from any working
  directory.
- Test coverage raised from ~30% to ~89% (measured across the full `src` tree),
  enforced by an `--cov-fail-under=85` floor.
- Refined dashboard typography, spacing, controls, motion, and mobile header
  behavior while retaining the established information architecture.
- Redesigned the GitHub Pages landing/redirect page to match the dashboard's
  design language (removing the old gradient/glass/serif treatment) and added
  light/dark support.
- Unified the brand palette (accent, ink, muted, good/warn/bad) across the
  dashboard, the matplotlib chart pack, and the PDF report to one canonical
  set of hex values, so all three read as one product instead of three
  near-matches.
- Retypeset the PDF report with PT Serif for narrative prose and sans-serif
  typography for tables, labels, and metric cards.
- Fixed score smoothing and order-value transforms so they no longer depend on
  full-sample outcomes or future records.
- Made governed Markdown, dashboard HTML, and PDF builds deterministic.
- Escaped embedded dashboard JSON and data-backed DOM strings without changing
  the dashboard design.

### Fixed
- The pipeline accepted `--required-release-state` values
  (`analytically acceptable`, `technically valid`) that the release gate did not
  understand, which would crash the gate step. The pipeline now derives its
  valid states from the gate's `STATE_ORDER`, making the gate the single source
  of truth.
- `generate_schema_contracts.py`'s datetime-column detection was dead code
  under pandas 3.0 (`read_csv` now returns the new `str` dtype, not `object`),
  so date columns were mistyped as `"string"`. Fixed detection and made the
  schema-contract validator null-tolerant for datetime columns with legitimate
  gaps; re-baselined the schema history snapshot so drift stays clean.
- Replaced hardcoded PDF probability and period-scope claims with governed
  scenario values.
- Corrected PDF and chart labeling, spacing, pagination, acronym casing, and
  numeric-column alignment after a 32-page visual review.
- Removed unused variables and modernised the codebase to pass a clean
  `ruff check` and `ruff format --check`.
