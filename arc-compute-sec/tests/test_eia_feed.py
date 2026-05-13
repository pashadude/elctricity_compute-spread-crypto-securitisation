import json

import pytest
import responses

from feeds import eia


@pytest.fixture
def fake_eia_key(monkeypatch):
    monkeypatch.setenv("EIA_API_KEY", "fake-key-12345")


@responses.activate
def test_fetch_latest_ok(fake_eia_key):
    payload = {
        "response": {
            "data": [
                {
                    "period": "2026-05-13T10",
                    "value": 78.5,
                    "value-units": "USD per megawatthour",
                    "respondent": "ERCO",
                }
            ]
        }
    }
    responses.add(
        responses.GET,
        "https://api.eia.gov/v2/electricity/rto/region-data/data/",
        json=payload,
        status=200,
    )
    pt = eia.fetch_latest("ERCO")
    assert pt is not None
    assert pt.region == "ERCO"
    assert pt.value_mwh == 78.5
    assert pt.period == "2026-05-13T10"


@responses.activate
def test_fetch_latest_empty(fake_eia_key):
    responses.add(
        responses.GET,
        "https://api.eia.gov/v2/electricity/rto/region-data/data/",
        json={"response": {"data": []}},
        status=200,
    )
    assert eia.fetch_latest("ERCO") is None


def test_missing_api_key(monkeypatch):
    monkeypatch.delenv("EIA_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        eia.fetch_latest("ERCO")
