from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from src.api.glm_client import GLMClient, GLMError
from src.api.prompts import SYSTEM_PROMPT_CLASSIFICATION, build_user_prompt
from src.core.models import TriagedTicket, AuditRecord
from src.pipeline.validator import validate_triaged_output, sanitize_ticket_text
from src import config

logger = logging.getLogger(__name__)


class Classifier:
    def __init__(self, client: GLMClient | None = None):
        self.client = client or GLMClient()

    async def classify(
        self,
        ticket_id: str,
        ticket_text: str,
    ) -> tuple[TriagedTicket | None, AuditRecord, int]:
        correlation_id = f"corr-{uuid.uuid4().hex[:6].upper()}"
        sanitized = sanitize_ticket_text(ticket_text)
        user_prompt = build_user_prompt(sanitized, ticket_id)

        attempts = 0
        last_error: str | None = None

        for attempt in range(1, self.client.max_retries + 1):
            attempts = attempt
            try:
                result = await self.client.call(
                    system_prompt=SYSTEM_PROMPT_CLASSIFICATION,
                    user_prompt=user_prompt,
                )

                result["ticket_id"] = ticket_id
                triaged, error = validate_triaged_output(result)

                if triaged:
                    if triaged.confidence < config.ABSTENTION_THRESHOLD:
                        triaged.requires_human_review = True
                        logger.info(
                            "Ticket %s marcado para revision humana (confidence=%.2f < %.2f)",
                            ticket_id, triaged.confidence, config.ABSTENTION_THRESHOLD,
                        )

                    audit = AuditRecord(
                        ticket_id=ticket_id,
                        model=config.GLM_MODEL,
                        attempts=attempts,
                        validation_status="valid",
                        correlation_id=correlation_id,
                        processed_at=datetime.now(timezone.utc).isoformat(),
                    )
                    return triaged, audit, attempts

                last_error = error or "Validacion fallida"
                logger.warning("Ticket %s intento %d: %s", ticket_id, attempt, last_error)

            except GLMError as e:
                last_error = str(e)
                logger.warning("Ticket %s intento %d error GLM: %s", ticket_id, attempt, e)

            except Exception as e:
                last_error = str(e)
                logger.warning("Ticket %s intento %d error inesperado: %s", ticket_id, attempt, e)

        triaged = TriagedTicket(
            ticket_id=ticket_id,
            category="Otro",
            priority="P3",
            sentiment="neutral",
            product_or_module="Desconocido",
            summary="No se pudo clasificar automaticamente.",
            suggested_action="Revisar manualmente.",
            suggested_response="Hemos recibido su solicitud y la estamos revisando.",
            confidence=0.0,
            requires_human_review=True,
        )

        audit = AuditRecord(
            ticket_id=ticket_id,
            model=config.GLM_MODEL,
            attempts=attempts,
            validation_status="degraded",
            correlation_id=correlation_id,
            processed_at=datetime.now(timezone.utc).isoformat(),
            error=last_error,
        )
        logger.info("Ticket %s degradado tras %d intentos", ticket_id, attempts)
        return triaged, audit, attempts
