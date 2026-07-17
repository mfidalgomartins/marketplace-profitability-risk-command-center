from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.api.database import CaseDatabase
from src.api.models import (
    ApprovalDecision,
    AuditVerification,
    CaseCreate,
    CaseList,
    CaseRecord,
    CaseStatus,
    CaseUpdate,
    Priority,
    Role,
)
from src.api.security import BearerAuthenticator, Principal, TokenRecord, parse_token_records

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
GENESIS_AUDIT_HASH = "0" * 64
CASE_SELECT_SQL = (
    "SELECT case_id, entity_type, entity_id, priority, status, owner, "
    "recommended_action, decision_rationale, version, created_at, updated_at, "
    "created_by, updated_by FROM cases"
)
CASE_BY_ID_SQL = CASE_SELECT_SQL + " WHERE case_id = ?"
CASE_LIST_SQL = CASE_SELECT_SQL + " ORDER BY updated_at DESC, case_id LIMIT ? OFFSET ?"
CASE_LIST_BY_STATUS_SQL = CASE_SELECT_SQL + " WHERE status = ? ORDER BY updated_at DESC, case_id LIMIT ? OFFSET ?"
CASE_LIST_BY_PRIORITY_SQL = CASE_SELECT_SQL + " WHERE priority = ? ORDER BY updated_at DESC, case_id LIMIT ? OFFSET ?"
CASE_LIST_BY_STATUS_PRIORITY_SQL = (
    CASE_SELECT_SQL + " WHERE status = ? AND priority = ? ORDER BY updated_at DESC, case_id LIMIT ? OFFSET ?"
)


@dataclass(frozen=True)
class ApiSettings:
    database_path: Path
    token_records: tuple[TokenRecord, ...]
    audit_hmac_key: bytes
    environment: str = "production"
    trusted_hosts: tuple[str, ...] = ("localhost", "127.0.0.1", "testserver")
    max_request_bytes: int = 65_536
    require_https: bool = False

    @classmethod
    def from_environment(cls) -> ApiSettings:
        environment = os.getenv("CASE_API_ENV", "production").strip().lower()
        trusted_hosts = tuple(
            host.strip()
            for host in os.getenv("CASE_API_TRUSTED_HOSTS", "localhost,127.0.0.1,testserver").split(",")
            if host.strip()
        )
        max_request_bytes = int(os.getenv("CASE_API_MAX_REQUEST_BYTES", "65536"))
        if max_request_bytes <= 0:
            raise ValueError("CASE_API_MAX_REQUEST_BYTES must be positive.")
        return cls(
            database_path=Path(os.getenv("CASE_DB_PATH", "outputs/runtime/case_management.sqlite3")),
            token_records=parse_token_records(os.getenv("CASE_API_TOKENS_JSON", "")),
            audit_hmac_key=os.getenv("CASE_API_AUDIT_HMAC_KEY", "").encode("utf-8"),
            environment=environment,
            trusted_hosts=trusted_hosts,
            max_request_bytes=max_request_bytes,
            require_https=os.getenv("CASE_API_REQUIRE_HTTPS", "0") == "1",
        )


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers", []))
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._reject(scope, receive, send)
                return

        messages: list[Message] = []
        total = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    await self._reject(scope, receive, send)
                    return
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                break

        async def replay() -> Message:
            if messages:
                return messages.pop(0)
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            content={"detail": "Request body exceeds the configured limit."},
        )
        await response(scope, receive, send)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _request_hash(payload: object) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _case_from_row(row: sqlite3.Row) -> CaseRecord:
    return CaseRecord.model_validate(dict(row))


def _ensure_write_ready(settings: ApiSettings) -> None:
    if len(settings.audit_hmac_key) < 32:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Write operations are disabled until a strong audit HMAC key is configured.",
        )


def _load_idempotent_response(
    connection: sqlite3.Connection,
    command_id: str,
    principal: Principal,
    route: str,
    request_sha256: str,
) -> dict[str, object] | None:
    row = connection.execute(
        "SELECT actor_id, route, request_sha256, response_json FROM case_commands WHERE command_id = ?",
        (command_id,),
    ).fetchone()
    if row is None:
        return None
    if row["actor_id"] != principal.subject or row["route"] != route or row["request_sha256"] != request_sha256:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Command id has already been used for a different request.",
        )
    loaded = json.loads(row["response_json"])
    if not isinstance(loaded, dict):
        raise RuntimeError("Stored idempotent response is invalid.")
    return loaded


def _store_command(
    connection: sqlite3.Connection,
    command_id: str,
    principal: Principal,
    route: str,
    request_sha256: str,
    response: dict[str, object],
    created_at: str,
) -> None:
    connection.execute(
        "INSERT INTO case_commands "
        "(command_id, actor_id, route, request_sha256, response_json, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            command_id,
            principal.subject,
            route,
            request_sha256,
            _canonical_json(response),
            created_at,
        ),
    )


def _append_case_event(
    connection: sqlite3.Connection,
    case_id: str,
    event_type: str,
    from_status: str | None,
    to_status: str,
    principal: Principal,
    event_at: str,
    details: Mapping[str, object],
) -> None:
    connection.execute(
        "INSERT INTO case_events "
        "(case_id, event_type, from_status, to_status, actor_id, actor_role, event_at, details_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            case_id,
            event_type,
            from_status,
            to_status,
            principal.subject,
            principal.role,
            event_at,
            _canonical_json(details),
        ),
    )


def _audit_payload(
    event_type: str,
    case_id: str | None,
    principal: Principal,
    event_at: str,
    details: Mapping[str, object],
    previous_hash: str,
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "case_id": case_id,
        "actor_id": principal.subject,
        "actor_role": principal.role,
        "event_at": event_at,
        "details": details,
        "previous_hash": previous_hash,
    }


def _append_audit(
    connection: sqlite3.Connection,
    settings: ApiSettings,
    principal: Principal,
    event_type: str,
    case_id: str | None,
    event_at: str,
    details: Mapping[str, object],
) -> None:
    row = connection.execute("SELECT audit_hash FROM audit_log ORDER BY audit_id DESC LIMIT 1").fetchone()
    previous_hash = str(row["audit_hash"]) if row else GENESIS_AUDIT_HASH
    payload = _audit_payload(event_type, case_id, principal, event_at, details, previous_hash)
    audit_hash = hmac.new(
        settings.audit_hmac_key,
        _canonical_json(payload).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    connection.execute(
        "INSERT INTO audit_log "
        "(event_type, case_id, actor_id, actor_role, event_at, details_json, previous_hash, audit_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event_type,
            case_id,
            principal.subject,
            principal.role,
            event_at,
            _canonical_json(details),
            previous_hash,
            audit_hash,
        ),
    )


def _verify_audit_chain(connection: sqlite3.Connection, settings: ApiSettings) -> AuditVerification:
    rows = connection.execute("SELECT * FROM audit_log ORDER BY audit_id").fetchall()
    previous_hash = GENESIS_AUDIT_HASH
    for row in rows:
        principal = Principal(
            subject=str(row["actor_id"]),
            role=cast(Role, str(row["actor_role"])),
            token_id=str(row["audit_id"]),
        )
        details = json.loads(row["details_json"])
        payload = _audit_payload(
            str(row["event_type"]),
            str(row["case_id"]) if row["case_id"] is not None else None,
            principal,
            str(row["event_at"]),
            details,
            previous_hash,
        )
        expected = hmac.new(
            settings.audit_hmac_key,
            _canonical_json(payload).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if row["previous_hash"] != previous_hash or not hmac.compare_digest(str(row["audit_hash"]), expected):
            return AuditVerification(
                verified=False,
                entry_count=len(rows),
                first_invalid_audit_id=int(row["audit_id"]),
            )
        previous_hash = str(row["audit_hash"])
    return AuditVerification(verified=True, entry_count=len(rows))


def _fetch_case(connection: sqlite3.Connection, case_id: str) -> CaseRecord:
    row = connection.execute(CASE_BY_ID_SQL, (case_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found.")
    return _case_from_row(row)


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    resolved = settings or ApiSettings.from_environment()
    database = CaseDatabase(resolved.database_path, MIGRATIONS_DIR)
    authenticator = BearerAuthenticator(resolved.token_records)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        database.migrate()
        yield

    docs_enabled = resolved.environment == "development"
    application = FastAPI(
        title="Marketplace Case Management API",
        version="1.0.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )
    application.add_middleware(RequestSizeLimitMiddleware, max_bytes=resolved.max_request_bytes)
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=list(resolved.trusted_hosts))
    if resolved.require_https:
        application.add_middleware(HTTPSRedirectMiddleware)

    @application.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    read_cases = authenticator.require("cases:read")
    write_cases = authenticator.require("cases:write")
    approve_cases = authenticator.require("cases:approve")
    verify_audit = authenticator.require("audit:verify")

    @application.get("/health/live")
    async def live() -> dict[str, str]:
        return {"status": "live"}

    @application.get("/health/ready")
    async def ready() -> dict[str, str]:
        try:
            with database.session() as connection:
                connection.execute("SELECT 1").fetchone()
        except sqlite3.Error as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Case database is unavailable.",
            ) from exc
        return {"status": "ready"}

    @application.get("/v1/cases", response_model=CaseList)
    async def list_cases(
        case_status: CaseStatus | None = Query(default=None, alias="status"),
        priority: Priority | None = None,
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        _: Principal = Depends(read_cases),
    ) -> CaseList:
        if case_status is not None and priority is not None:
            query = CASE_LIST_BY_STATUS_PRIORITY_SQL
            parameters: list[object] = [case_status, priority, limit, offset]
        elif case_status is not None:
            query = CASE_LIST_BY_STATUS_SQL
            parameters = [case_status, limit, offset]
        elif priority is not None:
            query = CASE_LIST_BY_PRIORITY_SQL
            parameters = [priority, limit, offset]
        else:
            query = CASE_LIST_SQL
            parameters = [limit, offset]
        with database.session() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return CaseList(items=[_case_from_row(row) for row in rows], limit=limit, offset=offset)

    @application.get("/v1/cases/{case_id}", response_model=CaseRecord)
    async def get_case(case_id: str, _: Principal = Depends(read_cases)) -> CaseRecord:
        with database.session() as connection:
            return _fetch_case(connection, case_id)

    @application.get("/v1/cases/{case_id}/events")
    async def get_case_events(case_id: str, _: Principal = Depends(read_cases)) -> list[dict[str, Any]]:
        with database.session() as connection:
            _fetch_case(connection, case_id)
            rows = connection.execute(
                "SELECT event_id, case_id, event_type, from_status, to_status, "
                "actor_id, actor_role, event_at, details_json "
                "FROM case_events WHERE case_id = ? ORDER BY event_id",
                (case_id,),
            ).fetchall()
        return [
            {
                **{key: value for key, value in dict(row).items() if key != "details_json"},
                "details": json.loads(row["details_json"]),
            }
            for row in rows
        ]

    @application.post("/v1/cases", response_model=CaseRecord, status_code=status.HTTP_201_CREATED)
    async def create_case(
        request: CaseCreate, principal: Principal = Depends(write_cases)
    ) -> CaseRecord | JSONResponse:
        _ensure_write_ready(resolved)
        route = "POST /v1/cases"
        payload = request.model_dump(mode="json")
        command_id = str(request.command_id)
        request_sha256 = _request_hash(payload)
        with database.transaction() as connection:
            existing = _load_idempotent_response(connection, command_id, principal, route, request_sha256)
            if existing is not None:
                return JSONResponse(existing, status_code=status.HTTP_200_OK)
            case_id = str(uuid4())
            now = _utc_now()
            connection.execute(
                "INSERT INTO cases "
                "(case_id, entity_type, entity_id, priority, status, owner, "
                "recommended_action, decision_rationale, version, created_at, updated_at, "
                "created_by, updated_by) VALUES (?, ?, ?, ?, 'open', ?, ?, ?, 1, ?, ?, ?, ?)",
                (
                    case_id,
                    request.entity_type,
                    request.entity_id,
                    request.priority,
                    request.owner,
                    request.recommended_action,
                    request.decision_rationale,
                    now,
                    now,
                    principal.subject,
                    principal.subject,
                ),
            )
            details = {"command_id": command_id, "entity_id": request.entity_id}
            _append_case_event(connection, case_id, "case_created", None, "open", principal, now, details)
            _append_audit(connection, resolved, principal, "case_created", case_id, now, details)
            response = _fetch_case(connection, case_id)
            response_payload = response.model_dump(mode="json")
            _store_command(
                connection,
                command_id,
                principal,
                route,
                request_sha256,
                response_payload,
                now,
            )
        return response

    @application.patch("/v1/cases/{case_id}", response_model=CaseRecord)
    async def update_case(
        case_id: str,
        request: CaseUpdate,
        principal: Principal = Depends(write_cases),
    ) -> CaseRecord | JSONResponse:
        _ensure_write_ready(resolved)
        route = f"PATCH /v1/cases/{case_id}"
        payload = request.model_dump(mode="json")
        command_id = str(request.command_id)
        request_sha256 = _request_hash(payload)
        update_fields = request.model_dump(exclude={"command_id", "expected_version"}, exclude_unset=True)
        if not update_fields:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="At least one case field must be supplied.",
            )
        if update_fields.get("recommended_action", "present") is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="recommended_action cannot be null.",
            )
        with database.transaction() as connection:
            existing = _load_idempotent_response(connection, command_id, principal, route, request_sha256)
            if existing is not None:
                return JSONResponse(existing, status_code=status.HTTP_200_OK)
            current = _fetch_case(connection, case_id)
            if current.version != request.expected_version:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Case version is stale; reload before updating.",
                )
            requested_status = update_fields.get("status")
            allowed_transitions = {
                "open": {"open", "investigating", "pending_approval"},
                "investigating": {"investigating", "pending_approval"},
                "pending_approval": {"pending_approval"},
                "resolved": {"resolved"},
                "rejected": {"rejected"},
            }
            if requested_status is not None and requested_status not in allowed_transitions[current.status]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Invalid case status transition; approval is required for closure.",
                )
            updated_values = current.model_dump()
            updated_values.update(update_fields)
            now = _utc_now()
            result = connection.execute(
                "UPDATE cases SET status = ?, priority = ?, owner = ?, "
                "recommended_action = ?, decision_rationale = ?, version = version + 1, "
                "updated_at = ?, updated_by = ? WHERE case_id = ? AND version = ?",
                (
                    updated_values["status"],
                    updated_values["priority"],
                    updated_values["owner"],
                    updated_values["recommended_action"],
                    updated_values["decision_rationale"],
                    now,
                    principal.subject,
                    case_id,
                    request.expected_version,
                ),
            )
            if result.rowcount != 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Concurrent update detected.",
                )
            updated = _fetch_case(connection, case_id)
            details = {"command_id": command_id, "changed_fields": sorted(update_fields)}
            _append_case_event(
                connection,
                case_id,
                "case_updated",
                current.status,
                updated.status,
                principal,
                now,
                details,
            )
            _append_audit(connection, resolved, principal, "case_updated", case_id, now, details)
            response_payload = updated.model_dump(mode="json")
            _store_command(
                connection,
                command_id,
                principal,
                route,
                request_sha256,
                response_payload,
                now,
            )
        return updated

    @application.post("/v1/cases/{case_id}/approval", response_model=CaseRecord)
    async def approve_case(
        case_id: str,
        request: ApprovalDecision,
        principal: Principal = Depends(approve_cases),
    ) -> CaseRecord | JSONResponse:
        _ensure_write_ready(resolved)
        route = f"POST /v1/cases/{case_id}/approval"
        payload = request.model_dump(mode="json")
        command_id = str(request.command_id)
        request_sha256 = _request_hash(payload)
        with database.transaction() as connection:
            existing = _load_idempotent_response(connection, command_id, principal, route, request_sha256)
            if existing is not None:
                return JSONResponse(existing, status_code=status.HTTP_200_OK)
            current = _fetch_case(connection, case_id)
            if current.version != request.expected_version:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Case version is stale; reload before approving.",
                )
            if current.status != "pending_approval":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Only pending cases can be approved or rejected.",
                )
            target_status = "resolved" if request.decision == "approved" else "rejected"
            now = _utc_now()
            result = connection.execute(
                "UPDATE cases SET status = ?, decision_rationale = ?, version = version + 1, "
                "updated_at = ?, updated_by = ? WHERE case_id = ? AND version = ?",
                (
                    target_status,
                    request.rationale,
                    now,
                    principal.subject,
                    case_id,
                    request.expected_version,
                ),
            )
            if result.rowcount != 1:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Concurrent approval detected.",
                )
            updated = _fetch_case(connection, case_id)
            details = {"command_id": command_id, "decision": request.decision}
            _append_case_event(
                connection,
                case_id,
                "case_approval_decided",
                current.status,
                target_status,
                principal,
                now,
                details,
            )
            _append_audit(
                connection,
                resolved,
                principal,
                "case_approval_decided",
                case_id,
                now,
                details,
            )
            response_payload = updated.model_dump(mode="json")
            _store_command(
                connection,
                command_id,
                principal,
                route,
                request_sha256,
                response_payload,
                now,
            )
        return updated

    @application.get("/v1/audit/verify", response_model=AuditVerification)
    async def audit_verification(
        _: Principal = Depends(verify_audit),
    ) -> AuditVerification:
        _ensure_write_ready(resolved)
        with database.session() as connection:
            return _verify_audit_chain(connection, resolved)

    return application


app = create_app()
