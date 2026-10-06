# Brave Contact Discovery Tasks

Feature: Add on-demand automatic internet contact discovery for selected companies using a configurable provider architecture, initially Brave Search API.

Status: implementation complete; verification complete; committed

Constraints:
- Use Brave Search API as the first provider, with Serper and SerpApi as additional configurable providers.
- Keep provider selection/configuration parameterized through environment settings, not hard-coded UI/programming changes.
- Do not auto-promote discovery results to valid contacts; user confirmation is required.
- Store discovered candidates separately from validated contacts.
- Dashboard UI copy remains Spanish; technical artifacts remain English.
- Do not push without explicit user authorization.

## Tasks

- [x] Add configurable contact-discovery settings and provider abstraction.
- [x] Implement Brave Search provider using configured API key, endpoint, country/language, count, timeout, and query templates.
- [x] Add Serper provider using configured API key, endpoint, country/language, count, timeout, and the same query templates.
- [x] Add SerpApi provider using configured API key, endpoint, country/language, count, timeout, and the same query templates.
- [x] Add discovery result model/table and local schema evolution.
- [x] Add discovery service to build queries, normalize candidates, save pending results, and accept/reject results.
- [x] Integrate Contactos tab with Buscar, results table, Usar como contacto, and Descartar actions.
- [x] Extract structured SerpApi contact fields such as `teléfono` from rich JSON responses.
- [x] Add visible loading feedback while discovery is running.
- [x] Document configuration and verify compile/startup behavior.

## Evidence log

- User selected automatic, one-by-one, on-demand lookup for a selected company.
- User approved design: store discovered data in a separate table and only convert to valid contacts after user confirmation.
- User selected Brave Search API and requested provider/configuration to be parameterized for later provider swaps without programming changes.
- Added contact-discovery settings in `app/config.py`: provider, enabled flag, query templates, query/result limits, timeout, Brave endpoint/API key, country, and language.
- Added `app/contact_discovery.py` with provider protocol, Brave provider, query builder, candidate extraction, and pending-result persistence.
- Added `CompanyContactDiscoveryResult` plus `DiscoveryResultStatus`; expanded `ContactMethodType` for web/social candidates.
- Local schema evolution now creates `company_contact_discovery_results`.
- Contactos tab now has `Buscar contactos en internet`, lists pending candidates, opens source URLs, and supports `Usar como contacto` / `Descartar`.
- Accepting a candidate creates a valid `CompanyContactMethod` and marks the discovery result as accepted; rejecting marks it rejected.
- README documents SerpApi/Serper/Brave contact discovery `.env` settings and workflow behavior.
- Added Serper provider after user created a Serper account and selected `CONTACT_DISCOVERY_PROVIDER=serper`.
- Added SerpApi provider after the user confirmed the free SerpApi account returns data and Serper returned HTTP 403 with the wrong provider/key combination; `CONTACT_DISCOVERY_PROVIDER=serpapi` is the documented setting, with `serverapi` accepted as a typo-compatible alias.
- SerpApi structured JSON extraction now walks the full payload and extracts contact fields such as `teléfono`, `telefono`, `phone`, `email`, and `correo`, so phone candidates are shown instead of only website links.
- Contact discovery now shows a Streamlit spinner while network processing is running.
- Default `CONTACT_DISCOVERY_TIMEOUT_SECONDS` increased to 120 seconds for slower SerpApi responses.
- User manually verified the SerpApi flow returns useful data in the dashboard.
- Verification: `python3 -m compileall app scripts` passed.
- Verification: `DATABASE_URL='sqlite:///pyme_prospects_demo.db' python3 -m app.init_db` created/updated tables.
- Verification: SQLite inspection confirmed `company_contact_discovery_results` columns exist.
- Verification: Streamlit startup smoke on port 8769 reached startup URLs and was stopped by the 15s timeout.
- Commit evidence: `5d2147f` (`feat: add automatic contact discovery`).
