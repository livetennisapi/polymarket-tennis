# Tennis Bot Arena — paper-only strategy leaderboard

An observe-only competition layered on `polymarket-tennis`. Entrants write a
small Python strategy; the organisers replay it over a recorded tape of
Polymarket tennis market snapshots joined with live match state; the
leaderboard ranks strategies by **paper** P&L. Nothing is traded by anyone.

**Not advice.** The arena is a programming exercise about reading market
price against live score. A top rank says nothing about real trading, where
fees, fills, latency and liquidity exist and this replay has none of them.

## Rules

1. **Paper only.** A strategy receives a `LiveMarketView` and a `PaperBook`
   and may append paper entries. There is no order code, no wallet and no
   venue client anywhere in this package, and strategy files that import
   one (`py_clob_client`, `web3`, `eth_account`, …) are refused before they
   run (`check_strategy_source`). That check catches mistakes, not
   adversaries; the real guarantee is that the arena API gives a strategy
   nothing it could trade with.
2. **A strategy is one Python file** exposing `STRATEGIES = [...]` or a
   `strategy()` factory. Each object needs a `name` and
   `on_view(view: LiveMarketView, book: PaperBook) -> None`. It may keep
   its own state between snapshots; it gets the snapshots in tape order,
   one at a time, and never sees the future.
3. **Scoring = replay on the season tape.** Every entry is a notional buy of
   `size_usd / price` shares of one outcome. P&L is marked to each later
   snapshot's Gamma price; when the final snapshot is a plain `completed`
   match with a `winner`, the winning outcome marks at 1 and the other at 0.
   Retirements, walkovers, defaults and abandoned matches are **not**
   settled by the arena — each venue's own rule decides those and we never
   hard-code it — so such entries are marked at the last observed price.
   No fees, no slippage, no fill model. A book holds at most 50 entries.
4. **Leaderboard = ranks + derived scores only**: paper P&L, max drawdown
   (peak-to-trough of the mark-to-market equity curve) and entry count.
   Ties: smaller drawdown, then fewer entries, then name.
5. **Baselines are always on the board**: `hold-favourite` (buy the
   first-snapshot favourite, hold), `fade-first-break` (buy the opponent the
   first time the favourite is broken), `never-trade` (the floor). Beat
   `never-trade` or it was not a strategy.

## Season 1 — US Open 2026

Main draw starts ~2026-08-31. The season tape is a set of singles moneyline
markets recorded across the fortnight with `pmtennis arena record` at a
300-second cadence. Which markets, how many, and the exact tape list are
announced when the season closes, so nobody can fit to the tape.

## Data handling — read this before asking for the tape

- **The live tape is recorded by the organisers on their own Live Tennis
  API key.** Entrants do not need a key to enter: they develop against the
  synthetic tape in this repo and submit a file.
- **Raw venue price data is not redistributed to entrants.** Tapes contain
  Polymarket price snapshots; those are Polymarket's data and we do not
  republish them. What is published is the leaderboard: ranks and the
  derived scores in rule 4. This is a legal constraint on the arena, not a
  style choice, and it is why `tape/*.jsonl` is git-ignored apart from the
  synthetic file.
- The only committed tape, `tape/synthetic_lehecka_fils.jsonl`, is
  **synthetic**: a hand-scripted 10-snapshot sequence built from the repo's
  test fixtures. It is for tests and for trying the CLI, never a record of
  a real market. See `tape/README.md`.

## Using it

```bash
pip install -e ".[dev]"

# replay the synthetic tape through the three baselines, write a leaderboard
pmtennis arena replay --tape tape/synthetic_lehecka_fils.jsonl \
    --strategies baselines --out leaderboard/

# replay your own strategy file alongside the baselines
pmtennis arena replay --tape tape/synthetic_lehecka_fils.jsonl \
    --strategies baselines my_strategy.py

# organisers: record a real tape (needs LIVETENNIS_API_KEY)
pmtennis arena record --market atp-lehecka-fils-2026-08-17 \
    --interval 300 --out tape/usopen-2026-r1-lehecka-fils.jsonl
```

Output of the synthetic replay, as produced by the tests:

| rank | strategy | paper P&L (USD) | max drawdown (USD) | entries |
|---:|---|---:|---:|---:|
| 1 | hold-favourite | +3.89 | 1.11 | 1 |
| 2 | never-trade | +0.00 | 0.00 | 0 |
| 3 | fade-first-break | -10.00 | 10.00 | 1 |

(The synthetic script has the favourite win, so the fade loses its full
stake. That is a property of the made-up tape, not of the idea.)

### Recording budget (free tier: 30 req/min, 100 req/day)

`arena record` spends **1 Live Tennis API request per poll** plus 2-3 once
at startup to pair the market (live matches, upcoming, fixtures). Gamma is
keyless and free. At the default 300 s cadence a three-hour match costs
about 40 requests, so a free key records roughly two matches a day; a paid
key is needed to cover a full slam day. Tapes append, so a recorder that is
restarted resumes the same file.

### Strategy skeleton

```python
from polymarket_tennis.arena import PaperBook
from polymarket_tennis import LiveMarketView

class MyStrategy:
    name = "my-strategy"

    def on_view(self, view: LiveMarketView, book: PaperBook) -> None:
        if view.break_point and not book.has_entry(view.market.slug):
            fav = max(view.prices, key=lambda o: view.prices[o] or 0)
            book.enter(view.live_as_of.isoformat(), view.market.slug, fav,
                       view.prices[fav], 10.0, "break point against someone")

STRATEGIES = [MyStrategy()]
```

Useful fields on `view`: `prices` (outcome → price), `score_line`, `sets`,
`server` (1/2), `break_point`, `is_tiebreak`, `player1`/`player2`,
`match_status`, `event_status`, and the raw `match` dict.
