import pytest
from src.pipeline.validator import validate_ticket_dict, validate_triaged_output, sanitize_ticket_text
from src.core.models import Ticket


class TestTicketValidation:
    def test_valid_ticket(self):
        raw = {
            "ticket_id": "T-001",
            "customer_id": "ACME",
            "created_at": "2026-09-16T08:15:00Z",
            "region": "latam-north",
            "text": "No puedo acceder al sistema.",
        }
        ticket, error = validate_ticket_dict(raw)
        assert ticket is not None
        assert error is None
        assert ticket.ticket_id == "T-001"

    def test_empty_ticket_id(self):
        raw = {"ticket_id": "", "text": "algo"}
        ticket, error = validate_ticket_dict(raw)
        assert ticket is None
        assert "ticket_id" in error

    def test_empty_text(self):
        raw = {"ticket_id": "T-001", "text": ""}
        ticket, error = validate_ticket_dict(raw)
        assert ticket is None
        assert "text" in error

    def test_missing_fields(self):
        raw = {"ticket_id": "T-001"}
        ticket, error = validate_ticket_dict(raw)
        assert ticket is None
        assert "text" in error

    def test_invalid_timestamp(self):
        raw = {
            "ticket_id": "T-001",
            "text": "algo",
            "created_at": "not-a-timestamp",
        }
        ticket, error = validate_ticket_dict(raw)
        assert ticket is not None
        assert ticket.created_at is None

    def test_not_a_dict(self):
        ticket, error = validate_ticket_dict("not a dict")
        assert ticket is None
        assert "objeto JSON" in error

    def test_whitespace_only(self):
        raw = {"ticket_id": "   ", "text": "   "}
        ticket, error = validate_ticket_dict(raw)
        assert ticket is None


class TestTriagedOutputValidation:
    def test_valid_output(self):
        data = {
            "ticket_id": "T-001",
            "category": "Cuenta y acceso",
            "priority": "P1",
            "sentiment": "negativo",
            "product_or_module": "SSO",
            "summary": "Sin acceso SSO",
            "suggested_action": "Escalar",
            "suggested_response": "Investigando",
            "confidence": 0.95,
        }
        triaged, error = validate_triaged_output(data)
        assert triaged is not None
        assert error is None
        assert triaged.priority == "P1"

    def test_invalid_category_degraded(self):
        data = {
            "ticket_id": "T-001",
            "category": "CategoriaInventada",
            "priority": "P3",
            "sentiment": "neutral",
            "product_or_module": "X",
            "summary": "s",
            "suggested_action": "a",
            "suggested_response": "r",
            "confidence": 0.5,
        }
        triaged, error = validate_triaged_output(data)
        assert triaged is not None
        assert triaged.category == "Otro"

    def test_invalid_priority_degraded(self):
        data = {
            "ticket_id": "T-001",
            "category": "Otro",
            "priority": "P9",
            "sentiment": "neutral",
            "product_or_module": "X",
            "summary": "s",
            "suggested_action": "a",
            "suggested_response": "r",
            "confidence": 0.5,
        }
        triaged, error = validate_triaged_output(data)
        assert triaged is not None
        assert triaged.priority == "P3"

    def test_confidence_clamped(self):
        data = {
            "ticket_id": "T-001",
            "category": "Otro",
            "priority": "P3",
            "sentiment": "neutral",
            "product_or_module": "X",
            "summary": "s",
            "suggested_action": "a",
            "suggested_response": "r",
            "confidence": 1.5,
        }
        triaged, error = validate_triaged_output(data)
        assert triaged is not None
        assert triaged.confidence == 1.0

    def test_missing_fields(self):
        data = {"ticket_id": "T-001", "category": "Otro"}
        triaged, error = validate_triaged_output(data)
        assert triaged is None
        assert "faltantes" in error


class TestSanitize:
    def test_truncation(self):
        text = "A" * 6000
        result = sanitize_ticket_text(text, max_length=5000)
        assert len(result) <= 5100
        assert "truncado" in result

    def test_empty(self):
        assert sanitize_ticket_text("") == ""

    def test_whitespace_normalization(self):
        result = sanitize_ticket_text("  hello   world  ")
        assert result == "hello world"
