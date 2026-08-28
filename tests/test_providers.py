"""LiveScoreProvider protocol: the default client satisfies it, and the whole
decide path runs offline through a StaticLiveScoreProvider — no network, no key.
"""

from __future__ import annotations

from polymarket_tennis.cli import _decide, _load_candidates
from polymarket_tennis.livetennis import LiveTennisClient
from polymarket_tennis.providers import LiveScoreProvider, StaticLiveScoreProvider

from .test_matching import market_from


def test_livetennisclient_satisfies_protocol():
    # the default implementation must conform to the interface the pipeline
    # depends on, so it stays swappable without a signature drift going unnoticed
    assert isinstance(LiveTennisClient(api_key="x"), LiveScoreProvider)


def test_static_provider_satisfies_protocol():
    assert isinstance(StaticLiveScoreProvider(), LiveScoreProvider)


def test_static_provider_serves_and_resolves(lta_live, lta_fixtures_payload):
    provider = StaticLiveScoreProvider(
        live=lta_live["data"], fixtures=lta_fixtures_payload["data"]
    )
    candidates = _load_candidates(provider)
    assert candidates  # live + fixtures flattened
    first_id = lta_live["data"][0]["id"]
    assert provider.match(first_id) is not None
    assert provider.match(-1) is None


def test_decide_runs_fully_offline(gamma_events, lta_live, lta_fixtures_payload):
    # the matcher already takes plain dicts; this proves the CLI orchestration
    # helpers accept any LiveScoreProvider, so pairing works with zero network
    market = market_from(gamma_events, "atp-lehecka-fils-2026-08-17")
    provider = StaticLiveScoreProvider(
        live=lta_live["data"], fixtures=lta_fixtures_payload["data"]
    )
    decision, candidates = _decide(market, provider, override=None)
    assert candidates
    assert decision is not None
    assert decision.match_id is not None
    assert decision.confidence >= 0.70
