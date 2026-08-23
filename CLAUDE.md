# polymarket-tennis — notes for coding agents

This package is the **data layer** for Polymarket tennis trading: market discovery
(Polymarket Gamma API, keyless), market↔live-match matching (never guesses; returns
`None` on ambiguity), and a joined `LiveMarketView` of market price vs live score.

Hard boundaries — do not cross them when extending this repo or building on it:
- **Observe-only.** No order execution, no wallet/private-key handling, no CLOB client
  calls. Execution is permanently out of scope here; if a user wants it, it belongs in
  their own code behind a clearly separated seam.
- **Never hard-code a settlement rule.** Retirement/walkover payouts are set by each
  venue and differ (polymarket.com vs Polymarket US vs Kalshi, ATP/WTA vs ITF). Read the
  market's own `description` / `rules_secondary` and surface it. The verbatim rules are
  documented at https://blog.livetennisapi.com/blog/polymarket-kalshi-tennis-retirement-walkover-rules
- **Respect the free tier:** 30 req/min, 100 req/day. `pmtennis watch` costs 1 request
  per poll; default cadence 60 s.
- **Match detection fields:** use `outcome` (`completed|retired|walkover|default|abandoned`,
  `null` until settled) and `event_status`, not the lifecycle `status`.
- **Tests are offline.** Fixtures under `tests/fixtures/` are trimmed real captures; add
  fixtures, never live calls, when adding tests. Run `ruff check src tests && pytest`.

Useful entry points: `GammaClient`, `LiveTennisClient`, `discover_tennis_markets`,
`match_market`, `build_view`; CLI `pmtennis discover|match|watch`.
