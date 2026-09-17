from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.core.models import Ticket
from src.pipeline.validator import validate_ticket_dict

logger = logging.getLogger(__name__)


class Ingester:
    @staticmethod
    def load_from_file(file_path: str | Path) -> tuple[list[Ticket], list[dict[str, Any]]]:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {path}")

        raw_text = path.read_text(encoding="utf-8")
        return Ingester.load_from_string(raw_text)

    @staticmethod
    def load_from_string(raw_text: str) -> tuple[list[Ticket], list[dict[str, Any]]]:
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON invalido: {e}")

        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            raise ValueError("El JSON debe ser una lista de tickets o un ticket individual")

        tickets: list[Ticket] = []
        errors: list[dict[str, Any]] = []

        for i, raw in enumerate(data):
            ticket, error = validate_ticket_dict(raw)
            if ticket:
                tickets.append(ticket)
            else:
                tid = raw.get("ticket_id", f"index-{i}") if isinstance(raw, dict) else f"index-{i}"
                errors.append({"ticket_id": tid, "error": error})
                logger.warning("Ticket invalido (%s): %s", tid, error)

        logger.info("Ingesta: %d tickets validos, %d errores", len(tickets), len(errors))
        return tickets, errors

    @staticmethod
    def load_single(ticket_dict: dict[str, Any]) -> tuple[Ticket | None, str | None]:
        ticket, error = validate_ticket_dict(ticket_dict)
        return ticket, error
