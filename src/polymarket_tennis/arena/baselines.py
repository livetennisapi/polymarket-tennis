"""Three tiny baseline strategies. They exist to anchor the leaderboard, not
to be good: a real entrant should beat at least ``never-trade``.

All three are paper-only and size every entry at ``STAKE_USD``.
"""

from __future__ import annotations

from ..join import LiveMarketView
from .strategy import PaperBook, Strategy

__all__ = [
    "STAKE_USD",
    "HoldFavourite",
    "FadeFirstBreak",
    "NeverTrade",
    "favourite_outcome",
    "outcome_player_index",
    "baseline_strategies",
]

STAKE_USD = 10.0


def _fold(text: str) -> str:
    return " ".join(text.lower().split())


def outcome_player_index(view: LiveMarketView, outcome: str) -> int | None:
    """Map a market outcome label to player 1 or 2 of the live match.

    Exact folded-name match first; then a surname match (the market label
    "Jiri Lehecka" against the feed's "Jiri Lehecka" is the easy case, but
    labels occasionally carry just the surname). ``None`` when neither
    player fits — the caller then does nothing rather than guessing.
    """
    label = _fold(outcome)
    names = {1: _fold(view.player1), 2: _fold(view.player2)}
    for idx, name in names.items():
        if name == label:
            return idx
    hits = [idx for idx, name in names.items() if name.split()[-1] == label.split()[-1]]
    return hits[0] if len(hits) == 1 else None


def favourite_outcome(view: LiveMarketView) -> tuple[str, float] | None:
    """The outcome with the highest price, or ``None`` on missing/tied prices."""
    priced = [(o, p) for o, p in view.prices.items() if p is not None]
    if len(priced) < 2:
        return None
    priced.sort(key=lambda op: op[1], reverse=True)
    if priced[0][1] == priced[1][1]:
        return None
    return priced[0]


def _ts(view: LiveMarketView) -> str:
    stamp = view.live_fetched_at or view.market_fetched_at
    return stamp.isoformat() if stamp else ""


class HoldFavourite:
    """Buy the pre-match favourite on the first snapshot and hold to the end."""

    name = "hold-favourite"

    def on_view(self, view: LiveMarketView, book: PaperBook) -> None:
        slug = view.market.slug
        if book.has_entry(slug, self.name):
            return
        fav = favourite_outcome(view)
        if fav is None:
            return
        book.enter(
            _ts(view), slug, fav[0], fav[1], STAKE_USD, f"{self.name}: first snapshot"
        )


class FadeFirstBreak:
    """Enter *against* the favourite the first time they are broken.

    A break is detected from consecutive snapshots within the same set: the
    favourite was serving, the game count moved by exactly one, and it was
    the opponent's count that moved. The favourite is fixed from the first
    snapshot's prices so a mid-match price flip cannot redefine it.
    """

    name = "fade-first-break"

    def __init__(self) -> None:
        self._fav: tuple[str, int] | None = None  # (outcome label, player idx)
        self._prev: tuple[int, tuple[int, int], int | None] | None = None

    def _current_set(self, view: LiveMarketView) -> tuple[int, tuple[int, int]] | None:
        games = (view.match.get("score") or {}).get("games") or []
        if len(games) != 2 or not games[0] or len(games[0]) != len(games[1]):
            return None
        idx = len(games[0]) - 1
        return idx, (int(games[0][idx]), int(games[1][idx]))

    def on_view(self, view: LiveMarketView, book: PaperBook) -> None:
        slug = view.market.slug
        if self._fav is None:
            fav = favourite_outcome(view)
            if fav is None:
                return
            player = outcome_player_index(view, fav[0])
            if player is None:
                return
            self._fav = (fav[0], player)
        current = self._current_set(view)
        if current is None:
            return
        prev = self._prev
        self._prev = (current[0], current[1], view.server)
        if prev is None or prev[0] != current[0] or book.has_entry(slug, self.name):
            return
        _, (p1_before, p2_before), server_before = prev
        p1_now, p2_now = current[1]
        fav_player = self._fav[1]
        opponent = 2 if fav_player == 1 else 1
        gained = {1: p1_now - p1_before, 2: p2_now - p2_before}
        broken = (
            server_before == fav_player
            and gained[opponent] == 1
            and gained[fav_player] == 0
        )
        if not broken:
            return
        against = [o for o in view.prices if o != self._fav[0]]
        if len(against) != 1:
            return
        book.enter(
            _ts(view),
            slug,
            against[0],
            view.prices.get(against[0]),
            STAKE_USD,
            f"{self.name}: favourite broken at {view.score_line}",
        )


class NeverTrade:
    """The floor of the leaderboard: zero entries, zero P&L, zero drawdown."""

    name = "never-trade"

    def on_view(self, view: LiveMarketView, book: PaperBook) -> None:
        return None


def baseline_strategies() -> list[Strategy]:
    """Fresh instances each call — strategies carry per-replay state."""
    return [HoldFavourite(), FadeFirstBreak(), NeverTrade()]
