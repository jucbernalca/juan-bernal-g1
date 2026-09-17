from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from src.core.models import Ticket, TriagedTicket
from src import config

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    pass


def validate_ticket_dict(raw: dict[str, Any]) -> tuple[Ticket | None, str | None]:
    if not isinstance(raw, dict):
        return None, "El ticket no es un objeto JSON valido"

    ticket_id = raw.get("ticket_id", "")
    if not ticket_id or not str(ticket_id).strip():
        return None, "ticket_id vacio o ausente"

    text = raw.get("text", "")
    if not text or not str(text).strip():
        return None, "text vacio o ausente"

    created_at = raw.get("created_at")
    if created_at:
        try:
            datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            raw["created_at"] = None
            logger.warning("Timestamp invalido en ticket %s, se ignora", ticket_id)

    try:
        ticket = Ticket(**raw)
        return ticket, None
    except Exception as e:
        return None, f"Error de validacion: {e}"


def validate_triaged_output(data: dict[str, Any]) -> tuple[TriagedTicket | None, str | None]:
    if not isinstance(data, dict):
        return None, "La salida no es un diccionario"

    required_fields = [
        "category", "priority", "sentiment", "product_or_module",
        "summary", "suggested_action", "suggested_response", "confidence",
    ]
    missing = [f for f in required_fields if f not in data or data[f] is None]
    if missing:
        return None, f"Campos faltantes: {missing}"

    if data["category"] not in config.VALID_CATEGORIES:
        data["category"] = "Otro"
        logger.warning("Categoria invalida, degradada a 'Otro'")

    if data["priority"] not in config.VALID_PRIORITIES:
        data["priority"] = "P3"
        logger.warning("Prioridad invalida, degradada a 'P3'")

    if data["sentiment"] not in config.VALID_SENTIMENTS:
        data["sentiment"] = "neutral"
        logger.warning("Sentimiento invalido, degradado a 'neutral'")

    try:
        confidence = float(data["confidence"])
        data["confidence"] = max(0.0, min(1.0, confidence))
    except (ValueError, TypeError):
        data["confidence"] = 0.0
        logger.warning("Confianza invalida, degradada a 0.0")

    try:
        triaged = TriagedTicket(**data)
        return triaged, None
    except Exception as e:
        return None, f"Error de validacion de schema: {e}"


def sanitize_ticket_text(text: str, max_length: int = 5000) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) > max_length:
        text = text[:max_length] + "... [truncado]"
    text = text.replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    return text
