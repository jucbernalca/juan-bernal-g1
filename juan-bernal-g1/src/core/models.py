from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Ticket(BaseModel):
    ticket_id: str = Field(..., min_length=1)
    customer_id: Optional[str] = None
    created_at: Optional[str] = None
    region: Optional[str] = None
    text: str = Field(..., min_length=1)

    @field_validator("ticket_id", "text")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("El campo no puede estar vacio o solo contener espacios")
        return v.strip()


class TriagedTicket(BaseModel):
    ticket_id: str
    category: str
    priority: str
    sentiment: str
    product_or_module: str
    summary: str
    suggested_action: str
    suggested_response: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    requires_human_review: bool = False
    incident_group_id: Optional[str] = None

    @field_validator("priority")
    @classmethod
    def valid_priority(cls, v: str) -> str:
        allowed = ["P1", "P2", "P3", "P4"]
        if v not in allowed:
            raise ValueError(f"Prioridad invalida: {v}. Debe ser una de {allowed}")
        return v

    @field_validator("confidence")
    @classmethod
    def valid_confidence(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError("Confianza debe estar entre 0.0 y 1.0")
        return v


class IncidentGroup(BaseModel):
    incident_group_id: str
    title: str
    ticket_count: int
    highest_priority: str
    affected_module: str
    affected_region: str
    summary: str
    major_incident_candidate: bool = False
    operational_priority: Optional[str] = None
    ticket_ids: list[str] = Field(default_factory=list)


class AuditRecord(BaseModel):
    ticket_id: str
    model: str
    attempts: int
    validation_status: str
    correlation_id: str
    processed_at: str
    error: Optional[str] = None


class ProcessingResult(BaseModel):
    ticket_id: str
    success: bool
    triaged: Optional[TriagedTicket] = None
    audit: Optional[AuditRecord] = None
    error: Optional[str] = None


class ExecutiveBrief(BaseModel):
    incident_id: str
    executive_summary: str
    affected_scope: str
    probable_pattern: str
    recommended_next_actions: list[str] = Field(default_factory=list)


class BatchResult(BaseModel):
    total: int
    successful: int
    failed: int
    results: list[ProcessingResult] = Field(default_factory=list)
    triaged_tickets: list[TriagedTicket] = Field(default_factory=list)
    incident_groups: list[IncidentGroup] = Field(default_factory=list)
    audit_records: list[AuditRecord] = Field(default_factory=list)
