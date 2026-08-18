# polymarket-tennis

> **Disclosure:** this toolkit is built and maintained by the team behind the
> [Live Tennis API](https://livetennisapi.com). It joins Polymarket's public
> market data with our live-score feed, so this is vendor-authored tooling —
> judge accordingly.

Tennis event markets on Polymarket, made first-class: **discover** them,
**match** them to real live matches, and **watch** market prices next to live
match state — score line, server, break-point flag — in one joined view.

**Observe-only by design.** This package reads public market data and live
scores. It contains no order execution, no wallet or key handling, and no
strategy advice; execution is out of scope, permanently.

```text
Cincinnati Open: Jiri Lehecka vs Arthur Fils  [atp-lehecka-fils-2026-08-17]
  market: Jiri Lehecka 0.095 | Arthur Fils 0.905  (as of 12s ago)
  live:   Jiri Lehecka vs Arthur Fils  4-6 3-4 (15-40)  serving: Jiri Lehecka  [BREAK POINT]  (as of 8s ago)
```

## What it does

- **`discovery`** — find current tennis markets via Polymarket's public
  [Gamma API](https://gamma-api.polymarket.com) (keyless): the `tennis` tag,
  per-match events (`atp-lehecka-fils-2026-08-17`), futures, doubles;
  normalized to plain Python objects (question, outcomes, prices, volume,
  end date).
- **`matching`** — pair a market with a Live Tennis API match/fixture using
  player-name + date heuristics with an explicit confidence score. Handles
  reversed name order ("Alcaraz vs Sinner" / "Sinner vs Alcaraz"), diacritics
  ("Báez" = "Baez"), shared surnames, and retirement/walkover wording. On
  ambiguity it returns `None` — it never guesses silently. An explicit
  match-id override is always available.
- **`join`** — `LiveMarketView`: one snapshot holding the market question and
  outcome prices next to the live score line, server, break-point flag, and
  set/game state, with staleness timestamps for **both** feeds.

## Install

```bash
pip install "polymarket-tennis @ git+https://github.com/livetennisapi/polymarket-tennis"
```

Python 3.10+. Single runtime dependency: `httpx`.

## Quickstart

```bash
# 1. list current tennis markets — keyless, Gamma only
pmtennis discover --matches-only --moneyline-only

# 2. get a free Live Tennis API key (https://livetennisapi.com/subscribe/free)
export LIVETENNIS_API_KEY=ltapi_...

# 3. inspect the matching decision for one market
pmtennis match atp-lehecka-fils-2026-08-17

# 4. watch market price vs live match state, one poll per minute
pmtennis watch atp-lehecka-fils-2026-08-17
```

As a library:

```python
from polymarket_tennis import (
    GammaClient, LiveTennisClient,
    discover_tennis_markets, match_market, build_view,
)

with GammaClient() as gamma, LiveTennisClient() as lta:
    markets = discover_tennis_markets(gamma, market_types={"moneyline"},
                                      matches_only=True)
    candidates = lta.live_matches() + lta.fixtures()
    for market in markets:
        decision = match_market(market, candidates)
        if decision is None:
            continue  # ambiguous or no live counterpart — never guessed
        view = build_view(market, decision.match)
        print(view.render())
```

## Free-tier budget math (honest numbers)

The Live Tennis API free tier allows **30 requests/minute and 100
requests/day** and includes live scores (score/server/state), players (with
each player's own current ranking), fixtures, and usage.

`pmtennis watch` spends **1 Live Tennis API request per poll** (the market
price comes from Gamma, which is keyless and doesn't touch your quota):

| cadence | requests/hour | free-key watching per day |
|---|---|---|
| 60 s (default) | 60 | ~100 minutes |
| 300 s | 12 | ~8 hours |

So the free tier comfortably covers developing, testing, and following a
handful of tracked matches at a gentle cadence — it is not sized for
continuous fast polling of many matches. Paid tiers add completed-match
history and point-by-point (Basic), match events, market prices and bulk
packages (Pro), and win probability and in-play stats (Ultra) — details at
[livetennisapi.com](https://livetennisapi.com).

**Note on price data:** all market prices in this toolkit come from
Polymarket's public Gamma API. The Live Tennis API's own market-prices and
win-probability fields are paid-tier features and are **not required** by
anything here.

## Matching semantics

- Confidence comes from folded full-name agreement (diacritics stripped,
  punctuation collapsed), tried in both orientations, gated by the market
  slug's date vs the match's scheduled date (±1 day; matches often start
  after midnight UTC).
- Two near-equal candidates → `None`. One player agreeing → `None`. A date
  disagreeing by more than a day → `None`.
- Doubles markets are rejected in v0.1 (team-name matching is a separate
  problem); use `--match-id`/`override_match_id` explicitly if you need one.
- Break-point flag: receiver at AD, or receiver at 40 while the server is at
  0/15/30; never in tiebreaks; `False` whenever server or points are null
  (completed matches carry null points).

## Tests

Fixture-driven, zero network: the Gamma fixtures are trimmed captures of real
Polymarket payloads (Cincinnati Open, August 2026); the Live Tennis API
fixtures are constructed to the published
[OpenAPI schema](https://github.com/livetennisapi/openapi). See
`tests/fixtures/README.md` for exact provenance.

```bash
pip install -e ".[dev]"
ruff check src tests && pytest
```

## License

MIT — see [LICENSE](LICENSE).
