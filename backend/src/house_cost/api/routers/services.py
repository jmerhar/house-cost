"""Suppliers and the services the house has with them. Anyone may keep them up to date."""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ...audit import record
from ...models import Category, Service, Supplier
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


@router.get("/suppliers")
async def list_suppliers(db: DbDep) -> list[SupplierOut]:
    """Every supplier, by name."""
    rows = await db.execute(select(Supplier).order_by(Supplier.name))
    return [SupplierOut.model_validate(row) for row in rows.scalars()]


@router.post("/suppliers", status_code=status.HTTP_201_CREATED)
async def create_supplier(body: SupplierIn, person: PersonDep, db: DbDep) -> SupplierOut:
    """Add a supplier. Its tax number, when given, must be its own."""
    await _known_category(db, body.default_category_id)
    supplier = Supplier(**body.model_dump())
    db.add(supplier)
    await _flush_unique(db, "supplier_exists")
    out = SupplierOut.model_validate(supplier)
    record(db, person, "create", "supplier", supplier.id, after=out)
    return out


@router.put("/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: int, body: SupplierIn, person: PersonDep, db: DbDep
) -> SupplierOut:
    """Correct a supplier's details."""
    supplier = await get_or_404(db, Supplier, supplier_id)
    await _known_category(db, body.default_category_id)
    before = SupplierOut.model_validate(supplier)
    for key, value in body.model_dump().items():
        setattr(supplier, key, value)
    await _flush_unique(db, "supplier_exists")
    out = SupplierOut.model_validate(supplier)
    record(db, person, "update", "supplier", supplier.id, before=before, after=out)
    return out


@router.get("/services")
async def list_services(db: DbDep) -> list[ServiceOut]:
    """Every service, by supplier and name."""
    rows = await db.execute(
        select(Service).join(Supplier).order_by(Supplier.name, Service.name, Service.id)
    )
    return [ServiceOut.model_validate(row) for row in rows.scalars()]


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
    out = ServiceOut.model_validate(service)
    record(db, person, "create", "service", service.id, after=out)
    return out


@router.put("/services/{service_id}")
async def update_service(
    service_id: int, body: ServiceIn, person: PersonDep, db: DbDep
) -> ServiceOut:
    """Correct a service, or mark it ended by deactivating it."""
    service = await get_or_404(db, Service, service_id)
    await _check(db, body)
    before = ServiceOut.model_validate(service)
    for key, value in body.model_dump().items():
        setattr(service, key, value)
    await db.flush()
    await db.refresh(service)
    out = ServiceOut.model_validate(service)
    record(db, person, "update", "service", service.id, before=before, after=out)
    return out
