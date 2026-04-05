# Contributing

## Engineering Standard
- Prioritize correctness over speed.
- Keep metric and scoring logic interpretable.
- Preserve reproducibility (deterministic seeds, explicit assumptions).
- Do not introduce hidden leakage into feature engineering.

## Local Development
1. Create environment:
```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```
2. Generate reproducible artifacts (required on fresh clone):
```bash
make all
```
3. Run tests:
```bash
.venv/bin/pytest -q
```
4. Regenerate governance execution queue only:
```bash
make governance
```
5. Regenerate executive KPI snapshot only:
```bash
make snapshot
```

## Pull Request Expectations
- Explain business impact and analytical trade-offs.
- Include affected modules (data generation, features, scoring, scenarios, dashboard, validation).
- Add or update tests when logic changes.
- Regenerate validation outputs when data or scoring assumptions change.

## Review Checklist
- [ ] No key duplications introduced in order/seller/buyer grain tables.
- [ ] Reconciliation checks still pass (order-level vs item-level totals).
- [ ] Tier mappings remain consistent with score boundaries.
- [ ] Governance action register is regenerated and owner/SLA fields are populated.
- [ ] Scenario arithmetic reconciles.
- [ ] Dashboard feed schemas remain backward-compatible.
