from __future__ import annotations

import logging
from typing import Any

from src.api.glm_client import GLMClient
from src.api.prompts import SYSTEM_PROMPT_EXECUTIVE_BRIEF, build_executive_brief_prompt
from src.core.models import IncidentGroup, TriagedTicket, ExecutiveBrief
from src import config

logger = logging.getLogger(__name__)


class IncidentDetector:
    def __init__(self, client: GLMClient | None = None):
        self.client = client or GLMClient()

    def detect_major_incidents(
        self,
        groups: list[IncidentGroup],
    ) -> list[IncidentGroup]:
        for group in groups:
            is_major = (
                group.ticket_count >= config.MAJOR_INCIDENT_MIN_TICKETS
                and group.highest_priority in ("P1", "P2")
            )
            group.major_incident_candidate = is_major

            if is_major:
                group.operational_priority = "P1"
            elif group.ticket_count >= 3 and group.highest_priority in ("P1", "P2"):
                group.operational_priority = group.highest_priority
            else:
                group.operational_priority = group.highest_priority

        major = [g for g in groups if g.major_incident_candidate]
        logger.info("Detectados %d incidentes mayores de %d grupos", len(major), len(groups))
        return groups

    def reprioritize_by_blast_radius(
        self,
        groups: list[IncidentGroup],
        triaged_tickets: list[TriagedTicket],
    ) -> list[IncidentGroup]:
        group_map: dict[str, IncidentGroup] = {g.incident_group_id: g for g in groups}

        for group in groups:
            member_tickets = [
                t for t in triaged_tickets if t.incident_group_id == group.incident_group_id
            ]
            unique_regions: set[str] = set()
            for t in member_tickets:
                pass

            if group.ticket_count >= 10:
                group.operational_priority = "P1"
            elif group.ticket_count >= 5 and group.highest_priority in ("P1", "P2"):
                group.operational_priority = "P1"
            elif group.ticket_count >= 3:
                group.operational_priority = group.highest_priority

        return groups

    async def generate_executive_brief(
        self,
        incident: IncidentGroup,
        tickets: list[TriagedTicket],
    ) -> ExecutiveBrief | None:
        try:
            incident_dict = incident.model_dump()
            tickets_dict = [t.model_dump() for t in tickets if t.incident_group_id == incident.incident_group_id]

            result = await self.client.call(
                system_prompt=SYSTEM_PROMPT_EXECUTIVE_BRIEF,
                user_prompt=build_executive_brief_prompt(incident_dict, tickets_dict),
            )

            return ExecutiveBrief(
                incident_id=incident.incident_group_id,
                executive_summary=result.get("executive_summary", ""),
                affected_scope=result.get("affected_scope", ""),
                probable_pattern=result.get("probable_pattern", ""),
                recommended_next_actions=result.get("recommended_next_actions", []),
            )
        except Exception as e:
            logger.error("Error generando brief ejecutivo para %s: %s", incident.incident_group_id, e)
            return ExecutiveBrief(
                incident_id=incident.incident_group_id,
                executive_summary=f"Incidente mayor detectado: {incident.title}",
                affected_scope=f"{incident.ticket_count} tickets, region: {incident.affected_region}",
                probable_pattern="No determinado (fallo de generacion de brief)",
                recommended_next_actions=["Investigar causa raiz", "Comunicar a clientes impactados"],
            )
