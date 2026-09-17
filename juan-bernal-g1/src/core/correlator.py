from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from src.api.glm_client import GLMClient
from src.api.prompts import SYSTEM_PROMPT_CORRELATION, build_correlation_prompt
from src.core.models import TriagedTicket, IncidentGroup
from src import config

logger = logging.getLogger(__name__)


class Correlator:
    def __init__(self, client: GLMClient | None = None):
        self.client = client or GLMClient()

    @staticmethod
    def _parse_timestamp(ts: str | None) -> datetime | None:
        if not ts:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    @staticmethod
    def _extract_keywords(text: str) -> set[str]:
        text_lower = text.lower()
        keywords: set[str] = set()

        patterns = {
            "sso": r"\bsso\b",
            "api": r"\bapi\b",
            "503": r"\b503\b",
            "500": r"\b500\b",
            "csv": r"\bcsv\b",
            "erp": r"\berp\b",
            "deploy": r"\bdeploy\b",
            "despliegue": r"\bdespliegue\b",
            "actualizacion": r"\bactualizaci[oó]n\b",
            "login": r"\blogin\b|\binicio de sesi[oó]n\b",
            "factura": r"\bfactura\b",
            "export": r"\bexport\b|\bexportar\b",
            "checkout": r"\bcheckout\b",
            "latam-north": r"\blatam-north\b",
            "latam-south": r"\blatam-south\b",
            "emea": r"\bemea\b",
            "sync": r"\bsincroniz\b|\bsync\b",
        }
        for kw, pattern in patterns.items():
            if re.search(pattern, text_lower):
                keywords.add(kw)

        return keywords

    def _are_related_heuristic(
        self,
        ticket_a: TriagedTicket,
        ticket_b: TriagedTicket,
        raw_a: dict | None = None,
        raw_b: dict | None = None,
    ) -> tuple[bool, float, str]:
        score = 0.0
        reasons: list[str] = []

        if ticket_a.category == ticket_b.category:
            score += 0.25
            reasons.append("misma categoria")

        if ticket_a.product_or_module.lower() == ticket_b.product_or_module.lower():
            score += 0.25
            reasons.append("mismo modulo")

        region_a = (raw_a or {}).get("region")
        region_b = (raw_b or {}).get("region")
        if region_a and region_b and region_a == region_b:
            score += 0.15
            reasons.append("misma region")

        ts_a = self._parse_timestamp((raw_a or {}).get("created_at"))
        ts_b = self._parse_timestamp((raw_b or {}).get("created_at"))
        if ts_a and ts_b:
            diff = abs((ts_a - ts_b).total_seconds()) / 60
            if diff <= config.MAJOR_INCIDENT_WINDOW_MINUTES:
                score += 0.15
                reasons.append(f"proximidad temporal ({diff:.0f}min)")
            elif diff <= 60:
                score += 0.05

        text_a = (raw_a or {}).get("text", "")
        text_b = (raw_b or {}).get("text", "")
        kw_a = self._extract_keywords(text_a)
        kw_b = self._extract_keywords(text_b)
        shared = kw_a & kw_b
        if shared:
            score += min(0.20 * len(shared), 0.20)
            reasons.append(f"entidades compartidas: {shared}")

        related = score >= 0.50
        return related, min(score, 1.0), ", ".join(reasons)

    async def _are_related_glm(
        self,
        ticket_a: dict,
        ticket_b: dict,
    ) -> tuple[bool, float, str]:
        try:
            result = await self.client.call(
                system_prompt=SYSTEM_PROMPT_CORRELATION,
                user_prompt=build_correlation_prompt(ticket_a, ticket_b),
            )
            related = bool(result.get("related", False))
            confidence = float(result.get("confidence", 0.0))
            reason = result.get("reason", "")
            return related, confidence, reason
        except Exception as e:
            logger.warning("Correlacion GLM fallo, usando heuristica: %s", e)
            return False, 0.0, "GLM no disponible"

    async def correlate(
        self,
        triaged_tickets: list[TriagedTicket],
        raw_tickets: list[dict] | None = None,
        use_glm: bool = False,
    ) -> list[IncidentGroup]:
        n = len(triaged_tickets)
        if n == 0:
            return []

        raw_map: dict[str, dict] = {}
        if raw_tickets:
            for r in raw_tickets:
                tid = r.get("ticket_id")
                if tid:
                    raw_map[tid] = r

        parent = list(range(n))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        for i in range(n):
            for j in range(i + 1, n):
                ta, tb = triaged_tickets[i], triaged_tickets[j]
                raw_a = raw_map.get(ta.ticket_id, {})
                raw_b = raw_map.get(tb.ticket_id, {})

                if use_glm:
                    related, conf, reason = await self._are_related_glm(
                        {**raw_a, "triaged": ta.model_dump()},
                        {**raw_b, "triaged": tb.model_dump()},
                    )
                    if not related:
                        related, _, _ = self._are_related_heuristic(ta, tb, raw_a, raw_b)
                else:
                    related, _, _ = self._are_related_heuristic(ta, tb, raw_a, raw_b)

                if related:
                    union(i, j)

        groups: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            groups.setdefault(root, []).append(i)

        incident_groups: list[IncidentGroup] = []
        group_counter = 0

        for indices in groups.values():
            group_counter += 1
            group_id = f"INC-{group_counter:03d}"
            members = [triaged_tickets[i] for i in indices]

            priorities = [m.priority for m in members]
            highest = min(priorities, key=lambda p: config.PRIORITY_ORDER.get(p, 99))

            modules = [m.product_or_module for m in members if m.product_or_module]
            module = max(set(modules), key=modules.count) if modules else "Desconocido"

            regions: list[str] = []
            for m in members:
                r = raw_map.get(m.ticket_id, {}).get("region")
                if r:
                    regions.append(r)
            region = max(set(regions), key=regions.count) if regions else "desconocida"

            summaries = [m.summary for m in members]
            title = summaries[0] if summaries else "Grupo de incidente"

            for m in members:
                m.incident_group_id = group_id

            incident_groups.append(IncidentGroup(
                incident_group_id=group_id,
                title=title[:80],
                ticket_count=len(members),
                highest_priority=highest,
                affected_module=module,
                affected_region=region,
                summary=f"{len(members)} ticket(s) relacionados: {title}",
                ticket_ids=[m.ticket_id for m in members],
            ))

        logger.info("Correlacion: %d grupos desde %d tickets", len(incident_groups), n)
        return incident_groups
