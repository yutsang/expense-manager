"""Unit tests for MPF (Mandatory Provident Fund) tracking (Issue #46).

Tests cover:
  - SalaryRecord model exists with correct fields
  - MPF calculation: 5% employer/employee, capped at HK$1,500/month
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
_SERVICE_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "services" / "payroll.py"
_API_PATH = pathlib.Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "payroll.py"


class TestSalaryRecordModel:
    """SalaryRecord model source verification."""

    def test_salary_record_class_exists(self) -> None:
        source = _MODELS_PATH.read_text()
        assert "class SalaryRecord(Base):" in source

    def test_salary_records_table_name(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class SalaryRecord")
        block = source[idx : idx + 500]
        assert '"salary_records"' in block

    def test_has_required_fields(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class SalaryRecord")
        block = source[idx : idx + 2000]
        for field in [
            "employee_contact_id",
            "period_id",
            "gross_salary",
            "employer_mpf",
            "employee_mpf",
            "net_pay",
            "mpf_scheme_name",
            "payment_date",
            "journal_entry_id",
        ]:
            assert field in block, f"Missing field: {field}"

    def test_salary_uses_numeric_19_4(self) -> None:
        source = _MODELS_PATH.read_text()
        idx = source.index("class SalaryRecord")
        block = source[idx : idx + 2000]
        assert "Numeric(19, 4)" in block


class TestMpfCalculation:
    """Pure domain tests for MPF calculation logic."""

    def test_below_max_relevant_income(self) -> None:
        from app.domain.payroll.mpf import calculate_mpf

        result = calculate_mpf(gross_salary=Decimal("20000.0000"))
        assert result["employer_mpf"] == Decimal("1000.0000")
        assert result["employee_mpf"] == Decimal("1000.0000")

    def test_at_max_relevant_income_30000(self) -> None:
        from app.domain.payroll.mpf import calculate_mpf

        result = calculate_mpf(gross_salary=Decimal("30000.0000"))
        assert result["employer_mpf"] == Decimal("1500.0000")
        assert result["employee_mpf"] == Decimal("1500.0000")

    def test_above_max_relevant_income_capped(self) -> None:
        from app.domain.payroll.mpf import calculate_mpf

        result = calculate_mpf(gross_salary=Decimal("50000.0000"))
        # Capped at HK$1,500/month (5% of $30,000)
        assert result["employer_mpf"] == Decimal("1500.0000")
        assert result["employee_mpf"] == Decimal("1500.0000")

    def test_net_pay_calculation(self) -> None:
        from app.domain.payroll.mpf import calculate_mpf

        result = calculate_mpf(gross_salary=Decimal("20000.0000"))
        # Net pay = gross - employee_mpf
        assert result["net_pay"] == Decimal("19000.0000")

    def test_net_pay_with_high_salary(self) -> None:
        from app.domain.payroll.mpf import calculate_mpf

        result = calculate_mpf(gross_salary=Decimal("50000.0000"))
        # Net pay = 50000 - 1500 = 48500
        assert result["net_pay"] == Decimal("48500.0000")

    def test_minimum_relevant_income_exempt(self) -> None:
        from app.domain.payroll.mpf import calculate_mpf

        # Below minimum relevant income of $7,100: employee exempt, employer still pays
        result = calculate_mpf(gross_salary=Decimal("7000.0000"))
        assert result["employee_mpf"] == Decimal("0.0000")
        assert result["employer_mpf"] == Decimal("350.0000")

    def test_zero_salary(self) -> None:
        from app.domain.payroll.mpf import calculate_mpf

        result = calculate_mpf(gross_salary=Decimal("0.0000"))
        assert result["employer_mpf"] == Decimal("0.0000")
        assert result["employee_mpf"] == Decimal("0.0000")
        assert result["net_pay"] == Decimal("0.0000")

    def test_at_minimum_relevant_income(self) -> None:
        from app.domain.payroll.mpf import calculate_mpf

        # At exactly $7,100: employee pays, employer pays
        result = calculate_mpf(gross_salary=Decimal("7100.0000"))
        assert result["employer_mpf"] == Decimal("355.0000")
        assert result["employee_mpf"] == Decimal("355.0000")


class TestPayrollServiceSource:
    """Verify service source structure."""

    def test_service_file_exists(self) -> None:
        assert _SERVICE_PATH.exists(), "payroll.py service not found"

    def test_create_salary_record_function(self) -> None:
        source = _SERVICE_PATH.read_text()
        assert "async def create_salary_record(" in source

    def test_mpf_summary_function(self) -> None:
        source = _SERVICE_PATH.read_text()
        assert "async def mpf_summary(" in source


class TestPayrollApiSource:
    """Verify API endpoint source structure."""

    def test_api_file_exists(self) -> None:
        assert _API_PATH.exists(), "payroll.py API not found"

    def test_post_salary_records_endpoint(self) -> None:
        source = _API_PATH.read_text()
        assert "@router.post" in source

    def test_mpf_summary_endpoint(self) -> None:
        source = _API_PATH.read_text()
        assert "mpf-summary" in source


class TestSalaryRecordMigration:
    """Verify migration exists."""

    def test_migration_file_exists(self) -> None:
        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        files = list(migrations_dir.glob("*salary_records*"))
        assert len(files) >= 1, "No salary_records migration found"

    def test_migration_has_downgrade(self) -> None:
        migrations_dir = pathlib.Path(__file__).resolve().parents[2] / "migrations" / "versions"
        files = list(migrations_dir.glob("*salary_records*"))
        source = files[0].read_text()
        assert "def downgrade()" in source
        assert "drop_table" in source
