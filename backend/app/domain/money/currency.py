"""ISO 4217 currency codes. Extend as needed — keep alphabetically sorted."""
from __future__ import annotations

from enum import StrEnum


class Currency(StrEnum):
    AUD = "AUD"
    CAD = "CAD"
    CNY = "CNY"
    EUR = "EUR"
    GBP = "GBP"
    HKD = "HKD"
    JPY = "JPY"
    MYR = "MYR"
    NZD = "NZD"
    SGD = "SGD"
    TWD = "TWD"
    USD = "USD"

    @classmethod
    def from_str(cls, value: str) -> "Currency":
        try:
            return cls(value.upper())
        except ValueError:
            raise ValueError(f"Unknown currency code: {value!r}") from None

    @property
    def decimal_places(self) -> int:
        """Number of decimal places in minor units (0 for JPY, 2 for most, etc.)."""
        no_decimals = {"JPY", "KRW", "VND"}
        return 0 if self.value in no_decimals else 2
