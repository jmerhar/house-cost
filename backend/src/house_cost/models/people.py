"""Households, the people who log in, their sessions and their passkeys."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, UtcDateTime, utcnow


class Role(StrEnum):
    """What a person may change: an admin also sets households, people, categories and rules."""

    ADMIN = "admin"
    MEMBER = "member"


class Household(TimestampMixin, Base):
    """One of the households sharing the house's costs."""

    __tablename__ = "household"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    #: The order households are listed in, which also settles which household a rounding cent
    #: goes to when a split leaves one over.
    position: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    people: Mapped[list[Person]] = relationship(back_populates="household")


class Person(TimestampMixin, Base):
    """Someone who logs in, on behalf of their household."""

    __tablename__ = "person"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    #: Kept lower-case, so a login is matched whatever case it is typed in.
    login: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(String(20), default=Role.MEMBER)
    #: The interface's language for this person, or None to follow their browser.
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    household_id: Mapped[int] = mapped_column(ForeignKey("household.id", ondelete="RESTRICT"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: The random handle passkeys know this person by, made when their first passkey is added.
    #: Random rather than the id, so an authenticator holds nothing that identifies them.
    webauthn_handle: Mapped[bytes | None] = mapped_column(
        LargeBinary(64), nullable=True, unique=True
    )
    #: Where this person's notifications go, through the channels the deployment offers.
    #: The phone number is in international form ("+351912345678"); "" means none.
    email: Mapped[str] = mapped_column(String(254), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")
    #: Which notifications they want, by event; an event not named is wanted.
    notify_on: Mapped[dict[str, bool]] = mapped_column(JSON, default=dict)

    household: Mapped[Household] = relationship(back_populates="people", lazy="joined")

    def wants(self, event: str) -> bool:
        """Whether this person wants notifications of ``event``."""
        return self.active and self.notify_on.get(event, True)

    @property
    def is_admin(self) -> bool:
        """Whether this person may change households, people, categories and rules."""
        return self.role == Role.ADMIN


class Session(Base):
    """A browser's login. Only a hash of its token is kept, so the table cannot be replayed."""

    __tablename__ = "session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    user_agent: Mapped[str] = mapped_column(String(300), default="")

    person: Mapped[Person] = relationship(lazy="joined")


class Passkey(Base):
    """A passkey a person logs in with instead of their password."""

    __tablename__ = "passkey"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("person.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[bytes] = mapped_column(LargeBinary(1024), unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary(2048))
    #: The authenticator's signature counter; one that goes backwards betrays a cloned key.
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    transports: Mapped[list[str]] = mapped_column(JSON, default=list)
    label: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(UtcDateTime, nullable=True)

    person: Mapped[Person] = relationship(lazy="joined")
