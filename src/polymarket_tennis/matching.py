"""Match a Polymarket tennis market to a Live Tennis API match or fixture.

The matcher is deliberately conservative: it uses player-name + date
heuristics with an explicit confidence score, and returns ``None`` instead of
guessing when the evidence is ambiguous. An explicit match-id override is
always available for the cases heuristics cannot settle.

Doubles markets are rejected in v0.1 (team-name matching is a different
problem); pass an explicit override if you need one.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .models import TennisMarket, parse_iso8601

__all__ = [
    "MarketPlayers",
    "MatchDecision",
    "fold_name",
    "extract_market_players",
    "score_candidates",
    "match_market",
]

# confidence bookkeeping
MATCH_THRESHOLD = 0.70
AMBIGUITY_MARGIN = 0.10

_RETIREMENT_RE = re.compile(
    r"\s*[\(\[]?\b(retired|walk[\s-]?over|walkover|ret\.?|w/o|withdrew)\b\.?[\)\]]?\s*$",
    re.IGNORECASE,
)


def _strip_status_wording(name: str) -> str:
    """Drop retirement/walkover suffixes ("Paul (Retired)", "Vallejo w/o")."""
    previous = None
    while previous != name:
        previous = name
        name = _RETIREMENT_RE.sub("", name).strip()
    return name


def fold_name(name: str) -> str:
    """Lowercase, strip diacritics, collapse punctuation to spaces."""
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in decomposed if not unicodedata.combining(c))
    ascii_only = ascii_only.lower()
    ascii_only = re.sub(r"[-'.]", " ", ascii_only)
    return " ".join(ascii_only.split())


def _name_similarity(market_name: str, api_name: str) -> float:
    """Similarity between one market-side name and one API-side name."""
    a = fold_name(_strip_status_wording(market_name))
    b = fold_name(_strip_status_wording(api_name))
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ta, tb = a.split(), b.split()
    # one name is a token-subset of the other ("J. Lehecka" vs "Jiri Lehecka",
    # or a market that shows only "Davidovich Fokina")
    if set(ta) <= set(tb) or set(tb) <= set(ta):
        return 0.9
    # surname-only agreement (last token, the market's usual short form)
    if ta[-1] == tb[-1]:
        return 0.75
    return 0.0


@dataclass(frozen=True)
class MarketPlayers:
    """The two sides named by a market, plus its scheduling hints."""

    p1: str
    p2: str
    match_date: date | None
    is_doubles: bool


@dataclass
class MatchDecision:
    """A confident (or explicitly forced) market-to-match pairing."""

    match: dict[str, Any]
    match_id: int | None
    confidence: float
    method: str  # "explicit" | "names+date" | "names"
    notes: list[str] = field(default_factory=list)


def extract_market_players(market: TennisMarket) -> MarketPlayers | None:
    """Pull the two player names out of a market.

    Prefers the moneyline outcome labels (full player names on Polymarket);
    falls back to the event title's "Tournament: A vs B" form. Returns ``None``
    when no two sides can be identified (e.g. Yes/No futures markets).
    """
    is_doubles = False
    slug_blob = f"{market.event_slug or ''} {market.slug or ''}".lower()
    title_blob = (market.event_title or "").lower()
    if "-doubles-" in slug_blob or "(doubles)" in title_blob:
        is_doubles = True

    names: tuple[str, str] | None = None
    if (
        market.market_type == "moneyline"
        and len(market.outcomes) == 2
        and {o.strip().lower() for o in market.outcomes} != {"yes", "no"}
    ):
        names = (market.outcomes[0], market.outcomes[1])
    if names is None:
        title = market.event_title or market.question or ""
        title = title.split(":", 1)[-1]
        parts = re.split(r"\s+vs\.?\s+", title, flags=re.IGNORECASE)
        if len(parts) == 2:
            names = (parts[0].strip(), parts[1].strip())
    if names is None:
        return None
    if "/" in names[0] or "/" in names[1]:
        is_doubles = True

    match_date = market.slug_date
    if match_date is None and market.game_start_time is not None:
        match_date = market.game_start_time.date()
    return MarketPlayers(
        p1=_strip_status_wording(names[0]),
        p2=_strip_status_wording(names[1]),
        match_date=match_date,
        is_doubles=is_doubles,
    )


def _candidate_names(candidate: dict[str, Any]) -> tuple[str, str] | None:
    """Names from either a Match object or a Fixture object."""
    players = candidate.get("players")
    if isinstance(players, dict):
        p1 = (players.get("p1") or {}).get("name")
        p2 = (players.get("p2") or {}).get("name")
        if p1 and p2:
            return str(p1), str(p2)
    p1 = candidate.get("player1_name")
    p2 = candidate.get("player2_name")
    if p1 and p2:
        return str(p1), str(p2)
    return None


def _candidate_date(candidate: dict[str, Any]) -> date | None:
    for key in ("scheduled_time", "start_time"):
        parsed = parse_iso8601(candidate.get(key))
        if parsed is not None:
            return parsed.date()
    raw = candidate.get("event_date")
    if raw:
        try:
            return date.fromisoformat(str(raw)[:10])
        except ValueError:
            return None
    return None


def _candidate_is_doubles(candidate: dict[str, Any]) -> bool:
    if candidate.get("is_doubles"):
        return True
    if candidate.get("draw") == "doubles":
        return True
    names = _candidate_names(candidate)
    return bool(names and ("/" in names[0] or "/" in names[1]))


def _pair_score(
    players: MarketPlayers, candidate: dict[str, Any]
) -> tuple[float, list[str]]:
    names = _candidate_names(candidate)
    if names is None:
        return 0.0, ["candidate has no player names"]
    notes: list[str] = []
    direct = min(
        _name_similarity(players.p1, names[0]),
        _name_similarity(players.p2, names[1]),
    )
    reversed_ = min(
        _name_similarity(players.p1, names[1]),
        _name_similarity(players.p2, names[0]),
    )
    score = max(direct, reversed_)
    if score == 0.0:
        return 0.0, ["player names do not agree"]
    if reversed_ > direct:
        notes.append("name order reversed between market and feed")

    candidate_date = _candidate_date(candidate)
    if players.match_date is not None and candidate_date is not None:
        delta = abs((candidate_date - players.match_date).days)
        if delta <= 1:
            score = min(1.0, score + 0.05)
            notes.append(f"date agrees (±{delta}d)")
        else:
            notes.append(f"date disagrees by {delta}d")
            return 0.0, notes
    else:
        notes.append("date unknown on one side; names only")
    return score, notes


def score_candidates(
    market: TennisMarket, candidates: list[dict[str, Any]]
) -> list[tuple[dict[str, Any], float, list[str]]]:
    """Score every candidate; sorted best-first. Empty when market unparsable."""
    players = extract_market_players(market)
    if players is None:
        return []
    scored = []
    for candidate in candidates:
        if players.is_doubles != _candidate_is_doubles(candidate):
            continue
        score, notes = _pair_score(players, candidate)
        if score > 0:
            scored.append((candidate, score, notes))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def match_market(
    market: TennisMarket,
    candidates: list[dict[str, Any]],
    override_match_id: int | None = None,
    threshold: float = MATCH_THRESHOLD,
    ambiguity_margin: float = AMBIGUITY_MARGIN,
) -> MatchDecision | None:
    """Pick the Live Tennis API match/fixture for a market, or ``None``.

    Returns ``None`` (never a guess) when: the market names cannot be parsed,
    the market is a doubles market (unsupported in v0.1 without an override),
    no candidate clears ``threshold``, or two candidates are within
    ``ambiguity_margin`` of each other at the top.
    """
    if override_match_id is not None:
        for candidate in candidates:
            if candidate.get("id") == override_match_id:
                return MatchDecision(
                    match=candidate,
                    match_id=override_match_id,
                    confidence=1.0,
                    method="explicit",
                    notes=["explicit match-id override"],
                )
        # an explicit instruction is honored even when the id is not in the
        # candidate set (e.g. a completed match no longer listed as live);
        # the note keeps that visible
        return MatchDecision(
            match={"id": override_match_id},
            match_id=override_match_id,
            confidence=1.0,
            method="explicit",
            notes=["explicit match-id override (id not in candidate set)"],
        )

    players = extract_market_players(market)
    if players is None:
        return None
    if players.is_doubles:
        return None

    scored = score_candidates(market, candidates)
    if not scored:
        return None
    best, best_score, best_notes = scored[0]
    if best_score < threshold:
        return None
    if len(scored) > 1 and (best_score - scored[1][1]) < ambiguity_margin:
        return None
    method = (
        "names+date"
        if any(note.startswith("date agrees") for note in best_notes)
        else "names"
    )
    return MatchDecision(
        match=best,
        match_id=best.get("id"),
        confidence=round(best_score, 3),
        method=method,
        notes=best_notes,
    )
