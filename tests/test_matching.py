"""Matching edge cases: reversed order, diacritics, ambiguity, doubles."""

from __future__ import annotations

import copy

import pytest

from polymarket_tennis.matching import (
    extract_market_players,
    fold_name,
    match_market,
    score_candidates,
)
from polymarket_tennis.models import TennisMarket


def market_from(gamma_events, event_slug, index=0) -> TennisMarket:
    event = next(e for e in gamma_events if e["slug"] == event_slug)
    return TennisMarket.from_gamma(event["markets"][index], event=event)


@pytest.fixture
def lehecka_market(gamma_events):
    return market_from(gamma_events, "atp-lehecka-fils-2026-08-17")


@pytest.fixture
def live_candidates(lta_live, lta_fixtures_payload):
    return lta_live["data"] + lta_fixtures_payload["data"]


class TestFolding:
    def test_diacritics_folded(self):
        assert fold_name("Sebastián Báez") == "sebastian baez"
        assert fold_name("Francisco Cerúndolo") == "francisco cerundolo"

    def test_punctuation_collapsed(self):
        assert fold_name("Auger-Aliassime") == "auger aliassime"
        assert fold_name("J. Lehecka") == "j lehecka"


class TestExtraction:
    def test_moneyline_outcomes_preferred(self, lehecka_market):
        players = extract_market_players(lehecka_market)
        assert players is not None
        assert players.p1 == "Jiri Lehecka"
        assert players.p2 == "Arthur Fils"
        assert str(players.match_date) == "2026-08-17"
        assert not players.is_doubles

    def test_title_fallback_for_non_moneyline(self, gamma_events):
        # a set-winner market: outcomes are surnames, but the event title
        # still names both players in full
        market = market_from(gamma_events, "atp-lehecka-fils-2026-08-17", index=2)
        assert market.market_type == "tennis_set_winner"
        players = extract_market_players(market)
        assert players is not None
        assert players.p1 == "Jiri Lehecka"
        assert players.p2 == "Arthur Fils"

    def test_yes_no_futures_market_unparsable(self, gamma_events):
        market = market_from(gamma_events, "2026-mens-us-open-winner-tennis")
        # Yes/No outcomes + no "A vs B" title => no two sides identified
        assert extract_market_players(market) is None

    def test_doubles_market_flagged(self, gamma_events):
        market = market_from(gamma_events, "atp-doubles-cashgla-ramsali-2026-08-16")
        players = extract_market_players(market)
        assert players is not None
        assert players.is_doubles

    def test_retirement_wording_stripped(self, lehecka_market):
        raw = dict(lehecka_market.raw)
        raw["outcomes"] = '["Jiri Lehecka (Retired)", "Arthur Fils"]'
        market = TennisMarket.from_gamma(raw, event={"slug": lehecka_market.event_slug})
        players = extract_market_players(market)
        assert players is not None
        assert players.p1 == "Jiri Lehecka"

    def test_walkover_wording_stripped(self, lehecka_market):
        raw = dict(lehecka_market.raw)
        raw["outcomes"] = '["Jiri Lehecka w/o", "Arthur Fils"]'
        market = TennisMarket.from_gamma(raw, event={"slug": lehecka_market.event_slug})
        players = extract_market_players(market)
        assert players is not None
        assert players.p1 == "Jiri Lehecka"


class TestMatching:
    def test_direct_match_high_confidence(self, lehecka_market, live_candidates):
        decision = match_market(lehecka_market, live_candidates)
        assert decision is not None
        assert decision.match_id == 90211
        assert decision.confidence >= 0.9
        assert decision.method == "names+date"

    def test_reversed_name_order_still_matches(
        self, lehecka_market, live_candidates
    ):
        raw = dict(lehecka_market.raw)
        raw["outcomes"] = '["Arthur Fils", "Jiri Lehecka"]'
        market = TennisMarket.from_gamma(
            raw, event={"slug": lehecka_market.event_slug}
        )
        decision = match_market(market, live_candidates)
        assert decision is not None
        assert decision.match_id == 90211
        assert any("reversed" in note for note in decision.notes)

    def test_diacritics_market_vs_folded_feed(self, gamma_events, live_candidates):
        # market spells names without diacritics; the feed carries them
        event = {"slug": "atp-baez-cerundol-2026-08-17", "title": ""}
        raw = {
            "id": "555",
            "slug": "atp-baez-cerundol-2026-08-17",
            "question": "Cincinnati Open: Sebastian Baez vs Francisco Cerundolo",
            "outcomes": '["Sebastian Baez", "Francisco Cerundolo"]',
            "outcomePrices": '["0.4", "0.6"]',
            "sportsMarketType": "moneyline",
            "active": True,
            "closed": False,
        }
        market = TennisMarket.from_gamma(raw, event=event)
        decision = match_market(market, live_candidates)
        assert decision is not None
        assert decision.match_id == 90214

    def test_shared_surname_disambiguated_by_full_name(
        self, gamma_events, live_candidates
    ):
        # two live "Moeller" matches exist; full names must pick the right one
        market = market_from(gamma_events, "atp-moeller-ivanov-2026-08-17")
        decision = match_market(market, live_candidates)
        assert decision is not None
        assert decision.match_id == 90212

        market2 = market_from(gamma_events, "atp-kuzmano-moelle-2026-08-17")
        decision2 = match_market(market2, live_candidates)
        assert decision2 is not None
        assert decision2.match_id == 90213

    def test_ambiguous_candidates_return_none(self, lehecka_market, lta_live):
        # same two players appear twice on adjacent days (e.g. a suspended
        # match replayed): the matcher must refuse to guess
        original = lta_live["data"][0]
        duplicate = copy.deepcopy(original)
        duplicate["id"] = 99999
        duplicate["scheduled_time"] = "2026-08-17T20:00:00Z"
        decision = match_market(lehecka_market, [original, duplicate])
        assert decision is None

    def test_no_candidates_returns_none(self, lehecka_market):
        assert match_market(lehecka_market, []) is None

    def test_wrong_day_returns_none(self, lehecka_market, lta_live):
        candidate = copy.deepcopy(lta_live["data"][0])
        candidate["scheduled_time"] = "2026-08-25T01:15:00Z"
        assert match_market(lehecka_market, [candidate]) is None

    def test_single_player_agreement_insufficient(self, lehecka_market):
        candidate = {
            "id": 1,
            "scheduled_time": "2026-08-17T12:00:00Z",
            "is_doubles": False,
            "players": {
                "p1": {"id": 1, "name": "Jiri Lehecka"},
                "p2": {"id": 2, "name": "Somebody Else"},
            },
        }
        assert match_market(lehecka_market, [candidate]) is None

    def test_doubles_market_rejected(self, gamma_events, live_candidates):
        market = market_from(gamma_events, "atp-doubles-cashgla-ramsali-2026-08-16")
        assert match_market(market, live_candidates) is None

    def test_doubles_candidate_not_matched_to_singles_market(
        self, lehecka_market, lta_live
    ):
        doubles_only = [m for m in lta_live["data"] if m["is_doubles"]]
        assert match_market(lehecka_market, doubles_only) is None

    def test_fixture_candidates_match_upcoming_market(
        self, gamma_events, lta_fixtures_payload
    ):
        market = market_from(gamma_events, "wta-eala-anisimo-2026-08-17")
        decision = match_market(market, lta_fixtures_payload["data"])
        assert decision is not None
        assert decision.match_id == 70001

    def test_explicit_override_wins(self, lehecka_market, live_candidates):
        decision = match_market(
            lehecka_market, live_candidates, override_match_id=90213
        )
        assert decision is not None
        assert decision.match_id == 90213
        assert decision.method == "explicit"
        assert decision.confidence == 1.0

    def test_explicit_override_outside_candidate_set_is_honored_visibly(
        self, lehecka_market, live_candidates
    ):
        decision = match_market(
            lehecka_market, live_candidates, override_match_id=424242
        )
        assert decision is not None
        assert decision.match_id == 424242
        assert any("not in candidate set" in note for note in decision.notes)

    def test_explicit_override_allows_doubles(self, gamma_events, live_candidates):
        market = market_from(gamma_events, "atp-doubles-cashgla-ramsali-2026-08-16")
        decision = match_market(market, live_candidates, override_match_id=90215)
        assert decision is not None
        assert decision.match_id == 90215


class TestScoreCandidates:
    def test_sorted_best_first(self, lehecka_market, live_candidates):
        scored = score_candidates(lehecka_market, live_candidates)
        assert scored
        assert scored[0][0]["id"] == 90211
        assert all(
            scored[i][1] >= scored[i + 1][1] for i in range(len(scored) - 1)
        )

    def test_unparsable_market_scores_nothing(self, gamma_events, live_candidates):
        market = market_from(gamma_events, "2026-mens-us-open-winner-tennis")
        assert score_candidates(market, live_candidates) == []
