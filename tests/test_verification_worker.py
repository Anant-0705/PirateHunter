from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_verification_worker_end_to_end_synthetic():
    pytest.skip("requires fixture media and docker-compose services; covered by demo path")
