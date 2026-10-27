"""What the API accepts and returns. The interface's types are generated from these."""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from ..auth import MIN_PASSWORD_LENGTH
from ..contacts import PHONE_TYPED
from ..models import WHOLE

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
Login = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, min_length=1, max_length=100),
]
Password = Annotated[str, StringConstraints(min_length=MIN_PASSWORD_LENGTH, max_length=500)]
Language = Literal["en", "pt-PT"]
#: Whole cents; an amount may be negative (a refund or a credit note).
Cents = Annotated[int, Field(ge=-100_000_000, le=100_000_000)]
BasisPoints = Annotated[int, Field(ge=0, le=WHOLE)]


class Out(BaseModel):
    """A record read from the database.

    A field with a default is still always in a response, so the schema marks it required there,
    and the interface's generated types need not treat it as possibly missing.
    """

    model_config = ConfigDict(
        from_attributes=True, json_schema_serialization_defaults_required=True
    )


# --- People ------------------------------------------------------------------------------------


class HouseholdOut(Out):
    id: int
    name: str
    position: int
    active: bool


class HouseholdIn(BaseModel):
    name: Name
    position: int = 0
    active: bool = True


class PersonOut(Out):
    id: int
    name: str
    login: str
    role: Literal["admin", "member"]
    language: Language | None
    household_id: int
    active: bool


#: Contacts as typed; the routes check them and put a phone number in international form.
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=254)]
Phone = Annotated[str, StringConstraints(max_length=30, pattern=PHONE_TYPED)]


class PersonDetail(PersonOut):
    """A person with their contacts, which only an admin and the person themselves see; None
    for anyone else. The audit log records the plain ``PersonOut``, without them."""

    email: str | None = None
    phone: str | None = None


class PersonIn(BaseModel):
    name: Name
    login: Login
    role: Literal["admin", "member"] = "member"
    language: Language | None = None
    household_id: int
    password: Password
    email: Email = ""
    phone: Phone = ""


class PersonUpdate(BaseModel):
    """An admin's change to someone; a password given here resets theirs."""

    name: Name
    login: Login
    role: Literal["admin", "member"]
    language: Language | None = None
    household_id: int
    active: bool
    password: Password | None = None
    #: Left out, they stay as they are.
    email: Email | None = None
    phone: Phone | None = None


Event = Literal["new_bill", "price_change", "contract", "missing_bill"]


class Me(PersonOut):
    """The person logged in, with what the interface needs to know about the app."""

    household_name: str
    reconciliation_enabled: bool
    #: Whether an Anthropic API key is set, which the reading and document features need.
    claude_enabled: bool
    email: str
    phone: str
    #: The kinds of contact notifications can be sent to, as the deployment configures them.
    notify_channels: list[Literal["email", "signal"]]
    #: The country a phone number typed without a country code is taken to be in.
    phone_country_code: str
    notify_on: dict[Event, bool]


class MeUpdate(BaseModel):
    """A person's change to themselves. A new password needs the current one; notification
    settings left out stay as they are."""

    name: Name
    language: Language | None = None
    current_password: str | None = None
    new_password: Password | None = None
    email: Email | None = None
    phone: Phone | None = None
    notify_on: dict[Event, bool] | None = None


class TestSent(BaseModel):
    sent: bool


class SessionOut(Out):
    id: int
    created_at: datetime
    last_seen_at: datetime
    user_agent: str
    current: bool = False


class SetupState(BaseModel):
    """What the page needs before anyone logs in: whether setup is due, and the app's name, or
    None for the interface's own."""

    required: bool
    title: str | None


class SetupIn(BaseModel):
    """The first administrator and their household."""

    household_name: Name
    name: Name
    login: Login
    password: Password
    language: Language | None = None


class LoginIn(BaseModel):
    login: Login
    password: str = Field(max_length=500)


# --- Categories and rules -----------------------------------------------------------------------


class CategoryOut(Out):
    id: int
    name: str
    description: str
    active: bool


class CategoryIn(BaseModel):
    name: Name
    description: Text = ""
    active: bool = True


class RuleShare(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    household_id: int
    basis_points: BasisPoints


class RuleOut(Out):
    id: int
    category_id: int
    effective_from: date
    note: str
    shares: list[RuleShare]
    created_at: datetime
    in_use: bool = False


def _whole(shares: list[RuleShare]) -> list[RuleShare]:
    """Shares naming each household once and adding up to 100%."""
    ids = [share.household_id for share in shares]
    if len(ids) != len(set(ids)):
        raise ValueError("each household can have only one share")
    if sum(share.basis_points for share in shares) != WHOLE:
        raise ValueError("the shares must add up to 100%")
    return shares


class RuleIn(BaseModel):
    category_id: int
    effective_from: date
    note: Text = ""
    shares: list[RuleShare]

    _shares = field_validator("shares")(_whole)


# --- Bills --------------------------------------------------------------------------------------


class LineShare(Out):
    household_id: int
    amount_cents: int


class SplitPreview(BaseModel):
    """How an amount in a category would be split on a date, and by which rule."""

    rule_id: int
    shares: list[LineShare]


class LineOut(Out):
    id: int
    description: str
    category_id: int
    amount_cents: int
    rule_id: int
    shares: list[LineShare]


class AttachmentOut(Out):
    id: int
    filename: str
    content_type: str
    size: int


Quantity = Literal["electricity_kwh", "water_m3"]


class ReadingIn(BaseModel):
    """A quantity the bill measures, and its unit price in euros before tax."""

    model_config = ConfigDict(from_attributes=True)

    quantity: Quantity
    value: Annotated[float, Field(ge=0, le=10_000_000)]
    unit_price: Annotated[float, Field(ge=0, le=1000)] | None = None


class BillOut(Out):
    id: int
    date: date
    supplier: str
    description: str
    invoice_number: str | None
    period_start: date | None
    period_end: date | None
    due_date: date | None
    total_cents: int
    paid_by_id: int
    service_id: int | None
    notes: str
    lines: list[LineOut]
    attachments: list[AttachmentOut]
    readings: list[ReadingIn]
    created_at: datetime
    updated_at: datetime
    locked: bool = False


class LineIn(BaseModel):
    """A line of a bill. ``id`` names an existing line, whose split is kept if nothing that
    decides it (the category, the amount, the bill's date) has changed."""

    id: int | None = None
    description: Short = ""
    category_id: int
    amount_cents: Cents


class BillIn(BaseModel):
    """A bill; its total is the sum of its lines."""

    date: date
    supplier: Short = ""
    description: Short = ""
    invoice_number: (
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None
    ) = None
    period_start: date | None = None
    period_end: date | None = None
    due_date: date | None = None
    paid_by_id: int
    service_id: int | None = None
    notes: Text = ""
    lines: list[LineIn] = Field(min_length=1, max_length=50)
    readings: list[ReadingIn] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _period_in_order(self) -> BillIn:
        if self.period_start and self.period_end and self.period_end < self.period_start:
            raise ValueError("the period cannot end before it starts")
        return self


class BillPage(BaseModel):
    items: list[BillOut]
    total: int


# --- Settlements --------------------------------------------------------------------------------


class SettlementOut(Out):
    id: int
    date: date
    from_id: int
    to_id: int
    amount_cents: int
    note: str
    attachments: list[AttachmentOut]
    created_at: datetime


class SettlementIn(BaseModel):
    date: date
    from_id: int
    to_id: int
    amount_cents: Annotated[int, Field(gt=0, le=100_000_000)]
    note: Text = ""

    @model_validator(mode="after")
    def _between_households(self) -> SettlementIn:
        if self.from_id == self.to_id:
            raise ValueError("a settlement is between two different households")
        return self


# --- Suppliers, services and documents ----------------------------------------------------------

#: A Portuguese tax number, as invoices print it; spaces are dropped.
Nif = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^\d{9}$")]


class SupplierOut(Out):
    id: int
    name: str
    nif: str | None
    default_category_id: int | None
    notes: str
    active: bool
    #: Whether a service or a document refers to it, which keeps it from being deleted.
    in_use: bool = False


class SupplierIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    nif: Nif | None = None
    default_category_id: int | None = None
    notes: Text = ""
    active: bool = True

    @field_validator("nif", mode="before")
    @classmethod
    def _digits(cls, value: object) -> object:
        """A NIF typed with spaces, as invoices print it ("506 743 357"), or left empty."""
        if isinstance(value, str):
            value = value.replace(" ", "")
            return value or None
        return value


class ServiceOut(Out):
    id: int
    supplier_id: int
    name: str
    identifiers: dict[str, str]
    default_category_id: int | None
    starts_on: date | None
    ends_on: date | None
    renews_automatically: bool
    lock_in_until: date | None
    notice_days: int | None
    billed_every_days: int | None
    notes: str
    active: bool
    #: Whether a bill or a document refers to it, which keeps it from being deleted.
    in_use: bool = False


class ServiceIn(BaseModel):
    supplier_id: int
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    identifiers: dict[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)],
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)],
    ] = Field(default_factory=dict, max_length=20)
    default_category_id: int | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    renews_automatically: bool = True
    lock_in_until: date | None = None
    notice_days: Annotated[int, Field(ge=0, le=3650)] | None = None
    billed_every_days: Annotated[int, Field(ge=1, le=3650)] | None = None
    notes: Text = ""
    active: bool = True


DocumentKind = Literal["contract", "terms", "agreement", "bill", "info", "other"]


class DocumentOut(Out):
    id: int
    title: str
    kind: DocumentKind
    dated: date | None
    supplier_id: int | None
    service_id: int | None
    notes: str
    filename: str
    content_type: str
    size: int
    pages: int | None
    has_text: bool
    created_at: datetime


class DocumentUpdate(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
    kind: DocumentKind = "other"
    dated: date | None = None
    supplier_id: int | None = None
    service_id: int | None = None
    notes: Text = ""


class DocumentMatch(DocumentOut):
    """A document found by a search, with the text around the first match."""

    excerpt: str


# --- Reading bills ------------------------------------------------------------------------------


class ProposedLine(BaseModel):
    description: str
    amount_cents: int
    category_id: int | None


class ServiceChanges(BaseModel):
    """What the bill says about its service's contract that differs from what is on file."""

    ends_on: date | None = None
    renews_automatically: bool | None = None
    lock_in_until: date | None = None


class Terms(BaseModel):
    """A contract's terms as Claude read them, for a person to check before using any."""

    service_name: str | None
    supplier_name: str | None
    starts_on: date | None
    ends_on: date | None
    renews_automatically: bool | None
    lock_in_until: date | None
    notice_days: int | None
    billed_every_days: int | None
    summary: str


Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]


class QuestionIn(BaseModel):
    question: Question


class CitationOut(BaseModel):
    """A passage an answer rests on, and its page where the document has pages."""

    page: int | None
    quote: str


class AnswerOut(BaseModel):
    text: str
    citations: list[CitationOut]


class ProposedContract(BaseModel):
    """What a bill says about its contract, for a service set up from it: when it ends or renews,
    whether it renews by itself, its minimum term, and how often it bills."""

    ends_on: date | None
    renews_automatically: bool | None
    lock_in_until: date | None
    billed_every_days: int | None


class Proposal(BaseModel):
    """A bill as read from its file, to be checked and corrected before it is saved.

    ``sources`` says where each value came from: "qr" for the invoice's fiscal QR code, "text" for
    the PDF's own text, "ocr" for text read from the image of a page, "claude" for what Claude
    read where the others found nothing.
    """

    supplier_id: int | None
    supplier_name: str | None
    issuer_nif: str | None
    service_id: int | None
    date: date | None
    invoice_number: str | None
    total_cents: int | None
    period_start: date | None
    period_end: date | None
    due_date: date | None
    lines: list[ProposedLine]
    readings: list[ReadingIn]
    service_changes: ServiceChanges
    #: The service's references the bill prints, such as {"CPE": "PT0002…"}.
    identifiers: dict[str, str]
    contract: ProposedContract
    sources: dict[str, str]
    warnings: list[str]
    text_source: Literal["text", "ocr", "none"]
    duplicate_bill_id: int | None


class ReadingPoint(BaseModel):
    """One bill's reading, for a consumption chart."""

    bill_id: int
    date: date
    period_start: date | None
    period_end: date | None
    service_id: int | None
    quantity: Quantity
    value: float
    unit_price: float | None


# --- Balances and reports -----------------------------------------------------------------------


class BalanceOut(BaseModel):
    household_id: int
    name: str
    paid_cents: int
    share_cents: int
    adjustment_cents: int
    sent_cents: int
    received_cents: int
    balance_cents: int


class TransferOut(BaseModel):
    from_id: int
    to_id: int
    amount_cents: int


class Balances(BaseModel):
    households: list[BalanceOut]
    transfers: list[TransferOut]


class HouseholdAmount(BaseModel):
    household_id: int
    amount_cents: int


class CategoryTotal(BaseModel):
    category_id: int
    name: str
    total_cents: int
    shares: list[HouseholdAmount]


class MonthTotal(BaseModel):
    month: int
    total_cents: int
    shares: list[HouseholdAmount]


class Summary(BaseModel):
    """A year's costs by category and by month, with each household's share."""

    year: int
    years: list[int]
    total_cents: int
    shares: list[HouseholdAmount]
    categories: list[CategoryTotal]
    months: list[MonthTotal]


# --- Administration -----------------------------------------------------------------------------


class AuditOut(BaseModel):
    id: int
    at: datetime
    person_id: int | None
    person_name: str | None
    action: str
    entity: str
    entity_id: int | None
    before: dict | None
    after: dict | None
    #: Whether the record still exists to open: a deleted bill does not.
    exists: bool


class AuditPage(BaseModel):
    items: list[AuditOut]
    total: int


class SettingsOut(BaseModel):
    reconciliation_enabled: bool
    site_title: str


SiteTitle = Annotated[str, StringConstraints(strip_whitespace=True, max_length=60)]


class SettingsIn(BaseModel):
    """A change to the app's settings; a setting left out stays as it is."""

    reconciliation_enabled: bool | None = None
    site_title: SiteTitle | None = None


class ReconciliationShareIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category_id: int
    household_id: int
    basis_points: BasisPoints


class ReconciliationIn(BaseModel):
    period_start: date
    period_end: date
    note: Text = ""
    shares: list[ReconciliationShareIn] = []

    @model_validator(mode="after")
    def _valid(self) -> ReconciliationIn:
        if self.period_end < self.period_start:
            raise ValueError("the period cannot end before it starts")
        by_category: dict[int, list[RuleShare]] = {}
        for share in self.shares:
            by_category.setdefault(share.category_id, []).append(
                RuleShare(household_id=share.household_id, basis_points=share.basis_points)
            )
        for shares in by_category.values():
            _whole(shares)
        return self


class ReconciliationLine(BaseModel):
    """One household's position over a reconciliation's period."""

    household_id: int
    charged_cents: int
    reconciled_cents: int
    adjustment_cents: int


class ReconciliationOut(Out):
    id: int
    period_start: date
    period_end: date
    status: Literal["draft", "closed"]
    note: str
    shares: list[ReconciliationShareIn]
    closed_at: datetime | None
    lines: list[ReconciliationLine] = []
    bill_count: int = 0
