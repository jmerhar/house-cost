"""Categories and their split rules, bills, settlements and the files attached to them.

Money is whole cents throughout. A split is a share per household in basis points (1/100 of a
percent), which add up to 10 000.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UtcDateTime, utcnow
from .people import Household

#: The basis points a whole split adds up to.
WHOLE = 10_000


class Category(TimestampMixin, Base):
    """What a cost is for (electricity, road upkeep); its rules decide how it is split."""

    __tablename__ = "category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    rules: Mapped[list[SplitRule]] = relationship(
        back_populates="category", order_by="SplitRule.effective_from"
    )


class SplitRule(Base):
    """How a category is split from a date on, until a later rule for it takes over.

    Never edited: a change is a new rule from a later date, so the bills a rule split keep the
    split they were given.
    """

    __tablename__ = "split_rule"
    __table_args__ = (UniqueConstraint("category_id", "effective_from"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id", ondelete="RESTRICT"))
    effective_from: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    category: Mapped[Category] = relationship(back_populates="rules")
    shares: Mapped[list[SplitRuleShare]] = relationship(
        back_populates="rule", cascade="all, delete-orphan", lazy="selectin"
    )


class SplitRuleShare(Base):
    """One household's share of a rule; a household without a row has none."""

    __tablename__ = "split_rule_share"
    __table_args__ = (CheckConstraint("basis_points BETWEEN 0 AND 10000", name="basis_points"),)

    rule_id: Mapped[int] = mapped_column(
        ForeignKey("split_rule.id", ondelete="CASCADE"), primary_key=True
    )
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="RESTRICT"), primary_key=True
    )
    basis_points: Mapped[int] = mapped_column(Integer)

    rule: Mapped[SplitRule] = relationship(back_populates="shares")


class Bill(TimestampMixin, Base):
    """A bill or an agreed expense, paid by one household and split line by line.

    Deleting one only marks it, so the history of what was paid stays whole.
    """

    __tablename__ = "bill"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    #: The date on the bill, which picks the rule each line is split by.
    date: Mapped[date] = mapped_column(Date, index=True)
    supplier: Mapped[str] = mapped_column(String(200), default="")
    description: Mapped[str] = mapped_column(String(300), default="")
    invoice_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_cents: Mapped[int] = mapped_column(Integer)
    paid_by_id: Mapped[int] = mapped_column(ForeignKey("household.id", ondelete="RESTRICT"))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    paid_by: Mapped[Household] = relationship(lazy="joined")
    lines: Mapped[list[BillLine]] = relationship(
        back_populates="bill",
        cascade="all, delete-orphan",
        order_by="BillLine.position",
        lazy="selectin",
    )
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="bill", lazy="selectin", order_by="Attachment.id"
    )


class BillLine(Base):
    """Part of a bill in one category, split by the rule in force on the bill's date."""

    __tablename__ = "bill_line"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bill.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    description: Mapped[str] = mapped_column(String(300), default="")
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id", ondelete="RESTRICT"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    #: The rule the shares were taken from. A rule in use cannot be deleted.
    rule_id: Mapped[int] = mapped_column(ForeignKey("split_rule.id", ondelete="RESTRICT"))

    bill: Mapped[Bill] = relationship(back_populates="lines")
    category: Mapped[Category] = relationship(lazy="joined")
    shares: Mapped[list[BillLineShare]] = relationship(
        back_populates="line", cascade="all, delete-orphan", lazy="selectin"
    )


class BillLineShare(Base):
    """What one household owes of a line, fixed when the line was split."""

    __tablename__ = "bill_line_share"

    line_id: Mapped[int] = mapped_column(
        ForeignKey("bill_line.id", ondelete="CASCADE"), primary_key=True
    )
    household_id: Mapped[int] = mapped_column(
        ForeignKey("household.id", ondelete="RESTRICT"), primary_key=True
    )
    amount_cents: Mapped[int] = mapped_column(Integer)

    line: Mapped[BillLine] = relationship(back_populates="shares")


class Settlement(TimestampMixin, Base):
    """Money one household sent another to settle up."""

    __tablename__ = "settlement"
    __table_args__ = (
        CheckConstraint("from_id <> to_id", name="between_households"),
        CheckConstraint("amount_cents > 0", name="positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    from_id: Mapped[int] = mapped_column(ForeignKey("household.id", ondelete="RESTRICT"))
    to_id: Mapped[int] = mapped_column(ForeignKey("household.id", ondelete="RESTRICT"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    note: Mapped[str] = mapped_column(Text, default="")
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    from_household: Mapped[Household] = relationship(foreign_keys=[from_id], lazy="joined")
    to_household: Mapped[Household] = relationship(foreign_keys=[to_id], lazy="joined")
    attachments: Mapped[list[Attachment]] = relationship(
        back_populates="settlement", lazy="selectin", order_by="Attachment.id"
    )


class Attachment(Base):
    """A file attached to a bill or a settlement: the bill's PDF, a photo, a transfer receipt.

    The bytes live in the data directory under their SHA-256, so the same file attached twice is
    stored once.
    """

    __tablename__ = "attachment"
    __table_args__ = (
        CheckConstraint("(bill_id IS NULL) <> (settlement_id IS NULL)", name="one_owner"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bill_id: Mapped[int | None] = mapped_column(
        ForeignKey("bill.id", ondelete="CASCADE"), nullable=True, index=True
    )
    settlement_id: Mapped[int | None] = mapped_column(
        ForeignKey("settlement.id", ondelete="CASCADE"), nullable=True, index=True
    )
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("person.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)

    bill: Mapped[Bill | None] = relationship(back_populates="attachments")
    settlement: Mapped[Settlement | None] = relationship(back_populates="attachments")
