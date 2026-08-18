"""Discovery filtering over real (trimmed) Gamma payloads."""

from __future__ import annotations

from polymarket_tennis.discovery import (
    discover_tennis_markets,
    find_market,
    is_doubles_event,
    is_match_event,
    is_tennis_event,
    iter_markets,
)
from polymarket_tennis.models import TennisMarket


def _event(events, slug):
    return next(e for e in events if e["slug"] == slug)


class TestEventClassification:
    def test_tag_marks_tennis(self, gamma_events):
        assert all(is_tennis_event(e) for e in gamma_events)

    def test_non_tennis_event_rejected(self):
        event = {
            "slug": "xi-jinping-out-before-2027",
            "title": "Xi Jinping out before 2027?",
            "tags": [{"slug": "politics", "label": "Politics"}],
        }
        assert not is_tennis_event(event)

    def test_slug_prefix_alone_suffices(self):
        event = {"slug": "atp-lehecka-fils-2026-08-17", "title": "", "tags": []}
        assert is_tennis_event(event)

    def test_match_event_detection(self, gamma_events):
        assert is_match_event(_event(gamma_events, "atp-lehecka-fils-2026-08-17"))
        assert not is_match_event(
            _event(gamma_events, "2026-mens-us-open-winner-tennis")
        )

    def test_doubles_event_detection(self, gamma_events):
        assert is_doubles_event(
            _event(gamma_events, "atp-doubles-cashgla-ramsali-2026-08-16")
        )
        assert not is_doubles_event(
            _event(gamma_events, "atp-lehecka-fils-2026-08-17")
        )


class TestIterMarkets:
    def test_open_markets_only_by_default(self, gamma_events):
        markets = iter_markets(gamma_events)
        assert markets
        assert all(not m.closed for m in markets)

    def test_include_closed_widens(self, gamma_events):
        default = iter_markets(gamma_events)
        widened = iter_markets(gamma_events, include_closed=True)
        assert len(widened) > len(default)

    def test_market_type_filter(self, gamma_events):
        moneylines = iter_markets(gamma_events, market_types={"moneyline"})
        assert moneylines
        assert all(m.market_type == "moneyline" for m in moneylines)

    def test_non_tennis_event_dropped(self, gamma_events):
        polluted = gamma_events + [
            {
                "slug": "some-politics-event",
                "title": "Something else",
                "tags": [{"slug": "politics"}],
                "markets": [{"id": "1", "question": "?", "slug": "x"}],
            }
        ]
        markets = iter_markets(polluted, include_closed=True)
        assert all(m.event_slug != "some-politics-event" for m in markets)


class TestNormalization:
    def test_moneyline_normalization(self, gamma_events):
        event = _event(gamma_events, "atp-lehecka-fils-2026-08-17")
        raw = event["markets"][0]
        market = TennisMarket.from_gamma(raw, event=event)
        assert market.outcomes == ("Jiri Lehecka", "Arthur Fils")
        assert market.prices == (0.095, 0.905)
        assert market.market_type == "moneyline"
        assert market.event_slug == "atp-lehecka-fils-2026-08-17"
        assert market.volume and market.volume > 0
        assert market.end_date is not None and market.end_date.tzinfo is not None
        assert market.game_start_time is not None  # "YYYY-MM-DD HH:MM:SS+00" form
        assert str(market.slug_date) == "2026-08-17"

    def test_price_by_outcome_round_trip(self, gamma_events):
        event = _event(gamma_events, "atp-lehecka-fils-2026-08-17")
        market = TennisMarket.from_gamma(event["markets"][0], event=event)
        assert market.price_by_outcome == {
            "Jiri Lehecka": 0.095,
            "Arthur Fils": 0.905,
        }

    def test_malformed_outcomes_do_not_raise(self):
        market = TennisMarket.from_gamma(
            {"id": 1, "slug": "x", "question": "?", "outcomes": "not json"}
        )
        assert market.outcomes == ()
        assert market.prices == ()


class TestClientPaths:
    def test_discover_tennis_markets(self, gamma_client):
        markets = discover_tennis_markets(gamma_client)
        assert markets
        assert all(not m.closed for m in markets)

    def test_matches_only_drops_futures(self, gamma_client):
        markets = discover_tennis_markets(gamma_client, matches_only=True)
        assert markets
        assert all(m.event_slug != "2026-mens-us-open-winner-tennis" for m in markets)

    def test_find_market_by_id(self, gamma_client):
        market = find_market(gamma_client, "3625104")
        assert market is not None
        assert market.slug == "atp-lehecka-fils-2026-08-17"

    def test_find_market_by_market_slug(self, gamma_client):
        slug = "atp-lehecka-fils-2026-08-17-set-2-winner-Lehecka-vs-Fils"
        market = find_market(gamma_client, slug)
        assert market is not None
        assert market.market_type == "tennis_set_winner"

    def test_find_market_by_event_slug_falls_back(self, gamma_client):
        # a futures event whose market slugs differ from the event slug,
        # so resolution must fall back to the event lookup
        market = find_market(gamma_client, "2026-mens-us-open-winner-tennis")
        assert market is not None
        assert market.event_slug == "2026-mens-us-open-winner-tennis"

    def test_find_market_missing_returns_none(self, gamma_client):
        assert find_market(gamma_client, "999999999") is None
        assert find_market(gamma_client, "no-such-slug-2026-01-01") is None
