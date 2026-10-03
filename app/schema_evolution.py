from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from app.models import CompanyContactMethod


COMPANY_COLUMNS = {
    "prospect_priority": "VARCHAR(32) NOT NULL DEFAULT 'medium'",
    "next_follow_up_date": "DATE",
    "responsible_person": "VARCHAR(128)",
    "contact_result": "VARCHAR(255)",
    "certification_valid_until": "DATE",
    "meic_size": "VARCHAR(64)",
}

REMOVED_COMPANY_COLUMNS = ("pyme_interest", "estimated_renewal_date")

DATA_SOURCE_COLUMNS = {
    "terms_status": "VARCHAR(128)",
    "usage_notes": "TEXT",
}


def add_missing_columns(engine: Engine, table_name: str, columns: dict[str, str]) -> list[str]:
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    added: list[str] = []

    with engine.begin() as connection:
        for column_name, ddl_type in columns.items():
            if column_name in existing_columns:
                continue
            connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl_type}"))
            added.append(f"added {table_name}.{column_name}")

    return added


def migrate_company_validity_date(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns("companies")}
    changes: list[str] = []
    if {"certification_valid_until", "estimated_renewal_date"}.issubset(existing_columns):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE companies "
                    "SET certification_valid_until = estimated_renewal_date "
                    "WHERE certification_valid_until IS NULL AND estimated_renewal_date IS NOT NULL"
                )
            )
        changes.append("migrated companies.estimated_renewal_date to companies.certification_valid_until")
    return changes


def drop_removed_company_columns(engine: Engine) -> list[str]:
    """Drop removed columns when the local database supports ALTER TABLE DROP COLUMN."""
    inspector = inspect(engine)
    existing_columns = {column["name"] for column in inspector.get_columns("companies")}
    changes: list[str] = []

    for column_name in REMOVED_COMPANY_COLUMNS:
        if column_name not in existing_columns:
            continue
        try:
            with engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE companies DROP COLUMN {column_name}"))
            changes.append(f"dropped companies.{column_name}")
        except SQLAlchemyError as exc:
            changes.append(f"could not drop companies.{column_name}: {exc.__class__.__name__}")

    return changes


def create_company_contact_methods_table(engine: Engine) -> list[str]:
    inspector = inspect(engine)
    if "company_contact_methods" in inspector.get_table_names():
        return []
    CompanyContactMethod.__table__.create(engine, checkfirst=True)
    return ["created company_contact_methods table"]


def evolve_local_schema(engine: Engine) -> list[str]:
    """Apply MVP schema changes for local SQLite/PostgreSQL databases.

    The helper keeps development databases moving until Alembic exists: it adds the
    certification validity date, copies legacy estimated-renewal values into it,
    drops removed columns when the database backend allows it, and creates the
    dedicated company contact-method table.
    """
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    changes: list[str] = []
    if "companies" in table_names:
        changes.extend(add_missing_columns(engine, "companies", COMPANY_COLUMNS))
        changes.extend(migrate_company_validity_date(engine))
        changes.extend(drop_removed_company_columns(engine))
        changes.extend(create_company_contact_methods_table(engine))
    if "data_sources" in table_names:
        changes.extend(add_missing_columns(engine, "data_sources", DATA_SOURCE_COLUMNS))
    return changes
