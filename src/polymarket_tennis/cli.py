"""``pmtennis`` — observe tennis event markets next to live match state.

Commands:
  pmtennis discover                 list current tennis markets (keyless)
  pmtennis match <market-id|slug>   show the matching decision + confidence
  pmtennis watch <market-id|slug>   poll the joined view at a gentle cadence

``discover`` uses only Polymarket's public Gamma API and needs no key.
``match`` and ``watch`` also read live state from the Live Tennis API
(``LIVETENNIS_API_KEY``; free keys at https://livetennisapi.com/subscribe/free).

Free-tier budget honesty: the free tier allows 30 requests/minute and
100 requests/day. ``watch`` spends 1 Live Tennis API request per poll, so the
default 60s cadence funds about 100 minutes of watching per day; ``--interval
300`` stretches the same budget to roughly 8 hours. Watching several matches
at once divides that budget accordingly.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

from . import __version__
from .discovery import discover_tennis_markets, find_market
from .gamma import GammaClient
from .join import build_view
from .livetennis import LiveTennisClient, MissingAPIKeyError
from .matching import MatchDecision, match_market, score_candidates
from .models import TennisMarket

MIN_INTERVAL = 30.0  # seconds; keeps polling polite on every tier


def _print(text: str) -> None:
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


# ----------------------------------------------------------------- discover
def cmd_discover(args: argparse.Namespace) -> int:
    with GammaClient() as gamma:
        market_types = {"moneyline"} if args.moneyline_only else None
        markets = discover_tennis_markets(
            gamma,
            market_types=market_types,
            matches_only=args.matches_only,
            limit=args.limit,
        )
    if not markets:
        _print(
            "No open tennis markets found on Polymarket right now "
            "(the tennis calendar has quiet hours; try again later)."
        )
        return 0
    for market in markets:
        prices = " | ".join(
            f"{o} {p:.3f}" if p is not None else f"{o} ?"
            for o, p in market.price_by_outcome.items()
        )
        volume = f"{market.volume:,.0f}" if market.volume is not None else "?"
        _print(f"{market.slug}")
        _print(f"  {market.question}")
        _print(f"  {prices}  (volume {volume})")
    _print(f"\n{len(markets)} markets.")
    return 0


# -------------------------------------------------------------------- match
def _load_market(id_or_slug: str) -> TennisMarket | None:
    with GammaClient() as gamma:
        return find_market(gamma, id_or_slug)


def _load_candidates(lta: LiveTennisClient) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = list(lta.live_matches())
    candidates.extend(lta.matches(status="upcoming"))
    candidates.extend(lta.fixtures())
    return candidates


def _decide(
    market: TennisMarket,
    lta: LiveTennisClient,
    override: int | None,
) -> tuple[MatchDecision | None, list[dict[str, Any]]]:
    candidates = _load_candidates(lta)
    return match_market(market, candidates, override_match_id=override), candidates


def cmd_match(args: argparse.Namespace) -> int:
    market = _load_market(args.market)
    if market is None:
        _print(f"No Polymarket market found for {args.market!r}.")
        return 1
    _print(f"market: {market.question}  [{market.slug}]")
    with LiveTennisClient() as lta:
        decision, candidates = _decide(market, lta, args.match_id)
    scored = score_candidates(market, candidates)
    for candidate, score, notes in scored[:5]:
        names = candidate.get("players") or {}
        label = (
            f"{(names.get('p1') or {}).get('name', candidate.get('player1_name'))}"
            f" vs {(names.get('p2') or {}).get('name', candidate.get('player2_name'))}"
        )
        _print(
            f"  candidate {candidate.get('id')}: {label}  "
            f"score {score:.2f}  ({'; '.join(notes)})"
        )
    if decision is None:
        _print(
            "decision: NO MATCH — no candidate is confident enough "
            "(the matcher never guesses; use --match-id to override)."
        )
        return 1
    _print(
        f"decision: match id {decision.match_id}  "
        f"confidence {decision.confidence:.2f}  method {decision.method}"
    )
    for note in decision.notes:
        _print(f"  note: {note}")
    return 0


# -------------------------------------------------------------------- watch
def cmd_watch(args: argparse.Namespace) -> int:
    interval = max(float(args.interval), MIN_INTERVAL)
    if interval != float(args.interval):
        _print(f"interval raised to the {MIN_INTERVAL:.0f}s polite minimum.")
    market = _load_market(args.market)
    if market is None:
        _print(f"No Polymarket market found for {args.market!r}.")
        return 1
    polls_per_day = int(86400 / interval)
    _print(
        f"Watching at a {interval:.0f}s cadence: 1 Live Tennis API request per "
        f"poll ({int(3600 / interval)}/hour). The free tier allows 30 req/min "
        f"and 100 req/day, so this cadence funds about "
        f"{min(polls_per_day, 100) * interval / 60:.0f} minutes of watching "
        "per day on a free key."
    )
    with LiveTennisClient() as lta, GammaClient() as gamma:
        decision, _ = _decide(market, lta, args.match_id)
        if decision is None or decision.match_id is None:
            _print(
                "Could not confidently pair this market with a live match or "
                "fixture. Run `pmtennis match` to inspect candidates, then "
                "re-run watch with --match-id."
            )
            return 1
        _print(
            f"paired with match id {decision.match_id} "
            f"(confidence {decision.confidence:.2f}, {decision.method}).\n"
        )
        iterations = args.count if args.count and args.count > 0 else None
        while True:
            fresh_raw = gamma.market(market.id or market.slug)
            fresh = (
                TennisMarket.from_gamma(fresh_raw) if fresh_raw else market
            )
            match = lta.match(decision.match_id)
            if match is None:
                _print("live feed no longer returns this match; stopping.")
                return 1
            view = build_view(fresh, match)
            _print(view.render())
            if match.get("status") == "completed":
                _print("match completed; stopping.")
                return 0
            if iterations is not None:
                iterations -= 1
                if iterations <= 0:
                    return 0
            time.sleep(interval)


# --------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pmtennis",
        description=(
            "Observe tennis event markets on Polymarket next to live match "
            "state from the Live Tennis API. Observe-only by design: this "
            "tool reads public market data and live scores; execution is out "
            "of scope."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_discover = sub.add_parser(
        "discover", help="list current tennis markets (keyless)"
    )
    p_discover.add_argument(
        "--matches-only",
        action="store_true",
        help="only per-match events (skip futures/outrights)",
    )
    p_discover.add_argument(
        "--moneyline-only",
        action="store_true",
        help="only match-winner markets",
    )
    p_discover.add_argument("--limit", type=int, default=100)
    p_discover.set_defaults(func=cmd_discover)

    p_match = sub.add_parser(
        "match", help="show the market-to-match decision + confidence"
    )
    p_match.add_argument("market", help="Gamma market id or slug")
    p_match.add_argument(
        "--match-id", type=int, default=None, help="explicit override"
    )
    p_match.set_defaults(func=cmd_match)

    p_watch = sub.add_parser(
        "watch", help="poll the joined market + live-state view"
    )
    p_watch.add_argument("market", help="Gamma market id or slug")
    p_watch.add_argument(
        "--interval",
        type=float,
        default=60.0,
        help=f"poll cadence in seconds (default 60, minimum {MIN_INTERVAL:.0f})",
    )
    p_watch.add_argument(
        "--match-id", type=int, default=None, help="explicit override"
    )
    p_watch.add_argument(
        "--count",
        type=int,
        default=0,
        help="stop after N polls (0 = run until the match completes)",
    )
    p_watch.set_defaults(func=cmd_watch)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except MissingAPIKeyError as exc:
        _print(str(exc))
        return 2
    except KeyboardInterrupt:
        _print("\nstopped.")
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
