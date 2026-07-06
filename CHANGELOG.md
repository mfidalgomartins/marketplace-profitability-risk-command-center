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

### Changed
- Refactored `src/pipeline/run_full_pipeline.py` into a testable
  `build_pipeline_steps` / `build_parser` structure that runs from any working
  directory.
- Test coverage raised from ~30% to ~89% (measured across the full `src` tree),
  enforced by an `--cov-fail-under=85` floor.
- Elevated the executive dashboard to an Apple-grade finish (SF system type,
  `#f5f5f7` canvas, larger tokenised radii, soft ambient elevation, pill
  controls, frosted sticky nav, smoother motion) and stopped pinning the full
  header on mobile viewports, where it previously ate ~45% of the screen.
- Redesigned the GitHub Pages landing/redirect page to match the dashboard's
  design language (removing the old gradient/glass/serif treatment) and added
  light/dark support.
- Unified the brand palette (accent, ink, muted, good/warn/bad) across the
  dashboard, the matplotlib chart pack, and the PDF report to one canonical
  set of hex values, so all three read as one product instead of three
  near-matches.
- Retypeset the PDF report with a mixed serif/sans system (PT Serif for
  narrative prose, sans for tables and data chrome) after a full page-by-page
  audit against Big Four presentation standards.

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
- PDF report: three places asserted "probability of a positive contribution
  margin is 0.0%" as a hardcoded literal rather than reading the real
  `prob_cm_positive` column, and the scenario section's dollar figures (a
  6-month window) sat next to the 24-month headline figures with no scope
  disclosure. Both now derive from governed data.
- PDF report: a waterfall chart's total-bar label overlapped the axis tick
  labels below it; a chart headline stated precision (41.8%) under the word
  "captures", which describes recall (31.3%); two charts showed unitless axis
  ticks next to per-bar labels already in percent; pull-quote callouts had no
  vertical spacing and read as run-in text; two paragraphs left a stranded
  single word/line (a widow) at the top of a page; appendix metric labels ran
  through `str.title()` producing "Gmv" and "Top10 Seller Gmv Share"; and
  numeric table headers were left-aligned over right-aligned data. All fixed
  after a full 32-page visual audit.
- Removed unused variables and modernised the codebase to pass a clean
  `ruff check` and `ruff format --check`.
