"""Thin client for Polymarket's public Gamma API (keyless, read-only).

Only public GET endpoints are used: ``/events`` and ``/markets``. This module
never touches order books, wallets, or the CLOB — the toolkit is observe-only.
"""

from __future__ import annotations

from typing import Any

import httpx

__all__ = ["GammaClient", "GAMMA_BASE_URL"]

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
_USER_AGENT = "polymarket-tennis/0.1 (+https://github.com/livetennisapi/polymarket-tennis)"


class GammaClient:
    """Read-only access to Gamma ``/events`` and ``/markets``.

    Pass ``client`` to inject a preconfigured ``httpx.Client`` (tests use
    ``httpx.MockTransport`` this way). The instance can be used as a context
    manager; it closes the underlying client only if it created it.
    """

    def __init__(
        self,
        base_url: str = GAMMA_BASE_URL,
        client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=timeout, headers={"User-Agent": _USER_AGENT}
        )
        self._base_url = base_url.rstrip("/")

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> GammaClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- raw fetches -------------------------------------------------------
    def _get(self, path: str, params: dict[str, Any]) -> Any:
        response = self._client.get(self._base_url + path, params=params)
        response.raise_for_status()
        return response.json()

    def events(
        self,
        tag_slug: str = "tennis",
        closed: bool | None = False,
        active: bool | None = True,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List events carrying a tag (default: Polymarket's ``tennis`` tag)."""
        params: dict[str, Any] = {
            "tag_slug": tag_slug,
            "limit": limit,
            "offset": offset,
        }
        if closed is not None:
            params["closed"] = str(closed).lower()
        if active is not None:
            params["active"] = str(active).lower()
        data = self._get("/events", params)
        return data if isinstance(data, list) else []

    def event_by_slug(self, slug: str) -> dict[str, Any] | None:
        data = self._get("/events", {"slug": slug})
        if isinstance(data, list) and data:
            return data[0]
        return None

    def market_by_id(self, market_id: str) -> dict[str, Any] | None:
        try:
            data = self._get(f"/markets/{market_id}", {})
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise
        return data if isinstance(data, dict) else None

    def market_by_slug(self, slug: str) -> dict[str, Any] | None:
        data = self._get("/markets", {"slug": slug})
        if isinstance(data, list) and data:
            return data[0]
        return None

    def market(self, id_or_slug: str) -> dict[str, Any] | None:
        """Look up a market by numeric id or by slug."""
        if id_or_slug.isdigit():
            return self.market_by_id(id_or_slug)
        return self.market_by_slug(id_or_slug)
