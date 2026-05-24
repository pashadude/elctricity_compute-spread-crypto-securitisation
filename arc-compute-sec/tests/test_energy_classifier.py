from templates.energy.classifier import classify_energy


def test_oil_match():
    assert classify_energy("Will WTI > $90 by Q3?", "") == "energy_oil_price"


def test_gas_match():
    assert classify_energy("Henry Hub natural gas price spike", "") == "energy_gas_price"


def test_electricity_match():
    assert classify_energy("ERCOT real-time price > $200/MWh?", "") == "energy_electricity"


def test_policy_match():
    # Keep this title clean of electricity-class keywords (no "interconnect", etc.)
    assert classify_energy("Will FERC approve the new merger?", "") == "energy_policy"


def test_ai_infra_match():
    assert classify_energy("Will any hyperscaler announce a 1GW data center?", "") == "energy_ai_infra"


def test_non_energy_returns_none():
    assert classify_energy("Taylor Swift Q4 album release?", "") is None


def test_short_acronyms_need_token_boundary():
    assert classify_energy("Which party controls the Senate in 2026?", "Does the party win?") is None


def test_keyword_in_description():
    assert classify_energy("Q3 outcome", "Brent crude collapse below $50") == "energy_oil_price"


def test_upstream_category_ignored_per_drift():
    # Per delta D3, classifier ignores upstream_category. Even a non-energy
    # category passes if the title matches.
    assert classify_energy("WTI > $90", "", upstream_category="social_media") == "energy_oil_price"
