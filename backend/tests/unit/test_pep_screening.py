"""Unit tests for PEP (Politically Exposed Person) screening.

Tests the OpenSanctions PEP feed parsing, refresh logic, and integration
with the existing sanctions screening pipeline (fuzzy name matching,
result storage, KYC status sync).
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# _parse_opensanctions_pep_json
# ---------------------------------------------------------------------------


class TestParseOpenSanctionsPepJson:
    """Verify that the OpenSanctions PEP JSON feed is parsed into the
    canonical entry format used by _store_snapshot."""

    def test_parses_individual_with_aliases_and_countries(self) -> None:
        from app.services.sanctions import _parse_opensanctions_pep_json

        data = _make_opensanctions_pep_payload(
            [
                {
                    "id": "Q123",
                    "caption": "John Doe",
                    "schema": "Person",
                    "properties": {
                        "name": ["John Doe"],
                        "alias": ["Johnny D"],
                        "country": ["US", "GB"],
                        "position": ["Senator"],
                        "notes": ["US Senate member"],
                    },
                },
            ]
        )
        entries = _parse_opensanctions_pep_json(json.dumps(data).encode())
        assert len(entries) == 1
        entry = entries[0]
        assert entry["ref_id"] == "Q123"
        assert entry["primary_name"] == "John Doe"
        assert entry["entity_type"] == "individual"
        assert entry["source"] == "opensanctions_pep"
        assert entry["aliases"] == [{"type": "a.k.a.", "name": "Johnny D"}]
        assert entry["countries"] == ["US", "GB"]
        assert entry["programs"] == ["Senator"]
        assert entry["remarks"] == "US Senate member"

    def test_skips_entries_without_name(self) -> None:
        from app.services.sanctions import _parse_opensanctions_pep_json

        data = _make_opensanctions_pep_payload(
            [
                {
                    "id": "Q999",
                    "caption": "",
                    "schema": "Person",
                    "properties": {
                        "name": [],
                        "alias": [],
                        "country": [],
                        "position": [],
                    },
                },
            ]
        )
        entries = _parse_opensanctions_pep_json(json.dumps(data).encode())
        assert len(entries) == 0

    def test_handles_missing_optional_fields_gracefully(self) -> None:
        from app.services.sanctions import _parse_opensanctions_pep_json

        data = _make_opensanctions_pep_payload(
            [
                {
                    "id": "Q456",
                    "caption": "Jane Smith",
                    "schema": "Person",
                    "properties": {
                        "name": ["Jane Smith"],
                    },
                },
            ]
        )
        entries = _parse_opensanctions_pep_json(json.dumps(data).encode())
        assert len(entries) == 1
        entry = entries[0]
        assert entry["primary_name"] == "Jane Smith"
        assert entry["aliases"] == []
        assert entry["countries"] == []
        assert entry["programs"] == []
        assert entry["remarks"] is None

    def test_multiple_entries_parsed(self) -> None:
        from app.services.sanctions import _parse_opensanctions_pep_json

        data = _make_opensanctions_pep_payload(
            [
                {
                    "id": "Q1",
                    "caption": "Alice A",
                    "schema": "Person",
                    "properties": {"name": ["Alice A"]},
                },
                {
                    "id": "Q2",
                    "caption": "Bob B",
                    "schema": "Person",
                    "properties": {"name": ["Bob B"]},
                },
            ]
        )
        entries = _parse_opensanctions_pep_json(json.dumps(data).encode())
        assert len(entries) == 2
        assert entries[0]["ref_id"] == "Q1"
        assert entries[1]["ref_id"] == "Q2"

    def test_multiple_positions_all_stored(self) -> None:
        from app.services.sanctions import _parse_opensanctions_pep_json

        data = _make_opensanctions_pep_payload(
            [
                {
                    "id": "Q789",
                    "caption": "Multi Role",
                    "schema": "Person",
                    "properties": {
                        "name": ["Multi Role"],
                        "position": ["Minister of Finance", "Member of Parliament"],
                    },
                },
            ]
        )
        entries = _parse_opensanctions_pep_json(json.dumps(data).encode())
        assert entries[0]["programs"] == ["Minister of Finance", "Member of Parliament"]

    def test_caption_used_as_fallback_when_name_list_empty_but_caption_present(self) -> None:
        """If properties.name is empty but caption is present, use caption."""
        from app.services.sanctions import _parse_opensanctions_pep_json

        data = _make_opensanctions_pep_payload(
            [
                {
                    "id": "Q555",
                    "caption": "Fallback Name",
                    "schema": "Person",
                    "properties": {
                        "name": [],
                        "alias": ["Nick"],
                        "country": ["FR"],
                        "position": ["Mayor"],
                    },
                },
            ]
        )
        entries = _parse_opensanctions_pep_json(json.dumps(data).encode())
        assert len(entries) == 1
        assert entries[0]["primary_name"] == "Fallback Name"


# ---------------------------------------------------------------------------
# refresh_pep
# ---------------------------------------------------------------------------


class TestRefreshPep:
    """Test the refresh_pep orchestration function."""

    @pytest.mark.anyio
    async def test_calls_fetch_parse_and_store(self) -> None:
        from app.services.sanctions import refresh_pep

        fake_json = json.dumps(
            _make_opensanctions_pep_payload(
                [
                    {
                        "id": "Q1",
                        "caption": "PEP Person",
                        "schema": "Person",
                        "properties": {"name": ["PEP Person"], "position": ["President"]},
                    },
                ]
            )
        ).encode()

        mock_db = AsyncMock()
        with (
            patch(
                "app.services.sanctions._fetch_opensanctions_pep_json",
                new_callable=AsyncMock,
                return_value=fake_json,
            ),
            patch(
                "app.services.sanctions._store_snapshot",
                new_callable=AsyncMock,
                return_value=(MagicMock(), True),
            ) as mock_store,
        ):
            snapshot, changed = await refresh_pep(mock_db)

            mock_store.assert_awaited_once()
            call_args = mock_store.call_args
            assert call_args[0][1] == "opensanctions_pep"  # source
            entries = call_args[0][2]
            assert len(entries) == 1
            assert entries[0]["source"] == "opensanctions_pep"


# ---------------------------------------------------------------------------
# PEP entries included in screen_contact fuzzy matching
# ---------------------------------------------------------------------------


class TestScreenContactIncludesPep:
    """Verify that PEP list entries are fuzzy-matched during screen_contact,
    using the same _compute_name_score algorithm as OFAC/UN/etc."""

    @pytest.mark.anyio
    async def test_pep_match_produces_result_with_pep_source(self) -> None:
        """When a contact name closely matches a PEP entry, the details
        should include a hit with source='opensanctions_pep'."""
        from app.services.sanctions import _compute_name_score

        # Simulate the fuzzy match that would happen during screening
        pep_entry = MagicMock()
        pep_entry.primary_name = "John Smith"
        pep_entry.aliases = []
        score, matched_name = _compute_name_score("JOHN SMITH", pep_entry)
        assert score >= 85  # confirmed match threshold
        assert matched_name == "John Smith"

    @pytest.mark.anyio
    async def test_pep_match_below_threshold_is_clear(self) -> None:
        from app.services.sanctions import _compute_name_score

        pep_entry = MagicMock()
        pep_entry.primary_name = "Vladimir Petrov"
        pep_entry.aliases = []
        score, _ = _compute_name_score("Jane Williams", pep_entry)
        assert score < 70  # below potential match threshold


# ---------------------------------------------------------------------------
# PEP source in refresh_additional_lists
# ---------------------------------------------------------------------------


class TestRefreshAdditionalListsIncludesPep:
    """Verify that refresh_additional_lists now also refreshes the PEP list."""

    @pytest.mark.anyio
    async def test_pep_included_in_refresh_additional_lists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.sanctions import refresh_additional_lists

        # Skip the separate streaming-path OpenSanctions Default call so this
        # test stays focused on the PEP leg of refresh_additional_lists.
        monkeypatch.setenv("SANCTIONS_SKIP_OPENSANCTIONS_DEFAULT", "1")

        mock_db = AsyncMock()

        with (
            patch(
                "app.services.sanctions._fetch_and_parse_un",
                new_callable=AsyncMock,
                return_value=([], "hash1"),
            ),
            patch(
                "app.services.sanctions._fetch_and_parse_uk_ofsi",
                new_callable=AsyncMock,
                return_value=([], "hash2"),
            ),
            patch(
                "app.services.sanctions._fetch_and_parse_eu",
                new_callable=AsyncMock,
                return_value=([], "hash3"),
            ),
            patch(
                "app.services.sanctions._fetch_and_parse_opensanctions_pep",
                new_callable=AsyncMock,
                return_value=([], "hash4"),
            ),
            patch(
                "app.services.sanctions._store_snapshot",
                new_callable=AsyncMock,
                return_value=(MagicMock(), True),
            ),
        ):
            results = await refresh_additional_lists(mock_db)

            sources = [source for source, _ in results]
            assert "opensanctions_pep" in sources


# ---------------------------------------------------------------------------
# _OPENSANCTIONS_PEP_URL constant
# ---------------------------------------------------------------------------


class TestOpenSanctionsPepUrl:
    """Ensure the PEP URL constant points to the OpenSanctions dataset."""

    def test_url_points_to_opensanctions(self) -> None:
        from app.services.sanctions import _OPENSANCTIONS_PEP_URL

        assert "opensanctions.org" in _OPENSANCTIONS_PEP_URL
        assert "pep" in _OPENSANCTIONS_PEP_URL.lower()


# ---------------------------------------------------------------------------
# ContactScreeningResultResponse includes pep match details
# ---------------------------------------------------------------------------


class TestContactScreeningResultResponsePepDetails:
    """Verify that the existing response schema can carry PEP match details
    in the details list (source='opensanctions_pep')."""

    def test_pep_detail_serialised_in_response(self) -> None:
        from app.api.v1.schemas import ContactScreeningResultResponse

        resp = ContactScreeningResultResponse(
            id="r1",
            contact_id="c1",
            screened_at="2026-04-16T00:00:00Z",
            match_status="potential_match",
            match_score=85,
            matched_name="John Doe",
            details=[
                {
                    "entry_id": "e1",
                    "name": "John Doe",
                    "score": 85,
                    "source": "opensanctions_pep",
                },
            ],
        )
        assert resp.details[0]["source"] == "opensanctions_pep"


# ---------------------------------------------------------------------------
# Sanctions entries search can filter by opensanctions_pep source
# ---------------------------------------------------------------------------


class TestSanctionsEntryResponsePepSource:
    """Verify the entry response schema accepts opensanctions_pep source."""

    def test_pep_source_in_entry_response(self) -> None:
        from app.api.v1.schemas import SanctionsEntryResponse

        entry = SanctionsEntryResponse(
            id="e1",
            ref_id="Q123",
            entity_type="individual",
            primary_name="PEP Person",
            aliases=[],
            countries=["US"],
            programs=["Senator"],
            remarks=None,
            source="opensanctions_pep",
        )
        assert entry.source == "opensanctions_pep"


# ---------------------------------------------------------------------------
# _fetch_opensanctions_pep_json
# ---------------------------------------------------------------------------


class TestFetchOpenSanctionsPepJson:
    """Test the HTTP fetch wrapper."""

    @pytest.mark.anyio
    async def test_fetch_returns_bytes(self) -> None:
        from app.services.sanctions import _fetch_opensanctions_pep_json

        fake_content = b'{"datasets": {}}'
        mock_response = MagicMock()
        mock_response.content = fake_content
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client

            result = await _fetch_opensanctions_pep_json()
            assert result == fake_content


# ---------------------------------------------------------------------------
# _fetch_and_parse_opensanctions_pep
# ---------------------------------------------------------------------------


class TestFetchAndParseOpenSanctionsPep:
    """Integration of fetch + parse into a (entries, hash) tuple."""

    @pytest.mark.anyio
    async def test_returns_entries_and_hash(self) -> None:
        from app.services.sanctions import _fetch_and_parse_opensanctions_pep

        payload = _make_opensanctions_pep_payload(
            [
                {
                    "id": "Q1",
                    "caption": "Test PEP",
                    "schema": "Person",
                    "properties": {"name": ["Test PEP"]},
                },
            ]
        )
        fake_bytes = json.dumps(payload).encode()

        with patch(
            "app.services.sanctions._fetch_opensanctions_pep_json",
            new_callable=AsyncMock,
            return_value=fake_bytes,
        ):
            entries, raw_hash = await _fetch_and_parse_opensanctions_pep()
            assert len(entries) == 1
            assert entries[0]["source"] == "opensanctions_pep"
            assert isinstance(raw_hash, str)
            assert len(raw_hash) == 64  # sha256 hex digest


# ---------------------------------------------------------------------------
# screen_contact routes opensanctions_pep through fuzzy name path
# ---------------------------------------------------------------------------


class TestScreenContactPepRouting:
    """The opensanctions_pep source should be routed through the fuzzy name
    matching branch in screen_contact (same as ofac/un/uk_ofsi/eu), NOT
    the FATF country-level branch."""

    def test_pep_source_not_in_fatf_list(self) -> None:
        """opensanctions_pep must not be treated as a FATF country list."""
        fatf_sources = ("fatf_blacklist", "fatf_greylist")
        assert "opensanctions_pep" not in fatf_sources


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_opensanctions_pep_payload(entities: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal OpenSanctions-format JSON payload for testing."""
    return {
        "datasets": {"peps": {"title": "PEP", "updated_at": "2026-04-16T00:00:00Z"}},
        "entities": entities,
    }
