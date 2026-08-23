# polymarket-tennis — public API reference (v0.1.0)

Transcribed from `src/polymarket_tennis/` at the time of writing. Only the symbols
listed here exist; if code you are writing needs something else, it is not in the
package and must be written by you (observe-only, see SKILL.md).

## Exports (`from polymarket_tennis import ...`)

```
GammaClient, LiveTennisClient, TennisMarket, MatchDecision, LiveMarketView,
discover_tennis_markets, find_market, extract_market_players, match_market,
build_view, derive_break_point, score_line, __version__
```

Also importable from submodules (not re-exported at top level):

- `polymarket_tennis.matching.fold_name(name) -> str` — diacritics stripped,
  punctuation collapsed, lower-cased; `MarketPlayers`, `score_candidates`,
  `MATCH_THRESHOLD = 0.70`, `AMBIGUITY_MARGIN = 0.10`
- `polymarket_tennis.discovery.iter_markets`, `is_tennis_event`, `is_match_event`,
  `is_doubles_event`, `TENNIS_TAG_SLUG = "tennis"`
- `polymarket_tennis.gamma.GAMMA_BASE_URL = "https://gamma-api.polymarket.com"`
- `polymarket_tennis.livetennis.LIVETENNIS_BASE_URL = "https://api.livetennisapi.com/api/public/v1"`,
  `API_KEY_ENV = "LIVETENNIS_API_KEY"`, `MissingAPIKeyError(RuntimeError)`
- `polymarket_tennis.models.parse_iso8601(value) -> datetime | None`
- `polymarket_tennis.cli.main(argv=None) -> int`, `build_parser()`, `MIN_INTERVAL = 30.0`

## `GammaClient` (Polymarket Gamma API, keyless)

```text
GammaClient(base_url=GAMMA_BASE_URL, client: httpx.Client | None = None, timeout=15.0)
```

Context manager (`with GammaClient() as gamma:`); `close()`.

| Method | Returns | Notes |
|---|---|---|
| `events(tag_slug="tennis", closed=False, active=True, limit=100, offset=0)` | `list[dict]` | raw Gamma event objects, each with embedded `markets` |
| `event_by_slug(slug)` | `dict \| None` | `/events?slug=` |
| `market_by_id(market_id)` | `dict \| None` | `/markets/{id}`; `None` on 404 |
| `market_by_slug(slug)` | `dict \| None` | `/markets?slug=` |
| `market(id_or_slug)` | `dict \| None` | dispatches on `isdigit()` |

Pass `client=httpx.Client(transport=httpx.MockTransport(handler))` for offline tests.

## `LiveTennisClient` (Live Tennis API; 1 request per call)

```text
LiveTennisClient(api_key=None, base_url=LIVETENNIS_BASE_URL, client=None, timeout=15.0)
```

Key resolution: `api_key` argument, else `os.environ["LIVETENNIS_API_KEY"]`; a
request without a key raises `MissingAPIKeyError`. Context manager; `close()`.

| Method | Returns | Free tier |
|---|---|---|
| `matches(status="live", tour=None, limit=50, offset=0)` | `list[dict]` | `live` / `upcoming` are free |
| `live_matches(tour=None)` | `list[dict]` | = `matches(status="live")` |
| `match(match_id: int)` | `dict \| None` | `None` on 404 |
| `fixtures(limit=50, offset=0)` | `list[dict]` | upcoming fixtures, earliest first |
| `players(search, limit=20)` | `list[dict]` | |

Budget: free tier = **30 requests/minute, 100 requests/day**. Count every call.

## `TennisMarket` (frozen dataclass, `models.py`)

Fields: `id: str`, `slug: str`, `question: str`, `outcomes: tuple[str, ...]`,
`prices: tuple[float | None, ...]`, `volume`, `liquidity`, `end_date: datetime | None`,
`game_start_time: datetime | None`, `market_type: str | None` (Gamma
`sportsMarketType`, e.g. `"moneyline"`), `line: float | None`, `active: bool`,
`closed: bool`, `updated_at: datetime | None`, `event_slug: str | None`,
`event_title: str | None`, `raw: dict` (the untouched Gamma market object).

- `TennisMarket.from_gamma(raw, event=None)` — classmethod; uses the embedded
  `events[0]` when `event` is omitted.
- `.price_by_outcome -> dict[str, float | None]`
- `.slug_date -> date | None` — the `YYYY-MM-DD` suffix of the event/market slug.
- **There is no `description` attribute.** Settlement text:
  `market.raw.get("description")`.

## Discovery (`discovery.py`)

```text
discover_tennis_markets(client: GammaClient, market_types: set[str] | None = None,
                        include_closed: bool = False, matches_only: bool = False,
                        limit: int = 100) -> list[TennisMarket]
find_market(client: GammaClient, id_or_slug: str) -> TennisMarket | None
iter_markets(events, market_types=None, include_closed=False) -> list[TennisMarket]
```

`matches_only=True` keeps per-match events (slug like `atp-lehecka-fils-2026-08-17`)
and drops futures/outrights. `market_types={"moneyline"}` keeps match-winner markets.

## Matching (`matching.py`)

```text
match_market(market: TennisMarket, candidates: list[dict],
             override_match_id: int | None = None,
             threshold: float = 0.70, ambiguity_margin: float = 0.10) -> MatchDecision | None
extract_market_players(market: TennisMarket) -> MarketPlayers | None
```

`MatchDecision` (dataclass): `match: dict`, `match_id: int | None`,
`confidence: float`, `method: str` (`"explicit" | "names+date" | "names"`),
`notes: list[str]`.

`MarketPlayers` (frozen): `p1`, `p2`, `match_date: date | None`, `is_doubles: bool`.

Returns `None` (never a guess) when: names cannot be parsed (e.g. Yes/No futures),
the market is doubles (v0.1, unless overridden), no candidate clears `threshold`,
or the top two candidates are within `ambiguity_margin`. Date gate: market slug
date vs candidate `scheduled_time` date, ±1 day.

## Join (`join.py`)

```text
build_view(market: TennisMarket, match: dict,
           market_fetched_at: datetime | None = None,
           live_fetched_at: datetime | None = None) -> LiveMarketView
derive_break_point(score: dict | None) -> bool
score_line(score: dict | None) -> str      # "6-4 3-2 (40-15)"
```

`LiveMarketView` (dataclass) fields: `market: TennisMarket`, `match: dict`,
`match_id: int | None`, `player1: str`, `player2: str`, `match_status: str | None`
(lifecycle `status`), `event_status: str | None`, `score_line: str`,
`sets: tuple[int, ...]`, `server: int | None` (1 or 2), `is_tiebreak: bool`,
`break_point: bool`, `prices: dict[str, float | None]`, `market_as_of`,
`live_as_of`, `market_fetched_at`, `live_fetched_at`.

Methods: `market_staleness(now=None) -> float | None` (seconds),
`live_staleness(now=None) -> float | None`, `render(now=None) -> str`.

**`LiveMarketView` does not expose `outcome` or `withdrew`** — read
`view.match.get("outcome")`, `view.match.get("withdrew")`.

Break-point rule (`derive_break_point`): receiver at `AD`, or receiver at `40`
while server is at `0/15/30`; never in tiebreaks; `False` whenever `server` or
either point is `null` (completed matches carry null points).

## CLI (`pmtennis`)

```
pmtennis discover [--matches-only] [--moneyline-only] [--limit N]
pmtennis match <market-id-or-slug> [--match-id N]
pmtennis watch <market-id-or-slug> [--interval S] [--match-id N] [--count N]
```

`watch`: interval floor 30 s (`MIN_INTERVAL`), default 60 s; 1 Live Tennis API
request per poll (`lta.match(id)`), re-fetches the Gamma market each poll
(keyless); stops when lifecycle `status == "completed"`. Exit code 1 when the
market cannot be paired confidently — run `pmtennis match` and pass `--match-id`.

## Live Tennis API match object (shape used by this package)

```json
{
  "id": 90211, "tournament": "Cincinnati Open", "tour": "atp",
  "round": "Round of 16", "status": "live", "event_status": null,
  "is_doubles": false, "scheduled_time": "2026-08-18T01:15:00Z",
  "players": {"p1": {"id": 50101, "name": "Jiri Lehecka", "ranking": 21},
              "p2": {"id": 50102, "name": "Arthur Fils", "ranking": 15}},
  "score": {"sets": [0, 1], "games": [[4, 3], [6, 4]], "points": ["15", "40"],
            "server": 1, "is_tiebreak": false, "timestamp": "2026-08-18T02:31:04Z"},
  "winner": null, "withdrew": null
}
```

Settlement-relevant fields next to the lifecycle `status`:

- `outcome`: `completed | retired | walkover | default | abandoned`, `null` until settled
- `event_status`: `Retired`, `Walk Over`, `Cancelled`, `Postponed`, `Interrupted`, …
- `withdrew`: which player stopped or conceded

The package's offline fixtures carry `event_status` (`"Retired"`) but no
`outcome` key; code should read `outcome` first and fall back to `event_status`.
