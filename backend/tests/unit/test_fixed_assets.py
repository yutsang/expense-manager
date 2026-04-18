"""Unit tests for fixed assets register (Issue #41).

Tests cover:
  - FixedAsset model exists with correct fields
  - Depreciation calculation: straight-line and declining-balance
  - API endpoints exist (source inspection)
  - Migration exists with upgrade+downgrade
"""

from __future__ import annotations

import pathlib
import sys
from decimal import Decimal

import pytest

_NEEDS_311 = sys.version_info < (3, 11)
_skip_311 = pytest.mark.skipif(_NEEDS_311, reason="datetime.UTC requires Python >=3.11")

_MODELS_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "infra" / "models.py"
_SERVICE_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "fixed_assets.py"
_API_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "fixed_assets.py"


class TestFixedAssetModel:
    """FixedAsset model source verification."""

    def test_fixed_asset_class_exists(self) -> None:
        source = _MODELS_PATH.read_text()
        assert "class FixedAsset(Base):" in source

    def test_fixed_assets_table_name(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class FixedAsset")
        block = source[idx : idx + 500]
        assert '"fixed_assets"' in block

    def test_has_required_fields(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class FixedAsset")
        block = source[idx : idx + 2000]
        for field in [
            "name",
            "category",
            "acquisition_date",
            "cost",
            "residual_value",
            "useful_life_months",
            "depreciation_method",
            "asset_account_id",
            "depreciation_account_id",
            "accumulated_depreciation_account_id",
            "status",
        ]:
            assert field in block, f"Missing field: {field}"

    def test_cost_uses_numeric_19_4(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class FixedAsset")
        block = source[idx : idx + 2000]
        assert "Numeric(19, 4)" in block

    def test_status_constraint(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class FixedAsset")
        block = source[idx : idx + 3000]
        assert "active" in block
        assert "disposed" in block
        assert "fully_depreciated" in block

    def test_category_constraint(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class FixedAsset")
        block = source[idx : idx + 3000]
        assert "equipment" in block
        assert "vehicle" in block
        assert "furniture" in block


class TestDepreciationCalculation:
    """Pure domain tests for depreciation calculation logic."""

    def test_straight_line_monthly(self) -> None:
        from app.domain.assets.depreciation import calculate_depreciation

        result = calculate_depreciation(
            cost=Decimal("12000.0000"),
            residual_value=Decimal("0.0000"),
            useful_life_months=12,
            method="straight_line",
            months_elapsed=1,
        )
        assert result == Decimal("1000.0000")

    def test_straight_line_with_residual(self) -> None:
        from app.domain.assets.depreciation import calculate_depreciation

        result = calculate_depreciation(
            cost=Decimal("12000.0000"),
            residual_value=Decimal("2000.0000"),
            useful_life_months=10,
            method="straight_line",
            months_elapsed=1,
        )
        assert result == Decimal("1000.0000")

    def test_straight_line_full_life(self) -> None:
        from app.domain.assets.depreciation import calculate_depreciation

        result = calculate_depreciation(
            cost=Decimal("12000.0000"),
            residual_value=Decimal("2000.0000"),
            useful_life_months=10,
            method="straight_line",
            months_elapsed=10,
        )
        # Last month should give the remaining depreciable amount
        assert result == Decimal("1000.0000")

    def test_straight_line_past_useful_life_returns_zero(self) -> None:
        from app.domain.assets.depreciation import calculate_depreciation

        result = calculate_depreciation(
            cost=Decimal("12000.0000"),
            residual_value=Decimal("2000.0000"),
            useful_life_months=10,
            method="straight_line",
            months_elapsed=11,
        )
        assert result == Decimal("0.0000")

    def test_declining_balance_first_month(self) -> None:
        from app.domain.assets.depreciation import calculate_depreciation

        result = calculate_depreciation(
            cost=Decimal("10000.0000"),
            residual_value=Decimal("1000.0000"),
            useful_life_months=60,
            method="declining_balance",
            months_elapsed=1,
        )
        # Declining balance: rate = 2 / useful_life_months
        # First month: 10000 * (2/60) = 333.3333
        assert result > Decimal("0")
        assert result == Decimal("333.3333")

    def test_declining_balance_respects_residual(self) -> None:
        from app.domain.assets.depreciation import calculate_depreciation

        # If book value would go below residual, clamp to zero
        result = calculate_depreciation(
            cost=Decimal("1000.0000"),
            residual_value=Decimal("990.0000"),
            useful_life_months=12,
            method="declining_balance",
            months_elapsed=1,
        )
        # Book value is 1000, depreciation would be 1000 * (2/12) = 166.6667
        # But that would take us below residual of 990, so clamp to 10.0000
        assert result == Decimal("10.0000")

    def test_zero_useful_life_raises(self) -> None:
        from app.domain.assets.depreciation import calculate_depreciation

        with pytest.raises(ValueError):
            calculate_depreciation(
                cost=Decimal("1000.0000"),
                residual_value=Decimal("0.0000"),
                useful_life_months=0,
                method="straight_line",
                months_elapsed=1,
            )


class TestPartialMonthDepreciation:
    """Tests for partial first-month pro-rating (Bug #63)."""

    def test_full_month_when_acquired_on_first(self) -> None:
        """Asset acquired on the 1st gets a full month of depreciation."""
        from datetime import date
        from app.domain.assets.depreciation import calculate_depreciation

        result = calculate_depreciation(
            cost=Decimal("12000.0000"),
            residual_value=Decimal("0.0000"),
            useful_life_months=12,
            method="straight_line",
            months_elapsed=1,
            acquisition_date=date(2025, 1, 1),
        )
        assert result == Decimal("1000.0000")

    def test_half_month_when_acquired_mid_month(self) -> None:
        """Asset acquired on the 16th of a 30-day month gets ~50% depreciation."""
        from datetime import date
        from app.domain.assets.depreciation import calculate_depreciation

        # June has 30 days. Acquired on 16th = 15 days remaining (16..30).
        result = calculate_depreciation(
            cost=Decimal("12000.0000"),
            residual_value=Decimal("0.0000"),
            useful_life_months=12,
            method="straight_line",
            months_elapsed=1,
            acquisition_date=date(2025, 6, 16),
        )
        # monthly = 1000.0000, factor = 15/30 = 0.5, result = 500.0000
        assert result == Decimal("500.0000")

    def test_last_day_acquisition_gives_one_day(self) -> None:
        """Asset acquired on the last day gets 1/days_in_month depreciation."""
        from datetime import date
        from app.domain.assets.depreciation import calculate_depreciation

        # January has 31 days, acquired on 31st = 1 day remaining.
        result = calculate_depreciation(
            cost=Decimal("31000.0000"),
            residual_value=Decimal("0.0000"),
            useful_life_months=31,
            method="straight_line",
            months_elapsed=1,
            acquisition_date=date(2025, 1, 31),
        )
        # monthly = 1000.0000, factor = 1/31 = 0.0323 (ROUND_HALF_EVEN)
        # 1000 * 0.0323 = 32.3000 (quantized to 4dp)
        expected = Decimal("32.3000")
        assert result == expected

    def test_second_month_is_full_regardless_of_acquisition_date(self) -> None:
        """Only the first month is pro-rated."""
        from datetime import date
        from app.domain.assets.depreciation import calculate_depreciation

        result = calculate_depreciation(
            cost=Decimal("12000.0000"),
            residual_value=Decimal("0.0000"),
            useful_life_months=12,
            method="straight_line",
            months_elapsed=2,
            acquisition_date=date(2025, 6, 16),
        )
        assert result == Decimal("1000.0000")

    def test_no_prorate_without_acquisition_date(self) -> None:
        """Without acquisition_date, first month is full (backward compat)."""
        from app.domain.assets.depreciation import calculate_depreciation

        result = calculate_depreciation(
            cost=Decimal("12000.0000"),
            residual_value=Decimal("0.0000"),
            useful_life_months=12,
            method="straight_line",
            months_elapsed=1,
        )
        assert result == Decimal("1000.0000")

    def test_declining_balance_first_month_prorate(self) -> None:
        """Declining balance method also pro-rates the first month."""
        from datetime import date
        from app.domain.assets.depreciation import calculate_depreciation

        # Full first month: 10000 * (2/60) = 333.3333
        full = calculate_depreciation(
            cost=Decimal("10000.0000"),
            residual_value=Decimal("1000.0000"),
            useful_life_months=60,
            method="declining_balance",
            months_elapsed=1,
        )
        assert full == Decimal("333.3333")

        # Acquired on 16th of June (30 days), factor = 15/30 = 0.5
        prorated = calculate_depreciation(
            cost=Decimal("10000.0000"),
            residual_value=Decimal("1000.0000"),
            useful_life_months=60,
            method="declining_balance",
            months_elapsed=1,
            acquisition_date=date(2025, 6, 16),
        )
        # 333.3333 * 0.5 = 166.6666 (ROUND_HALF_EVEN: 5 rounds to even)
        assert prorated == Decimal("166.6666")

    def test_depreciation_never_exceeds_depreciable(self) -> None:
        """Total accumulated depreciation must not exceed cost - residual."""
        from datetime import date
        from app.domain.assets.depreciation import calculate_depreciation

        result = calculate_depreciation(
            cost=Decimal("100.0000"),
            residual_value=Decimal("99.0000"),
            useful_life_months=1,
            method="straight_line",
            months_elapsed=1,
            acquisition_date=date(2025, 1, 1),
        )
        # Depreciable = 1.0000, monthly = 1.0000, result should be clamped
        assert result <= Decimal("1.0000")


class TestFixedAssetServiceSource:
    """Verify service source structure."""

    def test_service_file_exists(self) -> None:
        assert _SERVICE_PATH.exists(), "fixed_assets.py service not found"

    def test_calculate_depreciation_imported(self) -> None:
        source = _SERVICE_PATH.read_text()
        assert "calculate_depreciation" in source

    def test_create_asset_function(self) -> None:
        source = _SERVICE_PATH.read_text()
        assert "async def create_asset(" in source

    def test_list_assets_function(self) -> None:
        source = _SERVICE_PATH.read_text()
        assert "async def list_assets(" in source

    def test_depreciate_asset_function(self) -> None:
        source = _SERVICE_PATH.read_text()
        assert "async def depreciate_asset(" in source


class TestFixedAssetApiSource:
    """Verify API endpoint source structure."""

    def test_api_file_exists(self) -> None:
        assert _API_PATH.exists(), "fixed_assets.py API not found"

    def test_post_assets_endpoint(self) -> None:
        source = _API_PATH.read_text()
        assert "POST" in source or "@router.post" in source

    def test_get_assets_endpoint(self) -> None:
        source = _API_PATH.read_text()
        assert "@router.get" in source

    def test_depreciate_endpoint(self) -> None:
        source = _API_PATH.read_text()
        assert "depreciate" in source


class TestFixedAssetAcquisitionDateColumn:
    """Verify acquisition_date uses proper Date type (Bug #64)."""

    def test_acquisition_date_is_date_type_in_source(self) -> None:
        """Verify the model source uses Date type (avoids Python 3.10 import issue)."""
        source = _MODELS_PATH.read_text()
        idx = source.index("class FixedAsset")
        block = source[idx : idx + 2000]
        # Should use Date, not String(10)
        assert "mapped_column(Date" in block or "mapped_column(sa.Date" in block, (
            "FixedAsset.acquisition_date should use Date type, not String(10)"
        )
        assert "Mapped[date]" in block or "Mapped[str]" not in block.split("acquisition_date")[1][:50], (
            "acquisition_date should be Mapped[date], not Mapped[str]"
        )

    def test_date_migration_file_exists(self) -> None:
        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        files = list(migrations_dir.glob("0033_*"))
        assert len(files) >= 1, "No 0033_* migration for fixed_assets date column found"

    def test_date_migration_has_downgrade(self) -> None:
        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        files = list(migrations_dir.glob("0033_*"))
        assert files, "No 0033_* migration found"
        source = files[0].read_text()
        assert "def downgrade()" in source
        assert "def upgrade()" in source


class TestFixedAssetMigration:
    """Verify migration exists."""

    def test_migration_file_exists(self) -> None:
        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        files = list(migrations_dir.glob("0030_*fixed_assets*"))
        assert len(files) >= 1, "No fixed_assets migration found"

    def test_migration_has_downgrade(self) -> None:
        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        files = list(migrations_dir.glob("0030_*fixed_assets*"))
        source = files[0].read_text()
        assert "def downgrade()" in source
        assert "drop_table" in source
