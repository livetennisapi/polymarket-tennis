"""Arena strategy contract and the paper book it writes into.

A strategy is anything with a ``name`` and an ``on_view(view, book)`` method.
It is handed one ``LiveMarketView`` per tape line and may append paper
entries to the ``PaperBook``. That is the whole surface: a strategy cannot
reach an exchange because nothing in this package can. There is no order
client, no wallet, no key other than the tennis API key used by the
organisers to record the tape.

Mark-to-market convention (deliberately simple and stated once):

* An entry is a notional purchase of ``size_usd / price`` outcome shares of
  ``side`` at ``price`` (Polymarket outcome prices live in [0, 1]).
* Its value at a later price ``p`` is ``shares * p``; its P&L is
  ``shares * (p - price)``. No fees, no slippage, no fill model — a paper
  book, not a backtest you should believe.
* When the tape's last line carries a completed match with a ``winner``, the
  winning outcome marks at 1.0 and the other at 0.0. Retirements, walkovers
  and any other non-``completed`` outcome are NOT settled here: the venue's
  own rule decides those and we never hard-code it (see CLAUDE.md), so such
  entries stay marked at the last observed price.
"""

from __future__ import annotations

import ast
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..join import LiveMarketView

__all__ = [
    "Strategy",
    "PaperBook",
    "PaperEntry",
    "ForbiddenImportError",
    "FORBIDDEN_MODULES",
    "check_strategy_source",
]

# Modules an entrant's strategy file must not import: the arena is paper-only
# and these are the usual routes to a real order or a real wallet.
FORBIDDEN_MODULES: frozenset[str] = frozenset(
    {
        "py_clob_client",
        "py_order_utils",
        "web3",
        "eth_account",
        "eth_keys",
        "solana",
        "bitcoin",
    }
)


@runtime_checkable
class Strategy(Protocol):
    """What an arena entrant implements. Pure observation in, paper entries out."""

    name: str

    def on_view(self, view: LiveMarketView, book: PaperBook) -> None: ...


@dataclass
class PaperEntry:
    """One imaginary position. Nothing here was sent anywhere."""

    ts: str
    market_slug: str
    side: str
    price: float
    size_usd: float
    reason: str

    @property
    def shares(self) -> float:
        return self.size_usd / self.price

    def value_at(self, price: float) -> float:
        return self.shares * price

    def pnl_at(self, price: float) -> float:
        return self.shares * (price - self.price)


@dataclass
class PaperBook:
    """Append-only list of paper entries plus mark-to-market helpers."""

    entries: list[PaperEntry] = field(default_factory=list)
    max_entries: int = 50  # keeps a runaway strategy from spamming the book

    def enter(
        self,
        ts: str,
        market_slug: str,
        side: str,
        price: float | None,
        size_usd: float,
        reason: str,
    ) -> PaperEntry | None:
        """Record a paper entry. Returns None (and records nothing) on a bad
        price, non-positive size, or when the book is full."""
        if price is None or not (0.0 < price < 1.0):
            return None
        if size_usd <= 0 or len(self.entries) >= self.max_entries:
            return None
        entry = PaperEntry(
            ts=ts,
            market_slug=market_slug,
            side=side,
            price=float(price),
            size_usd=float(size_usd),
            reason=reason,
        )
        self.entries.append(entry)
        return entry

    def has_entry(self, market_slug: str, reason_prefix: str | None = None) -> bool:
        for e in self.entries:
            if e.market_slug != market_slug:
                continue
            if reason_prefix is None or e.reason.startswith(reason_prefix):
                return True
        return False

    def pnl(self, prices: dict[str, float | None]) -> float:
        """Total mark-to-market P&L at the given outcome prices.

        An entry whose side has no price in ``prices`` is marked at cost
        (zero P&L) rather than guessed.
        """
        total = 0.0
        for e in self.entries:
            p = prices.get(e.side)
            if p is None:
                continue
            total += e.pnl_at(p)
        return total

    def to_list(self) -> list[dict[str, Any]]:
        return [asdict(e) for e in self.entries]


class ForbiddenImportError(ImportError):
    """A strategy file imports something that could reach a venue or wallet."""


def check_strategy_source(path: str | Path) -> None:
    """Static check: refuse a strategy file that imports a forbidden module.

    This is an organiser-side gate, not a sandbox — it catches the honest
    mistake, not a determined adversary. The real guarantee is that the
    arena API hands strategies nothing they could trade with.
    """
    tree = ast.parse(Path(path).read_text(), filename=str(path))
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            root = name.split(".")[0]
            if root in FORBIDDEN_MODULES:
                raise ForbiddenImportError(
                    f"{path}: imports {name!r}; the arena is paper-only and "
                    "strategies may not import order or wallet clients."
                )
