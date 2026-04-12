# Marketplace Project Validation Report

## QA Stance
Skeptical validation pass focused on reconciliation, coherence, leakage controls, and decision-risk overclaiming.

## Executive Summary
- Orders validated: `156,121`
- Sellers validated: `1,200`
- Buyers validated: `9,000`
- Issue count: `Critical=0`, `High=0`, `Medium=0`, `Low=0`
- Release state: `technically valid`
- Release gates: `publish_blocked=False`, `committee_grade_ready=True`, `min_module_confidence=98.0`

## Release Readiness Classification
Validation now enforces explicit release states to prevent false confidence between technical validity and committee-grade readiness.
- `technical_gate_passed`: `True`
- `analytical_gate_passed`: `True`
- `technically valid`: `True`
- `analytically acceptable`: `False`
- `decision-support only`: `False`
- `screening-grade only`: `False`
- `not committee-grade`: `False`
- `publish-blocked`: `False`
- Rationale: No detected validation issues across configured checks.

## Issues Ranked by Severity
- No issues detected by the configured validation checks.

## Fixes Applied During This QA Cycle
- Patched synthetic generator to enforce `promised_days >= processing_days + 1`, preventing shipped-after-delivered artifacts in future regenerations.
- Constrained refund/dispute/chargeback overlap in synthetic post-order events to reduce artificial leakage double-counting.
- Added reproducible full-validation runner and structured issue log output.

## Unresolved Caveats
- None.

## Confidence by Module
- `synthetic_data`: `98.0/100` (`High`)
- `processed_features`: `98.0/100` (`High`)
- `metrics_logic`: `98.0/100` (`High`)
- `metric_governance`: `98.0/100` (`High`)
- `scoring`: `98.0/100` (`High`)
- `scenarios`: `98.0/100` (`High`)
- `schema_contracts`: `98.0/100` (`High`)
- `dashboard_feeds`: `98.0/100` (`High`)
- `narrative`: `98.0/100` (`High`)

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

