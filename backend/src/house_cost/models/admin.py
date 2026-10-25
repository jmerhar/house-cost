"""The audit log, the app's settings, and annual reconciliation."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import JSON, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UtcDateTime, utcnow


class AuditEvent(Base):
    """One change anyone made: who, when, to what, and the record before and after."""

    __tablename__ = "audit_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow, index=True)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    #: create, update, delete, close, login and the like.
    action: Mapped[str] = mapped_column(String(30))
    #: The kind of record: bill, settlement, rule, household and so on.
    entity: Mapped[str] = mapped_column(String(30), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    before: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class AppSetting(Base):
    """One of the app's settings, kept as JSON under its name."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[object] = mapped_column(JSON)


class ReconciliationStatus(StrEnum):
    """A draft can be changed and deleted; a closed reconciliation is final."""

    DRAFT = "draft"
    CLOSED = "closed"


class Reconciliation(TimestampMixin, Base):
    """A period whose bills are split again by the shares worked out at its end.

    Closing one writes the difference as an adjustment per household and locks the bills dated
    within the period.
    """

    __tablename__ = "reconciliation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    status: Mapped[ReconciliationStatus] = mapped_column(
        String(20), default=ReconciliationStatus.DRAFT
    )
    note: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)
    closed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )

    shares: Mapped[list[ReconciliationShare]] = relationship(
        back_populates="reconciliation", cascade="all, delete-orphan", lazy="selectin"
    )
    adjustments: Mapped[list[Adjustment]] = relationship(
        back_populates="reconciliation", cascade="all, delete-orphan", lazy="selectin"
    )


class ReconciliationShare(Base):
    """A category's reconciled share for one household; categories without rows are unchanged."""

    __tablename__ = "reconciliation_share"

    reconciliation_id: Mapped[int] = mapped_column(
        ForeignKey("reconciliation.id", ondelete="CASCADE"), primary_key=True
    )
    category_id: Mapped[int] = mapped_column(
        ForeignKey("category.id", ondelete="RESTRICT"), primary_key=True
    )
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="RESTRICT"), primary_key=True
    )
    basis_points: Mapped[int] = mapped_column(Integer)

    reconciliation: Mapped[Reconciliation] = relationship(back_populates="shares")


class Adjustment(Base):
    """What a closed reconciliation adds to one household's share; positive means it owes more."""

    __tablename__ = "adjustment"

    reconciliation_id: Mapped[int] = mapped_column(
        ForeignKey("reconciliation.id", ondelete="CASCADE"), primary_key=True
    )
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="RESTRICT"), primary_key=True
    )
    amount_cents: Mapped[int] = mapped_column(Integer)

    reconciliation: Mapped[Reconciliation] = relationship(back_populates="adjustments")
