from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.api.glm_client import GLMClient
from src.core.classifier import Classifier
from src.core.models import (
    Ticket,
    TriagedTicket,
    ProcessingResult,
    BatchResult,
    AuditRecord,
)
from src.pipeline.ingester import Ingester

logger = logging.getLogger(__name__)


class Processor:
    def __init__(self, client: GLMClient | None = None, max_concurrency: int = 0):
        self.client = client or GLMClient()
        self.classifier = Classifier(self.client)
        from src import config
        self.max_concurrency = max_concurrency or config.MAX_CONCURRENCY

    async def process_single(self, ticket: Ticket) -> ProcessingResult:
        try:
            triaged, audit, _ = await self.classifier.classify(
                ticket_id=ticket.ticket_id,
                ticket_text=ticket.text,
            )
            return ProcessingResult(
                ticket_id=ticket.ticket_id,
                success=True,
                triaged=triaged,
                audit=audit,
            )
        except Exception as e:
            logger.error("Error procesando ticket %s: %s", ticket.ticket_id, e)
            return ProcessingResult(
                ticket_id=ticket.ticket_id,
                success=False,
                error=str(e),
            )

    async def process_batch(
        self,
        tickets: list[Ticket],
        on_progress: Any = None,
    ) -> BatchResult:
        semaphore = asyncio.Semaphore(self.max_concurrency)
        results: list[ProcessingResult] = []

        async def _process_with_semaphore(ticket: Ticket) -> ProcessingResult:
            async with semaphore:
                result = await self.process_single(ticket)
                if on_progress:
                    on_progress(len(results) + 1, len(tickets))
                return result

        tasks = [_process_with_semaphore(t) for t in tickets]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        triaged_tickets: list[TriagedTicket] = []
        audit_records: list[AuditRecord] = []
        successful = 0
        failed = 0

        for r in results:
            if r.success and r.triaged:
                triaged_tickets.append(r.triaged)
                successful += 1
            else:
                failed += 1
            if r.audit:
                audit_records.append(r.audit)

        logger.info(
            "Lote procesado: %d exitosos, %d fallidos de %d total",
            successful, failed, len(tickets),
        )

        return BatchResult(
            total=len(tickets),
            successful=successful,
            failed=failed,
            results=results,
            triaged_tickets=triaged_tickets,
            audit_records=audit_records,
        )

    async def process_file(
        self,
        file_path: str,
        on_progress: Any = None,
    ) -> BatchResult:
        tickets, errors = Ingester.load_from_file(file_path)
        logger.info("Cargados %d tickets (%d errores de ingesta)", len(tickets), len(errors))

        batch_result = await self.process_batch(tickets, on_progress)

        for err in errors:
            batch_result.results.append(
                ProcessingResult(
                    ticket_id=err["ticket_id"],
                    success=False,
                    error=err["error"],
                )
            )
            batch_result.failed += 1
            batch_result.total += 1

        return batch_result

    async def process_ticket_dict(self, ticket_dict: dict) -> ProcessingResult:
        ticket, error = Ingester.load_single(ticket_dict)
        if error:
            return ProcessingResult(
                ticket_id=ticket_dict.get("ticket_id", "unknown"),
                success=False,
                error=error,
            )
        return await self.process_single(ticket)
