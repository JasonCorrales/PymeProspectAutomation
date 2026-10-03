from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from sqlalchemy import text
from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel
from app.db import SessionLocal, engine, init_db
from app.models import (
    CertificationEvidenceStatus,
    Company,
    RunStatus,
    ScrapeRun,
    SourceType,
)
from app.schema_evolution import evolve_local_schema
from scripts.import_companies_csv import clean, find_company, normalize_name, upsert_certification, upsert_source

MEIC_SOURCE_URL = "https://www.meic.go.cr/tramites-y-servicios/pymes-activas/"
DEFAULT_SOURCE_NAME = "meic_active_pymes_local_xlsx"
TERMS_STATUS = "official_public_meic_page"
USAGE_NOTES = "Manually downloaded official MEIC active PYMES workbook; this importer does not scrape the MEIC page."
HEADER_ROW = 4

SHEET_CONFIGS = {
    "Registros PYME": {
        "kind": "pyme",
        "certification_name": "MEIC active PYME",
        "id_column": "ID_PYME",
        "condition_column": "CONDICION_PYME",
    },
    "Emprendimientos Activos": {
        "kind": "entrepreneurship",
        "certification_name": "MEIC active entrepreneurship",
        "id_column": "ID_EMPRENDEDOR",
        "condition_column": "ESTADO_SOLICITUD",
    },
}

SHEET_ALIASES = {
    "all": None,
    "pyme": "Registros PYME",
    "emprendimientos": "Emprendimientos Activos",
    "entrepreneurship": "Emprendimientos Activos",
    "Registros PYME": "Registros PYME",
    "Emprendimientos Activos": "Emprendimientos Activos",
}


@dataclass
class ValidationIssue:
    sheet: str
    row_number: int
    severity: str
    field: str
    message: str


@dataclass
class ImportReport:
    source_name: str
    xlsx_path: str
    sheets: list[str]
    workbook_generated_date: str | None
    requested_limit: int | None
    limit_reached: bool
    rows_seen: int
    rows_valid: int
    rows_rejected: int
    warnings: int
    imported: int = 0
    updated: int = 0
    run_id: int | None = None
    sheet_summaries: dict[str, dict[str, int]] = field(default_factory=dict)


def normalize_header(value: object) -> str | None:
    text = clean(value)
    if not text:
        return None
    text = re.sub(r"\s+", "_", text.upper())
    return text


def parse_excel_date(value: object) -> date | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            return from_excel(value).date()
        except Exception:
            return None
    text = clean(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def stringify_identifier(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value).strip()
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def status_is_active(sheet_name: str, value: object) -> bool:
    text = (clean(value) or "").upper()
    if sheet_name == "Registros PYME":
        return any(token in text for token in ("VIGENTE", "ACTIV", "APROB"))
    return any(token in text for token in ("APROB", "ACTIV", "VIGENTE"))


def read_workbook_generated_date(workbook: Any) -> str | None:
    generated_date_cells = {
        "Registros PYME": "N1",
        "Emprendimientos Activos": "K1",
    }
    for sheet_name, cell_reference in generated_date_cells.items():
        if sheet_name not in workbook.sheetnames:
            continue
        parsed = parse_excel_date(workbook[sheet_name][cell_reference].value)
        if parsed:
            return parsed.isoformat()
    return None


def iter_sheet_rows(workbook: Any, sheet_name: str) -> Iterable[tuple[int, dict[str, object]]]:
    worksheet = workbook[sheet_name]
    headers: list[str | None] = [normalize_header(cell.value) for cell in worksheet[HEADER_ROW]]
    for row_number, row in enumerate(
        worksheet.iter_rows(min_row=HEADER_ROW + 1, values_only=True), start=HEADER_ROW + 1
    ):
        mapped = {
            header: value
            for header, value in zip(headers, row, strict=False)
            if header is not None
        }
        if not any(clean(value) for value in mapped.values()):
            continue
        yield row_number, mapped


def build_evidence(sheet_name: str, row: dict[str, object]) -> str:
    config = SHEET_CONFIGS[sheet_name]
    evidence_fields = [
        "TAMAÑO",
        "ACTIVIDAD_CIIU",
        "DESCRIPCION_ACTIVIDAD",
        "REGIÓN",
        "DISTRITO",
        config["id_column"],
        config["condition_column"],
    ]
    parts = [f"sheet={sheet_name}"]
    for field_name in evidence_fields:
        value = clean(row.get(field_name))
        if value:
            parts.append(f"{field_name}={value}")
    return "; ".join(parts)


def build_notes(sheet_name: str, row: dict[str, object]) -> str:
    return build_evidence(sheet_name, row)


def mapped_import_row(sheet_name: str, row: dict[str, object]) -> dict[str, object]:
    config = SHEET_CONFIGS[sheet_name]
    certification_valid_until = parse_excel_date(row.get("FECHA_VIGENCIA"))
    sector = clean(row.get("SECTOR"))
    if sheet_name == "Emprendimientos Activos":
        sector = "Emprendimiento"
    return {
        "legal_name": clean(row.get("NOMBRE")),
        "tax_id": stringify_identifier(row.get("IDENTIFICACION")),
        "sector": sector,
        "meic_size": clean(row.get("TAMAÑO")),
        "province": clean(row.get("PROVINCIA")),
        "canton": clean(row.get("CANTÓN")),
        "notes": build_notes(sheet_name, row),
        "certification_valid_until": certification_valid_until.isoformat() if certification_valid_until else None,
        "source_url": MEIC_SOURCE_URL,
        "source_evidence": build_evidence(sheet_name, row),
        "terms_status": TERMS_STATUS,
        "usage_notes": USAGE_NOTES,
        "certification_name": config["certification_name"],
        "certification_status": CertificationEvidenceStatus.certified_with_public_evidence.value,
        "certification_evidence_url": MEIC_SOURCE_URL,
        "certification_evidence_text": build_evidence(sheet_name, row),
    }


def validate_mapped_row(sheet_name: str, row_number: int, row: dict[str, object]) -> list[ValidationIssue]:
    config = SHEET_CONFIGS[sheet_name]
    issues: list[ValidationIssue] = []
    if not clean(row.get("NOMBRE")):
        issues.append(ValidationIssue(sheet_name, row_number, "error", "NOMBRE", "Company name is required."))
    if not stringify_identifier(row.get("IDENTIFICACION")):
        issues.append(
            ValidationIssue(sheet_name, row_number, "warning", "IDENTIFICACION", "Tax identifier is missing.")
        )
    condition_field = config["condition_column"]
    if not status_is_active(sheet_name, row.get(condition_field)):
        issues.append(
            ValidationIssue(
                sheet_name,
                row_number,
                "error",
                condition_field,
                "Row is not clearly approved/active in the official workbook; certification will not be asserted.",
            )
        )
    if row.get("FECHA_VIGENCIA") is not None and parse_excel_date(row.get("FECHA_VIGENCIA")) is None:
        issues.append(
            ValidationIssue(sheet_name, row_number, "warning", "FECHA_VIGENCIA", "Date could not be parsed.")
        )
    return issues


def collect_rows(
    xlsx_path: Path,
    requested_sheet: str,
    limit: int | None = None,
) -> tuple[list[dict[str, object]], list[ValidationIssue], ImportReport]:
    workbook = load_workbook(xlsx_path, read_only=True, data_only=True)
    selected = SHEET_ALIASES[requested_sheet]
    sheet_names = [selected] if selected else list(SHEET_CONFIGS)
    generated_date = read_workbook_generated_date(workbook)

    mapped_rows: list[dict[str, object]] = []
    issues: list[ValidationIssue] = []
    sheet_summaries: dict[str, dict[str, int]] = {}
    rows_seen = 0

    for sheet_name in sheet_names:
        if sheet_name not in workbook.sheetnames:
            issues.append(
                ValidationIssue(sheet_name, 0, "warning", "sheet", "Expected workbook sheet is missing.")
            )
            sheet_summaries[sheet_name] = {"seen": 0, "valid": 0, "rejected": 0}
            continue

        seen = valid = rejected = 0
        for row_number, row in iter_sheet_rows(workbook, sheet_name):
            if limit is not None and rows_seen >= limit:
                break
            seen += 1
            rows_seen += 1
            row_issues = validate_mapped_row(sheet_name, row_number, row)
            issues.extend(row_issues)
            if any(issue.severity == "error" for issue in row_issues):
                rejected += 1
                continue
            mapped = mapped_import_row(sheet_name, row)
            mapped["_sheet"] = sheet_name
            mapped["_row_number"] = row_number
            mapped_rows.append(mapped)
            valid += 1
        sheet_summaries[sheet_name] = {"seen": seen, "valid": valid, "rejected": rejected}
        if limit is not None and rows_seen >= limit:
            break

    report = ImportReport(
        source_name=DEFAULT_SOURCE_NAME,
        xlsx_path=str(xlsx_path),
        sheets=sheet_names,
        workbook_generated_date=generated_date,
        requested_limit=limit,
        limit_reached=limit is not None and rows_seen >= limit,
        rows_seen=rows_seen,
        rows_valid=len(mapped_rows),
        rows_rejected=rows_seen - len(mapped_rows),
        warnings=sum(1 for issue in issues if issue.severity == "warning"),
        sheet_summaries=sheet_summaries,
    )
    return mapped_rows, issues, report


def write_validation_report(report_path: Path, report: ImportReport, issues: list[ValidationIssue]) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": asdict(report),
        "issues": [asdict(issue) for issue in issues],
    }
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def update_company_fields(company: Company, row: dict[str, object]) -> None:
    company.sector = clean(row.get("sector")) or company.sector
    company.meic_size = clean(row.get("meic_size")) or company.meic_size
    company.province = clean(row.get("province")) or company.province
    company.canton = clean(row.get("canton")) or company.canton
    company.notes = clean(row.get("notes")) or company.notes
    company.certification_valid_until = (
        parse_excel_date(row.get("certification_valid_until")) or company.certification_valid_until
    )


def replace_existing_database_records(session: Any) -> None:
    """Clear local import data in dependency order before a bounded test import."""
    for table_name in (
        "outreach_notes",
        "certification_statuses",
        "contacts",
        "data_sources",
        "companies",
        "scrape_runs",
    ):
        session.execute(text(f"DELETE FROM {table_name}"))


def import_rows(
    rows: list[dict[str, object]],
    source_name: str,
    report: ImportReport,
    issues: list[ValidationIssue],
    report_path: Path | None,
    validate_only: bool,
    replace_existing: bool = False,
) -> tuple[ScrapeRun | None, ImportReport, list[ValidationIssue]]:
    report.source_name = source_name
    if validate_only:
        if report_path:
            write_validation_report(report_path, report, issues)
        return None, report, issues

    init_db()
    evolve_local_schema(engine)
    with SessionLocal() as session:
        if replace_existing:
            replace_existing_database_records(session)
        run = ScrapeRun(
            source_name=source_name,
            source_type=SourceType.public_directory,
            status=RunStatus.running,
            rows_seen=report.rows_seen,
        )
        session.add(run)
        session.flush()
        source_keys_seen: set[tuple[int, str, str]] = set()
        certification_keys_seen: set[tuple[int, str]] = set()

        for row in rows:
            legal_name = clean(row.get("legal_name"))
            if not legal_name:
                continue
            tax_id = clean(row.get("tax_id"))
            company = find_company(session, legal_name, tax_id)
            if company is None:
                company = Company(
                    legal_name=legal_name,
                    normalized_name=normalize_name(legal_name),
                    tax_id=tax_id,
                )
                session.add(company)
                session.flush()
                run.rows_imported += 1
            else:
                run.rows_updated += 1

            update_company_fields(company, row)
            source_key = (company.id, source_name, MEIC_SOURCE_URL)
            if source_key not in source_keys_seen:
                upsert_source(
                    session,
                    company,
                    run,
                    source_name=source_name,
                    source_type=SourceType.public_directory,
                    source_url=MEIC_SOURCE_URL,
                    evidence_text=clean(row.get("source_evidence")),
                    terms_status=TERMS_STATUS,
                    usage_notes=USAGE_NOTES,
                )
                source_keys_seen.add(source_key)
            certification_name = clean(row.get("certification_name"))
            if certification_name:
                certification_key = (company.id, certification_name)
                if certification_key not in certification_keys_seen:
                    upsert_certification(session, company, row)
                    certification_keys_seen.add(certification_key)

        run.status = RunStatus.completed
        run.rows_seen = report.rows_seen
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(run)
        report.imported = run.rows_imported
        report.updated = run.rows_updated
        report.run_id = run.id

    if report_path:
        write_validation_report(report_path, report, issues)
    return run, report, issues


def import_workbook(
    xlsx_path: Path,
    source_name: str = DEFAULT_SOURCE_NAME,
    sheet: str = "all",
    report_path: Path | None = None,
    validate_only: bool = False,
    limit: int | None = None,
    replace_existing: bool = False,
) -> tuple[ScrapeRun | None, ImportReport, list[ValidationIssue]]:
    rows, issues, report = collect_rows(xlsx_path, sheet, limit=limit)
    return import_rows(rows, source_name, report, issues, report_path, validate_only, replace_existing=replace_existing)


def print_report(report: ImportReport, issues: list[ValidationIssue]) -> None:
    print(
        f"MEIC XLSX import report: source={report.source_name}, sheets={','.join(report.sheets)}, "
        f"limit={report.requested_limit or 'none'}, limit_reached={report.limit_reached}, "
        f"seen={report.rows_seen}, valid={report.rows_valid}, rejected={report.rows_rejected}, warnings={report.warnings}, "
        f"imported={report.imported}, updated={report.updated}"
    )
    for sheet_name, summary in report.sheet_summaries.items():
        print(
            f"- {sheet_name}: seen={summary['seen']}, valid={summary['valid']}, "
            f"rejected={summary['rejected']}"
        )
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    if errors:
        print("Errors:")
        for issue in errors[:20]:
            print(f"- {issue.sheet} row {issue.row_number}, {issue.field}: {issue.message}")
    if warnings:
        print("Warnings:")
        for issue in warnings[:20]:
            print(f"- {issue.sheet} row {issue.row_number}, {issue.field}: {issue.message}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import the manually downloaded official MEIC active PYMES XLSX workbook."
    )
    parser.add_argument("xlsx_path", type=Path, help="Path to the local MEIC XLSX workbook")
    parser.add_argument("--source-name", default=DEFAULT_SOURCE_NAME, help="Source label for import metadata")
    parser.add_argument(
        "--sheet",
        default="all",
        choices=sorted(SHEET_ALIASES),
        help="Workbook sheet to process; default imports all known MEIC sheets when present",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of valid rows to collect across the selected sheet(s)",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        help="Delete existing local database records in dependency order before importing",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        help="Optional JSON report path with validation summary and row-level issues",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the workbook and write/report issues without importing rows",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be a positive integer")

    run, report, issues = import_workbook(
        args.xlsx_path,
        source_name=args.source_name,
        sheet=args.sheet,
        report_path=args.report_path,
        validate_only=args.validate_only,
        limit=args.limit,
        replace_existing=args.replace_existing,
    )
    print_report(report, issues)
    if args.report_path:
        print(f"Validation report written to {args.report_path}")
    if run:
        print(f"Import completed: run_id={run.id}")
    else:
        print("Validation completed without import.")


if __name__ == "__main__":
    main()
