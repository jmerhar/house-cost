"""Suppliers and the services the house has with them. Anyone may keep them up to date, and
remove one nothing refers to."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import record
from ...models import Bill, Category, Document, SentNotification, Service, Supplier
from ...notify.events import service_key_prefixes
from ..deps import DbDep, PersonDep, get_or_404
from ..schemas import ServiceIn, ServiceOut, SupplierIn, SupplierOut

router = APIRouter(tags=["services"])


async def _known_category(db: AsyncSession, category_id: int | None) -> None:
    if category_id is not None and await db.get(Category, category_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_category")


async def _flush_unique(db: AsyncSession, conflict: str) -> None:
    try:
        await db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, conflict) from None


async def _suppliers_in_use(db: AsyncSession) -> set[int]:
    """The suppliers a service or a document refers to."""
    rows = await db.execute(
        select(Service.supplier_id).union(
            select(Document.supplier_id).where(Document.supplier_id.is_not(None))
        )
    )
    return set(rows.scalars())


async def _services_in_use(db: AsyncSession) -> set[int]:
    """The services a bill or a document refers to. A deleted bill does not count: it loses its
    service when the service goes."""
    rows = await db.execute(
        select(Bill.service_id)
        .where(Bill.service_id.is_not(None), Bill.deleted_at.is_(None))
        .union(select(Document.service_id).where(Document.service_id.is_not(None)))
    )
    return set(rows.scalars())


def _supplier_out(supplier: Supplier, in_use: set[int]) -> SupplierOut:
    return SupplierOut.model_validate(supplier).model_copy(update={"in_use": supplier.id in in_use})


def _service_out(service: Service, in_use: set[int]) -> ServiceOut:
    return ServiceOut.model_validate(service).model_copy(update={"in_use": service.id in in_use})


@router.get("/suppliers")
async def list_suppliers(db: DbDep) -> list[SupplierOut]:
    """Every supplier, by name."""
    rows = await db.execute(select(Supplier).order_by(Supplier.name))
    in_use = await _suppliers_in_use(db)
    return [_supplier_out(row, in_use) for row in rows.scalars()]


@router.post("/suppliers", status_code=status.HTTP_201_CREATED)
async def create_supplier(body: SupplierIn, person: PersonDep, db: DbDep) -> SupplierOut:
    """Add a supplier. Its tax number, when given, must be its own."""
    await _known_category(db, body.default_category_id)
    supplier = Supplier(**body.model_dump())
    db.add(supplier)
    await _flush_unique(db, "supplier_exists")
    out = _supplier_out(supplier, set())
    record(db, person, "create", "supplier", supplier.id, after=out)
    return out


@router.put("/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: int, body: SupplierIn, person: PersonDep, db: DbDep
) -> SupplierOut:
    """Correct a supplier's details."""
    supplier = await get_or_404(db, Supplier, supplier_id)
    await _known_category(db, body.default_category_id)
    in_use = await _suppliers_in_use(db)
    before = _supplier_out(supplier, in_use)
    for key, value in body.model_dump().items():
        setattr(supplier, key, value)
    await _flush_unique(db, "supplier_exists")
    out = _supplier_out(supplier, in_use)
    record(db, person, "update", "supplier", supplier.id, before=before, after=out)
    return out


@router.delete("/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_supplier(supplier_id: int, person: PersonDep, db: DbDep) -> None:
    """Remove a supplier added by mistake; one with services or documents cannot be removed."""
    supplier = await get_or_404(db, Supplier, supplier_id)
    if supplier.id in await _suppliers_in_use(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "supplier_in_use")
    record(db, person, "delete", "supplier", supplier.id, before=_supplier_out(supplier, set()))
    await db.delete(supplier)


@router.get("/services")
async def list_services(db: DbDep) -> list[ServiceOut]:
    """Every service, by supplier and name."""
    rows = await db.execute(
        select(Service).join(Supplier).order_by(Supplier.name, Service.name, Service.id)
    )
    in_use = await _services_in_use(db)
    return [_service_out(row, in_use) for row in rows.scalars()]


async def _check(db: AsyncSession, body: ServiceIn) -> None:
    if await db.get(Supplier, body.supplier_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown_supplier")
    await _known_category(db, body.default_category_id)


@router.post("/services", status_code=status.HTTP_201_CREATED)
async def create_service(body: ServiceIn, person: PersonDep, db: DbDep) -> ServiceOut:
    """Add a service, with what its contract says."""
    await _check(db, body)
    service = Service(**body.model_dump())
    db.add(service)
    await db.flush()
    out = _service_out(service, set())
    record(db, person, "create", "service", service.id, after=out)
    return out


@router.put("/services/{service_id}")
async def update_service(
    service_id: int, body: ServiceIn, person: PersonDep, db: DbDep
) -> ServiceOut:
    """Correct a service, or mark it ended by deactivating it."""
    service = await get_or_404(db, Service, service_id)
    await _check(db, body)
    in_use = await _services_in_use(db)
    before = _service_out(service, in_use)
    for key, value in body.model_dump().items():
        setattr(service, key, value)
    await db.flush()
    await db.refresh(service)
    out = _service_out(service, in_use)
    record(db, person, "update", "service", service.id, before=before, after=out)
    return out


@router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_service(service_id: int, person: PersonDep, db: DbDep) -> None:
    """Remove a service added by mistake; one with bills or documents cannot be removed.

    The reminders already sent about it go too, since SQLite can give a later service the same
    id, which would then never be reminded of its own contract.
    """
    service = await get_or_404(db, Service, service_id)
    if service.id in await _services_in_use(db):
        raise HTTPException(status.HTTP_409_CONFLICT, "service_in_use")
    record(db, person, "delete", "service", service.id, before=_service_out(service, set()))
    await db.execute(
        delete(SentNotification).where(
            or_(*(SentNotification.key.startswith(p) for p in service_key_prefixes(service.id)))
        )
    )
    await db.delete(service)
