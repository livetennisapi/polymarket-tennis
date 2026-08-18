"""Fixture-driven test harness — no network, ever.

Gamma fixtures are trimmed captures of REAL Polymarket Gamma API payloads
(fetched 2026-08-18 during the Cincinnati Open). Live Tennis API fixtures are
constructed to the published OpenAPI schema (livetennisapi/openapi), including
the documented completed-match edge case of null points and empty games — see
tests/fixtures/README.md for provenance.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from polymarket_tennis.gamma import GammaClient
from polymarket_tennis.livetennis import LiveTennisClient

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def gamma_events():
    return load_fixture("gamma_events_tennis.json")


@pytest.fixture
def lta_live():
    return load_fixture("lta_matches_live.json")


@pytest.fixture
def lta_fixtures_payload():
    return load_fixture("lta_fixtures.json")


@pytest.fixture
def lta_completed():
    return load_fixture("lta_match_completed.json")


def _gamma_handler(request: httpx.Request) -> httpx.Response:
    events = load_fixture("gamma_events_tennis.json")
    path = request.url.path
    params = dict(request.url.params)
    if path == "/events":
        if "slug" in params:
            hits = [e for e in events if e["slug"] == params["slug"]]
            return httpx.Response(200, json=hits)
        return httpx.Response(200, json=events)
    if path == "/markets":
        if "slug" in params:
            for event in events:
                for market in event["markets"]:
                    if market["slug"] == params["slug"]:
                        payload = dict(market)
                        payload["events"] = [
                            {k: event[k] for k in ("id", "slug", "title")}
                        ]
                        return httpx.Response(200, json=[payload])
            return httpx.Response(200, json=[])
        return httpx.Response(200, json=[])
    if path.startswith("/markets/"):
        market_id = path.rsplit("/", 1)[-1]
        for event in events:
            for market in event["markets"]:
                if str(market["id"]) == market_id:
                    payload = dict(market)
                    payload["events"] = [
                        {k: event[k] for k in ("id", "slug", "title")}
                    ]
                    return httpx.Response(200, json=payload)
        return httpx.Response(404, json={"error": "not found"})
    return httpx.Response(404, json={"error": "unknown path"})


def _lta_handler(request: httpx.Request) -> httpx.Response:
    if not request.headers.get("Authorization", "").startswith("Bearer "):
        return httpx.Response(401, json={"error": "missing key"})
    path = request.url.path
    params = dict(request.url.params)
    live = load_fixture("lta_matches_live.json")
    completed = load_fixture("lta_match_completed.json")
    if path.endswith("/matches") and "matches/" not in path:
        status = params.get("status", "live")
        if status == "live":
            return httpx.Response(200, json=live)
        if status == "upcoming":
            return httpx.Response(
                200,
                json={
                    "data": [],
                    "meta": {
                        "limit": 50,
                        "offset": 0,
                        "count": 0,
                        "total": 0,
                        "has_more": False,
                    },
                },
            )
        return httpx.Response(200, json=completed)
    if "/matches/" in path:
        match_id = path.rsplit("/", 1)[-1]
        for match in live["data"] + completed["data"]:
            if str(match["id"]) == match_id:
                return httpx.Response(200, json={"data": match})
        return httpx.Response(404, json={"error": "not found"})
    if path.endswith("/fixtures"):
        return httpx.Response(200, json=load_fixture("lta_fixtures.json"))
    if path.endswith("/players"):
        return httpx.Response(200, json={"data": [], "meta": {}})
    return httpx.Response(404, json={"error": "unknown path"})


@pytest.fixture
def gamma_client():
    transport = httpx.MockTransport(_gamma_handler)
    with GammaClient(client=httpx.Client(transport=transport)) as client:
        yield client


@pytest.fixture
def lta_client():
    transport = httpx.MockTransport(_lta_handler)
    with LiveTennisClient(
        api_key="test-key", client=httpx.Client(transport=transport)
    ) as client:
        yield client
