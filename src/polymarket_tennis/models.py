"""Typed views over the two data sources.

``TennisMarket`` normalizes a raw Polymarket Gamma market object (whose
``outcomes``/``outcomePrices`` arrive as JSON-encoded strings) into plain
Python types. The raw payload is always kept on ``.raw`` so nothing is lost.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

__all__ = ["TennisMarket", "parse_iso8601"]


def parse_iso8601(value: str | None) -> datetime | None:
    """Parse the timestamp formats Gamma and the Live Tennis API emit.

    Handles ``Z`` suffixes, space-separated ``YYYY-MM-DD HH:MM:SS+00`` (seen on
    Gamma's ``gameStartTime``), and fractional seconds. Returns ``None`` for
    ``None``/empty/unparseable input rather than raising: timestamps are
    advisory metadata here, never control flow.
    """
    if not value:
        return None
    text = value.strip().replace(" ", "T", 1)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    # "+00" (no minutes) is not accepted by fromisoformat on all versions
    if len(text) >= 3 and text[-3] in "+-" and text[-2:].isdigit():
        text += ":00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_json_list(value: Any) -> list[Any]:
    """Gamma encodes list fields as JSON strings; accept either form."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


@dataclass(frozen=True)
class TennisMarket:
    """A normalized Polymarket tennis market."""

    id: str
    slug: str
    question: str
    outcomes: tuple[str, ...]
    prices: tuple[float | None, ...]
    volume: float | None
    liquidity: float | None
    end_date: datetime | None
    game_start_time: datetime | None
    market_type: str | None  # Gamma's sportsMarketType, e.g. "moneyline"
    line: float | None
    active: bool
    closed: bool
    updated_at: datetime | None
    event_slug: str | None
    event_title: str | None
    raw: dict[str, Any] = field(repr=False, default_factory=dict, compare=False)

    @classmethod
    def from_gamma(
        cls,
        raw: dict[str, Any],
        event: dict[str, Any] | None = None,
    ) -> TennisMarket:
        """Build from a raw Gamma market object, optionally with its event.

        When ``event`` is not given, the market's own embedded ``events`` list
        (present on ``/markets`` responses) is used if available.
        """
        if event is None:
            embedded = raw.get("events")
            if isinstance(embedded, list) and embedded:
                event = embedded[0]
        outcomes = tuple(str(o) for o in _parse_json_list(raw.get("outcomes")))
        prices: list[float | None] = []
        for p in _parse_json_list(raw.get("outcomePrices")):
            try:
                prices.append(float(p))
            except (TypeError, ValueError):
                prices.append(None)
        # pad so zip(outcomes, prices) never drops an outcome
        while len(prices) < len(outcomes):
            prices.append(None)

        def _num(key: str) -> float | None:
            v = raw.get(key)
            if v is None:
                return None
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        return cls(
            id=str(raw.get("id", "")),
            slug=str(raw.get("slug", "")),
            question=str(raw.get("question", "")),
            outcomes=outcomes,
            prices=tuple(prices),
            volume=_num("volumeNum") if "volumeNum" in raw else _num("volume"),
            liquidity=(
                _num("liquidityNum") if "liquidityNum" in raw else _num("liquidity")
            ),
            end_date=parse_iso8601(raw.get("endDate")),
            game_start_time=parse_iso8601(raw.get("gameStartTime")),
            market_type=raw.get("sportsMarketType"),
            line=_num("line"),
            active=bool(raw.get("active", False)),
            closed=bool(raw.get("closed", False)),
            updated_at=parse_iso8601(raw.get("updatedAt")),
            event_slug=(event or {}).get("slug"),
            event_title=(event or {}).get("title"),
            raw=raw,
        )

    @property
    def price_by_outcome(self) -> dict[str, float | None]:
        return dict(zip(self.outcomes, self.prices, strict=False))

    @property
    def slug_date(self) -> date | None:
        """The YYYY-MM-DD suffix Polymarket puts on per-match market slugs."""
        for candidate in (self.event_slug, self.slug):
            if not candidate:
                continue
            parts = candidate.split("-")
            if len(parts) >= 3:
                tail = "-".join(parts[-3:])
                try:
                    return date.fromisoformat(tail)
                except ValueError:
                    continue
        return None
