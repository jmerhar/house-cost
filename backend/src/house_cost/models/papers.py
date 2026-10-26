"""Suppliers, the services the house has with them, and the documents kept about both."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UtcDateTime, utcnow


class Supplier(TimestampMixin, Base):
    """A company the house pays: MEO Energia, SMAS."""

    __tablename__ = "supplier"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    #: The Portuguese tax number on its invoices, which tells its bills apart from any other's.
    nif: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    #: The category its bills usually go under.
    default_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("category.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Service(TimestampMixin, Base):
    """Something the house has with a supplier: an electricity contract, an internet package.

    Holds what the paperwork says about it: its references, when it started, when it ends or
    renews, how long it is locked in and how much notice leaving needs.
    """

    __tablename__ = "service"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id", ondelete="RESTRICT"))
    name: Mapped[str] = mapped_column(String(200))
    #: The service's references, by what the supplier calls them: {"CPE": "PT0002…", "Cliente": …}.
    identifiers: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    default_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("category.id", ondelete="SET NULL"), nullable=True
    )
    starts_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: When the contract ends, or next renews when it renews by itself.
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    renews_automatically: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Until when leaving costs a penalty (the Portuguese "fidelização").
    lock_in_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    #: The notice leaving needs, in days.
    notice_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: How often a bill is expected, in days; none for a service billed irregularly.
    billed_every_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    supplier: Mapped[Supplier] = relationship(lazy="joined")


class Document(Base):
    """A file kept for reference: a contract, its terms, the signed agreement, a leaflet.

    Its text, read from the file when it has a text layer, is what the library is searched by.
    """

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(300))
    #: contract, terms, agreement, bill, info or other.
    kind: Mapped[str] = mapped_column(String(20), default="other")
    #: The date the document bears.
    dated: Mapped[date | None] = mapped_column(Date, nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("supplier.id", ondelete="SET NULL"), nullable=True, index=True
    )
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("service.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str] = mapped_column(Text, default="")
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    text: Mapped[str] = mapped_column(Text, default="")
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    @property
    def has_text(self) -> bool:
        """Whether the file gave any text to search by."""
        return bool(self.text and self.text.strip())
