# Contributing to polymarket-tennis

This package is the data layer for Polymarket tennis markets. It finds markets
through the Polymarket Gamma API, which needs no key. It matches each market to
a live match and joins the two into a `LiveMarketView` of price against score.

## Ground rules

Changes that cross these lines will not be merged.

- **Observe-only.** No order execution, no wallets, no private keys and no
  CLOB client calls. Execution stays out of this repo. If you want it, build it
  in your own code behind a clearly separated seam.
- **Matching never guesses.** When the market names cannot be parsed, or the
  best candidates score too close to call, `match_market` returns `None`. Keep
  it that way.
- **Never hard-code a settlement rule.** Each venue sets its own retirement and
  walkover payouts. They differ between polymarket.com, Polymarket US and
  Kalshi, and between ATP/WTA and ITF. Read the market's own `description` /
  `rules_secondary` and surface it. The verbatim venue rules are collected at
  <https://blog.livetennisapi.com/blog/polymarket-kalshi-tennis-retirement-walkover-rules>.
- **Respect the free tier.** The Live Tennis API free tier allows 30 requests a
  minute and 100 requests/day. `pmtennis watch` costs one request per poll and
  defaults to a 60 s cadence. Quotas are documented at
  <https://docs.livetennisapi.com>.
- **Detect match state from the right fields.** Use `outcome`
  (`completed|retired|walkover|default|abandoned`, `null` until settled) and
  `event_status`. Do not use the lifecycle `status`.
- **The arena is paper-only.** Strategies in `src/polymarket_tennis/arena/` get
  a `LiveMarketView` and a `PaperBook`, nothing else. Real tapes are organiser
  data and are never committed or redistributed. The one committed tape is
  synthetic. See [docs/ARENA.md](docs/ARENA.md) and [tape/README.md](tape/README.md).

## Tests

Tests are offline. Add fixtures under `tests/fixtures/`, never live calls.
`tests/fixtures/README.md` records where each fixture came from.

```bash
pip install -e ".[dev]"
ruff check src tests && pytest
```

CI runs the same two commands on Python 3.10 and 3.12.

## Where to start reading

`GammaClient`, `LiveTennisClient`, `discover_tennis_markets`, `match_market` and
`build_view` are the main entry points. The CLI is `pmtennis` with the
subcommands `discover`, `match`, `watch` and `arena`.
