from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.api.models import Role


@dataclass(frozen=True)
class Principal:
    subject: str
    role: Role
    token_id: str


@dataclass(frozen=True)
class TokenRecord:
    token_id: str
    subject: str
    role: Role
    token_sha256: str


ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    "viewer": frozenset({"cases:read"}),
    "analyst": frozenset({"cases:read", "cases:write"}),
    "manager": frozenset({"cases:read", "cases:write", "cases:approve"}),
    "admin": frozenset({"cases:read", "cases:write", "cases:approve", "audit:verify"}),
}

bearer_scheme = HTTPBearer(auto_error=False)


def parse_token_records(payload: str) -> tuple[TokenRecord, ...]:
    if not payload.strip():
        return ()
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("CASE_API_TOKENS_JSON must contain valid JSON.") from exc
    if not isinstance(decoded, dict):
        raise ValueError("CASE_API_TOKENS_JSON must be an object keyed by token id.")
    records: list[TokenRecord] = []
    for token_id, raw_record in decoded.items():
        if not isinstance(token_id, str) or not isinstance(raw_record, dict):
            raise ValueError("Token records must be objects with string identifiers.")
        role = raw_record.get("role")
        if role not in ROLE_PERMISSIONS:
            raise ValueError(f"Invalid role for token {token_id}.")
        token_hash = raw_record.get("sha256")
        subject = raw_record.get("subject")
        if not isinstance(token_hash, str) or len(token_hash) != 64:
            raise ValueError(f"Token {token_id} must include a SHA-256 digest.")
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError(f"Token {token_id} must include a subject.")
        records.append(
            TokenRecord(
                token_id=token_id,
                subject=subject,
                role=role,
                token_sha256=token_hash.lower(),
            )
        )
    return tuple(records)


class BearerAuthenticator:
    def __init__(self, token_records: tuple[TokenRecord, ...]) -> None:
        self.token_records = token_records

    async def authenticate(
        self,
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    ) -> Principal:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        digest = hashlib.sha256(credentials.credentials.encode("utf-8")).hexdigest()
        for record in self.token_records:
            if hmac.compare_digest(digest, record.token_sha256):
                return Principal(record.subject, record.role, record.token_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def require(self, permission: str) -> Callable[..., Awaitable[Principal]]:
        async def dependency(
            principal: Principal = Depends(self.authenticate),
        ) -> Principal:
            if permission not in ROLE_PERMISSIONS[principal.role]:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permission.",
                )
            return principal

        return dependency
