from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["viewer", "analyst", "manager", "admin"]
CaseStatus = Literal["open", "investigating", "pending_approval", "resolved", "rejected"]
Priority = Literal["critical", "high", "moderate", "low"]
EntityType = Literal["order", "seller"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CaseCreate(StrictModel):
    command_id: UUID
    entity_type: EntityType
    entity_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9._:-]+$")
    priority: Priority
    owner: str | None = Field(default=None, max_length=100)
    recommended_action: str = Field(min_length=3, max_length=500)
    decision_rationale: str | None = Field(default=None, max_length=2000)


class CaseUpdate(StrictModel):
    command_id: UUID
    expected_version: int = Field(ge=1)
    status: CaseStatus | None = None
    priority: Priority | None = None
    owner: str | None = Field(default=None, max_length=100)
    recommended_action: str | None = Field(default=None, min_length=3, max_length=500)
    decision_rationale: str | None = Field(default=None, max_length=2000)


class ApprovalDecision(StrictModel):
    command_id: UUID
    expected_version: int = Field(ge=1)
    decision: Literal["approved", "rejected"]
    rationale: str = Field(min_length=3, max_length=2000)


class CaseRecord(StrictModel):
    case_id: str
    entity_type: EntityType
    entity_id: str
    priority: Priority
    status: CaseStatus
    owner: str | None
    recommended_action: str
    decision_rationale: str | None
    version: int
    created_at: str
    updated_at: str
    created_by: str
    updated_by: str


class CaseList(StrictModel):
    items: list[CaseRecord]
    limit: int
    offset: int


class AuditVerification(StrictModel):
    verified: bool
    entry_count: int
    first_invalid_audit_id: int | None = None
