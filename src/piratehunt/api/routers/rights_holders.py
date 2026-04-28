from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.api.dependencies import get_db
from piratehunt.dmca.rights_holders import RightsHolderRegistry
from piratehunt.dmca.types import RightsHolderInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rights-holders", tags=["dmca"])


class RightsHolderCreate(BaseModel):
    """Request body for creating a rights holder."""

    name: str
    legal_email: str
    address: str
    authorized_agent: str
    default_language: str = "en"
    signature_block: str = ""


class RightsHolderUpdate(BaseModel):
    """Request body for updating a rights holder."""

    name: Optional[str] = None
    legal_email: Optional[str] = None
    address: Optional[str] = None
    authorized_agent: Optional[str] = None
    default_language: Optional[str] = None
    signature_block: Optional[str] = None


@router.get("/", response_model=list[RightsHolderInfo])
async def list_rights_holders(db: AsyncSession = Depends(get_db)) -> list[RightsHolderInfo]:
    """List all rights holders."""
    registry = RightsHolderRegistry()
    return await registry.list_rights_holders(db)


@router.post("/", response_model=RightsHolderInfo, status_code=status.HTTP_201_CREATED)
async def create_rights_holder(
    request: RightsHolderCreate, db: AsyncSession = Depends(get_db)
) -> RightsHolderInfo:
    """Create a new rights holder."""
    registry = RightsHolderRegistry()
    holder = await registry.create_rights_holder(
        db,
        name=request.name,
        legal_email=request.legal_email,
        address=request.address,
        authorized_agent=request.authorized_agent,
        default_language=request.default_language,
        signature_block=request.signature_block,
    )
    await db.commit()
    return holder


@router.get("/{holder_id}", response_model=RightsHolderInfo)
async def get_rights_holder(
    holder_id: str, db: AsyncSession = Depends(get_db)
) -> RightsHolderInfo:
    """Get a rights holder by ID."""
    registry = RightsHolderRegistry()
    holder = await registry.get_rights_holder(db, holder_id)

    if not holder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rights holder not found"
        )

    return holder


@router.patch("/{holder_id}", response_model=RightsHolderInfo)
async def update_rights_holder(
    holder_id: str, request: RightsHolderUpdate, db: AsyncSession = Depends(get_db)
) -> RightsHolderInfo:
    """Update a rights holder."""
    import uuid

    from sqlalchemy import select

    from piratehunt.db.models import RightsHolder

    result = await db.execute(
        select(RightsHolder).where(RightsHolder.id == uuid.UUID(holder_id))
    )
    holder = result.scalar_one_or_none()

    if not holder:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Rights holder not found"
        )

    # Update fields
    update_data = request.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(holder, field, value)

    await db.commit()
    await db.refresh(holder)

    registry = RightsHolderRegistry()
    return await registry.get_rights_holder(db, holder_id)
