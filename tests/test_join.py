"""Break-point truth table, score-line rendering, and join staleness."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from polymarket_tennis.join import build_view, derive_break_point, score_line
from polymarket_tennis.models import TennisMarket


def score(points, server=1, tiebreak=False):
    return {
        "sets": [0, 0],
        "games": [[3], [3]],
        "points": points,
        "server": server,
        "is_tiebreak": tiebreak,
        "timestamp": "2026-08-18T02:31:04Z",
    }


class TestBreakPointTruthTable:
    """Rule: receiver at AD, or receiver at 40 while server at 0/15/30;
    never in tiebreaks; False when server/points are null."""

    @pytest.mark.parametrize(
        ("points", "server", "expected"),
        [
            # server = 1, receiver = p2 (points[1])
            (["0", "40"], 1, True),
            (["15", "40"], 1, True),
            (["30", "40"], 1, True),
            (["40", "40"], 1, False),  # deuce is not a break point
            (["40", "AD"], 1, True),  # receiver advantage
            (["AD", "40"], 1, False),  # server advantage
            (["40", "0"], 1, False),  # game point, not break point
            (["0", "30"], 1, False),
            (["0", "0"], 1, False),
            # server = 2, receiver = p1 (points[0])
            (["40", "0"], 2, True),
            (["40", "15"], 2, True),
            (["40", "30"], 2, True),
            (["40", "40"], 2, False),
            (["AD", "40"], 2, True),
            (["40", "AD"], 2, False),
            (["0", "40"], 2, False),
        ],
    )
    def test_truth_table(self, points, server, expected):
        assert derive_break_point(score(points, server=server)) is expected

    def test_never_in_tiebreak(self):
        assert derive_break_point(score(["6", "6"], tiebreak=True)) is False
        # even wording that would qualify in a normal game
        assert derive_break_point(score(["30", "40"], tiebreak=True)) is False

    def test_null_server_is_false(self):
        assert derive_break_point(score(["30", "40"], server=None)) is False

    def test_null_points_are_false(self):
        assert derive_break_point(score([None, None])) is False
        assert derive_break_point(score(["40", None])) is False
        assert derive_break_point(score([])) is False

    def test_missing_score_is_false(self):
        assert derive_break_point(None) is False
        assert derive_break_point({}) is False

    def test_completed_match_fixture_shape(self, lta_completed):
        # completed matches carry null points + empty games (per the schema)
        assert derive_break_point(lta_completed["data"][0]["score"]) is False


class TestScoreLine:
    def test_mid_match_line(self):
        line = score_line(
            {
                "games": [[6, 4, 3], [4, 6, 2]],
                "points": ["15", "40"],
            }
        )
        assert line == "6-4 4-6 3-2 (15-40)"

    def test_completed_match_line_omits_null_points(self, lta_completed):
        line = score_line(lta_completed["data"][0]["score"])
        assert "None" not in line
        assert "(" not in line

    def test_empty_score(self):
        assert score_line(None) == ""
        assert score_line({}) == ""


class TestBuildView:
    @pytest.fixture
    def market(self, gamma_events):
        event = next(
            e for e in gamma_events if e["slug"] == "atp-lehecka-fils-2026-08-17"
        )
        return TennisMarket.from_gamma(event["markets"][0], event=event)

    @pytest.fixture
    def live_match(self, lta_live):
        return lta_live["data"][0]

    def test_join_fields(self, market, live_match):
        view = build_view(market, live_match)
        assert view.match_id == 90211
        assert view.player1 == "Jiri Lehecka"
        assert view.player2 == "Arthur Fils"
        assert view.prices == {"Jiri Lehecka": 0.095, "Arthur Fils": 0.905}
        assert view.score_line == "4-6 3-4 (15-40)"
        assert view.server == 1
        assert view.break_point is True  # server p1 at 15, receiver p2 at 40
        assert view.sets == (0, 1)

    def test_staleness_tracks_both_feeds(self, market, live_match):
        market_fetch = datetime(2026, 8, 18, 2, 32, 0, tzinfo=timezone.utc)
        live_fetch = datetime(2026, 8, 18, 2, 32, 30, tzinfo=timezone.utc)
        view = build_view(
            market,
            live_match,
            market_fetched_at=market_fetch,
            live_fetched_at=live_fetch,
        )
        now = datetime(2026, 8, 18, 2, 33, 0, tzinfo=timezone.utc)
        # live_as_of comes from the score's own timestamp (02:31:04)
        assert view.live_staleness(now) == pytest.approx(116.0)
        # market_as_of comes from Gamma's updatedAt stamp
        assert view.market_as_of == market.updated_at
        assert view.market_staleness(now) is not None
        assert view.market_fetched_at == market_fetch
        assert view.live_fetched_at == live_fetch

    def test_staleness_falls_back_to_fetch_time(self, market, live_match):
        match = dict(live_match)
        match["score"] = dict(match["score"], timestamp=None)
        fetch = datetime.now(timezone.utc) - timedelta(seconds=10)
        view = build_view(market, match, live_fetched_at=fetch)
        age = view.live_staleness()
        assert age is not None and 9 <= age <= 60

    def test_render_is_plain_text(self, market, live_match):
        view = build_view(market, live_match)
        text = view.render(now=datetime(2026, 8, 18, 2, 33, 0, tzinfo=timezone.utc))
        assert "Jiri Lehecka vs Arthur Fils" in text
        assert "BREAK POINT" in text
        assert "serving: Jiri Lehecka" in text
        assert "0.095" in text and "0.905" in text
        assert "ago" in text  # staleness surfaced for both feeds

    def test_retired_match_shows_event_status(self, market, lta_completed):
        view = build_view(market, lta_completed["data"][0])
        text = view.render()
        assert "Retired" in text
        assert view.break_point is False
