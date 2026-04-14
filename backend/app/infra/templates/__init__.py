"""CoA templates indexed by ISO-3166-2 country code.

Add new country modules here; they must export COA_TEMPLATE and DEFAULT_TAX_CODES.
"""
from __future__ import annotations

from app.infra.templates import coa_au, coa_us


def get_coa_template(country: str) -> list[dict]:
    """Return the CoA template for the given country code. Falls back to US."""
    mapping = {
        "US": coa_us.COA_TEMPLATE,
        "AU": coa_au.COA_TEMPLATE,
    }
    return mapping.get(country.upper(), coa_us.COA_TEMPLATE)


def get_tax_codes_template(country: str) -> list[dict]:
    mapping = {
        "US": coa_us.DEFAULT_TAX_CODES,
        "AU": coa_au.DEFAULT_TAX_CODES,
    }
    return mapping.get(country.upper(), coa_us.DEFAULT_TAX_CODES)


SUPPORTED_COUNTRIES = {"US", "AU"}
