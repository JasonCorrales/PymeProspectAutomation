from __future__ import annotations

from app.db import engine, init_db
from app.schema_evolution import evolve_local_schema


if __name__ == "__main__":
    init_db()
    added_columns = evolve_local_schema(engine)
    print("Database tables are ready.")
    if added_columns:
        print("Added missing MVP columns: " + ", ".join(added_columns))
