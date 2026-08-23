"""Offline replay: feed a recorded tape through a strategy and score it.

Tape format (``tape/*.jsonl``): one JSON object per line, one line per poll::

    {"ts": "<ISO-8601>", "market": <raw Gamma market object>,
     "match": <Live Tennis API match object>}

``market`` is exactly what ``GammaClient.market()`` returns and ``match`` is
exactly what ``LiveTennisClient.match()`` returns, so a tape line rebuilds
the same ``LiveMarketView`` the live ``pmtennis watch`` command shows.
Replay is deterministic: no clocks, no network, no randomness.
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..join import LiveMarketView, build_view
from ..models import TennisMarket, parse_iso8601
from .baselines import baseline_strategies, outcome_player_index
from .strategy import PaperBook, Strategy, check_strategy_source

__all__ = [
    "TapeLine",
    "ReplayResult",
    "read_tape",
    "views_from_tape",
    "settlement_prices",
    "replay",
    "load_strategies",
]


@dataclass(frozen=True)
class TapeLine:
    ts: str
    market: dict[str, Any]
    match: dict[str, Any]


@dataclass
class ReplayResult:
    strategy: str
    tape: str
    pnl: float
    max_drawdown: float
    entries: int
    final_prices: dict[str, float | None]
    settled: bool
    equity_curve: list[float] = field(default_factory=list)
    book: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "tape": self.tape,
            "pnl": round(self.pnl, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "entries": self.entries,
            "settled": self.settled,
            "final_prices": self.final_prices,
            "equity_curve": [round(v, 4) for v in self.equity_curve],
            "book": self.book,
        }


def read_tape(path: str | Path) -> list[TapeLine]:
    lines: list[TapeLine] = []
    for number, raw in enumerate(Path(path).read_text().splitlines(), start=1):
        if not raw.strip():
            continue
        obj = json.loads(raw)
        try:
            lines.append(
                TapeLine(ts=str(obj["ts"]), market=obj["market"], match=obj["match"])
            )
        except KeyError as exc:
            raise ValueError(f"{path}:{number}: tape line missing {exc}") from None
    if not lines:
        raise ValueError(f"{path}: empty tape")
    return lines


def views_from_tape(lines: list[TapeLine]) -> list[LiveMarketView]:
    views = []
    for line in lines:
        stamp = parse_iso8601(line.ts)
        market = TennisMarket.from_gamma(line.market)
        views.append(
            build_view(
                market,
                line.match,
                market_fetched_at=stamp,
                live_fetched_at=stamp,
            )
        )
    return views


def settlement_prices(view: LiveMarketView) -> dict[str, float | None] | None:
    """Terminal prices when the match is ``completed`` with a winner.

    Only the plain completed case settles to 1/0. Retired, walkover, default
    and abandoned outcomes are venue-rule territory and return ``None`` so
    the caller keeps marking at the last observed price.
    """
    match = view.match
    if match.get("status") != "completed":
        return None
    outcome = match.get("outcome")
    if outcome not in (None, "completed"):
        return None
    if view.event_status and view.event_status.lower() not in ("completed", "ended"):
        return None
    winner = match.get("winner")
    if winner not in (1, 2):
        return None
    prices: dict[str, float | None] = {}
    for label in view.prices:
        idx = outcome_player_index(view, label)
        if idx is None:
            return None
        prices[label] = 1.0 if idx == winner else 0.0
    return prices


def replay(
    strategy: Strategy,
    lines: list[TapeLine],
    tape_name: str = "",
    book: PaperBook | None = None,
) -> ReplayResult:
    """Run one strategy over a tape; mark the book after every snapshot."""
    book = book or PaperBook()
    views = views_from_tape(lines)
    equity: list[float] = []
    peak = 0.0
    max_dd = 0.0
    marks: dict[str, float | None] = {}
    for view in views:
        strategy.on_view(view, book)
        marks = dict(view.prices)
        value = book.pnl(marks)
        equity.append(value)
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    settled = settlement_prices(views[-1])
    if settled is not None:
        marks = settled
        value = book.pnl(marks)
        equity.append(value)
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)
    return ReplayResult(
        strategy=strategy.name,
        tape=tape_name,
        pnl=book.pnl(marks),
        max_drawdown=max_dd,
        entries=len(book.entries),
        final_prices=marks,
        settled=settled is not None,
        equity_curve=equity,
        book=book.to_list(),
    )


def load_strategies(spec: str) -> list[Strategy]:
    """``"baselines"`` or a path to a Python file.

    The file must expose either ``STRATEGIES`` (a list of strategy objects)
    or a zero-argument ``strategy()`` factory. Its imports are checked
    against ``FORBIDDEN_MODULES`` before it is executed.
    """
    if spec == "baselines":
        return baseline_strategies()
    path = Path(spec)
    if path.suffix != ".py" or not path.exists():
        raise ValueError(
            f"unknown strategies spec {spec!r}: use 'baselines' or a .py path"
        )
    check_strategy_source(path)
    module_spec = importlib.util.spec_from_file_location(
        f"arena_entrant_{path.stem}", path
    )
    if module_spec is None or module_spec.loader is None:
        raise ValueError(f"cannot import {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    found: list[Any] = []
    if hasattr(module, "STRATEGIES"):
        found = list(module.STRATEGIES)
    elif callable(getattr(module, "strategy", None)):
        found = [module.strategy()]
    strategies = [s for s in found if isinstance(s, Strategy)]
    if not strategies:
        raise ValueError(
            f"{path}: expose STRATEGIES = [...] or strategy() returning objects "
            "with a `name` and an on_view(view, book) method"
        )
    return strategies
