# Case Management API

## Purpose

The API turns governed seller and order signals into a controlled case workflow. It is independent of the static dashboard and does not change its front-end or publication path.

The bundled SQLite store supports local demonstration and a single application instance. A multi-instance deployment should retain the API contracts and move the migration to a managed transactional database.

## Security model

- Bearer tokens are stored only as SHA-256 digests in configuration.
- Authentication and authorization are deny-by-default.
- Roles are `viewer`, `analyst`, `manager`, and `admin`.
- Every write requires a UUID command id and is idempotent.
- Updates require the current case version and reject stale writes.
- Cases can only close from `pending_approval`, through a manager/admin approval decision.
- Case events and audit records are append-only at the database layer.
- Audit records form an HMAC-SHA-256 chain; admins can verify it through the API.
- Production API documentation is disabled. Development mode may expose `/docs`.

## Local configuration

Generate a local token, configure only its digest, and create an independent audit key:

```bash
export CASE_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export CASE_API_TOKEN_SHA256="$(printf %s "$CASE_API_TOKEN" | shasum -a 256 | awk '{print $1}')"
export CASE_API_TOKENS_JSON="$(python -c 'import json, os; print(json.dumps({"local-admin": {"subject": "local-admin", "role": "admin", "sha256": os.environ["CASE_API_TOKEN_SHA256"]}}))')"
export CASE_API_AUDIT_HMAC_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
make api
```

Verify readiness without authentication:

```bash
curl http://127.0.0.1:8000/health/ready
```

List cases:

```bash
curl -H "Authorization: Bearer $CASE_API_TOKEN" \
  http://127.0.0.1:8000/v1/cases
```

## Configuration reference

| Variable | Required | Purpose |
|---|---:|---|
| `CASE_API_TOKENS_JSON` | Protected routes | Object keyed by token id, with `subject`, `role`, and 64-character SHA-256 digest |
| `CASE_API_AUDIT_HMAC_KEY` | Writes and audit verification | Secret of at least 32 bytes; configure through a secret manager in deployment |
| `CASE_DB_PATH` | No | SQLite path; defaults to `outputs/runtime/case_management.sqlite3` |
| `CASE_API_TRUSTED_HOSTS` | No | Comma-separated host allowlist |
| `CASE_API_MAX_REQUEST_BYTES` | No | Request-body limit; defaults to 65,536 bytes |
| `CASE_API_REQUIRE_HTTPS` | No | Set to `1` when TLS is terminated by the application |
| `CASE_API_ENV` | No | Set to `development` only when local OpenAPI documentation is needed |

No default credential, token, or audit key is included in the repository.

## Roles

| Capability | Viewer | Analyst | Manager | Admin |
|---|:---:|:---:|:---:|:---:|
| Read cases and events | Yes | Yes | Yes | Yes |
| Create and update cases | No | Yes | Yes | Yes |
| Approve or reject closure | No | No | Yes | Yes |
| Verify audit chain | No | No | No | Yes |

## Endpoints

| Method and path | Permission | Behavior |
|---|---|---|
| `GET /health/live` | Public | Process liveness |
| `GET /health/ready` | Public | Database readiness |
| `GET /v1/cases` | `cases:read` | Filtered, bounded pagination |
| `GET /v1/cases/{case_id}` | `cases:read` | Current case state |
| `GET /v1/cases/{case_id}/events` | `cases:read` | Immutable case history |
| `POST /v1/cases` | `cases:write` | Create an open case |
| `PATCH /v1/cases/{case_id}` | `cases:write` | Update fields or move to investigation/pending approval |
| `POST /v1/cases/{case_id}/approval` | `cases:approve` | Resolve or reject a pending case |
| `GET /v1/audit/verify` | `audit:verify` | Verify the full HMAC chain |

Pydantic rejects unknown fields. SQL statements use bound parameters, request bodies are bounded, hosts are allowlisted, and responses carry no-store, CSP, referrer, content-type, and frame security headers.

## Deployment boundary

For a real deployment, place the service behind centralized identity, TLS, a network rate limiter, structured security monitoring, managed secrets, and backups. Replace local bearer-token provisioning with the organization’s identity provider and map verified claims to the same permission model.
