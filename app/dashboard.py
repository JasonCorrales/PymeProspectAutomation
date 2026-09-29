from __future__ import annotations

from io import StringIO

import pandas as pd
import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import selectinload

from app.config import settings
from app.db import SessionLocal, init_db
from app.models import Company, CompanyStatus, OutreachNote


STATUS_LABELS: dict[CompanyStatus, str] = {
    CompanyStatus.new: "Nuevo",
    CompanyStatus.reviewed: "Revisado",
    CompanyStatus.contacted: "Contactado",
    CompanyStatus.qualified: "Calificado",
    CompanyStatus.disqualified: "Descartado",
}
STATUS_BY_LABEL = {label: status for status, label in STATUS_LABELS.items()}

SOURCE_TYPE_LABELS = {
    "sample_csv": "CSV de muestra",
    "public_directory": "Directorio público",
    "referral": "Referencia",
    "manual": "Manual",
}


st.set_page_config(page_title=settings.app_title, layout="wide")
st.title("Prospectos PYME Costa Rica")
st.caption(
    "Dashboard local para revisar prospectos PYME, fuentes, certificación y seguimiento comercial. "
    "Este MVP no realiza scraping en vivo."
)


@st.cache_data(ttl=30)
def load_companies(search: str, province: str, sector: str, status: str) -> pd.DataFrame:
    with SessionLocal() as session:
        query = select(Company)
        if search:
            like = f"%{search.lower()}%"
            query = query.where(Company.normalized_name.like(like))
        if province and province != "Todas":
            query = query.where(Company.province == province)
        if sector and sector != "Todos":
            query = query.where(Company.sector == sector)
        if status and status != "Todos":
            query = query.where(Company.status == STATUS_BY_LABEL[status])

        companies = session.scalars(query.order_by(Company.legal_name)).all()
        return pd.DataFrame(
            [
                {
                    "id": company.id,
                    "legal_name": company.legal_name,
                    "trade_name": company.trade_name,
                    "sector": company.sector,
                    "province": company.province,
                    "canton": company.canton,
                    "email": company.email,
                    "phone": company.phone,
                    "website": company.website,
                    "status": company.status.value,
                    "status_label": STATUS_LABELS[company.status],
                }
                for company in companies
            ]
        )


@st.cache_data(ttl=60)
def load_filter_values() -> tuple[list[str], list[str]]:
    with SessionLocal() as session:
        companies = session.scalars(select(Company)).all()
        provinces = sorted({company.province for company in companies if company.province})
        sectors = sorted({company.sector for company in companies if company.sector})
        return provinces, sectors


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


def update_company_status(company_id: int, status: CompanyStatus) -> None:
    with SessionLocal() as session:
        company = session.get(Company, company_id)
        if company:
            company.status = status
            session.commit()
    st.cache_data.clear()


def company_table(companies_df: pd.DataFrame) -> int | None:
    display_df = companies_df[
        [
            "id",
            "legal_name",
            "trade_name",
            "sector",
            "province",
            "canton",
            "email",
            "phone",
            "status_label",
        ]
    ].rename(
        columns={
            "id": "ID",
            "legal_name": "Razón social",
            "trade_name": "Nombre comercial",
            "sector": "Sector",
            "province": "Provincia",
            "canton": "Cantón",
            "email": "Correo",
            "phone": "Teléfono",
            "status_label": "Estado",
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
            "ID": st.column_config.NumberColumn("ID", width="small"),
            "Razón social": st.column_config.TextColumn("Razón social", width="medium"),
            "Nombre comercial": st.column_config.TextColumn("Nombre comercial", width="medium"),
            "Sector": st.column_config.TextColumn("Sector", width="medium"),
            "Provincia": st.column_config.TextColumn("Provincia", width="small"),
            "Cantón": st.column_config.TextColumn("Cantón", width="small"),
            "Correo": st.column_config.TextColumn("Correo", width="medium"),
            "Teléfono": st.column_config.TextColumn("Teléfono", width="small"),
            "Estado": st.column_config.TextColumn("Estado", width="small"),
        },
    )

    selected_rows = table_event.selection.rows
    if not selected_rows:
        return None
    selected_position = selected_rows[0]
    return int(companies_df.iloc[selected_position]["id"])


def render_company_detail(company: Company) -> None:
    st.markdown(f"### {company.legal_name}")

    summary_left, summary_mid, summary_right = st.columns(3)
    summary_left.metric("Estado comercial", STATUS_LABELS[company.status])
    summary_mid.metric("Sector", company.sector or "Sin dato")
    summary_right.metric("Ubicación", ", ".join(part for part in [company.canton, company.province] if part) or "Sin dato")

    with st.expander("Información general", expanded=True):
        st.write(
            {
                "Nombre comercial": company.trade_name,
                "Razón social": company.legal_name,
                "Sitio web": company.website,
                "Correo principal": company.email,
                "Teléfono principal": company.phone,
                "Notas": company.notes,
            }
        )

    status_options = list(STATUS_LABELS.values())
    selected_status_label = st.selectbox(
        "Actualizar estado comercial",
        status_options,
        index=status_options.index(STATUS_LABELS[company.status]),
    )
    if st.button("Guardar estado"):
        update_company_status(company.id, STATUS_BY_LABEL[selected_status_label])
        st.success("Estado actualizado.")
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
                "Estado": cert.status,
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
                    f"URL: {source.source_url or 'Sin URL'}\n\n"
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
    if st.button("Inicializar tablas"):
        init_db()
        st.success("Las tablas de la base de datos están listas.")
        st.cache_data.clear()

    try:
        provinces, sectors = load_filter_values()
    except SQLAlchemyError as exc:
        provinces, sectors = [], []
        st.warning(
            f"La base de datos todavía no está lista: {exc.__class__.__name__}. "
            "Inicializá las tablas después de levantar la base."
        )

    search = st.text_input("Buscar empresa")
    province = st.selectbox("Provincia", ["Todas", *provinces])
    sector = st.selectbox("Sector", ["Todos", *sectors])
    status = st.selectbox("Estado", ["Todos", *STATUS_LABELS.values()])

try:
    companies_df = load_companies(search, province, sector, status)
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
    export_df = companies_df.drop(columns=["status_label"]).rename(columns={"status": "pipeline_status"})
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
