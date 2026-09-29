# PYME Prospect Automation Tasks

Feature: Build an initial Python/PostgreSQL automation with an admin dashboard for Costa Rica PYME prospect discovery and certification-status tracking.

Status: pilot implementation complete

Constraints:
- Use only public or authorized data sources.
- Store source URL/evidence and capture timestamp for every imported data point.
- Treat certification status as unknown unless an official/public source verifies it.
- Technical artifacts are written in English.
- This directory is not currently a Git repository, so work-unit commits are blocked until Git is initialized by the user.

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

## Pilot implementation tasks

Selected pilot: professional services in San José.

- [x] P1: Define the pilot segment inside the app and documentation.
  - Evidence: `README.md` and `app/dashboard.py` define professional services in San José.
- [x] P2: Add a controlled real-source importer pattern for the selected pilot, using an approved-source registry and CSV/manual seed data rather than unapproved scraping.
  - Evidence: `sample_data/approved_sources.csv`, `sample_data/professional_services_san_jose.csv`, and `scripts/import_companies_csv.py`.
- [x] P3: Add commercial follow-up fields for prospect priority, next follow-up date, responsible person, contact result, PYME interest, and estimated renewal date.
  - Evidence: `app/models.py`, `scripts/import_companies_csv.py`, and `app/dashboard.py`.
- [x] P4: Add safe PYME certification validation statuses that never assert certification without official/public evidence.
  - Evidence: `CertificationEvidenceStatus` in `app/models.py` and README certification rules.
- [x] P5: Prepare the SQLite-to-PostgreSQL path with clear commands and migration notes.
  - Evidence: `app/schema_evolution.py`, `app/init_db.py`, and README SQLite/PostgreSQL workflow.
