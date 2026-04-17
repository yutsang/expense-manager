"""MPF (Mandatory Provident Fund) calculation — pure domain logic.

HK MPF Ordinance Cap 485 rules:
  - 5% employer contribution on relevant income
  - 5% employee contribution on relevant income
  - Maximum relevant income: HK$30,000/month -> cap at HK$1,500/month each
  - Minimum relevant income: HK$7,100/month -> employee exempt below this
  - Employer always contributes 5% (no minimum exemption for employer)
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

_QUANTIZE_4 = Decimal("0.0001")

# MPF parameters (current as of 2026)
MPF_RATE = Decimal("0.05")
MPF_MAX_RELEVANT_INCOME = Decimal("30000.0000")
MPF_MIN_RELEVANT_INCOME = Decimal("7100.0000")
MPF_MAX_CONTRIBUTION = Decimal("1500.0000")


def calculate_mpf(*, gross_salary: Decimal) -> dict[str, Decimal]:
    """Calculate MPF contributions for a monthly salary.

    Returns:
        Dict with keys: employer_mpf, employee_mpf, net_pay
    """
    if gross_salary <= Decimal("0"):
        return {
            "employer_mpf": Decimal("0.0000"),
            "employee_mpf": Decimal("0.0000"),
            "net_pay": Decimal("0.0000"),
        }

    # Employer always contributes 5%, capped at $1,500
    employer_mpf = min(
        (gross_salary * MPF_RATE).quantize(_QUANTIZE_4, ROUND_HALF_EVEN),
        MPF_MAX_CONTRIBUTION,
    )

    # Employee contributes 5%, capped at $1,500, but exempt below min relevant income
    if gross_salary < MPF_MIN_RELEVANT_INCOME:
        employee_mpf = Decimal("0.0000")
    else:
        employee_mpf = min(
            (gross_salary * MPF_RATE).quantize(_QUANTIZE_4, ROUND_HALF_EVEN),
            MPF_MAX_CONTRIBUTION,
        )

    net_pay = (gross_salary - employee_mpf).quantize(_QUANTIZE_4, ROUND_HALF_EVEN)

    return {
        "employer_mpf": employer_mpf,
        "employee_mpf": employee_mpf,
        "net_pay": net_pay,
    }
