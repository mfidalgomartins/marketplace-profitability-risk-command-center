# Release Readiness Governance

## Purpose
This project enforces a release-state gate so outputs are not treated as committee-grade by default when only technical checks pass.

Primary artifact:
- `reports/validation_release_assessment.csv`
- `reports/metric_governance_issues.csv`

## Classification States
- `technically valid`
- `analytically acceptable`
- `decision-support only`
- `screening-grade only`
- `not committee-grade`
- `publish-blocked`

## Blocker Rules
`publish-blocked` is triggered by:
- any `Critical` issue
- any `High` issue in blocker modules:
  - `metrics_logic`
  - `scoring`
  - `scenarios`
  - `schema_contracts`
  - `dashboard_feeds`
- any `High` issue in blocker checks:
  - order-item reconciliation
  - realized margin consistency
  - join inflation at order grain
  - scenario arithmetic reconciliation
  - required dashboard feed existence/schema
  - governed executive snapshot feed and metric alignment

## Decision Standard
- `technically valid` does not imply decision-grade quality.
- `committee_grade_ready=true` requires:
  - no high/critical issues
  - no medium issues
  - low issue burden
  - high module confidence floor

## Release Discipline
Before publishing conclusions or dashboard snapshots:
1. Run `src/validation/run_full_validation.py`.
2. Confirm `release_state != publish-blocked`.
3. Confirm committee context required by audience:
   - Leadership workshop: `decision-support only` or better.
   - Executive committee: `committee_grade_ready=true`.
4. Enforce gate in automation/CI:
   - `src/validation/enforce_release_gate.py --required-state "decision-support only"`
   - optionally add `--require-committee-grade` for strict approvals.
