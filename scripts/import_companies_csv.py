from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine, init_db
from app.models import (
    CertificationEvidenceStatus,
    CertificationStatus,
    Company,
    Contact,
    DataSource,
    ProspectPriority,
    RunStatus,
    ScrapeRun,
    SourceType,
)
from app.schema_evolution import evolve_local_schema


APPROVED_SOURCE_REGISTRY = Path("sample_data/approved_sources.csv")
REQUIRED_COLUMNS = ["legal_name"]
RECOMMENDED_CONTACT_COLUMNS = ["email", "phone", "contact_email", "contact_phone"]
SAFE_CERTIFICATION_STATUSES = {item.value for item in CertificationEvidenceStatus}


@dataclass
class ValidationIssue:
    row_number: int
    severity: str
    field: str
    message: str


@dataclass
class ImportReport:
    source_name: str
    csv_path: str
    rows_seen: int
    rows_valid: int
    rows_rejected: int
    warnings: int
    imported: int = 0
    updated: int = 0
    run_id: int | None = None


def clean(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def normalize_name(value: str) -> str:
    text = value.lower().strip()
    text = re.sub(r"\b(sociedad anonima|s\.a\.|sa|srl|s\.r\.l\.|ltda)\b", "", text)
    text = re.sub(r"[^a-z0-9áéíóúñü]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_date(value: object) -> date | None:
    text = clean(value)
    if not text:
        return None
    return date.fromisoformat(text)


def enum_value(enum_type, value: object, default):
    text = clean(value)
    if not text:
        return default
    try:
        return enum_type(text)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise ValueError(f"Invalid {enum_type.__name__} value '{text}'. Allowed: {allowed}") from exc


def load_source_registry(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    frame = pd.read_csv(path).fillna("")
    return {str(row["source_name"]): row.to_dict() for _, row in frame.iterrows()}


def source_type_from_registry(registry_entry: dict[str, str] | None) -> SourceType:
    if not registry_entry:
        return SourceType.sample_csv
    return enum_value(SourceType, registry_entry.get("source_type"), SourceType.approved_pilot_csv)


def validate_csv_columns(frame: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for column in REQUIRED_COLUMNS:
        if column not in frame.columns and not (column == "legal_name" and "company_name" in frame.columns):
            issues.append(
                ValidationIssue(
                    row_number=0,
                    severity="error",
                    field=column,
                    message=f"Required column '{column}' is missing.",
                )
            )
    return issues


def validate_row(row: dict[str, Any], row_number: int) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    legal_name = clean(row.get("legal_name")) or clean(row.get("company_name"))
    if not legal_name:
        issues.append(
            ValidationIssue(
                row_number=row_number,
                severity="error",
                field="legal_name",
                message="Company legal_name or company_name is required.",
            )
        )

    if not any(clean(row.get(column)) for column in RECOMMENDED_CONTACT_COLUMNS):
        issues.append(
            ValidationIssue(
                row_number=row_number,
                severity="warning",
                field="contact",
                message="No company or contact email/phone was provided.",
            )
        )

    certification_status = clean(row.get("certification_status"))
    if certification_status and certification_status not in SAFE_CERTIFICATION_STATUSES:
        issues.append(
            ValidationIssue(
                row_number=row_number,
                severity="error",
                field="certification_status",
                message=(
                    f"Invalid certification_status '{certification_status}'. "
                    f"Allowed: {', '.join(sorted(SAFE_CERTIFICATION_STATUSES))}."
                ),
            )
        )

    for field in ["next_follow_up_date", "certification_valid_until"]:
        value = clean(row.get(field))
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                issues.append(
                    ValidationIssue(
                        row_number=row_number,
                        severity="error",
                        field=field,
                        message="Date must use ISO format YYYY-MM-DD.",
                    )
                )

    for enum_type, field in [
        (ProspectPriority, "prospect_priority"),
    ]:
        value = clean(row.get(field))
        if value and value not in {item.value for item in enum_type}:
            allowed = ", ".join(item.value for item in enum_type)
            issues.append(
                ValidationIssue(
                    row_number=row_number,
                    severity="error",
                    field=field,
                    message=f"Invalid value '{value}'. Allowed: {allowed}.",
                )
            )

    return issues


def split_valid_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[ValidationIssue]]:
    issues = validate_csv_columns(frame)
    if any(issue.severity == "error" and issue.row_number == 0 for issue in issues):
        return frame.iloc[0:0], issues

    valid_indexes: list[int] = []
    for index, raw_row in frame.iterrows():
        row_issues = validate_row(raw_row.to_dict(), row_number=index + 2)
        issues.extend(row_issues)
        if not any(issue.severity == "error" for issue in row_issues):
            valid_indexes.append(index)

    return frame.loc[valid_indexes].copy(), issues


def write_validation_report(
    report_path: Path,
    report: ImportReport,
    issues: list[ValidationIssue],
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": asdict(report),
        "issues": [asdict(issue) for issue in issues],
    }
    report_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def find_company(session: Session, legal_name: str, tax_id: str | None) -> Company | None:
    if tax_id:
        company = session.scalar(select(Company).where(Company.tax_id == tax_id))
        if company:
            return company

    normalized = normalize_name(legal_name)
    return session.scalar(select(Company).where(Company.normalized_name == normalized))


def upsert_contact(session: Session, company: Company, row: dict[str, object]) -> None:
    email = clean(row.get("contact_email")) or clean(row.get("email"))
    phone = clean(row.get("contact_phone")) or clean(row.get("phone"))
    name = clean(row.get("contact_name"))
    role = clean(row.get("contact_role"))

    if not any([email, phone, name]):
        return

    existing = None
    if email:
        existing = session.scalar(
            select(Contact).where(Contact.company_id == company.id, Contact.email == email)
        )

    if existing:
        existing.name = existing.name or name
        existing.role = existing.role or role
        existing.phone = existing.phone or phone
        existing.is_primary = True
        return

    session.add(
        Contact(
            company=company,
            name=name,
            role=role,
            email=email,
            phone=phone,
            is_primary=True,
        )
    )


def upsert_source(
    session: Session,
    company: Company,
    run: ScrapeRun,
    source_name: str,
    source_type: SourceType,
    source_url: str | None,
    evidence_text: str | None,
    terms_status: str | None,
    usage_notes: str | None,
) -> None:
    existing = session.scalar(
        select(DataSource).where(
            DataSource.company_id == company.id,
            DataSource.source_name == source_name,
            DataSource.source_url == source_url,
        )
    )
    if existing:
        existing.evidence_text = evidence_text or existing.evidence_text
        existing.terms_status = terms_status or existing.terms_status
        existing.usage_notes = usage_notes or existing.usage_notes
        existing.scrape_run = run
        return

    session.add(
        DataSource(
            company=company,
            source_type=source_type,
            source_name=source_name,
            source_url=source_url,
            evidence_text=evidence_text,
            terms_status=terms_status,
            usage_notes=usage_notes,
            scrape_run=run,
        )
    )


def upsert_certification(session: Session, company: Company, row: dict[str, object]) -> None:
    certification_name = clean(row.get("certification_name"))
    if not certification_name:
        return

    existing = session.scalar(
        select(CertificationStatus).where(
            CertificationStatus.company_id == company.id,
            CertificationStatus.certification_name == certification_name,
        )
    )
    status = enum_value(
        CertificationEvidenceStatus,
        row.get("certification_status"),
        CertificationEvidenceStatus.unknown,
    )
    evidence_url = clean(row.get("certification_evidence_url"))
    evidence_text = clean(row.get("certification_evidence_text"))

    if existing:
        existing.status = status
        existing.evidence_url = evidence_url or existing.evidence_url
        existing.evidence_text = evidence_text or existing.evidence_text
        return

    session.add(
        CertificationStatus(
            company=company,
            certification_name=certification_name,
            status=status,
            evidence_url=evidence_url,
            evidence_text=evidence_text,
        )
    )


def update_commercial_fields(company: Company, row: dict[str, object]) -> None:
    company.prospect_priority = enum_value(
        ProspectPriority,
        row.get("prospect_priority"),
        company.prospect_priority or ProspectPriority.medium,
    )
    company.next_follow_up_date = parse_date(row.get("next_follow_up_date")) or company.next_follow_up_date
    company.responsible_person = clean(row.get("responsible_person")) or company.responsible_person
    company.contact_result = clean(row.get("contact_result")) or company.contact_result
    company.certification_valid_until = (
        parse_date(row.get("certification_valid_until")) or company.certification_valid_until
    )


def import_csv(
    csv_path: Path,
    source_name: str,
    registry_path: Path = APPROVED_SOURCE_REGISTRY,
    allow_unregistered_source: bool = False,
    report_path: Path | None = None,
    validate_only: bool = False,
) -> tuple[ScrapeRun | None, ImportReport, list[ValidationIssue]]:
    init_db()
    evolve_local_schema(engine)
    registry = load_source_registry(registry_path)
    registry_entry = registry.get(source_name)
    if not registry_entry and not allow_unregistered_source:
        known_sources = ", ".join(sorted(registry)) or "none"
        raise ValueError(
            f"Source '{source_name}' is not registered in {registry_path}. "
            f"Known sources: {known_sources}. Use --allow-unregistered-source only for local tests."
        )

    source_type = source_type_from_registry(registry_entry)
    registry_terms_status = clean(registry_entry.get("terms_status")) if registry_entry else None
    registry_usage_notes = clean(registry_entry.get("usage_notes")) if registry_entry else None
    registry_source_url = clean(registry_entry.get("source_url")) if registry_entry else None
    frame = pd.read_csv(csv_path).fillna("")
    valid_frame, issues = split_valid_rows(frame)
    report = ImportReport(
        source_name=source_name,
        csv_path=str(csv_path),
        rows_seen=len(frame),
        rows_valid=len(valid_frame),
        rows_rejected=len(frame) - len(valid_frame),
        warnings=sum(1 for issue in issues if issue.severity == "warning"),
    )

    if validate_only:
        if report_path:
            write_validation_report(report_path, report, issues)
        return None, report, issues

    with SessionLocal() as session:
        run = ScrapeRun(
            source_name=source_name,
            source_type=source_type,
            status=RunStatus.running,
            rows_seen=len(frame),
        )
        session.add(run)
        session.flush()

        for _, raw_row in valid_frame.iterrows():
            row = raw_row.to_dict()
            legal_name = clean(row.get("legal_name")) or clean(row.get("company_name"))
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

            company.trade_name = clean(row.get("trade_name")) or company.trade_name
            company.sector = clean(row.get("sector")) or company.sector
            company.province = clean(row.get("province")) or company.province
            company.canton = clean(row.get("canton")) or company.canton
            company.website = clean(row.get("website")) or company.website
            company.email = clean(row.get("email")) or company.email
            company.phone = clean(row.get("phone")) or company.phone
            company.notes = clean(row.get("notes")) or company.notes
            update_commercial_fields(company, row)

            row_source_url = clean(row.get("source_url")) or registry_source_url
            upsert_contact(session, company, row)
            upsert_source(
                session,
                company,
                run,
                source_name=source_name,
                source_type=source_type,
                source_url=row_source_url,
                evidence_text=clean(row.get("source_evidence")),
                terms_status=clean(row.get("terms_status")) or registry_terms_status,
                usage_notes=clean(row.get("usage_notes")) or registry_usage_notes,
            )
            upsert_certification(session, company, row)

        run.status = RunStatus.completed
        run.rows_seen = len(frame)
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(run)

        report.imported = run.rows_imported
        report.updated = run.rows_updated
        report.run_id = run.id
        if report_path:
            write_validation_report(report_path, report, issues)
        return run, report, issues


def print_report(report: ImportReport, issues: list[ValidationIssue]) -> None:
    print(
        f"Import report: source={report.source_name}, seen={report.rows_seen}, "
        f"valid={report.rows_valid}, rejected={report.rows_rejected}, warnings={report.warnings}, "
        f"imported={report.imported}, updated={report.updated}"
    )
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]
    if errors:
        print("Errors:")
        for issue in errors[:20]:
            print(f"- row {issue.row_number}, {issue.field}: {issue.message}")
    if warnings:
        print("Warnings:")
        for issue in warnings[:20]:
            print(f"- row {issue.row_number}, {issue.field}: {issue.message}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import approved pilot company prospects from CSV.")
    parser.add_argument("csv_path", type=Path, help="Path to the source CSV file")
    parser.add_argument("--source-name", default="pilot_sample_csv", help="Approved source label")
    parser.add_argument(
        "--source-registry",
        type=Path,
        default=APPROVED_SOURCE_REGISTRY,
        help="CSV registry of approved/controlled data sources",
    )
    parser.add_argument(
        "--allow-unregistered-source",
        action="store_true",
        help="Allow local test imports from a source not listed in the registry",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        help="Optional JSON report path with validation summary and row-level issues",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the CSV and write/report issues without importing rows",
    )
    args = parser.parse_args()

    run, report, issues = import_csv(
        args.csv_path,
        args.source_name,
        registry_path=args.source_registry,
        allow_unregistered_source=args.allow_unregistered_source,
        report_path=args.report_path,
        validate_only=args.validate_only,
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
