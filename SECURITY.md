# Security Policy

## Data and secret scope

All committed marketplace records are synthetic and deterministic. The repository contains no real buyers, sellers, payment instruments, credentials, bearer tokens, or audit keys.

The batch pipeline is local and makes no external service calls. The optional case-management API is the only network-facing runtime and starts in fail-closed mode when credentials or the audit key are absent.

## Dashboard boundary

The standalone dashboard treats embedded records as untrusted at the HTML boundary:

- JSON is escaped before insertion into the script element.
- Data-backed strings are escaped before DOM rendering.
- The artifact has no authentication or write path and is intended for synthetic publication only.

## API controls

- Bearer tokens are configured as SHA-256 digests; plaintext tokens are never stored by the application.
- RBAC denies permissions not explicitly granted to `viewer`, `analyst`, `manager`, or `admin`.
- Unknown request fields are rejected and SQL uses bound parameters.
- Trusted-host checks, bounded request bodies, optional HTTPS redirect, and restrictive response headers reduce web attack surface.
- Every write requires an idempotent UUID command and an expected case version.
- Case closure requires manager/admin approval from `pending_approval`.
- Case events and audit records are append-only through SQLite triggers.
- Audit entries are chained with HMAC-SHA-256 and can be verified by an admin.
- Production OpenAPI endpoints are disabled.

The API deliberately does not implement application-local password storage, permissive CORS, or default credentials.

## Deployment requirements

Before any non-local deployment:

- use managed secret storage and rotate token/audit material;
- terminate TLS and configure an exact trusted-host allowlist;
- place a distributed rate limiter and centralized identity provider in front of the API;
- move SQLite state to a managed transactional database for multi-instance service;
- enable structured security logs, alerting, backups, and restore tests;
- avoid embedding real order/seller records in the public dashboard.

See [docs/api.md](docs/api.md) for the operating contract.

## Automated checks

- `bandit` scans `src/` for Python security issues.
- `pip-audit` checks the pinned runtime dependency graph for known vulnerabilities.
- `ruff`, `mypy`, compilation, and tests catch unsafe or inconsistent changes.
- Dependabot monitors Python and GitHub Actions dependencies.
- GitHub Actions are pinned to immutable commit SHAs.
- CI rebuilds governed artifacts and checks them against Git.

Run the complete gate with `make verify`.

## Analytical safety

The outputs are not approved for financial reporting, production fraud decisions, seller enforcement, or causal inference. Model release status and experiment outputs explicitly preserve this boundary.

## Reporting a vulnerability

Open a GitHub security report or contact the maintainer privately when a report contains sensitive details. Include affected files, impact, and reproducible steps where possible.
