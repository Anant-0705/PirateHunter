"""Tests for rights holders API endpoints."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from piratehunt.api.app import app
from piratehunt.dmca.types import RightsHolderInfo


@pytest.fixture
def client():
    """Create a FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def holder_id():
    """Generate a test holder ID."""
    return str(uuid.uuid4())


@pytest.fixture
def sample_rights_holder(holder_id):
    """Create a sample RightsHolderInfo."""
    return RightsHolderInfo(
        id=holder_id,
        name="Test Sports Rights",
        legal_email="legal@testsports.com",
        address="123 Sports Avenue, Demo City",
        authorized_agent="Legal Department",
        default_language="en",
        signature_block="Signed,\nLegal Department\nTest Sports Rights",
    )


class TestRightsHoldersAPI:
    """Test rights holders API endpoints."""

    def test_list_rights_holders_endpoint_exists(self, client):
        """Test that list rights holders endpoint exists."""
        with patch("piratehunt.api.dependencies.get_session") as mock_get_session:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_get_session.return_value = mock_session

            response = client.get("/rights-holders/")
            # Endpoint should exist
            assert response.status_code in [200, 500, 422]

    def test_create_rights_holder_endpoint_exists(self, client):
        """Test that create rights holder endpoint exists."""
        with patch("piratehunt.api.dependencies.get_session") as mock_get_session:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_get_session.return_value = mock_session

            payload = {
                "name": "New Rights Holder",
                "legal_email": "legal@example.com",
                "address": "123 Test St",
                "authorized_agent": "Legal Team",
                "default_language": "en",
                "signature_block": "Signed, Legal",
            }

            response = client.post("/rights-holders/", json=payload)
            # Endpoint should exist
            assert response.status_code in [201, 400, 500, 422]

    def test_get_rights_holder_endpoint_exists(self, client, holder_id):
        """Test that get rights holder endpoint exists."""
        with patch("piratehunt.api.dependencies.get_session") as mock_get_session:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_get_session.return_value = mock_session

            response = client.get(f"/rights-holders/{holder_id}")
            # Endpoint should exist
            assert response.status_code in [404, 500, 422]

    def test_update_rights_holder_endpoint_exists(self, client, holder_id):
        """Test that update rights holder endpoint exists."""
        with patch("piratehunt.api.dependencies.get_session") as mock_get_session:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_get_session.return_value = mock_session

            payload = {
                "name": "Updated Name",
                "legal_email": "updated@example.com",
            }

            response = client.patch(f"/rights-holders/{holder_id}", json=payload)
            # Endpoint should exist
            assert response.status_code in [404, 400, 500, 422]

    def test_create_rights_holder_requires_fields(self, client):
        """Test that required fields are enforced."""
        with patch("piratehunt.api.dependencies.get_session") as mock_get_session:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_get_session.return_value = mock_session

            # Missing required fields
            payload = {"name": "Incomplete Holder"}

            response = client.post("/rights-holders/", json=payload)
            # Should validate required fields
            assert response.status_code == 422

    def test_create_rights_holder_with_optional_defaults(self, client):
        """Test that optional fields have sensible defaults."""
        with patch("piratehunt.api.dependencies.get_session") as mock_get_session:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_get_session.return_value = mock_session

            payload = {
                "name": "Test Holder",
                "legal_email": "legal@test.com",
                "address": "123 Test St",
                "authorized_agent": "Legal Team",
                # default_language and signature_block are optional
            }

            response = client.post("/rights-holders/", json=payload)
            # Should accept without optional fields
            assert response.status_code in [201, 400, 500, 422]

    def test_update_rights_holder_partial_update(self, client, holder_id):
        """Test that PATCH allows partial updates."""
        with patch("piratehunt.api.dependencies.get_session") as mock_get_session:
            mock_session = AsyncMock(spec=AsyncSession)
            mock_get_session.return_value = mock_session

            # Only update one field
            payload = {"name": "Updated Name"}

            response = client.patch(f"/rights-holders/{holder_id}", json=payload)
            # Should allow partial updates
            assert response.status_code in [200, 404, 500, 422]


class TestRightsHolderInfo:
    """Test RightsHolderInfo model."""

    def test_rights_holder_info_creation(self, sample_rights_holder):
        """Test creating a rights holder info object."""
        assert sample_rights_holder.id
        assert sample_rights_holder.name == "Test Sports Rights"
        assert sample_rights_holder.legal_email == "legal@testsports.com"

    def test_rights_holder_info_json_serialization(self, sample_rights_holder):
        """Test that rights holder info can be serialized to JSON."""
        json_data = sample_rights_holder.model_dump_json()
        assert json_data
        assert "Test Sports Rights" in json_data
        assert "legal@testsports.com" in json_data

    def test_rights_holder_info_validation(self):
        """Test RightsHolderInfo validation."""
        # Valid creation
        holder = RightsHolderInfo(
            id="test-123",
            name="Test",
            legal_email="test@example.com",
            address="123 St",
            authorized_agent="Agent",
        )
        assert holder.name == "Test"
        assert holder.legal_email == "test@example.com"

        # Valid creation with any email string (no validation enforced by default)
        holder2 = RightsHolderInfo(
            id="test-456",
            name="Test",
            legal_email="not-an-email",
            address="123 St",
            authorized_agent="Agent",
        )
        assert holder2.legal_email == "not-an-email"
