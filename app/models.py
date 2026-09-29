from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.db import Base


class CompanyStatus(str, Enum):
    new = "new"
    reviewed = "reviewed"
    contacted = "contacted"
    qualified = "qualified"
    disqualified = "disqualified"


class SourceType(str, Enum):
    sample_csv = "sample_csv"
    public_directory = "public_directory"
    referral = "referral"
    manual = "manual"


class RunStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trade_name: Mapped[str | None] = mapped_column(String(255))
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    sector: Mapped[str | None] = mapped_column(String(128))
    province: Mapped[str | None] = mapped_column(String(128))
    canton: Mapped[str | None] = mapped_column(String(128))
    website: Mapped[str | None] = mapped_column(String(512))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[CompanyStatus] = mapped_column(
        SAEnum(CompanyStatus, name="company_status"), default=CompanyStatus.new, nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    contacts: Mapped[list[Contact]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    data_sources: Mapped[list[DataSource]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    certification_statuses: Mapped[list[CertificationStatus]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )
    outreach_notes: Mapped[list[OutreachNote]] = relationship(
        back_populates="company", cascade="all, delete-orphan", order_by="OutreachNote.created_at.desc()"
    )

    __table_args__ = (
        Index("ix_companies_normalized_name", "normalized_name"),
        Index("ix_companies_sector_province", "sector", "province"),
    )


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(128))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(64))
    is_primary: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped[Company] = relationship(back_populates="contacts")

    __table_args__ = (
        UniqueConstraint("company_id", "email", name="uq_contacts_company_email"),
    )


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type"), default=SourceType.sample_csv, nullable=False
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1024))
    evidence_text: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    scrape_run_id: Mapped[int | None] = mapped_column(ForeignKey("scrape_runs.id"))

    company: Mapped[Company] = relationship(back_populates="data_sources")
    scrape_run: Mapped[ScrapeRun | None] = relationship(back_populates="data_sources")

    __table_args__ = (
        UniqueConstraint("company_id", "source_name", "source_url", name="uq_source_company_name_url"),
    )


class CertificationStatus(Base):
    __tablename__ = "certification_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    certification_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(128), default="unknown", nullable=False)
    evidence_url: Mapped[str | None] = mapped_column(String(1024))
    evidence_text: Mapped[str | None] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped[Company] = relationship(back_populates="certification_statuses")

    __table_args__ = (
        UniqueConstraint("company_id", "certification_name", name="uq_cert_company_name"),
    )


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="scrape_run_source_type"), default=SourceType.sample_csv, nullable=False
    )
    status: Mapped[RunStatus] = mapped_column(
        SAEnum(RunStatus, name="run_status"), default=RunStatus.completed, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_seen: Mapped[int] = mapped_column(default=0, nullable=False)
    rows_imported: Mapped[int] = mapped_column(default=0, nullable=False)
    rows_updated: Mapped[int] = mapped_column(default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)

    data_sources: Mapped[list[DataSource]] = relationship(back_populates="scrape_run")


class OutreachNote(Base):
    __tablename__ = "outreach_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str | None] = mapped_column(String(64))
    next_action: Mapped[str | None] = mapped_column(String(255))
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    company: Mapped[Company] = relationship(back_populates="outreach_notes")
