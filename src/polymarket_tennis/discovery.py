"""Find tennis event markets on Polymarket and normalize them.

Polymarket tags tennis events with the ``tennis`` tag (id 864), and per-match
events carry slugs like ``atp-lehecka-fils-2026-08-17`` or
``wta-doubles-sinitow-jurawu-2026-08-16``. Discovery works in two layers:

1. query Gamma ``/events?tag_slug=tennis`` (server-side filter), then
2. re-check each event locally (:func:`is_tennis_event`) so a mis-tagged
   payload can never slip through, and classify it
   (:func:`is_match_event` / :func:`is_doubles_event`).
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from .gamma import GammaClient
from .models import TennisMarket

__all__ = [
    "TENNIS_TAG_SLUG",
    "is_tennis_event",
    "is_match_event",
    "is_doubles_event",
    "iter_markets",
    "discover_tennis_markets",
    "find_market",
]

TENNIS_TAG_SLUG = "tennis"

# atp-lehecka-fils-2026-08-17 / wta-doubles-a-b-2026-08-16 / itf-x-y-...
_MATCH_SLUG_RE = re.compile(
    r"^(?:atp|wta|itf|challenger|ch)(?:-doubles)?-.+-\d{4}-\d{2}-\d{2}$"
)
_TENNIS_SLUG_PREFIX_RE = re.compile(r"^(?:atp|wta|itf|challenger|ch)-")
_TENNIS_TITLE_HINTS = (
    "tennis",
    "atp",
    "wta",
    "grand slam",
    "us open",
    "australian open",
    "wimbledon",
    "roland garros",
)


def _event_tags(event: dict[str, Any]) -> list[str]:
    tags = event.get("tags") or []
    slugs = []
    for tag in tags:
        if isinstance(tag, dict) and tag.get("slug"):
            slugs.append(str(tag["slug"]).lower())
    return slugs


def is_tennis_event(event: dict[str, Any]) -> bool:
    """True when the event is recognizably tennis (tag, slug, or title)."""
    if TENNIS_TAG_SLUG in _event_tags(event):
        return True
    slug = str(event.get("slug") or "").lower()
    if _TENNIS_SLUG_PREFIX_RE.match(slug):
        return True
    title = str(event.get("title") or "").lower()
    return any(hint in title for hint in _TENNIS_TITLE_HINTS)


def is_match_event(event: dict[str, Any]) -> bool:
    """True for a per-match event (vs a futures/outright event)."""
    slug = str(event.get("slug") or "").lower()
    if _MATCH_SLUG_RE.match(slug):
        return True
    title = str(event.get("title") or "")
    return " vs " in title.lower()


def is_doubles_event(event: dict[str, Any]) -> bool:
    slug = str(event.get("slug") or "").lower()
    if "-doubles-" in slug:
        return True
    title = str(event.get("title") or "").lower()
    return "(doubles)" in title


def iter_markets(
    events: Iterable[dict[str, Any]],
    market_types: set[str] | None = None,
    include_closed: bool = False,
) -> list[TennisMarket]:
    """Normalize the markets inside events, with local tennis re-checking."""
    found: list[TennisMarket] = []
    for event in events:
        if not is_tennis_event(event):
            continue
        for raw in event.get("markets") or []:
            market = TennisMarket.from_gamma(raw, event=event)
            if market.closed and not include_closed:
                continue
            if market_types and (market.market_type or "") not in market_types:
                continue
            found.append(market)
    return found


def discover_tennis_markets(
    client: GammaClient,
    market_types: set[str] | None = None,
    include_closed: bool = False,
    matches_only: bool = False,
    limit: int = 100,
) -> list[TennisMarket]:
    """Fetch open tennis events from Gamma and return normalized markets.

    ``matches_only`` keeps only per-match events (drops futures/outrights).
    ``market_types`` filters on Gamma's ``sportsMarketType`` (for example
    ``{"moneyline"}`` for match-winner markets).
    """
    events = client.events(tag_slug=TENNIS_TAG_SLUG, closed=False, limit=limit)
    if matches_only:
        events = [e for e in events if is_match_event(e)]
    return iter_markets(
        events, market_types=market_types, include_closed=include_closed
    )


def find_market(client: GammaClient, id_or_slug: str) -> TennisMarket | None:
    """Resolve one market by Gamma id or slug (market slug or event slug)."""
    raw = client.market(id_or_slug)
    if raw is not None:
        return TennisMarket.from_gamma(raw)
    # fall back: the given slug may be an *event* slug; use its first
    # non-closed market (the moneyline market comes first on match events)
    if not id_or_slug.isdigit():
        event = client.event_by_slug(id_or_slug)
        if event:
            markets = iter_markets([event], include_closed=True)
            open_markets = [m for m in markets if not m.closed]
            chosen = open_markets or markets
            if chosen:
                return chosen[0]
    return None
