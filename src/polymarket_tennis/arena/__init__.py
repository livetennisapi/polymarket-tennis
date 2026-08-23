"""Tennis Bot Arena — an observe-only, paper-wallet strategy leaderboard.

Strategies implement :class:`Strategy` (``on_view(view, book)``), get replayed
over a recorded tape of (market, live match) snapshots, and are ranked by
paper P&L. No order code, no wallets; see docs/ARENA.md.
"""

from .baselines import FadeFirstBreak, HoldFavourite, NeverTrade, baseline_strategies
from .replay import ReplayResult, TapeLine, load_strategies, read_tape, replay
from .scoreboard import leaderboard_markdown, rank, write_leaderboard
from .strategy import (
    ForbiddenImportError,
    PaperBook,
    PaperEntry,
    Strategy,
    check_strategy_source,
)

__all__ = [
    "Strategy",
    "PaperBook",
    "PaperEntry",
    "ForbiddenImportError",
    "check_strategy_source",
    "TapeLine",
    "ReplayResult",
    "read_tape",
    "replay",
    "load_strategies",
    "rank",
    "leaderboard_markdown",
    "write_leaderboard",
    "HoldFavourite",
    "FadeFirstBreak",
    "NeverTrade",
    "baseline_strategies",
]
