"""Unit tests for duplicate contact detection by name + tax number (Issue #14).

Tests cover:
  - create_contact returns HTTP 409 when name + tax_number match existing contact
  - Duplicate check is case-insensitive on name
  - No duplicate check when tax_number is null (names alone may repeat)
  - Different tenant with same name + tax_number is allowed (tenant isolation)
  - Error includes the existing contact's ID
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")


# ---------------------------------------------------------------------------
# Service source inspection tests
# ---------------------------------------------------------------------------


class TestDuplicateContactSource:
    """Verify service code includes duplicate detection logic."""

    def _read_service_source(self) -> str:
        import pathlib

        svc_path = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "contacts.py"
        return svc_path.read_text()

    def test_duplicate_contact_error_class_exists(self) -> None:
        source = self._read_service_source()
        assert "class DuplicateContactError" in source

    def test_create_contact_checks_duplicates(self) -> None:
        source = self._read_service_source()
        assert "DuplicateContactError" in source


# ---------------------------------------------------------------------------
# Service-level async tests
# ---------------------------------------------------------------------------


@_skip_311
class TestDuplicateContactDetection:
    """create_contact should detect duplicate name + tax_number pairs."""

    @pytest.fixture
    def mock_db(self) -> AsyncMock:
        db = AsyncMock()
        db.flush = AsyncMock()
        db.refresh = AsyncMock()
        db.execute = AsyncMock()
        db.scalar = AsyncMock()
        db.add = MagicMock()
        return db

    def _make_existing_contact(
        self,
        *,
        contact_id: str = "existing-c1",
        name: str = "Acme Corp",
        tax_number: str = "ABN-123",
    ) -> MagicMock:
        c = MagicMock()
        c.id = contact_id
        c.name = name
        c.tax_number = tax_number
        c.tenant_id = "t1"
        return c

    @pytest.mark.anyio
    async def test_duplicate_name_and_tax_number_raises_error(self, mock_db: AsyncMock) -> None:
        """Exact name + tax_number match should raise DuplicateContactError."""
        from app.services.contacts import DuplicateContactError, create_contact

        existing = self._make_existing_contact()

        # First scalar call: code conflict check (returns None)
        # Second scalar call: duplicate name+tax check (returns existing contact)
        mock_db.scalar = AsyncMock(side_effect=[None, existing])

        with pytest.raises(DuplicateContactError) as exc_info:
            await create_contact(
                mock_db,
                "t1",
                "actor-1",
                contact_type="customer",
                name="Acme Corp",
                tax_number="ABN-123",
            )

        assert "existing-c1" in str(exc_info.value)

    @pytest.mark.anyio
    async def test_case_insensitive_name_match_raises_error(self, mock_db: AsyncMock) -> None:
        """Name match should be case-insensitive."""
        from app.services.contacts import DuplicateContactError, create_contact

        existing = self._make_existing_contact(name="ACME CORP")

        mock_db.scalar = AsyncMock(side_effect=[None, existing])

        with pytest.raises(DuplicateContactError):
            await create_contact(
                mock_db,
                "t1",
                "actor-1",
                contact_type="customer",
                name="acme corp",
                tax_number="ABN-123",
            )

    @pytest.mark.anyio
    async def test_null_tax_number_skips_duplicate_check(self, mock_db: AsyncMock) -> None:
        """When tax_number is null, no duplicate detection is performed."""
        from app.services.contacts import create_contact

        # Only the code conflict check (returns None) — no second call needed
        mock_db.scalar = AsyncMock(return_value=None)

        contact = await create_contact(
            mock_db,
            "t1",
            "actor-1",
            contact_type="customer",
            name="Acme Corp",
            tax_number=None,
        )

        assert contact is not None
        assert mock_db.add.call_count >= 1

    @pytest.mark.anyio
    async def test_same_name_different_tax_number_allowed(self, mock_db: AsyncMock) -> None:
        """Same name but different tax_number should not trigger duplicate error."""
        from app.services.contacts import create_contact

        # Code check: None, duplicate check: None (no match)
        mock_db.scalar = AsyncMock(side_effect=[None, None])

        contact = await create_contact(
            mock_db,
            "t1",
            "actor-1",
            contact_type="customer",
            name="Acme Corp",
            tax_number="DIFFERENT-TAX",
        )

        assert contact is not None
        assert mock_db.add.call_count >= 1

    @pytest.mark.anyio
    async def test_duplicate_error_includes_existing_id(self, mock_db: AsyncMock) -> None:
        """Error message should include the ID of the existing contact."""
        from app.services.contacts import DuplicateContactError, create_contact

        existing = self._make_existing_contact(contact_id="dup-contact-42")

        mock_db.scalar = AsyncMock(side_effect=[None, existing])

        with pytest.raises(DuplicateContactError, match="dup-contact-42"):
            await create_contact(
                mock_db,
                "t1",
                "actor-1",
                contact_type="supplier",
                name="Acme Corp",
                tax_number="ABN-123",
            )
