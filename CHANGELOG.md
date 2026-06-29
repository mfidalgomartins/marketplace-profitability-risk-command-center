# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `pyproject.toml` centralising `ruff`, `mypy`, `pytest`, `coverage`, and
  `bandit` configuration.
- `requirements-dev.txt` separating tooling from runtime dependencies.
- Developer docs: `CONTRIBUTING.md`, `SECURITY.md`, and this changelog.
- `.pre-commit-config.yaml` running the full quality gate on commit.
- In-process unit tests for the pipeline step builder, release-gate parsing,
  validation engine helpers, schema-contract/governance/snapshot builders, and
  schema-drift reporting.
- `tests/test_pipeline_integration.py`: an in-process end-to-end run of the
  analytical chain on a small synthetic dataset.
- `make` targets: `lint`, `format`, `format-check`, `typecheck`, `security`,
  `audit`, and `verify`.
- CI now runs lint, format, type, and security gates alongside the existing
  pipeline rebuild and tests, with an enforced coverage floor.
- CLI/edge-case tests for the GitHub Pages publisher, release-gate runner,
  schema-contract validator/generator, and the full-validation report writer.
- Unit tests for the score-policy backtesting decision logic (config
  validation, threshold curve, recommended-policy selection) and for the
  metric-governance validator's failure branches and CLI.
- `prefers-reduced-motion` support on the dashboard and the Pages landing page
  so animations/transitions respect the OS Reduce Motion setting (accessibility).

### Changed
- Refactored `src/pipeline/run_full_pipeline.py` into a testable
  `build_pipeline_steps` / `build_parser` structure that runs from any working
  directory.
- Test coverage raised from ~30% to ~89% (measured across the full `src` tree),
  enforced by an `--cov-fail-under=85` floor.
- Elevated the executive dashboard to an Apple-grade finish (SF system type,
  `#f5f5f7` canvas, larger tokenised radii, soft ambient elevation, pill
  controls, frosted sticky nav, smoother motion).
- Redesigned the GitHub Pages landing/redirect page to match the dashboard's
  design language (removing the old gradient/glass/serif treatment) and added
  light/dark support.

### Fixed
- The pipeline accepted `--required-release-state` values
  (`analytically acceptable`, `technically valid`) that the release gate did not
  understand, which would crash the gate step. The pipeline now derives its
  valid states from the gate's `STATE_ORDER`, making the gate the single source
  of truth.
- Removed unused variables and modernised the codebase to pass a clean
  `ruff check` and `ruff format --check`.
