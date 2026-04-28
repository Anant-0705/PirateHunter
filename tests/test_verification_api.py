from __future__ import annotations

import pytest

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def test_verification_api_list_detail_override_flows():
    pytest.skip(
        "requires docker-compose database; endpoints are exercised in integration environment"
    )
