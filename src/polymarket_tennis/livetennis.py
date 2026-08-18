"""Thin client for the Live Tennis API's free-tier endpoints.

Disclosure: this project is maintained by the Live Tennis API team. Everything
this client calls by default (``/matches?status=live``, ``/matches/{id}``,
``/fixtures``, ``/players``) is available on the free keyed tier
(30 requests/minute, 100 requests/day). The API also serves its own
market-prices and win-probability fields on paid tiers, but this toolkit does
NOT need them: market prices come from Polymarket's public Gamma API.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

__all__ = ["LiveTennisClient", "LIVETENNIS_BASE_URL", "MissingAPIKeyError"]

LIVETENNIS_BASE_URL = "https://api.livetennisapi.com/api/public/v1"
API_KEY_ENV = "LIVETENNIS_API_KEY"
_USER_AGENT = "polymarket-tennis/0.1 (+https://github.com/livetennisapi/polymarket-tennis)"


class MissingAPIKeyError(RuntimeError):
    """Raised when no API key is configured."""

    def __init__(self) -> None:
        super().__init__(
            f"No Live Tennis API key found. Set the {API_KEY_ENV} environment "
            "variable. Free keys: https://livetennisapi.com/subscribe/free"
        )


class LiveTennisClient:
    """Free-tier live-state access: live matches, fixtures, players.

    Pass ``client`` to inject a preconfigured ``httpx.Client`` (tests use
    ``httpx.MockTransport`` this way).
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = LIVETENNIS_BASE_URL,
        client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._api_key = api_key or os.environ.get(API_KEY_ENV) or ""
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout, headers={"User-Agent": _USER_AGENT}
        )
        self._base_url = base_url.rstrip("/")

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> LiveTennisClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- raw fetches -------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self._api_key:
            raise MissingAPIKeyError()
        response = self._client.get(
            self._base_url + path,
            params=params or {},
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        if response.status_code == 429:
            raise RuntimeError(
                "Live Tennis API rate limit hit (free tier: 30 req/min, "
                "100 req/day). Slow the polling cadence."
            )
        response.raise_for_status()
        return response.json()

    def matches(
        self,
        status: str = "live",
        tour: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List matches by lifecycle status (``live``/``upcoming`` are free)."""
        params: dict[str, Any] = {"status": status, "limit": limit, "offset": offset}
        if tour:
            params["tour"] = tour
        data = self._get("/matches", params)
        return data.get("data", []) if isinstance(data, dict) else []

    def live_matches(self, tour: str | None = None) -> list[dict[str, Any]]:
        return self.matches(status="live", tour=tour)

    def match(self, match_id: int) -> dict[str, Any] | None:
        try:
            data = self._get(f"/matches/{match_id}")
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        if isinstance(data, dict):
            return data.get("data", data)
        return None

    def fixtures(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Upcoming scheduled fixtures, earliest first (free tier)."""
        data = self._get("/fixtures", {"limit": limit, "offset": offset})
        return data.get("data", []) if isinstance(data, dict) else []

    def players(self, search: str, limit: int = 20) -> list[dict[str, Any]]:
        data = self._get("/players", {"search": search, "limit": limit})
        return data.get("data", []) if isinstance(data, dict) else []
