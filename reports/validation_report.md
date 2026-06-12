# Marketplace Project Validation Report

## QA Stance
Skeptical validation pass focused on reconciliation, coherence, leakage controls, and decision-risk overclaiming.

## Executive Summary
- Orders validated: `156,121`
- Sellers validated: `1,200`
- Buyers validated: `9,000`
- Issue count: `Critical=0`, `High=0`, `Medium=0`, `Low=0`
- Release state: `decision-support only`
- Release gates: `publish_blocked=False`, `public_release_ready=True`, `committee_grade_ready=False`

## Release Readiness Classification
Release states are governance labels for this project and do not imply external certification.
- `technical_gate_passed`: `True`
- `analytical_checks_passed`: `True`
- `public_release_ready`: `True`
- `decision-support only`: `True`
- `not committee-grade`: `True`
- `publish-blocked`: `False`
- Rationale: Configured technical and analytical checks pass. Synthetic data, heuristic scores, proxy economics, and assumption-driven scenarios limit use to decision support.

## Issues Ranked by Severity
- No issues detected within the configured validation checks in this run.

## Known Limitations
- All data is synthetic; findings demonstrate analytical workflow behavior, not real marketplace performance.
- Risk and governance scores are interpretable heuristic indices, not calibrated probabilities or causal estimates.
- The threshold policy evaluation is retrospective and in-sample; it requires later-period holdout validation before deployment.
- Scenario outputs are assumption-driven stress tests, not forecasts.
- Realized contribution margin is a conservative gross-leakage proxy; expected margin after risk is a pre-outcome underwriting proxy and is not directly comparable.

## Validation Coverage by Module
- `synthetic_data`: checks=`8`, open_issues=`0`, status=`passed`
- `processed_features`: checks=`6`, open_issues=`0`, status=`passed`
- `metrics_logic`: checks=`6`, open_issues=`0`, status=`passed`
- `metric_governance`: checks=`5`, open_issues=`0`, status=`passed`
- `scoring`: checks=`3`, open_issues=`0`, status=`passed`
- `scenarios`: checks=`4`, open_issues=`0`, status=`passed`
- `schema_contracts`: checks=`1`, open_issues=`0`, status=`passed`
- `dashboard_feeds`: checks=`3`, open_issues=`0`, status=`passed`
- `narrative`: checks=`1`, open_issues=`0`, status=`passed`

## Validation Scope Checklist
- row count sanity
- duplicates
- null issues
- impossible values
- date consistency
- order-item reconciliation
- refund/dispute/payment coherence
- subsidy logic coherence
- margin logic consistency
- denominator correctness
- join inflation risk
- leakage risk
- tier assignment correctness
- scenario arithmetic
- narrative overclaiming risk
- metric governance contracts and recomputation

