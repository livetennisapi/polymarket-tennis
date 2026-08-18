"""CLI behaviour, fixture-driven via mock transports — no network."""

from __future__ import annotations

import httpx
import pytest

from polymarket_tennis import cli
from polymarket_tennis.gamma import GammaClient
from polymarket_tennis.livetennis import LiveTennisClient

from .conftest import _gamma_handler, _lta_handler


@pytest.fixture(autouse=True)
def offline_clients(monkeypatch):
    """Route every client the CLI builds through the fixture transports."""

    def make_gamma(*args, **kwargs):
        return GammaClient(
            client=httpx.Client(transport=httpx.MockTransport(_gamma_handler))
        )

    def make_lta(*args, **kwargs):
        return LiveTennisClient(
            api_key="test-key",
            client=httpx.Client(transport=httpx.MockTransport(_lta_handler)),
        )

    monkeypatch.setattr(cli, "GammaClient", make_gamma)
    monkeypatch.setattr(cli, "LiveTennisClient", make_lta)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: None)


def run(capsys, *argv):
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


class TestDiscover:
    def test_lists_markets(self, capsys):
        code, out = run(capsys, "discover")
        assert code == 0
        assert "atp-lehecka-fils-2026-08-17" in out
        assert "Jiri Lehecka" in out
        assert "markets." in out

    def test_moneyline_only(self, capsys):
        code, out = run(capsys, "discover", "--moneyline-only", "--matches-only")
        assert code == 0
        assert "Set 2 Winner" not in out
        assert "US Open" not in out


class TestMatch:
    def test_confident_decision(self, capsys):
        code, out = run(capsys, "match", "atp-lehecka-fils-2026-08-17")
        assert code == 0
        assert "match id 90211" in out
        assert "confidence" in out

    def test_ambiguity_reported_not_guessed(self, capsys):
        code, out = run(capsys, "match", "atp-doubles-cashgla-ramsali-2026-08-16")
        assert code == 1
        assert "NO MATCH" in out
        assert "never guesses" in out

    def test_unknown_market(self, capsys):
        code, out = run(capsys, "match", "totally-unknown-slug")
        assert code == 1
        assert "No Polymarket market found" in out

    def test_explicit_override(self, capsys):
        code, out = run(
            capsys, "match", "atp-lehecka-fils-2026-08-17", "--match-id", "90213"
        )
        assert code == 0
        assert "match id 90213" in out
        assert "explicit" in out


class TestWatch:
    def test_watch_prints_joined_view_and_budget_note(self, capsys):
        code, out = run(
            capsys, "watch", "atp-lehecka-fils-2026-08-17", "--count", "2"
        )
        assert code == 0
        assert "100 req/day" in out  # budget honesty up front
        assert "paired with match id 90211" in out
        assert out.count("BREAK POINT") == 2  # one joined block per poll
        assert "4-6 3-4 (15-40)" in out

    def test_interval_clamped_to_polite_minimum(self, capsys):
        code, out = run(
            capsys,
            "watch",
            "atp-lehecka-fils-2026-08-17",
            "--interval",
            "1",
            "--count",
            "1",
        )
        assert code == 0
        assert "polite minimum" in out

    def test_watch_stops_when_completed(self, capsys):
        # match 90209 is completed; force-pair it and watch should stop
        code, out = run(
            capsys,
            "watch",
            "atp-lehecka-fils-2026-08-17",
            "--match-id",
            "90209",
            "--count",
            "5",
        )
        assert code == 0
        assert "match completed; stopping." in out


class TestKeyHandling:
    def test_missing_key_is_a_clear_error(self, capsys, monkeypatch):
        def make_lta(*args, **kwargs):
            return LiveTennisClient(
                api_key=None,
                client=httpx.Client(
                    transport=httpx.MockTransport(_lta_handler)
                ),
            )

        monkeypatch.setattr(cli, "LiveTennisClient", make_lta)
        monkeypatch.delenv("LIVETENNIS_API_KEY", raising=False)
        code, out = run(capsys, "match", "atp-lehecka-fils-2026-08-17")
        assert code == 2
        assert "LIVETENNIS_API_KEY" in out
        assert "livetennisapi.com/subscribe/free" in out
