from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from src.api.app import ApiSettings, create_app
from src.api.security import TokenRecord, parse_token_records


def _token_record(token: str, role: str, subject: str) -> TokenRecord:
    return TokenRecord(
        token_id=f"{role}-token",
        subject=subject,
        role=role,  # type: ignore[arg-type]
        token_sha256=hashlib.sha256(token.encode("utf-8")).hexdigest(),
    )


def _settings(tmp_path: Path, *, audit_key: bytes = b"a" * 32, max_bytes: int = 65_536) -> ApiSettings:
    return ApiSettings(
        database_path=tmp_path / "cases.sqlite3",
        token_records=(
            _token_record("viewer-secret", "viewer", "viewer@example.com"),
            _token_record("analyst-secret", "analyst", "analyst@example.com"),
            _token_record("manager-secret", "manager", "manager@example.com"),
            _token_record("admin-secret", "admin", "admin@example.com"),
        ),
        audit_hmac_key=audit_key,
        environment="production",
        max_request_bytes=max_bytes,
    )


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_payload(command_id: str | None = None) -> dict[str, object]:
    return {
        "command_id": command_id or str(uuid4()),
        "entity_type": "seller",
        "entity_id": "S00123",
        "priority": "critical",
        "owner": "Risk Operations",
        "recommended_action": "Enhanced manual review",
        "decision_rationale": "High governed risk score.",
    }


def test_case_workflow_rbac_idempotency_and_audit_chain(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health/live").json() == {"status": "live"}
        assert client.get("/health/ready").json() == {"status": "ready"}
        assert client.get("/docs").status_code == 404
        assert client.get("/v1/cases").status_code == 401
        assert client.get("/v1/cases", headers=_headers("wrong")).status_code == 401

        payload = _create_payload()
        response = client.post("/v1/cases", json=payload, headers=_headers("analyst-secret"))
        assert response.status_code == 201
        created = response.json()
        case_id = created["case_id"]
        assert created["status"] == "open"
        assert created["version"] == 1

        replay = client.post("/v1/cases", json=payload, headers=_headers("analyst-secret"))
        assert replay.status_code == 200
        assert replay.json() == created

        conflict_payload = {**payload, "priority": "high"}
        conflict = client.post(
            "/v1/cases",
            json=conflict_payload,
            headers=_headers("analyst-secret"),
        )
        assert conflict.status_code == 409

        listed = client.get(
            "/v1/cases?status=open&priority=critical",
            headers=_headers("viewer-secret"),
        )
        assert listed.status_code == 200
        assert listed.json()["items"][0]["case_id"] == case_id
        assert client.post("/v1/cases", json=_create_payload(), headers=_headers("viewer-secret")).status_code == 403

        stale = client.patch(
            f"/v1/cases/{case_id}",
            json={
                "command_id": str(uuid4()),
                "expected_version": 99,
                "status": "investigating",
            },
            headers=_headers("analyst-secret"),
        )
        assert stale.status_code == 409

        investigating = client.patch(
            f"/v1/cases/{case_id}",
            json={
                "command_id": str(uuid4()),
                "expected_version": 1,
                "status": "investigating",
                "owner": "Senior Risk Analyst",
            },
            headers=_headers("analyst-secret"),
        )
        assert investigating.status_code == 200
        assert investigating.json()["version"] == 2

        pending = client.patch(
            f"/v1/cases/{case_id}",
            json={
                "command_id": str(uuid4()),
                "expected_version": 2,
                "status": "pending_approval",
            },
            headers=_headers("analyst-secret"),
        )
        assert pending.status_code == 200
        assert pending.json()["status"] == "pending_approval"

        approval_payload = {
            "command_id": str(uuid4()),
            "expected_version": 3,
            "decision": "approved",
            "rationale": "Evidence reviewed and action completed.",
        }
        assert (
            client.post(
                f"/v1/cases/{case_id}/approval",
                json=approval_payload,
                headers=_headers("analyst-secret"),
            ).status_code
            == 403
        )
        approved = client.post(
            f"/v1/cases/{case_id}/approval",
            json=approval_payload,
            headers=_headers("manager-secret"),
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "resolved"
        assert approved.json()["version"] == 4

        events = client.get(f"/v1/cases/{case_id}/events", headers=_headers("viewer-secret"))
        assert events.status_code == 200
        assert [event["event_type"] for event in events.json()] == [
            "case_created",
            "case_updated",
            "case_updated",
            "case_approval_decided",
        ]
        assert client.get("/v1/audit/verify", headers=_headers("manager-secret")).status_code == 403
        audit = client.get("/v1/audit/verify", headers=_headers("admin-secret"))
        assert audit.status_code == 200
        assert audit.json() == {
            "verified": True,
            "entry_count": 4,
            "first_invalid_audit_id": None,
        }

    with TestClient(create_app(settings)) as restarted_client:
        assert restarted_client.get("/health/ready").status_code == 200

    connection = sqlite3.connect(settings.database_path)
    migration = connection.execute(
        "SELECT migration_sha256 FROM schema_migrations WHERE migration_name = '001_initial.sql'"
    ).fetchone()
    assert migration is not None and len(migration[0]) == 64
    with connection:
        try:
            connection.execute("UPDATE audit_log SET actor_id = 'tampered'")
        except sqlite3.DatabaseError as exc:
            assert "append-only" in str(exc)
        else:
            raise AssertionError("Audit log update should have been rejected.")
    connection.close()


def test_case_validation_transitions_and_fail_closed_configuration(tmp_path: Path) -> None:
    settings = _settings(tmp_path, audit_key=b"")
    with TestClient(create_app(settings)) as client:
        response = client.post("/v1/cases", json=_create_payload(), headers=_headers("analyst-secret"))
        assert response.status_code == 503
        assert client.get("/v1/cases/not-found", headers=_headers("viewer-secret")).status_code == 404


def test_request_size_host_validation_and_token_config(tmp_path: Path) -> None:
    settings = _settings(tmp_path, max_bytes=128)
    with TestClient(create_app(settings)) as client:
        oversized = client.post(
            "/v1/cases",
            content=b"x" * 129,
            headers={**_headers("analyst-secret"), "Content-Type": "application/json"},
        )
        assert oversized.status_code == 413
        assert client.get("/health/live", headers={"Host": "untrusted.example"}).status_code == 400

    token_hash = hashlib.sha256(b"secret").hexdigest()
    parsed = parse_token_records(
        '{"token-1":{"subject":"user@example.com","role":"viewer","sha256":"' + token_hash + '"}}'
    )
    assert parsed[0].subject == "user@example.com"


def test_token_config_rejects_invalid_payloads() -> None:
    for payload in ["not-json", "[]", '{"x":{"role":"owner"}}']:
        try:
            parse_token_records(payload)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid token configuration was accepted: {payload}")
