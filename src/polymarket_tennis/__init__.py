"""polymarket-tennis: observe tennis event markets next to live match state.

Maintained by the Live Tennis API team (https://livetennisapi.com).
Observe-only by design: discovery, matching, and joined state — no order
execution, no wallet handling.
"""

from .discovery import discover_tennis_markets, find_market
from .gamma import GammaClient
from .join import LiveMarketView, build_view, derive_break_point, score_line
from .livetennis import LiveTennisClient
from .matching import MatchDecision, extract_market_players, match_market
from .models import TennisMarket

__version__ = "0.1.0"

__all__ = [
    "GammaClient",
    "LiveTennisClient",
    "TennisMarket",
    "MatchDecision",
    "LiveMarketView",
    "discover_tennis_markets",
    "find_market",
    "extract_market_players",
    "match_market",
    "build_view",
    "derive_break_point",
    "score_line",
    "__version__",
]
