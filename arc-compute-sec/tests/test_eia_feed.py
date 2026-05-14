import pytest
import responses

from feeds import eia


@pytest.fixture
def fake_eia_key(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "fake-key-12345")


@responses.activate
def test_fetch_latest_ok_converts_cents_to_dollars_per_mwh(fake_eia_key):
    # EIA retail-sales returns INDUSTRIAL price in cents/kWh.
    # 7.2 cents/kWh * 10 = $72/MWh
    payload = {
        "response": {
            "data": [
                {
                    "period": "2026-02",
                    "stateid": "TX",
                    "sectorid": "IND",
                    "price": 7.2,
                    "price-units": "cents per kilowatt-hour",
                }
            ]
        }
    }
    responses.add(
        responses.GET,
        "https://api.eia.gov/v2/electricity/retail-sales/data/",
        json=payload,
        status=200,
    )
    pt = eia.fetch_latest("ERCO")
    assert pt is not None
    assert pt.region == "ERCO"
    assert pt.state == "TX"
    assert pt.raw_value == 7.2
    assert pt.value_mwh == 72.0
    assert pt.period == "2026-02"


@responses.activate
def test_fetch_latest_empty(fake_eia_key):
    responses.add(
        responses.GET,
        "https://api.eia.gov/v2/electricity/retail-sales/data/",
        json={"response": {"data": []}},
        status=200,
    )
    assert eia.fetch_latest("ERCO") is None


@responses.activate
def test_fetch_latest_caiso_maps_to_california(fake_eia_key):
    payload = {
        "response": {
            "data": [
                {"period": "2026-02", "stateid": "CA", "sectorid": "IND",
                 "price": 14.5, "price-units": "cents per kilowatt-hour"}
            ]
        }
    }
    responses.add(
        responses.GET,
        "https://api.eia.gov/v2/electricity/retail-sales/data/",
        json=payload, status=200,
    )
    pt = eia.fetch_latest("CISO")
    assert pt is not None
    assert pt.state == "CA"
    assert pt.value_mwh == 145.0


def test_fetch_unknown_region_returns_none(fake_eia_key):
    # Don't even hit HTTP for an unmapped region.
    assert eia.fetch_latest("MADE-UP-ISO") is None


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        eia.fetch_latest("ERCO")
