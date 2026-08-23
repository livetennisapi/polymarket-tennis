"""Offline tests — fixture clients only, no network, no key."""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import watcher
from conftest import FIXTURES
from paper_book import BANNER, PaperBook

from polymarket_tennis import TennisMarket, build_view

NOW = datetime(2026, 8, 18, 2, 32, tzinfo=timezone.utc)


def _lehecka_market() -> TennisMarket:
    events = json.loads((FIXTURES / "gamma_events_tennis.json").read_text())
    event = next(e for e in events if e["slug"] == "atp-lehecka-fils-2026-08-17")
    return TennisMarket.from_gamma(event["markets"][0], event=event)


def _lehecka_match() -> dict:
    live = json.loads((FIXTURES / "lta_matches_live.json").read_text())
    return copy.deepcopy(next(m for m in live["data"] if m["id"] == 90211))


def test_once_with_fixtures_runs_and_matches(tmp_path, capsys):
    book = tmp_path / "book.json"
    rc = watcher.main(["--once", "--fixtures", str(FIXTURES), "--book", str(book)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "NO REAL ORDERS ARE EVER SENT" in out
    assert "Lehecka" in out and "break pt:   True" in out
    assert "serving:    Jiri Lehecka" in out
    assert "staleness:  market" in out
    # Eala/Anisimova matches a fixture (no score yet); the two Moeller matches
    # and the doubles market are handled by the package's matcher
    assert "confidently matched" in out


def test_underdog_break_point_opens_no_paper_entry(tmp_path):
    # fixture: Lehecka (0.095) serves at 15-40 — the UNDERDOG faces the BP
    view = build_view(_lehecka_market(), _lehecka_match(), NOW, NOW)
    book = PaperBook.load(tmp_path / "book.json")
    watcher.process_view(view, book, NOW)
    assert book.entries == []


def test_favourite_break_point_then_resolution(tmp_path, capsys):
    match = _lehecka_match()
    # Fils (0.905, the favourite) serves; points are [p1, p2] so 40-15 here
    # means the receiver Lehecka is at 40 -> break point against the favourite
    match["score"]["server"] = 2
    match["score"]["points"] = ["40", "15"]
    view = build_view(_lehecka_market(), match, NOW, NOW)
    book = PaperBook.load(tmp_path / "book.json")
    watcher.process_view(view, book, NOW)
    assert len(book.entries) == 1
    entry = book.entries[0]
    assert entry.side == "Arthur Fils" and entry.price == 0.905
    assert entry.resolved_time is None
    # same poll again: no duplicate
    watcher.process_view(view, book, NOW)
    assert len(book.entries) == 1

    # game resolves (broken), favourite price drifts down
    later = copy.deepcopy(match)
    later["score"]["games"][-1] = [5, 3]
    later["score"]["points"] = ["0", "0"]
    raw = dict(_lehecka_market().raw)
    raw["outcomePrices"] = '["0.15", "0.85"]'
    cheaper = TennisMarket.from_gamma(
        raw, event={"slug": "atp-lehecka-fils-2026-08-17"}
    )
    watcher.process_view(build_view(cheaper, later, NOW, NOW), book, NOW)
    entry = PaperBook.load(tmp_path / "book.json").entries[0]
    assert entry.resolved_price == 0.85
    assert entry.move == -0.055
    assert "PAPER resolved" in capsys.readouterr().out


def test_retired_prints_venue_description(tmp_path, capsys):
    match = _lehecka_match()
    match["outcome"] = "retired"
    view = build_view(_lehecka_market(), match, NOW, NOW)
    watcher.process_view(view, PaperBook.load(tmp_path / "b.json"), NOW)
    out = capsys.readouterr().out
    assert "match outcome = 'retired'" in out
    assert "[FIXTURE TEXT, not Polymarket's wording]" in out


def test_missing_description_is_reported_not_invented(tmp_path, capsys):
    raw = {k: v for k, v in _lehecka_market().raw.items() if k != "description"}
    market = TennisMarket.from_gamma(raw, event={"slug": "atp-lehecka-fils-2026-08-17"})
    match = _lehecka_match()
    match["event_status"] = "Walkover"  # no `outcome` key: falls back
    watcher.process_view(
        build_view(market, match, NOW, NOW), PaperBook.load(tmp_path / "b.json"), NOW
    )
    out = capsys.readouterr().out
    assert "match outcome = 'walkover'" in out
    assert "carries no `description`" in out


def test_paper_book_round_trips(tmp_path):
    path = tmp_path / "book.json"
    book = PaperBook.load(path)
    book.open_entry("m", "A", 0.8, "g1", NOW)
    assert PaperBook.load(path).entries[0].side == "A"
    assert book.resolve_entry("m", "g1", 0.7, NOW) is None  # same game: not yet
    resolved = book.resolve_entry("m", "g2", 0.7, NOW)
    assert resolved is not None and resolved.move == -0.1
    assert book.open_for("m") is None


def test_no_order_code_anywhere():
    for name in ("watcher.py", "paper_book.py"):
        text = (FIXTURES.parents[1] / name).read_text().lower()
        for banned in ("clob", "wallet", "private_key", "place_order", "web3"):
            assert banned not in text, f"{banned} in {name}"
    assert "NO REAL ORDERS" in BANNER
