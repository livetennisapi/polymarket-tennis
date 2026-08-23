---
name: polymarket-tennis
description: Build observe-only Polymarket and Kalshi tennis market tooling on the polymarket-tennis Python package (MIT) plus the Live Tennis API free tier. Use when asked for a Polymarket tennis bot or market watcher, a Kalshi tennis trading bot, tennis prediction-market data, Gamma API tennis markets, matching a market to a live match, break-point or serving state next to market prices, or how a tennis retirement, walkover, or cancelled match settles (venue rule text, never hard-coded). Covers the real package API (GammaClient, LiveTennisClient, discover_tennis_markets, match_market, build_view, pmtennis CLI), the free-tier request budget (30/min, 100/day), the outcome and event_status fields, and the verbatim 2026 settlement matrix. No order execution, wallets, or strategy advice.
license: MIT
compatibility: Python 3.10+, pip install polymarket-tennis (single runtime dependency httpx). Live match data needs a free Live Tennis API key in LIVETENNIS_API_KEY; Polymarket Gamma and Kalshi market reads are keyless.
metadata:
  author: Live Tennis API (hello@livetennisapi.com)
  version: "0.1.0"
  homepage: https://github.com/livetennisapi/polymarket-tennis
  attribution: Vendor-authored. The live-score side of every join comes from the Live Tennis API; judge accordingly.
---

# Polymarket / Kalshi tennis trading data

> **Vendor-authored, observe-only.** This skill is maintained by the team behind the
> [Live Tennis API](https://livetennisapi.com). It teaches the `polymarket-tennis`
> package, which reads public market data and live scores. It contains no order
> execution, no wallet or private-key handling, no CLOB client, and no strategy
> advice. Execution is permanently out of scope. Nothing here is financial advice.

## Hard guardrails (apply to every file you write with this skill)

1. **Observe-only.** Never add order placement, wallet, private-key, or CLOB code to
   anything built on this package. If the user wants execution, it belongs in their
   own code behind a clearly separated seam, using the venue's own official
   interfaces, and this skill does not write it.
2. **Never hard-code a settlement rule.** Retirement and walkover payouts differ by
   venue (polymarket.com vs Polymarket US vs Kalshi) and by tour (ATP/WTA vs ITF).
   Read the market's own text — Gamma `description` (`market.raw["description"]`),
   Kalshi `rules_secondary` — and print it. The reference matrix in
   [references/settlement-rules.md](references/settlement-rules.md) is for the
   human, not for code branches.
3. **Respect the free tier: 30 requests/minute, 100 requests/day.** Every
   `LiveTennisClient` call costs one request; Gamma and Kalshi reads cost nothing.
   `pmtennis watch` is 1 request per poll at a 60 s default (minimum 30 s). A
   watcher that calls `live_matches()` + `fixtures()` per poll costs 2 per poll
   and must self-cap (the reference build caps at 96/day, `--interval 300`).
4. **Detect match endings with `outcome` and `event_status`, not `status`.**
   `status` is only the lifecycle (`upcoming|live|completed|cancelled`).
   `outcome` is `completed|retired|walkover|default|abandoned` and `null` until
   settled; `event_status` is the feed designator (`Retired`, `Walk Over`,
   `Cancelled`, `Postponed`, `Interrupted`); `withdrew` names who stopped.
5. **Never guess a market-to-match pairing.** `match_market` returns `None` on
   ambiguity; skip it. Use `override_match_id` / `--match-id` only when the user
   supplies the id explicitly.
6. **Tests stay offline.** Use trimmed fixtures and `httpx.MockTransport`; never
   put live calls in tests.

## Quick start

```bash
pip install polymarket-tennis          # Python 3.10+, depends only on httpx
pmtennis discover --matches-only --moneyline-only   # keyless, Gamma only
export LIVETENNIS_API_KEY=ltapi_...    # free, no card: https://livetennisapi.com/subscribe/free
pmtennis match atp-lehecka-fils-2026-08-17          # show the pairing decision + confidence
pmtennis watch atp-lehecka-fils-2026-08-17          # 1 request per poll, 60 s default
```

Env-var names differ between the two Live Tennis API tools: the Python package reads
`LIVETENNIS_API_KEY`; the `livetennisapi-mcp` server/plugin reads `LIVETENNISAPI_KEY`.
Same key value works in both.

Library form — every symbol below is exported from `polymarket_tennis.__init__`:

```python
from polymarket_tennis import (
    GammaClient, LiveTennisClient,
    discover_tennis_markets, match_market, build_view,
)

with GammaClient() as gamma, LiveTennisClient() as lta:
    markets = discover_tennis_markets(gamma, market_types={"moneyline"},
                                      matches_only=True)
    candidates = lta.live_matches() + lta.fixtures()   # 2 free-tier requests
    for market in markets:
        decision = match_market(market, candidates)
        if decision is None:
            continue  # ambiguous or no live counterpart — never guessed
        view = build_view(market, decision.match)
        print(view.render())
```

Sample `view.render()` output:

```text
Cincinnati Open: Jiri Lehecka vs Arthur Fils  [atp-lehecka-fils-2026-08-17]
  market: Jiri Lehecka 0.095 | Arthur Fils 0.905  (as of 12s ago)
  live:   Jiri Lehecka vs Arthur Fils  4-6 3-4 (15-40)  serving: Jiri Lehecka  [BREAK POINT]  (as of 8s ago)
```

## The package, in one screen

| Symbol | What it does | Network cost |
|---|---|---|
| `GammaClient()` | Polymarket Gamma API (keyless): `events()`, `event_by_slug()`, `market_by_id()`, `market_by_slug()`, `market()` | none against your key |
| `LiveTennisClient(api_key=None)` | Live Tennis API; key from `LIVETENNIS_API_KEY`: `matches()`, `live_matches()`, `match(id)`, `fixtures()`, `players(search)` | 1 request per call |
| `discover_tennis_markets(client, market_types=None, include_closed=False, matches_only=False, limit=100)` | normalized `TennisMarket` list from the `tennis` tag | Gamma only |
| `find_market(client, id_or_slug)` | one `TennisMarket` by Gamma id, market slug, or event slug | Gamma only |
| `match_market(market, candidates, override_match_id=None, threshold=0.70, ambiguity_margin=0.10)` | `MatchDecision` or `None` | pure |
| `build_view(market, match)` | `LiveMarketView` with both feeds' staleness | pure |
| `derive_break_point(score)`, `score_line(score)` | helpers used by the view | pure |
| `TennisMarket.price_by_outcome`, `.slug_date`, `.raw` | prices dict, slug date, the raw Gamma object (settlement text lives in `raw["description"]`) | — |

Full signatures, dataclass fields, and the live-match JSON shape are in
[references/api.md](references/api.md). Read it before writing code that touches
fields not shown above — in particular, `TennisMarket` has **no** `description`
attribute and `LiveMarketView` does **not** expose `outcome`; go through `.raw`
and `.match`.

## Workflow: build a watcher or bot data layer

1. **Discover** with `discover_tennis_markets(gamma, market_types={"moneyline"}, matches_only=True)`.
   Futures/outrights are dropped by `matches_only`; doubles markets are rejected by
   the matcher in v0.1.
2. **Fetch candidates once per poll**: `lta.live_matches()` (+ `lta.fixtures()` if
   you need pre-start matches). Count the requests; budget them against 100/day.
3. **Pair** each market with `match_market(market, candidates)`; skip `None`.
   Log `decision.confidence` and `decision.method` (`"explicit" | "names+date" | "names"`).
4. **Join** with `build_view(market, decision.match)`; read `view.prices`,
   `view.score_line`, `view.server` (1/2), `view.break_point`, `view.is_tiebreak`,
   `view.event_status`, and both `view.market_staleness()` / `view.live_staleness()`.
5. **Settlement branch**: read `view.match.get("outcome")` and
   `view.match.get("event_status")`; when `outcome in ("retired", "walkover",
   "default", "abandoned")` or `event_status == "Cancelled"`, print
   `view.market.raw.get("description")` verbatim (fall back to `rules_secondary`,
   then say the payload carries no rule text). Do not compute a payout.
6. **Paper only**: any "signal" the user asks for is logged to a local JSON book
   with a loud banner that no orders are sent. See the verified reference build.

```python
def settlement_text(view) -> str:
    raw = view.market.raw
    text = raw.get("description") or raw.get("rules_secondary")
    return text or "(market payload carries no settlement text; read it on the venue)"
```

## Kalshi

The package discovers **Polymarket** markets (Gamma). Kalshi publishes each market's
rule text in its public read endpoint, keyless; the same `outcome`/`event_status`
detection applies. Use the package's `LiveTennisClient` for the live side and read
Kalshi directly for the market side (see
[references/settlement-rules.md](references/settlement-rules.md) for the Kalshi
snippet and the ATP/WTA vs ITF series difference). Do not hard-code the ITF `$0.50`
rule; print `rules_secondary`.

## One-prompt build (verified output checked in)

When the user wants a watcher "vibe-coded" end to end, use the prompt in
[references/one-prompt-build.md](references/one-prompt-build.md). It is the exact
prompt from the package README; what it produced, unedited except for lint, is in
`examples/claude-code-watcher/` of the repository (7 offline tests, `ruff` clean,
`--once --fixtures` dry run without a key). That README also lists the honest
deviations — read them before re-running the prompt, because two of them are
traps: the prompt's "once a minute" costs 2 requests per poll (so the watcher must
self-cap), and the offline fixtures carry `event_status` but no `outcome` key.

## Retirement / walkover rule matrix (retrieved 2026-08-23)

The short version, for the human reading this — the code must still print the
market's own text:

| Scenario | Polymarket (polymarket.com) | Polymarket US | Kalshi (ATP/WTA) | Kalshi (ITF) |
|---|---|---|---|---|
| Walkover / withdrawal before the match starts | 50-50 | Last fair market price at announcement | Fair price per rules | $0.50 per contract |
| Match cancelled, not played | 50-50 | Last fair market price | Fair price per rules | $0.50 |
| Retirement after play starts (injury, default, DQ) | Advancing player wins | Awarded winner settles $1.00 | Winner resolves Yes ("after a ball has been played") | Winner Yes; withdrawing/forfeiting player No |
| Delayed / postponed | 50-50 if beyond 7 days with no winner | — (see venue FAQ) | Stays open, closes after rescheduled match (within two weeks) | Same as ATP/WTA |
| What counts as "started" | "the match begins" | First serve is struck | A ball has been played | A ball has been played |

Verbatim venue quotes, source URLs, retrieval dates, and the live-data mapping
(`outcome`/`event_status`/`withdrew` to each venue column) are in
[references/settlement-rules.md](references/settlement-rules.md). Rules are per
market and can change; the market's own text always wins over that file.

## Verification checklist before you hand code back

- `ruff check` clean; tests run with no network (`httpx.MockTransport` or fixture files).
- Every import resolves to a symbol listed in `references/api.md`.
- Request count per poll is computed and documented against 30/min, 100/day.
- No payout number appears in code; the venue text is printed instead.
- Match-end detection reads `outcome` / `event_status`, never `status == "completed"` alone.
- A banner states that no orders are ever sent.

## Further reading

- Package: https://github.com/livetennisapi/polymarket-tennis (PyPI `polymarket-tennis`)
- Pillar guide: https://blog.livetennisapi.com/blog/build-polymarket-tennis-trading-bot
- Verbatim rules: https://blog.livetennisapi.com/blog/polymarket-kalshi-tennis-retirement-walkover-rules
- Kalshi walkthrough: https://blog.livetennisapi.com/blog/kalshi-tennis-trading-bot
- Live Tennis API docs: https://docs.livetennisapi.com — free key: https://livetennisapi.com/subscribe/free
- Sibling skill (entry gate, simmer-sdk style): https://github.com/livetennisapi/simmer-tennis-live-gate
- MCP server for the same data: https://github.com/livetennisapi/livetennisapi-mcp
