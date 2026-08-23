# claude-code-watcher — observe-only Polymarket tennis watcher (paper book)

What came out of pasting the one-prompt recipe from the package README into
Claude Code. It sits entirely on the public API of `polymarket-tennis`
(`GammaClient`, `LiveTennisClient`, `discover_tennis_markets`, `match_market`,
`build_view`, `LiveMarketView`).

**Paper only.** It prints a banner on start: no real orders are ever sent.
There is no exchange client, no wallet, no key other than `LIVETENNIS_API_KEY`.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
export LIVETENNIS_API_KEY=ltapi_...        # free key: https://livetennisapi.com/subscribe/free

python watcher.py                          # poll every 60 s
python watcher.py --once                   # one poll
python watcher.py --once --fixtures tests/fixtures   # offline dry run, no key
```

Each poll logs, per confidently-matched market: the question, both outcome
prices, the score line, who is serving, the break-point flag, and the
staleness of both feeds. Markets the matcher cannot pair confidently are
skipped (`match_market` returns `None`; the watcher never guesses).

## Paper book (`paper_book.json`)

When the **favourite** (higher-priced outcome) is the one *serving* and the
package's break-point flag is on, a `PAPER` entry is recorded
`{time, market, side, price, game_key}`. When the game counter moves on
(the game resolved either way) the entry is closed with the favourite's new
price and the `move`. One open entry per market; repeated polls of the same
break point are not double-counted.

## Retirement / walkover

If the match's `outcome` becomes `retired` or `walkover`, the watcher prints
the market's own `description` (or `rules_secondary`) text verbatim. No
payout rule is hard-coded. If the payload has no description text it says so
instead of inventing one.

## Free-tier budget (honest numbers)

One poll = **2** Live Tennis API requests (`live_matches()` + `fixtures()`);
Gamma is keyless and costs nothing. The free tier is 30 req/min and 100
req/day, so at the 60 s default the watcher funds about **48 minutes** of
watching per day and stops itself at `--daily-budget` (default 96) requests.
Use `--interval 300` for roughly 4 hours. The budget counter is per process —
restarting resets it, the API's daily quota does not.

## Tests

```bash
pytest            # 7 tests, offline, fixture clients via httpx.MockTransport
ruff check .
```

## Honest deviations from the prompt

- **`match.outcome` is not in the offline fixtures.** The package's fixtures
  (constructed to the OpenAPI schema) carry `event_status` (e.g. `"Retired"`)
  but no `outcome` key, and `LiveMarketView` does not expose `outcome`. The
  watcher reads `view.match["outcome"]` first and falls back to
  `event_status` lower-cased; tests cover both.
- **`TennisMarket` has no `description` attribute.** The settlement text is
  read from `view.market.raw["description"]` (falling back to
  `rules_secondary`). The package's trimmed Gamma capture has no description
  field at all, so the copy under `tests/fixtures/` adds a clearly labelled
  stand-in string (`[FIXTURE TEXT, not Polymarket's wording]`) — it is NOT
  Polymarket's rule text. See `tests/fixtures/README.md`.
- **"Favourite facing a break point"** is interpreted as: the favourite is the
  *server* while `break_point` is True. The server is mapped to an outcome
  label by folded-name equality (`polymarket_tennis.matching.fold_name`); if
  the names do not line up, no entry is recorded.
- **Two requests per poll, not one.** The prompt asks for `live_matches() +
  fixtures()` every minute; that is 120 req/hour, more than the free tier's
  100/day, so the watcher caps itself at 96 requests per process.
