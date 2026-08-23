"""Local JSON "paper book" — a notebook, never an order book.

Every entry here is imaginary. Nothing in this module (or this example) can
reach an exchange or any order endpoint; it only writes a JSON file.

Lifecycle of one paper entry:

1. ``open_entry`` — the favourite is facing a break point. We note the time,
   the market, the side (the favourite's outcome label), and the favourite's
   price at that moment, keyed by the game being played (set/game counter) so
   the same break point is not recorded twice across polls.
2. ``resolve_entry`` — the game counter has moved on (the game resolved, one
   way or the other). We record the favourite's new price and the move.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

BANNER = """
############################################################
#  PAPER BOOK ONLY — NO REAL ORDERS ARE EVER SENT.         #
#  This program observes prices and writes a JSON file.    #
#  It has no exchange client and no order code at all.     #
############################################################
"""


@dataclass
class PaperEntry:
    time: str
    market: str  # market slug
    side: str  # favourite's outcome label
    price: float  # favourite's price when the break point was seen
    game_key: str  # "sets=0-1 games=4-3" — identifies the game in play
    resolved_time: str | None = None
    resolved_price: float | None = None
    move: float | None = None
    note: str = "PAPER — nothing was sent anywhere"


@dataclass
class PaperBook:
    path: Path
    entries: list[PaperEntry] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> PaperBook:
        path = Path(path)
        if not path.exists():
            return cls(path=path)
        raw = json.loads(path.read_text() or "[]")
        return cls(path=path, entries=[PaperEntry(**item) for item in raw])

    def save(self) -> None:
        self.path.write_text(
            json.dumps([asdict(e) for e in self.entries], indent=2) + "\n"
        )

    def open_for(self, market: str) -> PaperEntry | None:
        for entry in self.entries:
            if entry.market == market and entry.resolved_time is None:
                return entry
        return None

    def open_entry(
        self,
        market: str,
        side: str,
        price: float,
        game_key: str,
        now: datetime | None = None,
    ) -> PaperEntry | None:
        """Record a break-point sighting once per game; returns the new entry."""
        existing = self.open_for(market)
        if existing is not None:
            return None  # already watching this break point / game
        stamp = (now or datetime.now(timezone.utc)).isoformat()
        entry = PaperEntry(
            time=stamp, market=market, side=side, price=price, game_key=game_key
        )
        self.entries.append(entry)
        self.save()
        return entry

    def resolve_entry(
        self,
        market: str,
        game_key: str,
        price: float | None,
        now: datetime | None = None,
    ) -> PaperEntry | None:
        """When the game counter moved on, record the price move and close."""
        entry = self.open_for(market)
        if entry is None or entry.game_key == game_key or price is None:
            return None
        entry.resolved_time = (now or datetime.now(timezone.utc)).isoformat()
        entry.resolved_price = price
        entry.move = round(price - entry.price, 4)
        self.save()
        return entry
