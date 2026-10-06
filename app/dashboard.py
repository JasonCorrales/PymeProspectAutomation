from __future__ import annotations

from datetime import date, datetime
from io import StringIO

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.config import settings
from app.contact_discovery import (
    ContactDiscoveryConfigError,
    ContactDiscoveryRuntimeError,
    discover_company_contacts,
)
from app.db import SessionLocal, engine, init_db
from app.models import (
    Company,
    CompanyContactDiscoveryResult,
    CompanyContactMethod,
    CompanyStatus,
    ContactMethodType,
    DiscoveryResultStatus,
    OutreachNote,
    ProspectPriority,
)
from app.schema_evolution import evolve_local_schema


STATUS_LABELS: dict[CompanyStatus, str] = {
    CompanyStatus.new: "Nuevo",
    CompanyStatus.reviewed: "Revisado",
    CompanyStatus.contacted: "Contactado",
    CompanyStatus.qualified: "Calificado",
    CompanyStatus.disqualified: "Descartado",
}
STATUS_BY_LABEL = {label: status for status, label in STATUS_LABELS.items()}

PRIORITY_LABELS: dict[ProspectPriority, str] = {
    ProspectPriority.low: "Baja",
    ProspectPriority.medium: "Media",
    ProspectPriority.high: "Alta",
}
PRIORITY_BY_LABEL = {label: priority for priority, label in PRIORITY_LABELS.items()}

st.set_page_config(page_title=settings.app_title, layout="wide")
st.markdown(
    """
    <style>
    html, body, [class*="css"] {
        font-size: 16px;
    }
    .stMarkdown, .stText, .stCaption, .stSelectbox, .stTextInput, .stDateInput,
    .stButton, .stDownloadButton, .stDataFrame, .stTable {
        font-size: 1rem;
    }
    [data-testid="stSidebar"] label, [data-testid="stSidebar"] p {
        font-size: 1rem;
    }
    div[data-testid="stCaptionContainer"] p {
        font-size: 1.1rem;
        line-height: 1.4;
    }
    div[data-testid="stTabs"] [role="tab"],
    div[data-testid="stTabs"] [role="tab"] *,
    button[role="tab"],
    button[role="tab"] *,
    [data-baseweb="tab"],
    [data-baseweb="tab"] * {
        font-size: 1.4rem !important;
        font-weight: 700 !important;
        line-height: 1.2 !important;
    }
    div[data-testid="stTabs"] [role="tab"],
    button[role="tab"],
    [data-baseweb="tab"] {
        min-height: 3rem !important;
        padding: 0.35rem 1rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("Prospectos para renovación de certificación PYME")
st.caption("Dashboard para revisión de prospectos para renovación de certificación y seguimiento")


@st.cache_data(ttl=30)
def load_companies(
    search: str,
    sector: str,
    meic_size: str,
    start_date: date | None,
    end_date: date | None,
    province: str,
    commercial_status: str,
) -> pd.DataFrame:
    with SessionLocal() as session:
        query = select(Company)
        if search:
            like = f"%{search.lower()}%"
            query = query.where(Company.normalized_name.like(like))
        if sector and sector != "Todos":
            query = query.where(Company.sector == sector)
        if meic_size and meic_size != "Todos":
            query = query.where(Company.meic_size == meic_size)
        if start_date:
            query = query.where(Company.certification_valid_until >= start_date)
        if end_date:
            query = query.where(Company.certification_valid_until <= end_date)
        if province and province != "Todas":
            query = query.where(Company.province == province)
        if commercial_status and commercial_status != "Todos":
            query = query.where(Company.status == STATUS_BY_LABEL[commercial_status])

        companies = session.scalars(query.order_by(Company.legal_name)).all()
        return pd.DataFrame(
            [
                {
                    "id": company.id,
                    "legal_name": company.legal_name,
                    "trade_name": company.trade_name,
                    "tax_id": company.tax_id,
                    "sector": company.sector,
                    "meic_size": company.meic_size,
                    "province": company.province,
                    "canton": company.canton,
                    "email": company.email,
                    "phone": company.phone,
                    "website": company.website,
                    "status": company.status.value,
                    "status_label": STATUS_LABELS[company.status],
                    "priority": company.prospect_priority.value,
                    "priority_label": PRIORITY_LABELS[company.prospect_priority],
                    "next_follow_up_date": company.next_follow_up_date,
                    "responsible_person": company.responsible_person,
                    "contact_result": company.contact_result,
                    "certification_valid_until": company.certification_valid_until,
                }
                for company in companies
            ]
        )


@st.cache_data(ttl=60)
def load_filter_values() -> tuple[list[str], list[str], list[str]]:
    with SessionLocal() as session:
        companies = session.scalars(select(Company)).all()
        sectors = sorted({company.sector for company in companies if company.sector})
        sizes = sorted({company.meic_size for company in companies if company.meic_size})
        provinces = sorted({company.province for company in companies if company.province})
        return sectors, sizes, provinces


def get_company(company_id: int) -> Company | None:
    with SessionLocal() as session:
        return session.scalar(
            select(Company)
            .options(
                selectinload(Company.contact_methods),
                selectinload(Company.contact_discovery_results),
                selectinload(Company.certification_statuses),
                selectinload(Company.data_sources),
                selectinload(Company.outreach_notes),
            )
            .where(Company.id == company_id)
        )


def add_outreach_note(
    company_id: int, note: str, channel: str | None, next_action: str | None, created_by: str | None
) -> None:
    with SessionLocal() as session:
        session.add(
            OutreachNote(
                company_id=company_id,
                note=note,
                channel=channel,
                next_action=next_action,
                created_by=created_by,
            )
        )
        session.commit()
    st.cache_data.clear()


def add_company_contact_method(
    company_id: int,
    name: str,
    contact_medium: str,
    contact_type: ContactMethodType,
) -> None:
    with SessionLocal() as session:
        session.add(
            CompanyContactMethod(
                company_id=company_id,
                name=name,
                contact_medium=contact_medium,
                contact_type=contact_type,
            )
        )
        session.commit()
    st.cache_data.clear()


def update_company_contact_method(
    contact_id: int,
    name: str,
    contact_medium: str,
    contact_type: ContactMethodType,
) -> None:
    with SessionLocal() as session:
        contact = session.get(CompanyContactMethod, contact_id)
        if contact:
            contact.name = name
            contact.contact_medium = contact_medium
            contact.contact_type = contact_type
            session.commit()
    st.cache_data.clear()


def delete_company_contact_method(contact_id: int) -> None:
    with SessionLocal() as session:
        contact = session.get(CompanyContactMethod, contact_id)
        if contact:
            session.delete(contact)
            session.commit()
    st.cache_data.clear()


def delete_outreach_note(note_id: int) -> None:
    with SessionLocal() as session:
        note = session.get(OutreachNote, note_id)
        if note:
            session.delete(note)
            session.commit()
    st.cache_data.clear()


def run_contact_discovery(company_id: int) -> int:
    with SessionLocal() as session:
        company = session.get(Company, company_id)
        if not company:
            return 0
        discovered_count = discover_company_contacts(session, company)
    st.cache_data.clear()
    return discovered_count


def accept_discovered_contact(result_id: int) -> None:
    with SessionLocal() as session:
        result = session.get(CompanyContactDiscoveryResult, result_id)
        if result and result.status == DiscoveryResultStatus.pending:
            session.add(
                CompanyContactMethod(
                    company_id=result.company_id,
                    name=result.candidate_name or result.source_title or "Contacto encontrado",
                    contact_medium=result.contact_medium,
                    contact_type=result.contact_type,
                )
            )
            result.status = DiscoveryResultStatus.accepted
            result.accepted_at = datetime.now()
            session.commit()
    st.cache_data.clear()


def reject_discovered_contact(result_id: int) -> None:
    with SessionLocal() as session:
        result = session.get(CompanyContactDiscoveryResult, result_id)
        if result and result.status == DiscoveryResultStatus.pending:
            result.status = DiscoveryResultStatus.rejected
            result.rejected_at = datetime.now()
            session.commit()
    st.cache_data.clear()


def update_company_tracking(
    company_id: int,
    status: CompanyStatus,
    priority: ProspectPriority,
    next_follow_up_date: date | None,
    responsible_person: str | None,
    contact_result: str | None,
) -> None:
    with SessionLocal() as session:
        company = session.get(Company, company_id)
        if company:
            company.status = status
            company.prospect_priority = priority
            company.next_follow_up_date = next_follow_up_date
            company.responsible_person = responsible_person
            company.contact_result = contact_result
            session.commit()
    st.cache_data.clear()


def company_table(companies_df: pd.DataFrame) -> int | None:
    page_size = st.session_state.get("company_table_page_size", 25)
    total_rows = len(companies_df)
    total_pages = max(1, (total_rows + page_size - 1) // page_size)

    current_page = st.session_state.get("company_table_page", 1)
    current_page = min(max(current_page, 1), total_pages)
    st.session_state.company_table_page = current_page

    start = (current_page - 1) * page_size
    end = start + page_size
    page_df = companies_df.iloc[start:end].reset_index(drop=True)
    display_df = page_df[
        [
            "tax_id",
            "legal_name",
            "sector",
            "meic_size",
            "certification_valid_until",
            "province",
            "status_label",
        ]
    ].rename(
        columns={
            "tax_id": "IDENTIFICACION",
            "legal_name": "NOMBRE",
            "sector": "SECTOR",
            "meic_size": "TAMAÑO",
            "certification_valid_until": "FECHA_VIGENCIA",
            "province": "PROVINCIA",
            "status_label": "ESTADO COMERCIAL",
        }
    )

    table_height = min(720, 38 * (len(display_df) + 1))
    table_event = st.dataframe(
        display_df,
        hide_index=True,
        use_container_width=True,
        height=table_height,
        selection_mode="single-row",
        on_select="rerun",
        column_config={
            "IDENTIFICACION": st.column_config.TextColumn("IDENTIFICACION", width="small"),
            "NOMBRE": st.column_config.TextColumn("NOMBRE", width="large"),
            "SECTOR": st.column_config.TextColumn("SECTOR", width="medium"),
            "TAMAÑO": st.column_config.TextColumn("TAMAÑO", width="small"),
            "FECHA_VIGENCIA": st.column_config.DateColumn(
                "FECHA_VIGENCIA",
                width="small",
                format="DD/MM/YYYY",
            ),
            "PROVINCIA": st.column_config.TextColumn("PROVINCIA", width="small"),
            "ESTADO COMERCIAL": st.column_config.TextColumn("ESTADO COMERCIAL", width="medium"),
        },
    )

    nav_left, nav_size, nav_mid, nav_right = st.columns([1, 1, 2, 1])
    with nav_left:
        if st.button("Página anterior", disabled=current_page <= 1):
            st.session_state.company_table_page = current_page - 1
            st.rerun()
    with nav_size:
        selected_page_size = st.selectbox(
            "Filas por página",
            [10, 25, 50],
            index=[10, 25, 50].index(page_size),
            key="company_table_page_size",
        )
        if selected_page_size != page_size:
            st.session_state.company_table_page = 1
            st.rerun()
    with nav_mid:
        st.write(f"Página {current_page} de {total_pages} · {total_rows} empresas")
    with nav_right:
        if st.button("Página siguiente", disabled=current_page >= total_pages):
            st.session_state.company_table_page = current_page + 1
            st.rerun()

    selected_rows = table_event.selection.rows
    if not selected_rows:
        return None
    selected_position = selected_rows[0]
    return int(page_df.iloc[selected_position]["id"])


def format_display_date(value: date | None) -> str:
    if value is None:
        return "sin fecha"
    return value.strftime("%d/%m/%Y")


def optional_date_input(label: str, value: date | None) -> date | None:
    enabled = st.checkbox(f"Definir {label.lower()}", value=value is not None, key=f"enable_{label}")
    if not enabled:
        return None
    return st.date_input(label, value=value or date.today(), format="DD/MM/YYYY")


def render_company_detail(company: Company) -> None:
    st.markdown(f"### {company.legal_name}")

    summary_left, summary_right = st.columns(2)
    summary_left.metric("Estado comercial", STATUS_LABELS[company.status])
    summary_right.metric("Prioridad", PRIORITY_LABELS[company.prospect_priority])

    with st.expander("Seguimiento comercial", expanded=True):
        status_options = list(STATUS_LABELS.values())
        priority_options = list(PRIORITY_LABELS.values())

        tracking_left, tracking_right = st.columns(2)
        with tracking_left:
            selected_status_label = st.selectbox(
                "Estado comercial",
                status_options,
                index=status_options.index(STATUS_LABELS[company.status]),
            )
            selected_priority_label = st.selectbox(
                "Prioridad",
                priority_options,
                index=priority_options.index(PRIORITY_LABELS[company.prospect_priority]),
            )
            responsible_person = st.text_input("Responsable", value=company.responsible_person or "")
        with tracking_right:
            contact_result = st.text_input("Resultado del contacto", value=company.contact_result or "")
            next_follow_up_date = optional_date_input(
                "Próximo seguimiento", company.next_follow_up_date
            )

        if st.button("Guardar seguimiento"):
            update_company_tracking(
                company.id,
                STATUS_BY_LABEL[selected_status_label],
                PRIORITY_BY_LABEL[selected_priority_label],
                next_follow_up_date,
                responsible_person.strip() or None,
                contact_result.strip() or None,
            )
            st.success("Seguimiento actualizado.")
            st.rerun()

    contacts_tab, add_note_tab, history_tab = st.tabs(
        ["Contactos", "Agregar nota comercial", "Historial comercial"]
    )

    with contacts_tab:
        st.markdown("#### Contactos")
        if st.session_state.pop("contact_success", None):
            st.success("Contacto guardado correctamente.")
        if st.session_state.pop("contact_deleted", None):
            st.success("Contacto eliminado correctamente.")

        editing_contact_id = st.session_state.get("editing_contact_id")
        editing_contact = next(
            (contact for contact in company.contact_methods if contact.id == editing_contact_id),
            None,
        )
        form_suffix = editing_contact.id if editing_contact else "new"
        contact_type_values = [contact_type.value for contact_type in ContactMethodType]

        form_title = "Modificar contacto" if editing_contact else "Nuevo contacto"
        st.markdown(f"##### {form_title}")
        if editing_contact and st.button("Nuevo", key="new_contact_mode"):
            st.session_state.pop("editing_contact_id", None)
            st.session_state.pop("pending_delete_contact_id", None)
            st.rerun()

        with st.form(f"company_contact_method_form_{form_suffix}", clear_on_submit=editing_contact is None):
            contact_name = st.text_input(
                "Nombre",
                value=editing_contact.name if editing_contact else "",
                key=f"contact_name_form_{form_suffix}",
            )
            contact_medium = st.text_input(
                "Medio de contacto",
                value=editing_contact.contact_medium if editing_contact else "",
                placeholder="correo@empresa.com o número",
                key=f"contact_medium_form_{form_suffix}",
            )
            selected_contact_type = editing_contact.contact_type.value if editing_contact else contact_type_values[0]
            contact_type_label = st.selectbox(
                "Tipo de contacto",
                contact_type_values,
                index=contact_type_values.index(selected_contact_type),
                key=f"contact_type_form_{form_suffix}",
            )
            contact_submitted = st.form_submit_button("Guardar cambios" if editing_contact else "Agregar contacto")
            if contact_submitted:
                if not contact_name.strip() or not contact_medium.strip():
                    st.error("El nombre y el medio de contacto son obligatorios.")
                elif editing_contact:
                    update_company_contact_method(
                        editing_contact.id,
                        name=contact_name.strip(),
                        contact_medium=contact_medium.strip(),
                        contact_type=ContactMethodType(contact_type_label),
                    )
                    st.session_state.contact_success = True
                    st.session_state.pop("editing_contact_id", None)
                    st.rerun()
                else:
                    add_company_contact_method(
                        company.id,
                        name=contact_name.strip(),
                        contact_medium=contact_medium.strip(),
                        contact_type=ContactMethodType(contact_type_label),
                    )
                    st.session_state.contact_success = True
                    st.rerun()

        st.markdown("##### Contactos registrados")
        if company.contact_methods:
            header_name, header_medium, header_type, header_actions = st.columns([2, 3, 1.5, 2])
            header_name.markdown("**Nombre**")
            header_medium.markdown("**Medio de contacto**")
            header_type.markdown("**Tipo**")
            header_actions.markdown("**Acciones**")

            for contact in company.contact_methods:
                row_name, row_medium, row_type, row_actions = st.columns([2, 3, 1.5, 2])
                row_name.write(contact.name)
                row_medium.write(contact.contact_medium)
                row_type.write(contact.contact_type.value)
                with row_actions:
                    modify_col, delete_col = st.columns(2)
                    if modify_col.button("Modificar", key=f"edit_contact_{contact.id}"):
                        st.session_state.editing_contact_id = contact.id
                        st.session_state.pop("pending_delete_contact_id", None)
                        st.rerun()
                    if delete_col.button("Eliminar", key=f"request_delete_contact_{contact.id}"):
                        st.session_state.pending_delete_contact_id = contact.id
                        st.rerun()

                if st.session_state.get("pending_delete_contact_id") == contact.id:
                    st.warning(f"¿Eliminar el contacto de {contact.name}?")
                    confirm_col, cancel_col = st.columns([1, 5])
                    if confirm_col.button("Sí, eliminar", key=f"confirm_delete_contact_{contact.id}"):
                        delete_company_contact_method(contact.id)
                        st.session_state.contact_deleted = True
                        st.session_state.pop("pending_delete_contact_id", None)
                        if st.session_state.get("editing_contact_id") == contact.id:
                            st.session_state.pop("editing_contact_id", None)
                        st.rerun()
                    if cancel_col.button("Cancelar", key=f"cancel_delete_contact_{contact.id}"):
                        st.session_state.pop("pending_delete_contact_id", None)
                        st.rerun()
        else:
            st.info("No hay contactos registrados.")

        st.markdown("##### Búsqueda automática")
        if st.session_state.pop("contact_discovery_success", None):
            st.success("Búsqueda completada. Revisá los candidatos encontrados.")
        if st.session_state.pop("contact_discovery_accepted", None):
            st.success("Candidato agregado como contacto válido.")
        if st.session_state.pop("contact_discovery_rejected", None):
            st.success("Candidato descartado.")

        if st.button("Buscar contactos en internet", key=f"discover_contacts_{company.id}"):
            try:
                with st.spinner("Buscando contactos en internet... Esto puede tardar unos segundos."):
                    discovered_count = run_contact_discovery(company.id)
                if discovered_count:
                    st.session_state.contact_discovery_success = True
                else:
                    st.info("No se encontraron candidatos nuevos para esta empresa.")
            except (ContactDiscoveryConfigError, ContactDiscoveryRuntimeError) as exc:
                st.warning(str(exc))
            else:
                st.rerun()

        pending_results = [
            result
            for result in company.contact_discovery_results
            if result.status == DiscoveryResultStatus.pending
        ]
        if pending_results:
            result_headers = st.columns([2, 2.5, 1.2, 1.2, 3])
            result_headers[0].markdown("**Tipo**")
            result_headers[1].markdown("**Medio**")
            result_headers[2].markdown("**Confianza**")
            result_headers[3].markdown("**Fuente**")
            result_headers[4].markdown("**Acciones**")
            for result in pending_results:
                type_col, medium_col, confidence_col, source_col, action_col = st.columns([2, 2.5, 1.2, 1.2, 3])
                type_col.write(result.contact_type.value)
                medium_col.write(result.contact_medium)
                confidence_col.write(result.confidence)
                if result.source_url:
                    source_col.link_button("Abrir", result.source_url)
                else:
                    source_col.write("Sin URL")
                with action_col:
                    accept_col, reject_col = st.columns(2)
                    if accept_col.button("Usar como contacto", key=f"accept_discovery_{result.id}"):
                        accept_discovered_contact(result.id)
                        st.session_state.contact_discovery_accepted = True
                        st.rerun()
                    if reject_col.button("Descartar", key=f"reject_discovery_{result.id}"):
                        reject_discovered_contact(result.id)
                        st.session_state.contact_discovery_rejected = True
                        st.rerun()
        else:
            st.caption("No hay candidatos pendientes de revisar.")

    with add_note_tab:
        if st.session_state.pop("note_success", None):
            st.success("Nota comercial guardada correctamente.")
        with st.form("add_outreach_note", clear_on_submit=True):
            st.markdown("#### Agregar nota comercial")
            note = st.text_area("Nota")
            channel = st.text_input("Canal", placeholder="correo, teléfono, LinkedIn, reunión")
            next_action = st.text_input("Próxima acción")
            created_by = st.text_input("Creado por")
            submitted = st.form_submit_button("Agregar nota")
            if submitted:
                if not note.strip():
                    st.error("La nota es obligatoria.")
                else:
                    add_outreach_note(
                        company.id,
                        note=note.strip(),
                        channel=channel.strip() or None,
                        next_action=next_action.strip() or None,
                        created_by=created_by.strip() or None,
                    )
                    st.session_state.note_success = True
                    st.rerun()

    with history_tab:
        st.markdown("#### Historial comercial")
        if st.session_state.pop("note_deleted", None):
            st.success("Nota comercial eliminada correctamente.")
        if company.outreach_notes:
            for note in company.outreach_notes:
                note_text = (
                    f"{format_display_date(note.created_at)} | {note.channel or 'sin canal'} | "
                    f"{note.note} | Próxima acción: {note.next_action or 'ninguna'}"
                )
                note_col, delete_col = st.columns([12, 1])
                note_col.info(note_text)
                if delete_col.button("❌", key=f"delete_note_{note.id}", help="Eliminar nota"):
                    delete_outreach_note(note.id)
                    st.session_state.note_deleted = True
                    st.rerun()
        else:
            st.info("Todavía no hay notas comerciales.")


with st.sidebar:
    st.header("Filtros")
    if st.button("Inicializar / actualizar tablas"):
        init_db()
        added_columns = evolve_local_schema(engine)
        if added_columns:
            st.success("Tablas actualizadas: " + ", ".join(added_columns))
        else:
            st.success("Las tablas de la base de datos están listas.")
        st.cache_data.clear()

    try:
        sectors, sizes, provinces = load_filter_values()
    except SQLAlchemyError as exc:
        sectors, sizes, provinces = [], [], []
        st.warning(
            f"La base de datos todavía no está lista: {exc.__class__.__name__}. "
            "Inicializá las tablas después de levantar la base."
        )

    if st.button("Limpiar filtros"):
        st.session_state.filter_search = ""
        st.session_state.filter_sector = "Todos"
        st.session_state.filter_meic_size = "Todos"
        st.session_state.filter_start_date = None
        st.session_state.filter_end_date = None
        st.session_state.filter_province = "Todas"
        st.session_state.filter_commercial_status = "Todos"
        st.session_state.company_table_page = 1
        st.rerun()

    search = st.text_input("Buscar empresa", key="filter_search")
    sector = st.selectbox("Sector", ["Todos", *sectors], key="filter_sector")
    meic_size = st.selectbox("Tamaño", ["Todos", *sizes], key="filter_meic_size")
    start_date = st.date_input(
        "Fecha inicio",
        value=None,
        format="DD/MM/YYYY",
        key="filter_start_date",
    )
    end_date = st.date_input(
        "Fecha fin",
        value=None,
        format="DD/MM/YYYY",
        key="filter_end_date",
    )
    province = st.selectbox("Provincia", ["Todas", *provinces], key="filter_province")
    commercial_status = st.selectbox(
        "Estado comercial",
        ["Todos", *STATUS_LABELS.values()],
        key="filter_commercial_status",
    )

if start_date and end_date and start_date > end_date:
    st.warning("La fecha inicio no puede ser posterior a la fecha fin.")
    companies_df = pd.DataFrame()
else:
    try:
        companies_df = load_companies(
            search,
            sector,
            meic_size,
            start_date,
            end_date,
            province,
            commercial_status,
        )
    except SQLAlchemyError as exc:
        st.warning(
            f"No se pudieron cargar las empresas: {exc.__class__.__name__}. "
            "Inicializá la base de datos e importá datos primero."
        )
        companies_df = pd.DataFrame()

st.subheader("Empresas")
if companies_df.empty:
    st.info("No hay empresas que coincidan con los filtros actuales.")
else:
    selected_company_id = company_table(companies_df)

    csv_buffer = StringIO()
    export_df = companies_df.drop(columns=["status_label", "priority_label"]).rename(
        columns={"status": "pipeline_status"}
    )
    export_df.to_csv(csv_buffer, index=False)
    st.download_button(
        "Exportar empresas filtradas a CSV",
        data=csv_buffer.getvalue(),
        file_name="empresas_filtradas.csv",
        mime="text/csv",
    )

    st.divider()
    st.subheader("Detalle de la empresa")
    if selected_company_id is None:
        st.info("Seleccioná una fila de la tabla principal para ver el detalle interactivo.")
    else:
        company = get_company(selected_company_id)
        if company:
            render_company_detail(company)
        else:
            st.warning("No se encontró la empresa seleccionada.")
