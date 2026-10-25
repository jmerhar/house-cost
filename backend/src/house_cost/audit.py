"""Recording who changed what, and the app's settings."""

from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AppSetting, AuditEvent, Person

#: The settings the app keeps, and their values until someone changes them.
DEFAULTS: dict[str, Any] = {"reconciliation_enabled": False}


def snapshot(model: BaseModel | None) -> dict | None:
    """A record as the audit log keeps it: the API's own view of it, in JSON."""
    return None if model is None else model.model_dump(mode="json")


def record(
    db: AsyncSession,
    actor: Person | None,
    action: str,
    entity: str,
    entity_id: int | None,
    *,
    before: BaseModel | None = None,
    after: BaseModel | None = None,
) -> None:
    """Add an event to the audit log, in the same transaction as the change it describes."""
    db.add(
        AuditEvent(
            person_id=actor.id if actor else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=snapshot(before),
            after=snapshot(after),
        )
    )


async def get_setting(db: AsyncSession, key: str) -> Any:
    """A setting's value, or its default when it was never set."""
    row = await db.get(AppSetting, key)
    return DEFAULTS[key] if row is None else row.value


async def set_setting(db: AsyncSession, key: str, value: Any) -> None:
    """Store a setting's value."""
    if key not in DEFAULTS:
        raise KeyError(key)
    row = await db.get(AppSetting, key)
    if row is None:
        db.add(AppSetting(key=key, value=value))
    else:
        row.value = value
