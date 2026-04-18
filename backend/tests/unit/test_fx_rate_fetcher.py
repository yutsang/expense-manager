"""Unit tests for the ECB FX rate fetcher — XML parsing and cross-rate derivation."""

from __future__ import annotations

from decimal import Decimal

from app.workers.fx_rate_fetcher import derive_cross_rates, parse_ecb_xml


class TestParseEcbXml:
    def test_parses_valid_xml(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <gesmes:subject>Reference rates</gesmes:subject>
  <Cube>
    <Cube time="2026-04-18">
      <Cube currency="USD" rate="1.0800"/>
      <Cube currency="GBP" rate="0.8560"/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""
        rate_date, rates = parse_ecb_xml(xml)
        assert rate_date == "2026-04-18"
        assert rates["USD"] == Decimal("1.0800")
        assert rates["GBP"] == Decimal("0.8560")

    def test_extracts_multiple_currencies(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time="2026-01-01">
      <Cube currency="USD" rate="1.10"/>
      <Cube currency="GBP" rate="0.85"/>
      <Cube currency="JPY" rate="160.00"/>
      <Cube currency="AUD" rate="1.65"/>
    </Cube>
  </Cube>
</gesmes:Envelope>"""
        rate_date, rates = parse_ecb_xml(xml)
        assert rate_date == "2026-01-01"
        assert len(rates) == 4
        assert rates["JPY"] == Decimal("160.00")

    def test_raises_on_missing_cube(self) -> None:
        xml = """<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube></Cube>
</gesmes:Envelope>"""
        try:
            parse_ecb_xml(xml)
            assert False, "Should have raised"
        except ValueError as exc:
            assert "Could not find" in str(exc)


class TestDeriveCrossRates:
    def test_usd_gbp_cross_rate(self) -> None:
        eur_rates = {
            "USD": Decimal("1.08"),
            "GBP": Decimal("0.856"),
        }
        results = derive_cross_rates(eur_rates)
        result_map = {(f, t): r for f, t, r in results}

        # USD/GBP = EUR/GBP / EUR/USD = 0.856 / 1.08
        assert ("USD", "GBP") in result_map
        expected = Decimal("0.856") / Decimal("1.08")
        assert abs(result_map[("USD", "GBP")] - expected) < Decimal("0.0001")

    def test_usd_eur_cross_rate(self) -> None:
        eur_rates = {
            "USD": Decimal("1.08"),
            "GBP": Decimal("0.856"),
        }
        results = derive_cross_rates(eur_rates)
        result_map = {(f, t): r for f, t, r in results}

        # USD/EUR = EUR/EUR / EUR/USD = 1 / 1.08
        assert ("USD", "EUR") in result_map
        expected = Decimal("1") / Decimal("1.08")
        assert abs(result_map[("USD", "EUR")] - expected) < Decimal("0.0001")

    def test_eur_usd_cross_rate(self) -> None:
        eur_rates = {
            "USD": Decimal("1.08"),
        }
        results = derive_cross_rates(eur_rates)
        result_map = {(f, t): r for f, t, r in results}

        # EUR/USD = EUR/USD / EUR/EUR = 1.08 / 1 = 1.08
        assert ("EUR", "USD") in result_map
        assert result_map[("EUR", "USD")] == Decimal("1.08")

    def test_missing_currency_skipped(self) -> None:
        # Only USD available — pairs requiring GBP should be skipped
        eur_rates = {"USD": Decimal("1.08")}
        results = derive_cross_rates(eur_rates)
        result_map = {(f, t): r for f, t, r in results}
        assert ("USD", "GBP") not in result_map
        assert ("GBP", "USD") not in result_map

    def test_empty_rates(self) -> None:
        results = derive_cross_rates({})
        # Only pairs involving EUR should appear, if EUR is in CROSS_RATE_PAIRS
        for f, t, _ in results:
            assert f == "EUR" or t == "EUR"
