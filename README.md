# Costa Rica PYME Prospect Automation MVP

Local MVP for importing safe pilot CSV data about Costa Rica PYME prospects, storing it in PostgreSQL, and reviewing outreach status from a Streamlit dashboard.

## What is included

- Python project with SQLAlchemy 2.0 models that can be reused from FastAPI endpoints later.
- PostgreSQL service via Docker Compose.
- Environment-variable based configuration.
- Database initialization helper.
- CSV importer for safe pilot data with basic normalization and deduplication.
- Sample CSV data under `sample_data/`.
- Streamlit dashboard to filter companies, inspect contacts/certification/source evidence, add outreach notes, update pipeline status, and export filtered CSV.

## Data-use and legal notes

This MVP intentionally does **not** scrape live sources. Use pilot data you have permission to process, public datasets with clear usage terms, referrals, or manually collected records. Before adding any automated collection:

1. Confirm source terms of use and robots/crawl policy.
2. Store source URL, evidence text, and collection timestamp.
3. Avoid collecting unnecessary personal data.
4. Provide a way to correct or remove records.
5. Review Costa Rica privacy/data-protection obligations with qualified counsel before production use.

## Setup

Python 3.11+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Create a local `.env` file. Example values:

```bash
POSTGRES_USER=pyme
POSTGRES_PASSWORD=pyme_dev_password
POSTGRES_DB=pyme_prospects
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
DATABASE_URL=postgresql+psycopg2://pyme:pyme_dev_password@localhost:5432/pyme_prospects
APP_TITLE=Costa Rica PYME Prospect Automation
```

> Note: `.env` should stay local and must not contain production secrets.

## Start PostgreSQL

```bash
docker compose up -d postgres
```

## Initialize tables

```bash
python -m app.init_db
```

The Streamlit sidebar also includes an "Initialize database tables" button for convenience.

## Import sample pilot data

```bash
python scripts/import_companies_csv.py sample_data/companies_sample.csv --source-name pilot_sample_csv
```

Importer behavior:

- Normalizes company names for basic deduplication.
- Prefers `tax_id` when present.
- Upserts company, primary contact, source evidence, and certification status.
- Records each import as a `scrape_runs` row, even though this MVP uses CSV import rather than live scraping.

## Run the dashboard

```bash
streamlit run app/dashboard.py
```

Open the local Streamlit URL shown in the terminal. From the dashboard you can:

- Filter companies by name, province, sector, and pipeline status.
- Inspect contacts, certification status, and source evidence.
- Add outreach notes and next actions.
- Update company pipeline status.
- Export the filtered company list as CSV.

## Project layout

```text
app/
  config.py       Environment-based settings
  dashboard.py    Streamlit dashboard
  db.py           SQLAlchemy engine/session/init helper
  init_db.py      CLI entry point for table creation
  models.py       SQLAlchemy ORM tables
scripts/
  import_companies_csv.py
sample_data/
  companies_sample.csv
```

## Next steps

1. Add Alembic migrations before production schema changes.
2. Add FastAPI routes for companies, contacts, imports, and outreach notes.
3. Add authentication for dashboard/admin use.
4. Add validation reports for imported CSV rows.
5. Define approved source registry and compliance checks before any live collection.
6. Add tests around importer deduplication and dashboard data queries.
