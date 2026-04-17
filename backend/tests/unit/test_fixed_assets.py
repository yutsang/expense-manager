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


class TestFixedAssetMigration:
    """Verify migration exists."""

    def test_migration_file_exists(self) -> None:
        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        files = list(migrations_dir.glob("*fixed_assets*"))
        assert len(files) >= 1, "No fixed_assets migration found"

    def test_migration_has_downgrade(self) -> None:
        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        files = list(migrations_dir.glob("*fixed_assets*"))
        source = files[0].read_text()
        assert "def downgrade()" in source
        assert "drop_table" in source
