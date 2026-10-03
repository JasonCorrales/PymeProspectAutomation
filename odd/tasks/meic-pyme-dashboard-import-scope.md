# MEIC PYME Dashboard Import Scope Tasks

Feature: Limit local MEIC PYME test imports and show a focused paginated dashboard table.

Status: implemented pending user review; no commit made

Constraints:
- Do not commit until the user gives explicit approval.
- Use only the `Registros PYME` workbook sheet for this test workflow.
- Load only the user-specified number of rows, currently first 500 rows, and clear existing database records before loading.
- Main dashboard table shows only `IDENTIFICACION`, `NOMBRE`, `SECTOR`, `TAMAÑO`, `FECHA_VIGENCIA`, and `PROVINCIA`; extra workbook details are available after selecting a row.
- Technical artifacts are written in English; dashboard UI remains Spanish.

## Tasks

- [x] D1: Extend the MEIC XLSX importer to support bounded `Registros PYME` imports and a destructive replace mode for local test data.
  - Evidence: `scripts/import_meic_active_pymes.py` supports `--sheet pyme`, `--limit 500`, and `--replace-existing`; validation/import output reports selected sheets, limit, and limit status.
- [x] D2: Persist MEIC `TAMAÑO` and enough workbook detail for the focused table and selected-row detail view.
  - Evidence: `app/models.py`, `app/schema_evolution.py`, and importer mapping add/persist `Company.meic_size`; `FECHA_VIGENCIA` continues to map to `estimated_renewal_date`.
- [x] D3: Update the Streamlit dashboard table to show only the requested columns and paginate dynamically by 10, 25, or 50 rows.
  - Evidence: `app/dashboard.py` main table renders only `IDENTIFICACION`, `NOMBRE`, `SECTOR`, `TAMAÑO`, `FECHA_VIGENCIA`, and `PROVINCIA`; selection maps through the paginated frame to the correct company id.
- [x] D4: Update README commands for the reduced local test workflow.
  - Evidence: `README.md` MEIC commands include `--sheet pyme --limit 500 --replace-existing`.
- [x] D5: Verify compile, validation-only import, destructive limited import, DB row count, and dashboard smoke check.
  - Evidence: focused commands ran successfully except expected foreground Streamlit timeout after startup; row count query returned 500.

## Evidence log

- Started from user request to avoid commits until explicit approval.
- `python3 -m compileall app scripts` completed successfully.
- Validation-only command: `DATABASE_URL='sqlite:///pyme_prospects_demo.db' python3 scripts/import_meic_active_pymes.py sample_data/meic_pymes_activas.xlsx --sheet pyme --limit 500 --validate-only` reported `sheets=Registros PYME`, `limit=500`, `limit_reached=True`, `seen=500`, `valid=500`, `rejected=0`.
- Destructive local import command: `DATABASE_URL='sqlite:///pyme_prospects_demo.db' python3 scripts/import_meic_active_pymes.py sample_data/meic_pymes_activas.xlsx --sheet pyme --limit 500 --replace-existing` reported `imported=500`, `updated=0`, `run_id=1`.
- SQLite row count query returned `500` companies after replace import.
- Headless Streamlit smoke command on port 8563 started the server and was stopped by the 15-second foreground timeout.
- Independent verifier reran compile, validate-only import, destructive import, row-count checks, and confirmed no new commit was created for this work.
- Native review inspect returned `rdd_disabled`, so no review transaction was started.
- Pre-commit UI adjustments: dashboard title now references certification renewal, caption changed to `Dashboard para revisión de prospectos para renovación de certificación y seguimiento`, base UI font was increased, and sidebar filters were reduced/reordered to search, sector, size, start date, end date, and province.
- Post-adjustment check: `python3 -m compileall app scripts` passed; Streamlit restarted on `http://127.0.0.1:8501` with HTTP 200.
