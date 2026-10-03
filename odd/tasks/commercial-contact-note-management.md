# Commercial Contact and Note Management Tasks

Feature: Improve company contact and commercial-note management in the renewal dashboard.

Status: implementation complete; verification complete; commit pending explicit authorization

Constraints:
- Dashboard UI copy remains Spanish.
- Technical artifacts remain English.
- Keep changes focused on the selected-company commercial detail tabs and requested company-table filter/column.
- Do not commit or push without explicit user authorization.

## Tasks

- [x] Add edit and delete actions for registered company contact methods.
- [x] Fix outreach-note save feedback so success is visible and form inputs reset after saving.
- [x] Add delete action for outreach notes from commercial history.
- [x] Display commercial-history dates and next-follow-up date in `dd/mm/yyyy` format.
- [x] Replace contact expanders with a registered-contacts table that exposes Modify/Delete actions per row.
- [x] Load selected contact data into the form for editing, with `Guardar cambios` and `Nuevo` controls.
- [x] Require delete confirmation before removing a contact.
- [x] Render each commercial-history delete action as a red X on the same line as the note text.
- [x] Add `Estado comercial` as a search filter and final company-table column.
- [x] Verify syntax/behavior and prepare the work unit for commit.

## Evidence log

- User requested four UI adjustments after commit `651f001` was pushed: edit/delete contacts, correct note-save success/reset behavior, delete notes, and `dd/mm/yyyy` date display for commercial history and `Próximo seguimiento`.
- Added `update_company_contact_method`, `delete_company_contact_method`, and `delete_outreach_note` dashboard actions.
- Contactos tab uses a form with create/edit mode; selecting `Modificar` loads a contact into the form and shows `Guardar cambios`, while `Nuevo` returns to create mode.
- Registered contacts render as a column-based table with `Modificar` and `Eliminar` actions; delete requires a visible confirmation before removal.
- Note creation uses `clear_on_submit=True`, preserves a success message through rerun via `st.session_state.note_success`, and clears the form after saving.
- Historial comercial includes a red X delete action in the same row as each note and displays note dates with `dd/mm/yyyy` formatting.
- `Próximo seguimiento` date input uses Streamlit `format="DD/MM/YYYY"`.
- Added `Estado comercial` to sidebar filters and as the final company-table column.
- Verification: `python3 -m compileall app scripts` passed.
- Verification: Streamlit startup smoke on port 8768 reached startup URLs and was stopped by the 15s timeout.
