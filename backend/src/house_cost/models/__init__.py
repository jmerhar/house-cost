"""The database models. Importing this package registers every table on ``Base.metadata``."""

from .admin import (
    Adjustment,
    AppSetting,
    AuditEvent,
    Reconciliation,
    ReconciliationShare,
    ReconciliationStatus,
)
from .base import Base, TimestampMixin, UtcDateTime, utcnow
from .ledger import (
    WHOLE,
    Attachment,
    Bill,
    BillLine,
    BillLineShare,
    Category,
    Settlement,
    SplitRule,
    SplitRuleShare,
)
from .papers import Document, Service, Supplier
from .people import Household, Passkey, Person, Role, Session

__all__ = [
    "WHOLE",
    "Adjustment",
    "AppSetting",
    "Attachment",
    "AuditEvent",
    "Base",
    "Bill",
    "BillLine",
    "BillLineShare",
    "Category",
    "Document",
    "Household",
    "Passkey",
    "Person",
    "Reconciliation",
    "ReconciliationShare",
    "ReconciliationStatus",
    "Role",
    "Service",
    "Session",
    "Settlement",
    "SplitRule",
    "SplitRuleShare",
    "Supplier",
    "TimestampMixin",
    "UtcDateTime",
    "utcnow",
]
