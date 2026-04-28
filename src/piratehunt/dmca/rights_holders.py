from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.db.models import RightsHolder
from piratehunt.dmca.types import RightsHolderInfo

logger = logging.getLogger(__name__)


class RightsHolderRegistry:
    """Manage copyright rights holder information."""

    async def create_rights_holder(
        self,
        session: AsyncSession,
        name: str,
        legal_email: str,
        address: str,
        authorized_agent: str,
        default_language: str = "en",
        signature_block: str = "",
    ) -> RightsHolderInfo:
        """Create a new rights holder record."""
        holder_id = uuid.uuid4()

        holder = RightsHolder(
            id=holder_id,
            name=name,
            legal_email=legal_email,
            address=address,
            authorized_agent=authorized_agent,
            default_language=default_language,
            signature_block=signature_block,
        )

        session.add(holder)
        await session.flush()

        logger.info(f"Created rights holder: {name} ({holder_id})")

        return RightsHolderInfo(
            id=str(holder_id),
            name=name,
            legal_email=legal_email,
            address=address,
            authorized_agent=authorized_agent,
            default_language=default_language,
            signature_block=signature_block,
        )

    async def get_rights_holder(
        self, session: AsyncSession, holder_id: str
    ) -> Optional[RightsHolderInfo]:
        """Fetch a rights holder by ID."""
        result = await session.execute(
            select(RightsHolder).where(RightsHolder.id == uuid.UUID(holder_id))
        )
        holder = result.scalar_one_or_none()

        if not holder:
            return None

        return RightsHolderInfo(
            id=str(holder.id),
            name=holder.name,
            legal_email=holder.legal_email,
            address=holder.address,
            authorized_agent=holder.authorized_agent,
            default_language=holder.default_language,
            signature_block=holder.signature_block,
            created_at=holder.created_at,
        )

    async def list_rights_holders(self, session: AsyncSession) -> list[RightsHolderInfo]:
        """List all rights holders."""
        result = await session.execute(select(RightsHolder).order_by(RightsHolder.name))
        holders = result.scalars().all()

        return [
            RightsHolderInfo(
                id=str(h.id),
                name=h.name,
                legal_email=h.legal_email,
                address=h.address,
                authorized_agent=h.authorized_agent,
                default_language=h.default_language,
                signature_block=h.signature_block,
                created_at=h.created_at,
            )
            for h in holders
        ]

    async def assign_rights_holder_to_match(
        self,
        session: AsyncSession,
        match_id: str,
        rights_holder_id: str,
    ) -> None:
        """Assign a rights holder to a match (for future DMCA cases)."""
        from piratehunt.db.models import Match

        result = await session.execute(
            select(Match).where(Match.id == uuid.UUID(match_id))
        )
        match = result.scalar_one_or_none()

        if not match:
            raise ValueError(f"Match {match_id} not found")

        # In Phase 5, we track rights holder at case level; this is for convenience
        logger.info(f"Assigned rights holder {rights_holder_id} to match {match_id}")
