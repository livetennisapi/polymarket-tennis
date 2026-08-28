"""Live-score provider interface for the matching and view pipeline.

The market -> match pipeline needs only a small slice of live-score access:
list the live matches, list upcoming/fixture candidates, and fetch one match by
id. ``LiveScoreProvider`` captures exactly that slice, so the matching and view
logic depends on the interface rather than on the concrete
:class:`~polymarket_tennis.livetennis.LiveTennisClient`.

Why this exists (see issues #1 and #2): the matcher (``matching.py``) and the
joined view (``join.py``) already operate on plain dicts, never on the client;
this protocol makes that boundary explicit at the orchestration layer too. The
practical payoffs are a swappable live-score source and offline tests that need
no network and no key.

``LiveTennisClient`` is the default implementation and satisfies this protocol
structurally — nothing about it changes. To plug in a different source, provide
an object with the four methods below returning dicts in the Live Tennis API
shape the pipeline already consumes (``players.p1.name``/``players.p2.name``,
``score``, ``status``, ``id``, ...); ``tests/fixtures`` are concrete examples,
and :class:`StaticLiveScoreProvider` is a worked, network-free implementation.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

__all__ = ["LiveScoreProvider", "StaticLiveScoreProvider"]


@runtime_checkable
class LiveScoreProvider(Protocol):
    """The live-score surface the ``pmtennis`` pipeline depends on.

    Implement these four methods to feed the matcher and view from a source
    other than the Live Tennis API. Each returns plain dicts (or ``None`` for a
    missing single match) — never provider-specific objects — so the matching
    and view code stays unchanged.
    """

    def live_matches(self, tour: str | None = None) -> list[dict[str, Any]]:
        """Matches currently in play, optionally filtered to one tour."""
        ...

    def matches(
        self,
        status: str = "live",
        tour: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Matches by lifecycle status (the pipeline asks for ``upcoming``)."""
        ...

    def fixtures(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Scheduled fixtures used as additional match candidates."""
        ...

    def match(self, match_id: int) -> dict[str, Any] | None:
        """One match by id, or ``None`` if the source no longer lists it."""
        ...


class StaticLiveScoreProvider:
    """An in-memory :class:`LiveScoreProvider` backed by preloaded lists.

    A worked example of implementing the protocol with no network access, and
    the provider the offline tests use. It serves the lists it is handed and
    resolves :meth:`match` by scanning them for a matching ``id``.
    """

    def __init__(
        self,
        live: list[dict[str, Any]] | None = None,
        upcoming: list[dict[str, Any]] | None = None,
        fixtures: list[dict[str, Any]] | None = None,
    ) -> None:
        self._live = list(live or [])
        self._upcoming = list(upcoming or [])
        self._fixtures = list(fixtures or [])

    def live_matches(self, tour: str | None = None) -> list[dict[str, Any]]:
        return [m for m in self._live if tour is None or m.get("tour") == tour]

    def matches(
        self,
        status: str = "live",
        tour: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        pool = {"live": self._live, "upcoming": self._upcoming}.get(status, [])
        if tour is not None:
            pool = [m for m in pool if m.get("tour") == tour]
        return pool[offset : offset + limit]

    def fixtures(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        return self._fixtures[offset : offset + limit]

    def match(self, match_id: int) -> dict[str, Any] | None:
        for pool in (self._live, self._upcoming, self._fixtures):
            for candidate in pool:
                if candidate.get("id") == match_id:
                    return candidate
        return None
