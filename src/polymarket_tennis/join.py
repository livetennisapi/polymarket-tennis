"""Joined view: Polymarket market prices next to live match state.

Break-point derivation rule (documented behaviour of the Live Tennis API's
score object): a break point is on when the RECEIVER is at AD, or the receiver
is at 40 while the server is at 0/15/30. It is never on in a tiebreak, and it
is reported ``False`` whenever the server or the points are null (completed
matches carry null points and empty games arrays).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .models import TennisMarket, parse_iso8601

__all__ = ["derive_break_point", "score_line", "LiveMarketView", "build_view"]


def derive_break_point(score: dict[str, Any] | None) -> bool:
    """True when the current point is a break point. Conservative on nulls."""
    if not score:
        return False
    if score.get("is_tiebreak"):
        return False
    server = score.get("server")
    if server not in (1, 2):
        return False
    points = score.get("points") or []
    if len(points) != 2 or points[0] is None or points[1] is None:
        return False
    receiver_points = str(points[1] if server == 1 else points[0])
    server_points = str(points[0] if server == 1 else points[1])
    if receiver_points == "AD":
        return True
    return receiver_points == "40" and server_points in ("0", "15", "30")


def score_line(score: dict[str, Any] | None) -> str:
    """Render "6-4 3-2 (40-15)" from a Live Tennis API score object."""
    if not score:
        return ""
    games = score.get("games") or []
    parts: list[str] = []
    if len(games) == 2 and games[0] and len(games[0]) == len(games[1]):
        parts = [f"{a}-{b}" for a, b in zip(games[0], games[1], strict=False)]
    points = score.get("points") or []
    if len(points) == 2 and points[0] is not None and points[1] is not None:
        parts.append(f"({points[0]}-{points[1]})")
    return " ".join(parts)


@dataclass
class LiveMarketView:
    """One snapshot of a market and its live match, side by side.

    Staleness is tracked separately for the two feeds: ``market_as_of`` is the
    market's last update stamp (Gamma ``updatedAt``, falling back to fetch
    time) and ``live_as_of`` is the score's own timestamp (falling back to
    fetch time). ``market_fetched_at``/``live_fetched_at`` are always the
    local fetch clocks.
    """

    market: TennisMarket
    match: dict[str, Any]
    match_id: int | None
    player1: str
    player2: str
    match_status: str | None
    event_status: str | None
    score_line: str
    sets: tuple[int, ...]
    server: int | None
    is_tiebreak: bool
    break_point: bool
    prices: dict[str, float | None] = field(default_factory=dict)
    market_as_of: datetime | None = None
    live_as_of: datetime | None = None
    market_fetched_at: datetime | None = None
    live_fetched_at: datetime | None = None

    def market_staleness(self, now: datetime | None = None) -> float | None:
        return _age_seconds(self.market_as_of, now)

    def live_staleness(self, now: datetime | None = None) -> float | None:
        return _age_seconds(self.live_as_of, now)

    def render(self, now: datetime | None = None) -> str:
        """Plain-text one-block rendering used by ``pmtennis watch``."""
        lines = [f"{self.market.question}  [{self.market.slug}]"]
        price_bits = [
            f"{outcome} {price:.3f}" if price is not None else f"{outcome} ?"
            for outcome, price in self.prices.items()
        ]
        market_age = _fmt_age(self.market_staleness(now))
        lines.append(f"  market: {' | '.join(price_bits)}  (as of {market_age})")
        server_mark = (
            ""
            if self.server not in (1, 2)
            else f"  serving: {self.player1 if self.server == 1 else self.player2}"
        )
        flags = []
        if self.break_point:
            flags.append("BREAK POINT")
        if self.is_tiebreak:
            flags.append("tiebreak")
        if self.event_status:
            flags.append(self.event_status)
        flag_text = f"  [{', '.join(flags)}]" if flags else ""
        live_age = _fmt_age(self.live_staleness(now))
        lines.append(
            f"  live:   {self.player1} vs {self.player2}  {self.score_line}"
            f"{server_mark}{flag_text}  (as of {live_age})"
        )
        return "\n".join(lines)


def _age_seconds(
    stamp: datetime | None, now: datetime | None
) -> float | None:
    if stamp is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - stamp).total_seconds())


def _fmt_age(age: float | None) -> str:
    if age is None:
        return "unknown"
    if age < 90:
        return f"{age:.0f}s ago"
    return f"{age / 60:.1f}m ago"


def build_view(
    market: TennisMarket,
    match: dict[str, Any],
    market_fetched_at: datetime | None = None,
    live_fetched_at: datetime | None = None,
) -> LiveMarketView:
    """Join one normalized market with one Live Tennis API match object."""
    now = datetime.now(timezone.utc)
    market_fetched_at = market_fetched_at or now
    live_fetched_at = live_fetched_at or now
    players = match.get("players") or {}
    score = match.get("score") or {}
    sets = tuple(int(s) for s in (score.get("sets") or []))
    return LiveMarketView(
        market=market,
        match=match,
        match_id=match.get("id"),
        player1=str((players.get("p1") or {}).get("name") or "?"),
        player2=str((players.get("p2") or {}).get("name") or "?"),
        match_status=match.get("status"),
        event_status=match.get("event_status"),
        score_line=score_line(score),
        sets=sets,
        server=score.get("server") if score.get("server") in (1, 2) else None,
        is_tiebreak=bool(score.get("is_tiebreak")),
        break_point=derive_break_point(score),
        prices=market.price_by_outcome,
        market_as_of=market.updated_at or market_fetched_at,
        live_as_of=parse_iso8601(score.get("timestamp")) or live_fetched_at,
        market_fetched_at=market_fetched_at,
        live_fetched_at=live_fetched_at,
    )
