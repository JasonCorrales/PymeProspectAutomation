# Costa Rica PYME Prospect Automation MVP

Local MVP for importing controlled pilot data about Costa Rica PYME prospects, storing it in SQLite or PostgreSQL, and reviewing outreach status from a Spanish Streamlit dashboard.

## Current pilot

The first commercial pilot is:

- **Segment:** professional services
- **Location:** San José, Costa Rica
- **Collection mode:** controlled CSV/manual seed only until each real source is approved
- **Goal:** validate prospect quality and outreach workflow before broad scraping or enrichment

## What is included

- Python project with SQLAlchemy 2.0 models that can be reused from FastAPI endpoints later.
- SQLite-compatible local demo and PostgreSQL service via Docker Compose.
- Environment-variable based configuration.
- Database initialization and local schema-evolution helper.
- CSV importer with basic normalization, deduplication, approved-source registry checks, and source evidence capture.
- Sample CSV data under `sample_data/`.
- Spanish Streamlit dashboard to filter companies, select a row, update commercial follow-up fields, register contact methods, add outreach notes, and export filtered CSV.

## Data-use and legal notes

This MVP intentionally does **not** scrape live sources. Use pilot data you have permission to process, public datasets with clear usage terms, referrals, or manually collected records. Before adding any automated collection:

1. Confirm source terms of use and robots/crawl policy.
2. Register the source in `sample_data/approved_sources.csv`.
3. Store source URL, evidence text, terms status, usage notes, and collection timestamp.
4. Avoid collecting unnecessary personal data.
5. Provide a way to correct or remove records.
6. Review Costa Rica privacy/data-protection obligations with qualified counsel before production use.

Certification status is intentionally conservative. The app must not mark a company as certified unless there is official/public evidence. Supported statuses are:

- `unknown`
- `needs_direct_validation`
- `certified_with_public_evidence`
- `not_found_in_public_source`
- `expired_with_public_evidence`

## Setup

Python 3.11+ is recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

If this machine does not have `python3-venv` or Docker, the local SQLite demo can still run after installing dependencies with user-level pip.

Create a local `.env` file for PostgreSQL usage. Example values:

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

## SQLite demo workflow

Use this path for local MVP validation without Docker:

```bash
export DATABASE_URL='sqlite:///pyme_prospects_demo.db'
python3 -m app.init_db
python3 scripts/import_companies_csv.py \
  sample_data/professional_services_san_jose.csv \
  --source-name professional_services_sj_manual_seed
python3 -m streamlit run app/dashboard.py
```

Open the local Streamlit URL shown in the terminal, usually `http://localhost:8501`.

## PostgreSQL workflow

```bash
docker compose up -d postgres
python -m app.init_db
python scripts/import_companies_csv.py \
  sample_data/professional_services_san_jose.csv \
  --source-name professional_services_sj_manual_seed
streamlit run app/dashboard.py
```

## Importer behavior

### Controlled CSV importer

- Validates `--source-name` against `sample_data/approved_sources.csv` by default.
- Validates required fields before writing to the database.
- Rejects rows with missing company name, invalid dates, invalid commercial enum values, or unsafe certification statuses.
- Warns when a row has no usable email or phone.
- Supports `--validate-only` to check a source without importing it.
- Supports `--report-path reports/<file>.json` for row-level validation evidence.
- Normalizes company names for basic deduplication.
- Prefers `tax_id` when present.
- Upserts company, primary contact, source evidence, certification status, certification validity date, and commercial follow-up fields.
- Records each import as a `scrape_runs` row, even though this MVP uses CSV import rather than live scraping.
- Use `--allow-unregistered-source` only for local tests.

Validation-only example:

```bash
python3 scripts/import_companies_csv.py \
  sample_data/professional_services_san_jose.csv \
  --source-name professional_services_sj_manual_seed \
  --validate-only \
  --report-path reports/professional_services_sj_validation.json
```

Import with report example:

```bash
python3 scripts/import_companies_csv.py \
  sample_data/professional_services_san_jose.csv \
  --source-name professional_services_sj_manual_seed \
  --report-path reports/professional_services_sj_import.json
```

### MEIC active PYMES local XLSX importer

The MEIC active PYMES workbook is handled as a bounded local-file import. Manually download the current workbook from the official MEIC page (`https://www.meic.go.cr/tramites-y-servicios/pymes-activas/`) and save it here:

```text
sample_data/meic_pymes_activas.xlsx
```

Do not scrape the MEIC page. Local `.xlsx` drops under `sample_data/` are ignored by Git so refreshed government workbooks are not committed accidentally.

Validate the workbook against the SQLite workflow:

```bash
DATABASE_URL='sqlite:///pyme_prospects_demo.db' python3 scripts/import_meic_active_pymes.py \
  sample_data/meic_pymes_activas.xlsx \
  --sheet pyme \
  --limit 500 \
  --replace-existing \
  --validate-only \
  --report-path reports/meic_active_pymes_validation.json
```

Import the validated workbook:

```bash
DATABASE_URL='sqlite:///pyme_prospects_demo.db' python3 scripts/import_meic_active_pymes.py \
  sample_data/meic_pymes_activas.xlsx \
  --sheet pyme \
  --limit 500 \
  --replace-existing \
  --report-path reports/meic_active_pymes_import.json
```

The local test workflow reads only the `Registros PYME` sheet via `--sheet pyme`, limits the import to the first 500 valid rows with `--limit 500`, and uses `--replace-existing` to clear existing database records before loading the bounded dataset. The importer uses row 4 as the header, stores `FECHA_VIGENCIA` as `certification_valid_until` for table display/date filters, ignores blank columns/rows, records the official MEIC page as source evidence, and only asserts `certified_with_public_evidence` for rows that are clearly active/approved in the workbook.

## Dashboard workflow

From the dashboard you can:

- Filter companies by name, province, sector, MEIC size, and `FECHA_VIGENCIA` date range.
- Select one company from the main table.
- Inspect and register contact methods in the `Contactos` tab.
- Update priority, next follow-up date, responsible person, and contact result.
- Add outreach notes and next actions from the commercial-note tab, and review commercial history in its own tab.
- Export the filtered company list as CSV.

## Project layout

```text
app/
  config.py             Environment-based settings
  dashboard.py          Spanish Streamlit dashboard
  db.py                 SQLAlchemy engine/session/init helper
  init_db.py            CLI entry point for table creation + local schema evolution
  models.py             SQLAlchemy ORM tables
  schema_evolution.py   Additive MVP schema helper before Alembic
scripts/
  import_companies_csv.py
  import_meic_active_pymes.py
sample_data/
  approved_sources.csv
  companies_sample.csv
  professional_services_san_jose.csv
```

## SQLite to PostgreSQL path

SQLite is fine for local validation. Move to PostgreSQL when you need multi-user access, larger imports, background jobs, or deployment.

Recommended path:

1. Keep using `DATABASE_URL` so the app code does not change.
2. Start PostgreSQL with Docker Compose.
3. Run `python -m app.init_db`.
4. Re-import approved CSV sources into PostgreSQL.
5. Add Alembic before any production schema changes.
6. Add authentication before exposing the dashboard outside localhost.

## Next steps

1. Replace the manual pilot seed with a real approved source after terms are reviewed.
2. Add CSV validation reports for rejected or incomplete rows.
3. Add tests around importer deduplication and dashboard query behavior.
4. Add authentication for dashboard/admin use.
5. Add FastAPI routes if another frontend or automation client is needed.
