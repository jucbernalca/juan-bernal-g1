from __future__ import annotations

import asyncio
import json
import sys
import logging
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src import config
from src.api.glm_client import GLMClient
from src.pipeline.processor import Processor
from src.pipeline.ingester import Ingester
from src.core.correlator import Correlator
from src.core.incident_detector import IncidentDetector
from src.core.models import TriagedTicket, IncidentGroup, BatchResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

PRIORITY_COLORS = {
    "P1": "🔴",
    "P2": "🟠",
    "P3": "🟡",
    "P4": "🟢",
}

PRIORITY_LABELS = {
    "P1": "P1 - Critica",
    "P2": "P2 - Alta",
    "P3": "P3 - Normal",
    "P4": "P4 - Baja",
}


def init_state() -> None:
    if "triaged_tickets" not in st.session_state:
        st.session_state.triaged_tickets = []
    if "incident_groups" not in st.session_state:
        st.session_state.incident_groups = []
    if "raw_tickets" not in st.session_state:
        st.session_state.raw_tickets = []
    if "audit_records" not in st.session_state:
        st.session_state.audit_records = []
    if "ingest_errors" not in st.session_state:
        st.session_state.ingest_errors = []
    if "processing_done" not in st.session_state:
        st.session_state.processing_done = False


def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def load_and_process(filepath: str) -> None:
    try:
        tickets, errors = Ingester.load_from_file(filepath)
        st.session_state.ingest_errors = errors
        st.session_state.raw_tickets = [t.model_dump() for t in tickets]

        if not tickets:
            st.error("No se encontraron tickets validos en el archivo.")
            return

        progress = st.progress(0.0, text="Procesando tickets...")
        total = len(tickets)

        def on_progress(done, tot):
            progress.progress(min(done / tot, 1.0), text=f"Procesando {done}/{tot} tickets...")

        processor = Processor()
        batch_result = run_async(processor.process_batch(tickets, on_progress))
        progress.progress(1.0, text="Clasificacion completada.")

        st.session_state.triaged_tickets = batch_result.triaged_tickets
        st.session_state.audit_records = batch_result.audit_records

        with st.spinner("Correlacionando tickets..."):
            correlator = Correlator()
            groups = run_async(correlator.correlate(
                batch_result.triaged_tickets,
                st.session_state.raw_tickets,
                use_glm=False,
            ))

            detector = IncidentDetector()
            groups = detector.detect_major_incidents(groups)
            groups = detector.reprioritize_by_blast_radius(groups, batch_result.triaged_tickets)

            st.session_state.incident_groups = groups

        st.session_state.processing_done = True
        st.success(
            f"Procesados {batch_result.successful} tickets exitosamente, "
            f"{batch_result.failed} fallidos, {len(groups)} grupos de incidente."
        )

    except Exception as e:
        st.error(f"Error durante el procesamiento: {e}")
        logger.exception("Error en load_and_process")


def process_single_ticket(ticket_id: str, customer_id: str, region: str, text: str) -> None:
    ticket_dict = {
        "ticket_id": ticket_id,
        "customer_id": customer_id,
        "region": region,
        "text": text,
    }
    processor = Processor()
    result = run_async(processor.process_ticket_dict(ticket_dict))

    if result.success and result.triaged:
        st.session_state.triaged_tickets.append(result.triaged)
        st.session_state.raw_tickets.append(ticket_dict)
        if result.audit:
            st.session_state.audit_records.append(result.audit)

        correlator = Correlator()
        groups = run_async(correlator.correlate(
            st.session_state.triaged_tickets,
            st.session_state.raw_tickets,
            use_glm=False,
        ))
        detector = IncidentDetector()
        groups = detector.detect_major_incidents(groups)
        groups = detector.reprioritize_by_blast_radius(groups, st.session_state.triaged_tickets)
        st.session_state.incident_groups = groups

        st.success(f"Ticket {ticket_id} procesado correctamente.")
    else:
        st.error(f"Error procesando ticket: {result.error}")


def render_queue() -> None:
    tickets: list[TriagedTicket] = st.session_state.triaged_tickets

    if not tickets:
        st.info("No hay tickets procesados. Carga y procesa un dataset primero.")
        return

    st.sidebar.markdown("### Filtros")

    priorities = ["Todas"] + list(PRIORITY_LABELS.keys())
    sel_priority = st.sidebar.selectbox("Prioridad", priorities, index=0)

    categories = ["Todas"] + config.VALID_CATEGORIES
    sel_category = st.sidebar.selectbox("Categoria", categories, index=0)

    modules = ["Todos"] + sorted(set(t.product_or_module for t in tickets if t.product_or_module))
    sel_module = st.sidebar.selectbox("Modulo", modules, index=0)

    regions = ["Todas"] + sorted(set(
        r.get("region", "") for r in st.session_state.raw_tickets if r.get("region")
    ))
    sel_region = st.sidebar.selectbox("Region", regions, index=0)

    groups = ["Todos"] + sorted(set(
        t.incident_group_id for t in tickets if t.incident_group_id
    ))
    sel_group = st.sidebar.selectbox("Grupo de incidente", groups, index=0)

    filtered = tickets
    if sel_priority != "Todas":
        filtered = [t for t in filtered if t.priority == sel_priority]
    if sel_category != "Todas":
        filtered = [t for t in filtered if t.category == sel_category]
    if sel_module != "Todos":
        filtered = [t for t in filtered if t.product_or_module == sel_module]
    if sel_region != "Todas":
        filtered = [
            t for t in filtered
            if any(r.get("ticket_id") == t.ticket_id and r.get("region") == sel_region
                   for r in st.session_state.raw_tickets)
        ]
    if sel_group != "Todos":
        filtered = [t for t in filtered if t.incident_group_id == sel_group]

    priority_sort = {p: i for i, p in enumerate(["P1", "P2", "P3", "P4"])}
    filtered.sort(key=lambda t: (priority_sort.get(t.priority, 99), -t.confidence))

    st.markdown(f"### Cola priorizada ({len(filtered)} tickets)")

    for t in filtered:
        icon = PRIORITY_COLORS.get(t.priority, "⚪")
        review_tag = " | ⚠️ Revisar" if t.requires_human_review else ""
        group_tag = f" | {t.incident_group_id}" if t.incident_group_id else ""

        with st.expander(
            f"{icon} {t.priority} | {t.ticket_id} | {t.category} | "
            f"conf: {t.confidence:.2f}{review_tag}{group_tag}"
        ):
            col1, col2 = st.columns(2)
            with col1:
                raw = next((r for r in st.session_state.raw_tickets if r.get("ticket_id") == t.ticket_id), {})
                st.markdown("**Texto original:**")
                st.text(raw.get("text", "N/A"))
                st.markdown(f"**Cliente:** {raw.get('customer_id', 'N/A')}")
                st.markdown(f"**Region:** {raw.get('region', 'N/A')}")
                st.markdown(f"**Creado:** {raw.get('created_at', 'N/A')}")
            with col2:
                st.markdown(f"**Categoria:** {t.category}")
                st.markdown(f"**Prioridad:** {PRIORITY_LABELS.get(t.priority, t.priority)}")
                st.markdown(f"**Sentimiento:** {t.sentiment}")
                st.markdown(f"**Modulo:** {t.product_or_module}")
                st.markdown(f"**Confianza:** {t.confidence:.2f}")
                st.markdown(f"**Revision humana:** {'Si' if t.requires_human_review else 'No'}")
                st.markdown(f"**Grupo:** {t.incident_group_id or 'N/A'}")

            st.markdown("**Resumen:**")
            st.write(t.summary)
            st.markdown("**Accion sugerida:**")
            st.write(t.suggested_action)
            st.markdown("**Respuesta sugerida:**")
            st.info(t.suggested_response)


def render_incidents() -> None:
    groups: list[IncidentGroup] = st.session_state.incident_groups

    if not groups:
        st.info("No hay grupos de incidente. Procesa tickets primero.")
        return

    major = [g for g in groups if g.major_incident_candidate]
    if major:
        st.markdown(f"### 🚨 Incidentes mayores ({len(major)})")
        for g in major:
            st.error(
                f"**{g.incident_group_id}** | {g.title}\n"
                f"Tickets: {g.ticket_count} | Prioridad: {g.highest_priority} | "
                f"Modulo: {g.affected_module} | Region: {g.affected_region} | "
                f"Prioridad operacional: {g.operational_priority}\n"
                f"{g.summary}\n"
                f"Tickets: {', '.join(g.ticket_ids[:10])}{'...' if len(g.ticket_ids) > 10 else ''}"
            )

            if st.button(f"Generar brief ejecutivo - {g.incident_group_id}", key=f"brief_{g.incident_group_id}"):
                with st.spinner("Generando brief ejecutivo con GLM 5.2..."):
                    detector = IncidentDetector()
                    brief = run_async(detector.generate_executive_brief(g, st.session_state.triaged_tickets))
                if brief:
                    st.markdown("**Executive Summary:**")
                    st.write(brief.executive_summary)
                    st.markdown("**Affected Scope:**")
                    st.write(brief.affected_scope)
                    st.markdown("**Probable Pattern:**")
                    st.write(brief.probable_pattern)
                    st.markdown("**Recommended Next Actions:**")
                    for action in brief.recommended_next_actions:
                        st.markdown(f"- {action}")

    normal = [g for g in groups if not g.major_incident_candidate]
    st.markdown(f"### Grupos de incidente ({len(normal)})")
    for g in normal:
        op_priority = g.operational_priority or g.highest_priority
        icon = PRIORITY_COLORS.get(op_priority, "⚪")
        with st.expander(
            f"{icon} {g.incident_group_id} | {g.ticket_count} tickets | "
            f"{g.highest_priority} | {g.affected_module}"
        ):
            st.markdown(f"**Titulo:** {g.title}")
            st.markdown(f"**Modulo:** {g.affected_module}")
            st.markdown(f"**Region:** {g.affected_region}")
            st.markdown(f"**Prioridad operacional:** {op_priority}")
            st.markdown(f"**Summary:** {g.summary}")
            st.markdown(f"**Tickets:** {', '.join(g.ticket_ids)}")


def render_manual() -> None:
    st.markdown("### Probar un ticket manualmente")
    st.markdown("Escribe un ticket nuevo y ejecuta el pipeline completo.")

    col1, col2 = st.columns(2)
    with col1:
        ticket_id = st.text_input("Ticket ID", value="T-MANUAL", key="manual_tid")
        customer_id = st.text_input("Customer ID", value="MANUAL-CO", key="manual_cid")
    with col2:
        region = st.text_input("Region", value="latam-north", key="manual_region")
        created_at = st.text_input("Created At (ISO)", value="2026-09-16T08:40:00Z", key="manual_ts")

    text = st.text_area("Texto del ticket", height=150, key="manual_text")

    if st.button("Procesar ticket", type="primary"):
        if not ticket_id.strip():
            st.error("Ticket ID no puede estar vacio.")
        elif not text.strip():
            st.error("El texto del ticket no puede estar vacio.")
        else:
            with st.spinner("Procesando con GLM 5.2..."):
                process_single_ticket(ticket_id, customer_id, region, text)


def render_audit() -> None:
    records = st.session_state.audit_records
    if not records:
        st.info("No hay registros de auditoria.")
        return

    st.markdown(f"### Registros de auditoria ({len(records)})")
    for r in records:
        status_icon = "✅" if r.validation_status == "valid" else "⚠️"
        with st.expander(
            f"{status_icon} {r.ticket_id} | {r.model} | intentos: {r.attempts} | {r.validation_status}"
        ):
            st.json(r.model_dump())


def main() -> None:
    init_state()

    st.set_page_config(
        page_title="ATLAS CLOUD // SIGNAL-80",
        page_icon="🚨",
        layout="wide",
    )

    st.markdown("# 🚨 ATLAS CLOUD // SIGNAL-80")
    st.markdown("### Motor Inteligente de Triage y Correlacion de Incidentes")
    st.markdown("---")

    st.sidebar.markdown("## ATLAS Control Room")

    st.sidebar.markdown("### Cargar dataset")
    sample_path = str(config.TICKETS_SAMPLE_PATH)
    if st.sidebar.button("Cargar tickets_sample.json", type="primary"):
        load_and_process(sample_path)

    uploaded = st.sidebar.file_uploader("O cargar archivo JSON", type=["json"])
    if uploaded and st.sidebar.button("Procesar archivo cargado"):
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            f.write(uploaded.getvalue().decode("utf-8"))
            f.flush()
            load_and_process(f.name)

    if st.session_state.ingest_errors:
        st.sidebar.markdown(f"⚠️ Errores de ingesta: {len(st.session_state.ingest_errors)}")

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Configuracion")
    st.sidebar.markdown(f"- Modelo: `{config.GLM_MODEL}`")
    st.sidebar.markdown(f"- Abstencion: `{config.ABSTENTION_THRESHOLD}`")
    st.sidebar.markdown(f"- Max retries: `{config.GLM_MAX_RETRIES}`")
    st.sidebar.markdown(f"- Concurrencia: `{config.MAX_CONCURRENCY}`")

    tab_queue, tab_incidents, tab_manual, tab_audit = st.tabs([
        "📋 Cola Priorizada",
        "🛰️ Incidentes",
        "✍️ Ticket Manual",
        "📊 Auditoria",
    ])

    with tab_queue:
        render_queue()

    with tab_incidents:
        render_incidents()

    with tab_manual:
        render_manual()

    with tab_audit:
        render_audit()


if __name__ == "__main__":
    main()
