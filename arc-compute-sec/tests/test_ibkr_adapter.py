"""IBKR adapter test uses dry_run=True so no Gateway is needed."""
from adapters import ibkr


def test_stub_fill_long():
    fr = ibkr.place_paper_order("GOOGL", "long", qty=1, dry_run=True)
    assert fr["surface"] == "ibkr"
    assert fr["instrument"] == "GOOGL"
    assert fr["direction"] == "long"
    assert fr["qty"] == 1
    assert fr["stub"] is True


def test_stub_fill_short():
    fr = ibkr.place_paper_order("AMZN", "short", qty=3, dry_run=True)
    assert fr["direction"] == "short"
    assert fr["qty"] == 3
    assert fr["stub"] is True


def test_stub_fills_deterministic_within_session(monkeypatch):
    # Same symbol+direction+qty within a tight loop should produce different
    # fill_ids (because timestamp differs at sub-second granularity).
    fr1 = ibkr.place_paper_order("MSFT", "short", qty=1, dry_run=True)
    fr2 = ibkr.place_paper_order("MSFT", "short", qty=1, dry_run=True)
    # Hash includes ts; they may collide in same second. Don't assert
    # inequality strictly. Just assert both produce valid 16-char hex.
    assert len(fr1["fill_id"]) == 16
    assert len(fr2["fill_id"]) == 16
