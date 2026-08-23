"""Observe-only Polymarket tennis market watcher (paper book, no orders).

Built on the ``polymarket-tennis`` package's public API only:
GammaClient, LiveTennisClient, discover_tennis_markets, match_market,
build_view, LiveMarketView.

    python watcher.py                 # live: Gamma (keyless) + LIVETENNIS_API_KEY
    python watcher.py --once          # one poll, then exit
    python watcher.py --once --fixtures tests/fixtures   # offline dry run

Budget: each poll costs 2 Live Tennis API requests (live_matches + fixtures).
The free tier allows 30 req/min and 100 req/day, so the watcher refuses to
spend more than ``--daily-budget`` requests (default 96) per process.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from paper_book import BANNER, PaperBook

from polymarket_tennis import (
    GammaClient,
    LiveMarketView,
    LiveTennisClient,
    build_view,
    discover_tennis_markets,
    match_market,
)
from polymarket_tennis.matching import fold_name

REQUESTS_PER_POLL = 2  # lta.live_matches() + lta.fixtures()
FREE_TIER_DAILY = 100
MIN_INTERVAL = 60.0
SETTLEMENT_OUTCOMES = {"retired", "walkover"}


def log(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


# ------------------------------------------------------------ pure helpers
def favourite(view: LiveMarketView) -> tuple[str, float] | None:
    """Outcome label + price of the higher-priced side (None if unpriced)."""
    priced = [(o, p) for o, p in view.prices.items() if p is not None]
    if len(priced) < 2:
        return None
    return max(priced, key=lambda item: item[1])


def server_outcome(view: LiveMarketView) -> str | None:
    """Map the serving player (1/2) to the market outcome label, or None."""
    if view.server not in (1, 2):
        return None
    server_name = view.player1 if view.server == 1 else view.player2
    for outcome in view.prices:
        if fold_name(outcome) == fold_name(server_name):
            return outcome
    return None  # names don't line up — never guess


def game_key(view: LiveMarketView) -> str:
    games = (view.match.get("score") or {}).get("games") or []
    current = (
        f"{games[0][-1]}-{games[1][-1]}"
        if len(games) == 2 and games[0] and games[1]
        else "?"
    )
    return f"sets={'-'.join(map(str, view.sets))} games={current}"


def match_outcome(match: dict[str, Any]) -> str | None:
    """``outcome`` per the API docs; fall back to ``event_status`` wording."""
    outcome = match.get("outcome")
    if outcome:
        return str(outcome).lower()
    status = match.get("event_status")
    return str(status).lower() if status else None


def settlement_text(view: LiveMarketView) -> str:
    raw = view.market.raw
    text = raw.get("description") or raw.get("rules_secondary")
    if text:
        return str(text).strip()
    return (
        "(this market payload carries no `description` text — fetch the "
        "market from Gamma directly to read the venue's settlement rule)"
    )


def fmt_age(seconds: float | None) -> str:
    return "unknown" if seconds is None else f"{seconds:.0f}s"


def render(view: LiveMarketView, now: datetime) -> str:
    prices = " | ".join(
        f"{o} {p:.3f}" if p is not None else f"{o} ?" for o, p in view.prices.items()
    )
    serving = (
        view.player1 if view.server == 1 else view.player2 if view.server == 2 else "-"
    )
    return (
        f"[{now.isoformat(timespec='seconds')}] {view.market.question}\n"
        f"  prices:     {prices}\n"
        f"  score:      {view.score_line or '(no score yet)'}\n"
        f"  serving:    {serving}\n"
        f"  break pt:   {view.break_point}\n"
        f"  staleness:  market {fmt_age(view.market_staleness(now))}, "
        f"live {fmt_age(view.live_staleness(now))}"
    )


# ------------------------------------------------------------- one poll
def process_view(view: LiveMarketView, book: PaperBook, now: datetime) -> None:
    """Log the view, update the paper book, surface settlement wording."""
    log(render(view, now))
    fav = favourite(view)
    key = game_key(view)
    if fav is not None:
        resolved = book.resolve_entry(view.market.slug, key, fav[1], now)
        if resolved is not None:
            log(
                f"  PAPER resolved: {resolved.side} {resolved.price:.3f} -> "
                f"{resolved.resolved_price:.3f} (move {resolved.move:+.3f})"
            )
        if view.break_point and server_outcome(view) == fav[0]:
            opened = book.open_entry(view.market.slug, fav[0], fav[1], key, now)
            if opened is not None:
                log(
                    f"  PAPER entry: {fav[0]} (favourite) faces BP @ {fav[1]:.3f}"
                )
    outcome = match_outcome(view.match)
    if outcome in SETTLEMENT_OUTCOMES:
        log(f"  match outcome = {outcome!r}; the venue's own settlement text:")
        log("    " + settlement_text(view).replace("\n", "\n    "))


def poll(gamma: GammaClient, lta: LiveTennisClient, book: PaperBook) -> int:
    now = datetime.now(timezone.utc)
    markets = discover_tennis_markets(
        gamma, market_types={"moneyline"}, matches_only=True
    )
    candidates = lta.live_matches() + lta.fixtures()
    shown = 0
    for market in markets:
        decision = match_market(market, candidates)
        if decision is None:
            continue  # ambiguous or unmatched — never guess
        view = build_view(market, decision.match, now, now)
        process_view(view, book, now)
        shown += 1
    log(f"-- {len(markets)} moneyline markets, {shown} confidently matched --")
    return shown


# --------------------------------------------------------- fixture clients
def fixture_clients(directory: Path) -> tuple[GammaClient, LiveTennisClient]:
    """Offline clients that answer from JSON files (no network at all)."""
    events = json.loads((directory / "gamma_events_tennis.json").read_text())
    live = json.loads((directory / "lta_matches_live.json").read_text())
    fixtures = json.loads((directory / "lta_fixtures.json").read_text())

    def gamma_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=events if request.url.path == "/events" else [])

    def lta_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/fixtures"):
            return httpx.Response(200, json=fixtures)
        return httpx.Response(200, json=live)

    gamma = GammaClient(
        client=httpx.Client(transport=httpx.MockTransport(gamma_handler))
    )
    lta = LiveTennisClient(
        api_key="fixture-key",
        client=httpx.Client(transport=httpx.MockTransport(lta_handler)),
    )
    return gamma, lta


# ------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--once", action="store_true", help="one poll, then exit")
    parser.add_argument("--fixtures", type=Path, help="offline JSON fixture dir")
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--book", type=Path, default=Path("paper_book.json"))
    parser.add_argument("--daily-budget", type=int, default=FREE_TIER_DAILY - 4)
    args = parser.parse_args(argv)

    log(BANNER)
    interval = max(args.interval, MIN_INTERVAL)
    log(
        f"cadence {interval:.0f}s, {REQUESTS_PER_POLL} Live Tennis API requests "
        f"per poll; stopping after {args.daily_budget} requests "
        f"(free tier: 30/min, {FREE_TIER_DAILY}/day)."
    )
    book = PaperBook.load(args.book)
    if args.fixtures:
        gamma, lta = fixture_clients(args.fixtures)
    else:
        gamma, lta = GammaClient(), LiveTennisClient()
    spent = 0
    with gamma, lta:
        while True:
            poll(gamma, lta, book)
            spent += REQUESTS_PER_POLL
            if args.once:
                return 0
            if spent + REQUESTS_PER_POLL > args.daily_budget:
                log("daily request budget reached; stopping (paper book saved).")
                return 0
            time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())
