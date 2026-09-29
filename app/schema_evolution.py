from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


COMPANY_COLUMNS = {
    "prospect_priority": "VARCHAR(32) NOT NULL DEFAULT 'medium'",
    "next_follow_up_date": "DATE",
    "responsible_person": "VARCHAR(128)",
    "contact_result": "VARCHAR(255)",
    "pyme_interest": "VARCHAR(64) NOT NULL DEFAULT 'unknown'",
    "estimated_renewal_date": "DATE",
}

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
            added.append(f"{table_name}.{column_name}")

    return added


def evolve_local_schema(engine: Engine) -> list[str]:
    """Apply additive MVP schema changes for local SQLite/PostgreSQL databases.

    This is intentionally small and additive. Use Alembic before production schema changes.
    """
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    added: list[str] = []
    if "companies" in table_names:
        added.extend(add_missing_columns(engine, "companies", COMPANY_COLUMNS))
    if "data_sources" in table_names:
        added.extend(add_missing_columns(engine, "data_sources", DATA_SOURCE_COLUMNS))
    return added
