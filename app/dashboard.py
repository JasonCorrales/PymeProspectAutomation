from __future__ import annotations

from datetime import date
from io import StringIO

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import SessionLocal, engine, init_db
from app.models import (
    Company,
    CompanyStatus,
    OutreachNote,
    ProspectPriority,
    PymeInterest,
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

PYME_INTEREST_LABELS: dict[PymeInterest, str] = {
    PymeInterest.unknown: "Desconocido",
    PymeInterest.interested: "Interesado",
    PymeInterest.not_interested: "No interesado",
    PymeInterest.already_certified: "Ya certificado",
    PymeInterest.needs_education: "Necesita educación",
}
PYME_INTEREST_BY_LABEL = {label: interest for interest, label in PYME_INTEREST_LABELS.items()}

SOURCE_TYPE_LABELS = {
    "sample_csv": "CSV de muestra",
    "approved_pilot_csv": "CSV piloto aprobado",
    "public_directory": "Directorio público",
    "referral": "Referencia",
    "manual": "Manual",
}


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
            query = query.where(Company.estimated_renewal_date >= start_date)
        if end_date:
            query = query.where(Company.estimated_renewal_date <= end_date)
        if province and province != "Todas":
            query = query.where(Company.province == province)

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
                    "pyme_interest": company.pyme_interest.value,
                    "pyme_interest_label": PYME_INTEREST_LABELS[company.pyme_interest],
                    "estimated_renewal_date": company.estimated_renewal_date,
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
                selectinload(Company.contacts),
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


def update_company_tracking(
    company_id: int,
    status: CompanyStatus,
    priority: ProspectPriority,
    next_follow_up_date: date | None,
    responsible_person: str | None,
    contact_result: str | None,
    pyme_interest: PymeInterest,
    estimated_renewal_date: date | None,
) -> None:
    with SessionLocal() as session:
        company = session.get(Company, company_id)
        if company:
            company.status = status
            company.prospect_priority = priority
            company.next_follow_up_date = next_follow_up_date
            company.responsible_person = responsible_person
            company.contact_result = contact_result
            company.pyme_interest = pyme_interest
            company.estimated_renewal_date = estimated_renewal_date
            session.commit()
    st.cache_data.clear()


def company_table(companies_df: pd.DataFrame) -> int | None:
    page_size = st.selectbox("Filas por página", [10, 25, 50], index=1)
    total_rows = len(companies_df)
    total_pages = max(1, (total_rows + page_size - 1) // page_size)

    current_page = st.session_state.get("company_table_page", 1)
    current_page = min(max(current_page, 1), total_pages)
    st.session_state.company_table_page = current_page

    nav_left, nav_mid, nav_right = st.columns([1, 2, 1])
    with nav_left:
        if st.button("Página anterior", disabled=current_page <= 1):
            st.session_state.company_table_page = current_page - 1
            st.rerun()
    with nav_mid:
        st.write(f"Página {current_page} de {total_pages} · {total_rows} empresas")
    with nav_right:
        if st.button("Página siguiente", disabled=current_page >= total_pages):
            st.session_state.company_table_page = current_page + 1
            st.rerun()

    start = (current_page - 1) * page_size
    end = start + page_size
    page_df = companies_df.iloc[start:end].reset_index(drop=True)
    display_df = page_df[
        [
            "tax_id",
            "legal_name",
            "sector",
            "meic_size",
            "estimated_renewal_date",
            "province",
        ]
    ].rename(
        columns={
            "tax_id": "IDENTIFICACION",
            "legal_name": "NOMBRE",
            "sector": "SECTOR",
            "meic_size": "TAMAÑO",
            "estimated_renewal_date": "FECHA_VIGENCIA",
            "province": "PROVINCIA",
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
        },
    )

    selected_rows = table_event.selection.rows
    if not selected_rows:
        return None
    selected_position = selected_rows[0]
    return int(page_df.iloc[selected_position]["id"])


def optional_date_input(label: str, value: date | None) -> date | None:
    enabled = st.checkbox(f"Definir {label.lower()}", value=value is not None, key=f"enable_{label}")
    if not enabled:
        return None
    return st.date_input(label, value=value or date.today())


def render_company_detail(company: Company) -> None:
    st.markdown(f"### {company.legal_name}")

    summary_left, summary_mid, summary_right = st.columns(3)
    summary_left.metric("Estado comercial", STATUS_LABELS[company.status])
    summary_mid.metric("Prioridad", PRIORITY_LABELS[company.prospect_priority])
    summary_right.metric("Interés PYME", PYME_INTEREST_LABELS[company.pyme_interest])

    with st.expander("Información general", expanded=True):
        st.write(
            {
                "Nombre comercial": company.trade_name,
                "Razón social": company.legal_name,
                "Identificación": company.tax_id,
                "Sector": company.sector,
                "Tamaño MEIC": company.meic_size,
                "Fecha de vigencia": company.estimated_renewal_date,
                "Ubicación": ", ".join(part for part in [company.canton, company.province] if part),
                "Sitio web": company.website,
                "Correo principal": company.email,
                "Teléfono principal": company.phone,
                "Notas": company.notes,
            }
        )

    with st.expander("Seguimiento comercial", expanded=True):
        status_options = list(STATUS_LABELS.values())
        priority_options = list(PRIORITY_LABELS.values())
        interest_options = list(PYME_INTEREST_LABELS.values())

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
            next_follow_up_date = optional_date_input(
                "Próximo seguimiento", company.next_follow_up_date
            )
        with tracking_right:
            selected_interest_label = st.selectbox(
                "Interés en certificación PYME",
                interest_options,
                index=interest_options.index(PYME_INTEREST_LABELS[company.pyme_interest]),
            )
            contact_result = st.text_input("Resultado del contacto", value=company.contact_result or "")
            estimated_renewal_date = optional_date_input(
                "Renovación estimada", company.estimated_renewal_date
            )

        if st.button("Guardar seguimiento"):
            update_company_tracking(
                company.id,
                STATUS_BY_LABEL[selected_status_label],
                PRIORITY_BY_LABEL[selected_priority_label],
                next_follow_up_date,
                responsible_person.strip() or None,
                contact_result.strip() or None,
                PYME_INTEREST_BY_LABEL[selected_interest_label],
                estimated_renewal_date,
            )
            st.success("Seguimiento actualizado.")
            st.rerun()

    detail_left, detail_right = st.columns(2)
    with detail_left:
        st.markdown("#### Contactos")
        contacts = [
            {
                "Nombre": contact.name,
                "Cargo": contact.role,
                "Correo": contact.email,
                "Teléfono": contact.phone,
                "Principal": "Sí" if contact.is_primary else "No",
            }
            for contact in company.contacts
        ]
        st.table(contacts or [{"Resultado": "No hay contactos registrados."}])

        st.markdown("#### Certificación PYME")
        certifications = [
            {
                "Certificación": cert.certification_name,
                "Estado seguro": cert.status.value,
                "Fuente": cert.evidence_url,
                "Evidencia": cert.evidence_text,
            }
            for cert in company.certification_statuses
        ]
        st.table(certifications or [{"Resultado": "No hay certificaciones registradas."}])

    with detail_right:
        st.markdown("#### Fuentes y evidencia")
        if company.data_sources:
            for source in company.data_sources:
                st.info(
                    f"**{source.source_name}** · "
                    f"{SOURCE_TYPE_LABELS.get(source.source_type.value, source.source_type.value)}\n\n"
                    f"Términos/uso: {source.terms_status or 'Sin validar'}\n\n"
                    f"URL: {source.source_url or 'Sin URL'}\n\n"
                    f"Notas de uso: {source.usage_notes or 'Sin notas'}\n\n"
                    f"Evidencia: {source.evidence_text or 'Sin evidencia textual'}"
                )
        else:
            st.info("No hay fuentes registradas.")

        st.markdown("#### Historial comercial")
        if company.outreach_notes:
            for note in company.outreach_notes:
                st.info(
                    f"{note.created_at:%Y-%m-%d %H:%M} | {note.channel or 'sin canal'} | "
                    f"{note.note} | Próxima acción: {note.next_action or 'ninguna'}"
                )
        else:
            st.info("Todavía no hay notas comerciales.")

    with st.form("add_outreach_note"):
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
                st.success("Nota comercial agregada.")
                st.rerun()


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

if start_date and end_date and start_date > end_date:
    st.warning("La fecha inicio no puede ser posterior a la fecha fin.")
    companies_df = pd.DataFrame()
else:
    try:
        companies_df = load_companies(search, sector, meic_size, start_date, end_date, province)
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
    export_df = companies_df.drop(columns=["status_label", "priority_label", "pyme_interest_label"]).rename(
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
