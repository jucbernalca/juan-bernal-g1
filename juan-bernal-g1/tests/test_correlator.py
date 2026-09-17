import pytest
from src.core.correlator import Correlator
from src.core.models import TriagedTicket


def make_triaged(ticket_id, category, module, priority, summary, group_id=None):
    return TriagedTicket(
        ticket_id=ticket_id,
        category=category,
        priority=priority,
        sentiment="negativo",
        product_or_module=module,
        summary=summary,
        suggested_action="accion",
        suggested_response="respuesta",
        confidence=0.9,
        requires_human_review=False,
        incident_group_id=group_id,
    )


class TestCorrelator:
    def test_empty_tickets(self):
        correlator = Correlator()
        import asyncio
        groups = asyncio.get_event_loop().run_until_complete(correlator.correlate([]))
        assert groups == []

    def test_related_tickets_grouped(self):
        tickets = [
            make_triaged("T-001", "Disponibilidad y rendimiento", "API", "P1", "Errores 503 en API latam-north"),
            make_triaged("T-002", "Disponibilidad y rendimiento", "API", "P1", "API falla 503 en latam-north"),
            make_triaged("T-003", "Disponibilidad y rendimiento", "API", "P2", "Checkout falla por 503 API"),
        ]
        raw = [
            {"ticket_id": "T-001", "region": "latam-north", "text": "La API devuelve 503 en latam-north", "created_at": "2026-09-16T08:15:00Z"},
            {"ticket_id": "T-002", "region": "latam-north", "text": "API falla 503 latam-north", "created_at": "2026-09-16T08:16:00Z"},
            {"ticket_id": "T-003", "region": "latam-north", "text": "Checkout falla porque API da 503", "created_at": "2026-09-16T08:17:00Z"},
        ]
        correlator = Correlator()
        import asyncio
        groups = asyncio.new_event_loop().run_until_complete(
            correlator.correlate(tickets, raw, use_glm=False)
        )
        assert len(groups) >= 1
        assert all(t.incident_group_id is not None for t in tickets)

    def test_unrelated_tickets_separate(self):
        tickets = [
            make_triaged("T-001", "Solicitud de funcion", "UI", "P4", "Modo oscuro"),
            make_triaged("T-002", "Facturacion", "Billing", "P2", "Doble cargo en factura"),
        ]
        raw = [
            {"ticket_id": "T-001", "region": "latam-south", "text": "Quiero modo oscuro", "created_at": "2026-09-16T08:15:00Z"},
            {"ticket_id": "T-002", "region": "emea", "text": "Factura con doble cargo", "created_at": "2026-09-16T08:20:00Z"},
        ]
        correlator = Correlator()
        import asyncio
        groups = asyncio.new_event_loop().run_until_complete(
            correlator.correlate(tickets, raw, use_glm=False)
        )
        assert len(groups) == 2
