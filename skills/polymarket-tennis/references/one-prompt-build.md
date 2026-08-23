# One-prompt build: observe-only Polymarket tennis watcher

This is the exact prompt from the package README. What it produced, unedited
except for lint, is checked in at `examples/claude-code-watcher/` in
https://github.com/livetennisapi/polymarket-tennis — 7 offline tests, `ruff` clean,
and a `--once --fixtures tests/fixtures` dry run that needs no key. The write-up is
https://blog.livetennisapi.com/blog/build-polymarket-tennis-trading-bot.

## The prompt

```text
Build me a Python tennis market watcher on top of the `polymarket-tennis`
package (pip install polymarket-tennis; docs: https://github.com/livetennisapi/polymarket-tennis).
Requirements:
1. Use GammaClient + discover_tennis_markets(market_types={"moneyline"}, matches_only=True)
   to list open Polymarket tennis markets, and LiveTennisClient (key from the env var
   LIVETENNIS_API_KEY; free key at https://livetennisapi.com/subscribe/free) to fetch
   lta.live_matches() + lta.fixtures().
2. For each market call match_market(market, candidates); skip None (never guess).
3. Build view = build_view(market, decision.match) and, once per minute (free tier:
   30 req/min, 100 req/day — stay under it), log: market question, both outcome prices,
   the live score line, who is serving, the break-point flag, and both staleness ages.
4. Keep a local JSON "paper book": when the favourite is facing a break point, record a
   PAPER entry {time, market, side, price}; when the game resolves, record the price
   move. Paper only — print a loud banner that no real orders are ever sent.
5. If the match's `outcome` becomes "retired" or "walkover" print the venue's own
   settlement text from the market `description` (do NOT hard-code a payout rule).
6. Add a README, a requirements.txt, and tests that run offline with fixtures.
Observe-only. No wallets, no keys other than the tennis API key, no order code.
```

## Known deviations the verified build had to make (read before re-running)

Copied from `examples/claude-code-watcher/README.md`:

- **`match.outcome` is not in the offline fixtures.** The package's fixtures
  (constructed to the OpenAPI schema) carry `event_status` (e.g. `"Retired"`) but
  no `outcome` key, and `LiveMarketView` does not expose `outcome`. The watcher reads
  `view.match["outcome"]` first and falls back to `event_status` lower-cased; tests
  cover both.
- **`TennisMarket` has no `description` attribute.** The settlement text is read
  from `view.market.raw["description"]` (falling back to `rules_secondary`). The
  package's trimmed Gamma capture has no description field at all, so the copy under
  `tests/fixtures/` adds a clearly labelled stand-in string
  (`[FIXTURE TEXT, not Polymarket's wording]`) — it is NOT Polymarket's rule text.
- **"Favourite facing a break point"** is interpreted as: the favourite is the
  *server* while `break_point` is True. The server is mapped to an outcome label by
  folded-name equality (`polymarket_tennis.matching.fold_name`); if the names do not
  line up, no entry is recorded.
- **Two requests per poll, not one.** The prompt asks for `live_matches() +
  fixtures()` every minute; that is 120 req/hour, more than the free tier's 100/day,
  so the watcher caps itself at 96 requests per process (`--daily-budget`) and
  documents `--interval 300` (about 4 hours of watching).

## Skeleton the verified build settled on

```python
from polymarket_tennis import (
    GammaClient, LiveTennisClient, LiveMarketView,
    build_view, discover_tennis_markets, match_market,
)

BANNER = "PAPER ONLY — no real orders are ever sent by this program."

def match_outcome(match: dict) -> str | None:
    outcome = match.get("outcome")
    if outcome:
        return str(outcome).lower()
    status = match.get("event_status")
    return str(status).lower() if status else None

def settlement_text(view: LiveMarketView) -> str:
    raw = view.market.raw
    text = raw.get("description") or raw.get("rules_secondary")
    return text or "(no settlement text in market payload)"

def poll(gamma: GammaClient, lta: LiveTennisClient) -> int:
    """One poll; returns the number of Live Tennis API requests spent."""
    markets = discover_tennis_markets(gamma, market_types={"moneyline"}, matches_only=True)
    candidates = lta.live_matches() + lta.fixtures()   # 2 requests
    for market in markets:
        decision = match_market(market, candidates)
        if decision is None:
            continue
        view = build_view(market, decision.match)
        print(view.render())
        if match_outcome(view.match) in ("retired", "walkover", "default", "abandoned"):
            print("venue settlement text:", settlement_text(view))
    return 2
```

Offline tests: build `GammaClient(client=httpx.Client(transport=httpx.MockTransport(h)))`
and the same for `LiveTennisClient(api_key="test", client=...)`, serving the JSON
files under `tests/fixtures/`.
