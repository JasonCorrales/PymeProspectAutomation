# PYME Prospect Automation Tasks

Feature: Build an initial Python/PostgreSQL automation with an admin dashboard for Costa Rica PYME prospect discovery and certification-status tracking.

Status: pilot implementation complete

Constraints:
- Use only public or authorized data sources.
- Store source URL/evidence and capture timestamp for every imported data point.
- Treat certification status as unknown unless an official/public source verifies it.
- Technical artifacts are written in English.
- Git is initialized on `main` with `origin` tracking GitHub.

## Tasks

- [x] T1: Scaffold the Python/PostgreSQL project structure with local runtime configuration.
  - Evidence: `pyproject.toml`, `docker-compose.yml`, `app/config.py`, `app/db.py`, `app/init_db.py`.
- [x] T2: Add database models and migration-ready schema for companies, contacts, sources, certification status, scrape runs, and outreach notes.
  - Evidence: `app/models.py` defines `companies`, `contacts`, `data_sources`, `certification_statuses`, `scrape_runs`, and `outreach_notes`.
- [x] T3: Add import/normalization scripts with a safe sample-source workflow for a pilot dataset.
  - Evidence: `scripts/import_companies_csv.py` and `sample_data/companies_sample.csv`.
- [x] T4: Add a basic dashboard/admin to browse, filter, update notes, and export prospects.
  - Evidence: `app/dashboard.py`.
- [x] T5: Add README setup, legal/data-use notes, and verification instructions.
  - Evidence: `README.md`; `.env.example` could not be created because the harness blocks env-like paths, so equivalent example values are documented in the README.

## Decisions

- Stack: Python + PostgreSQL.
- Initial consumption: database + dashboard/admin.
- Dashboard MVP: Streamlit unless a stronger reason appears during implementation.
- Pilot source strategy: start with a safe sample/importer pattern, then plug in specific public Costa Rica sources after terms and data fields are validated.

## Open items

- Optional: create `.env` locally from the README example values; the harness blocks creating `.env.example` directly.

## MEIC active PYMES local import tasks

Goal: Import the official MEIC active PYMES workbook downloaded manually from the live MEIC page, without scraping the protected HTML page.

- [x] M1: Ignore local MEIC workbook files so refreshed government extracts are not committed accidentally.
  - Evidence: `.gitignore` ignores `sample_data/*.xlsx` while tracked CSV samples remain unaffected.
- [x] M2: Inspect workbook sheets and columns from `sample_data/meic_pymes_activas.xlsx`.
  - Evidence: parent inspection found `Registros PYME` and `Emprendimientos Activos`, row 4 headers, workbook dimensions, and generated-date serial metadata.
- [x] M3: Add a local XLSX import/validation script for MEIC active PYMES.
  - Evidence: `scripts/import_meic_active_pymes.py`, `pyproject.toml` openpyxl dependency, and README local-workbook commands.
- [x] M4: Validate the MEIC workbook against the local SQLite workflow before importing.
  - Evidence: `reports/meic_active_pymes_validation.json` was generated from `sample_data/meic_pymes_activas.xlsx`; workbook date `2026-09-25`; 42,608 rows seen, 42,608 valid, 0 rejected, 2 warnings for missing entrepreneur identifiers, 0 rows imported in validate-only mode.
  - Import evidence: `reports/meic_active_pymes_import.json`; `scrape_runs.id=5` completed with 42,608 rows seen, 42,421 imported, 187 updated, 0 rejected, and 2 warnings.
  - Commit evidence: `f552426` (`feat: add MEIC active PYMES local importer`).

## Pilot implementation tasks

Selected pilot: professional services in San José.

- [x] P1: Define the pilot segment inside the app and documentation.
  - Evidence: `README.md` and `app/dashboard.py` define professional services in San José.
- [x] P2: Add a controlled real-source importer pattern for the selected pilot, using an approved-source registry and CSV/manual seed data rather than unapproved scraping.
  - Evidence: `sample_data/approved_sources.csv`, `sample_data/professional_services_san_jose.csv`, and `scripts/import_companies_csv.py`.
- [x] P2.1: Add validation-only mode and JSON import reports for controlled sources.
  - Evidence: `scripts/import_companies_csv.py`, README importer examples, and successful local reports for validation/import with 3 valid rows, 0 rejected rows, and 0 warnings.
- [x] P3: Add commercial follow-up fields for prospect priority, next follow-up date, responsible person, contact result, PYME interest, and estimated renewal date.
  - Evidence: `app/models.py`, `scripts/import_companies_csv.py`, and `app/dashboard.py`.
- [x] P4: Add safe PYME certification validation statuses that never assert certification without official/public evidence.
  - Evidence: `CertificationEvidenceStatus` in `app/models.py` and README certification rules.
- [x] P5: Prepare the SQLite-to-PostgreSQL path with clear commands and migration notes.
  - Evidence: `app/schema_evolution.py`, `app/init_db.py`, and README SQLite/PostgreSQL workflow.
