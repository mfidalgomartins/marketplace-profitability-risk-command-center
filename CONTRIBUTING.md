# Contributing

Thanks for taking the time to work on this project. This guide covers local
setup, the quality gates, and how to make a change land cleanly.

## Development setup

Requires Python 3.12+.

```bash
make setup            # create .venv and install runtime + dev dependencies
pre-commit install    # optional: run the quality gates on every commit
```

`make setup` installs `requirements-dev.txt`, which pulls in the runtime
dependencies plus the tooling (`pytest`, `pytest-cov`, `ruff`, `mypy`,
`bandit`, `pip-audit`).

## Quality gates

Every change must pass the same gate CI enforces. Run it all with one command:

```bash
make verify
```

That runs, in order:

| Gate | Command | What it checks |
|---|---|---|
| Lint | `make lint` (`ruff check`) | style, imports, bugbear, modernity |
| Format | `make format-check` (`ruff format --check`) | consistent formatting |
| Types | `make typecheck` (`mypy`) | static types across `src/` |
| Security | `make security` (`bandit` + `pip-audit`) | code issues and dependency CVEs |
| Tests | `make test` (`pytest`) | unit + integration, with a coverage floor |

Auto-fix formatting and lint before committing:

```bash
make format    # ruff format + ruff check --fix
```

## Tests and coverage

- The suite mixes fast in-process unit tests with an in-process integration
  test (`tests/test_pipeline_integration.py`) that runs the whole analytical
  chain on a small synthetic dataset.
- Coverage is gated at a floor configured in `pyproject.toml`
  (`--cov-fail-under`). New logic should ship with tests that keep coverage at
  or above the floor.
- Keep tests deterministic: pass explicit seeds and write to `tmp_path`.

## Conventions

- Code is formatted and linted by `ruff` (config in `pyproject.toml`); do not
  hand-format around it.
- Prefer pure, importable builder functions (`build_*`, `run_*`) with a small
  `Config` dataclass, mirroring the existing modules — it keeps the pipeline
  testable in-process.
- The release gate in `src/validation/enforce_release_gate.py` is the single
  source of truth for valid release states; reuse `STATE_ORDER` rather than
  re-listing states.

## Making a change

1. Branch off `main`.
2. Implement the change with tests.
3. Run `make verify` until green.
4. Open a pull request; CI runs the full pipeline plus the gates above.
