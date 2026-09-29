from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal, init_db
from app.models import (
    CertificationStatus,
    Company,
    Contact,
    DataSource,
    RunStatus,
    ScrapeRun,
    SourceType,
)


def clean(value: object) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


def normalize_name(value: str) -> str:
    text = value.lower().strip()
    text = re.sub(r"\b(sociedad anonima|s\.a\.|sa|srl|ltda)\b", "", text)
    text = re.sub(r"[^a-z0-9áéíóúñü]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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
    source_url: str | None,
    evidence_text: str | None,
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
        existing.scrape_run = run
        return

    session.add(
        DataSource(
            company=company,
            source_type=SourceType.sample_csv,
            source_name=source_name,
            source_url=source_url,
            evidence_text=evidence_text,
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
    status = clean(row.get("certification_status")) or "unknown"
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


def import_csv(csv_path: Path, source_name: str) -> ScrapeRun:
    init_db()
    frame = pd.read_csv(csv_path).fillna("")

    with SessionLocal() as session:
        run = ScrapeRun(
            source_name=source_name,
            source_type=SourceType.sample_csv,
            status=RunStatus.running,
            rows_seen=len(frame),
        )
        session.add(run)
        session.flush()

        for _, raw_row in frame.iterrows():
            row = raw_row.to_dict()
            legal_name = clean(row.get("legal_name")) or clean(row.get("company_name"))
            if not legal_name:
                continue

            tax_id = clean(row.get("tax_id"))
            company = find_company(session, legal_name, tax_id)
            is_new = company is None

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

            upsert_contact(session, company, row)
            upsert_source(
                session,
                company,
                run,
                source_name=source_name,
                source_url=clean(row.get("source_url")),
                evidence_text=clean(row.get("source_evidence")),
            )
            upsert_certification(session, company, row)

            if is_new:
                session.flush()

        run.status = RunStatus.completed
        run.finished_at = datetime.now(timezone.utc)
        session.commit()
        session.refresh(run)
        return run


def main() -> None:
    parser = argparse.ArgumentParser(description="Import safe pilot company prospects from CSV.")
    parser.add_argument("csv_path", type=Path, help="Path to the source CSV file")
    parser.add_argument("--source-name", default="pilot_csv", help="Friendly source label")
    args = parser.parse_args()

    run = import_csv(args.csv_path, args.source_name)
    print(
        f"Import completed: run_id={run.id}, seen={run.rows_seen}, "
        f"imported={run.rows_imported}, updated={run.rows_updated}"
    )


if __name__ == "__main__":
    main()
