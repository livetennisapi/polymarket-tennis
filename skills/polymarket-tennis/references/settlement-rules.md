# Polymarket & Kalshi tennis retirement / walkover rules — verbatim (retrieved 2026-08-23)

Source page (kept current; always prefer it over this copy):
https://blog.livetennisapi.com/blog/polymarket-kalshi-tennis-retirement-walkover-rules

Nothing here is advice. Rules are set per market and can change; the market's own
`description` / `rules_secondary` text always wins over this file. **Code must
print the venue text, never branch on the numbers below.**

Three venues, three different rule sets. A walkover on Polymarket settles 50-50; on
Polymarket US it settles at the last fair market price (ITF: $0.50); on Kalshi it
settles at a fair price per the rules (ITF: $0.50). A mid-match retirement pays the
advancing player on all three — except Kalshi ITF, where the withdrawing player's
contract resolves No.

## The settlement matrix (2026-08-23)

| Scenario | Polymarket (polymarket.com) | Polymarket US (docs.polymarket.us) | Kalshi (ATP/WTA) | Kalshi (ITF) |
|---|---|---|---|---|
| Walkover / withdrawal before the match starts | 50-50 | Last fair market price at announcement | Fair price per rules | $0.50 per contract |
| Match cancelled, not played | 50-50 | Last fair market price | Fair price per rules | $0.50 |
| Retirement after play starts (injury, default, DQ) | Advancing player wins | Awarded winner settles $1.00 | Winner resolves Yes ("after a ball has been played") | Winner Yes; withdrawing/forfeiting player No |
| Delayed / postponed | 50-50 if beyond 7 days with no winner | — (see venue FAQ) | Stays open, closes after rescheduled match (within two weeks) | Same as ATP/WTA |
| What counts as "started" | "the match begins" | First serve is struck | A ball has been played | A ball has been played |

"—" means the source we quote does not state it; read the specific market.

## Polymarket (polymarket.com) — the rule lives in the market description

Every per-match tennis market on Polymarket carries its settlement text in the market
object's `description` (public Gamma API, keyless). From a live ATP market, retrieved
2026-08-23 via `https://gamma-api.polymarket.com/events?tag_id=864` (event
`atp-norrie-navone-2026-05-20`):

> If the match is canceled (not played at all), ends in a tie, or is delayed beyond 7 days from the scheduled date without a winner determined, this market will resolve to 50-50.
>
> If the match begins but is not completed, and one player advances due to the opponent's retirement, default, or disqualification, this market will resolve to the player who advances.
>
> If the match ends in a walkover (player withdraws before the start and the other advances automatically), this market will resolve to 50-50.
>
> The primary resolution source will be official information from the ATP Tour. A consensus of credible reporting may also be used.

So on Polymarket a walkover is a 50-50, and a retirement is a win for the player who
advances. The text is per market: read it from the API rather than assuming it.

With the package (keyless; `TennisMarket.raw` is the untouched Gamma object):

```python
from polymarket_tennis import GammaClient, discover_tennis_markets

with GammaClient() as gamma:
    for market in discover_tennis_markets(gamma, market_types={"moneyline"}, matches_only=True):
        text = market.raw.get("description") or ""
        print(market.event_title or market.question)
        print("  walkover rule:", [s for s in text.split("\n") if "walkover" in s.lower()])
```

## Polymarket US (CFTC-regulated app) — first serve is the line

From the official Sports FAQ at `docs.polymarket.us/faqs/sports-faqs`, section
*Tennis (WTA, ATP, & ITF)*, retrieved 2026-08-23:

> **When does a match officially begin?** A tennis match officially begins when the first serve is struck. Anything happening before the first serve (cancellation, walkover, withdrawal) is treated as a pre-event scenario and Contracts settle at last fair market prices as of the official announcement. Except in the case of ITF Men's and Women's matches, cancellation, walkover, or withdrawal will resolve at $0.50 per Contract.
>
> **Mid-match retirement, default, or disqualification.** If a player retires after the first serve, defaults for a code violation, or is disqualified, the market resolves on the official result declared by the governing body. Whoever is awarded the win settles at $1.00, regardless of how many games or sets were completed.

Two things differ from polymarket.com: a pre-serve walkover is not a 50-50 but the
last fair market price (so a 0.90 favourite's contract settles near 0.90, not 0.50)
— unless it is an ITF match, which is $0.50.

## Kalshi — per-market `rules_secondary`, and ITF is different

Kalshi publishes each market's wording in the public API (`rules_primary` /
`rules_secondary`). Retrieved 2026-08-23 from
`https://api.elections.kalshi.com/trade-api/v2/markets?series_ticker=KXATPMATCH`:

> If Frances Tiafoe wins the Fils vs Tiafoe professional tennis match in the 2026 ATP Cincinnati Final after a ball has been played, then the market resolves to Yes. […] If the match does not occur (signaled by a ball being played) due to a player injury, walkover, forfeiture, or any other cancellation (all before the match starts), the market will resolve to a fair price in accordance with the rules. If this match is postponed or delayed, the market will remain open and close after the rescheduled match has finished (within two weeks).

The WTA series (`KXWTAMATCH`) carries the same text. The ITF series (`KXITFMATCH`,
same date) adds two different clauses:

> If the match does not occur (signaled by a ball being played) due to a player injury, walkover, forfeiture, or any other cancellation (all before the match starts), all markets will resolve to $0.50. If a player withdraws or forfeits after a match has started, that player will resolve to No.

Kalshi's series-level rulebook PDFs (e.g.
`assets.kalshi.com/regulatory/product-certifications/TENNISMATCH.pdf`) are generic
templates; the match-specific wording above is what the API returns per market.

```python
# Kalshi: read the per-market rule text (public endpoint, no key needed for reads).
# The polymarket-tennis package has no Kalshi client; this is plain httpx.
import httpx

r = httpx.get("https://api.elections.kalshi.com/trade-api/v2/markets",
              params={"series_ticker": "KXITFMATCH", "status": "open", "limit": 5},
              timeout=10)
for m in r.json()["markets"]:
    print(m["ticker"], "->", m["rules_secondary"][:160])
```

## Detecting each branch in live match data

The venue decides the payout; your feed has to tell you which branch happened, and
when. In the Live Tennis API every match carries two settlement-relevant fields next
to the lifecycle `status`:

- `outcome` (closed vocabulary, `null` until settled): `completed`, `retired`,
  `walkover`, `default`, `abandoned`
- `event_status` (the feed's designator): `Retired`, `Walk Over`, `Cancelled`,
  `Postponed`, `Interrupted`, …
- `withdrew`: which player stopped or conceded

| Live data | Polymarket | Polymarket US | Kalshi ATP/WTA | Kalshi ITF |
|---|---|---|---|---|
| `outcome = walkover` (never started) | 50-50 | Last fair price (ITF $0.50) | Fair price | $0.50 |
| `outcome = retired` or `default`, `withdrew = X` | Opponent of X wins | Opponent of X at $1.00 | Opponent of X = Yes | Opponent Yes, X = No |
| `event_status = Cancelled`, never started | 50-50 | Last fair price (ITF $0.50) | Fair price | $0.50 |
| `event_status = Postponed / Interrupted` | Open until 7-day limit | See FAQ | Open up to two weeks | Open up to two weeks |

Branch classification with the package client (1 request; returns a label, never a
payout):

```python
from polymarket_tennis import LiveTennisClient

def settlement_branch(lta: LiveTennisClient, match_id: int) -> str:
    m = lta.match(match_id) or {}
    if m.get("outcome") == "walkover":
        return "pre-start walkover"
    if m.get("outcome") in ("retired", "default"):
        return f"in-play retirement, withdrew={m.get('withdrew')}"
    if m.get("event_status") == "Cancelled":
        return "cancelled"
    return m.get("event_status") or m.get("status") or "unknown"
```

The free tier returns `status`, `event_status` and `outcome` on live and upcoming
matches; completed results (and the 60-second pre-start status poll that catches
walkovers before first serve) are on Basic and up.

## FAQ (from the source page)

**What happens on Polymarket if a tennis player retires mid-match?**
Per the market description on polymarket.com (retrieved 2026-08-23): if the match
begins but is not completed and one player advances due to the opponent's
retirement, default or disqualification, the market resolves to the player who
advances.

**Why did my Polymarket tennis market resolve at 50 cents?**
On polymarket.com a walkover (withdrawal before the start), a cancelled match, a
tie, or a delay beyond 7 days without a winner all resolve 50-50 per the market's
description. On Polymarket US and Kalshi, $0.50 is specifically the ITF pre-start
rule.

**How does Kalshi settle a tennis walkover?**
Per the market's `rules_secondary` (retrieved 2026-08-23): ATP/WTA match markets
resolve to a fair price in accordance with the rules if the match does not occur
before a ball has been played; ITF match markets resolve to $0.50, and on ITF a
player who withdraws or forfeits after the match has started resolves to No.

**When does a tennis match officially begin for settlement?**
Polymarket US: when the first serve is struck. Kalshi: when a ball has been played.
Polymarket.com distinguishes "the match begins" from a walkover where a player
withdraws before the start.

**How do I detect a retirement or walkover in live data?**
Read the match's `outcome` field (`walkover`, `retired`, `default`, `abandoned`,
`completed`) and `event_status` (`Retired`, `Walk Over`, `Cancelled`, `Postponed`,
`Interrupted`) plus `withdrew`, rather than the lifecycle `status`, which only says
`upcoming/live/completed/cancelled`.
