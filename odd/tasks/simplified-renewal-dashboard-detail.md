# Simplified Renewal Dashboard Detail Tasks

Feature: Move pagination below the company table and simplify selected-company detail for certification-renewal workflow.

Status: implementation complete; verification complete

Constraints:
- Do not commit until the user gives explicit approval.
- Pagination controls must appear below the table.
- Remove from UI and database model: PYME interest and estimated renewal fields.
- Keep `FECHA_VIGENCIA` behavior for the table and date filters by storing it as certification validity/expiration data, not as an editable estimated renewal field.
- Remove selected-company detail sections: `Información general`, `Fuentes y evidencia`, and `Certificación PYME`.
- Technical artifacts are written in English; dashboard UI remains Spanish.

## Tasks

- [x] S1: Replace editable PYME-interest/estimated-renewal model usage with a dedicated certification validity date for MEIC `FECHA_VIGENCIA`.
- [x] S2: Move dashboard pagination controls below the main company table.
- [x] S3: Remove requested detail sections and fields from the selected-company UI.
- [x] S4: Update importers/schema/docs to stop using removed fields and migrate local DB shape.
- [x] S5: Verify compile, limited MEIC import, row count, and Streamlit startup.
- [x] S6: Add company contact registration table with name, contact medium, and contact type.
- [x] S7: Render Contacts, Add commercial note, and Commercial history inside tabs.
- [x] S8: Verify contact table migration, form save, compile, and Streamlit startup.

## Evidence log

- Started after pushed commit `44c22d7`; user requested next feature before committing.
- `Company` now stores MEIC validity as `certification_valid_until`; `pyme_interest` and `estimated_renewal_date` are removed from the ORM model.
- Dashboard filters/table use `certification_valid_until` while the UI label remains `FECHA_VIGENCIA`; pagination controls render after the table.
- Selected-company detail no longer renders `Información general`, `Fuentes y evidencia`, or `Certificación PYME`, and commercial tracking no longer edits PYME interest or estimated renewal fields.
- MEIC importer maps workbook `FECHA_VIGENCIA` to `certification_valid_until`; CSV importer ignores deprecated `pyme_interest`/`estimated_renewal_date` columns and no longer writes removed fields.
- Local schema evolution adds `certification_valid_until`, copies legacy `estimated_renewal_date` values into it, and attempts to drop the removed company columns when the backend supports it.
- Verification: `python3 -m compileall app scripts` passed.
- Verification: limited SQLite MEIC import with `--sheet pyme --limit 500 --replace-existing --report-path reports/meic_active_pymes_import.json` imported 500 rows with 0 rejects/warnings.
- Verification: sanity query found 500 companies, 500 `certification_valid_until` values, and no `pyme_interest`/`estimated_renewal_date` columns in the local SQLite `companies` table.
- Verification: Streamlit startup smoke succeeded on port 8765 and was stopped by the 15s timeout after startup; port 8502 was unavailable for the first attempt.
- Parent check: restarted the app on `http://127.0.0.1:8501`; HTTP smoke returned 200.
- Native review inspect returned `rdd_disabled`, so no review transaction was started.
- Follow-up request: add a dedicated contact registration table with `nombre`, `medio de contacto`, and `tipo de contacto` (`correo`, `celular`, `telefono`), and render Contactos / Agregar nota comercial / Historial comercial as tabs.
- Added `CompanyContactMethod` / `company_contact_methods` with `name`, `contact_medium`, `contact_type`, `created_at`, and a company relationship; the legacy `contacts` table remains for compatibility but the dashboard now uses the new dedicated table.
- Selected-company detail now renders `Contactos`, `Agregar nota comercial`, and `Historial comercial` as Streamlit tabs; the Contactos tab includes a form for registering contact methods and a table of saved methods.
- Local schema evolution creates `company_contact_methods` when missing so existing SQLite databases can adopt the new contact registration table.
- Verification: `python3 -m compileall app scripts` passed.
- Verification: `DATABASE_URL='sqlite:///pyme_prospects_demo.db' python3 -m app.init_db` completed with `Database tables are ready.`
- Verification: sanity query confirmed `company_contact_methods` has `id`, `company_id`, `name`, `contact_medium`, `contact_type`, and `created_at` columns.
- Verification: rollback insert sanity passed for `CompanyContactMethod` using `ContactMethodType.correo`.
- Verification: Streamlit startup smoke on port 8766 reached the startup URLs and was stopped by the 15s timeout.
- Parent check: restarted the app on `http://127.0.0.1:8501`; HTTP smoke returned 200 after contact-tab changes.
- Native review inspect after contact-tab changes returned `rdd_disabled`, so no review transaction was started.
