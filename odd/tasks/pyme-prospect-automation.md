# PYME Prospect Automation Tasks

Feature: Build an initial Python/PostgreSQL automation with an admin dashboard for Costa Rica PYME prospect discovery and certification-status tracking.

Status: MVP scaffold complete

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

- Choose the first concrete public source/sector/canton for live ingestion.
- Initialize Git before commit-based evidence can be recorded.
- Optional: create `.env` locally from the README example values; the harness blocks creating `.env.example` directly.
