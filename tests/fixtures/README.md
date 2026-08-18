# Fixture provenance

Honesty note, so nobody mistakes synthetic shapes for captures (or vice versa):

- `gamma_events_tennis.json`, `gamma_market_by_slug.json` — **real Polymarket
  Gamma API payloads**, captured 2026-08-18 from
  `https://gamma-api.polymarket.com/events?tag_slug=tennis` during the
  Cincinnati Open (Lehecka vs Fils, Eala vs Anisimova, a Cash/Glasspool
  doubles event, the 2026 US Open winner futures event, and the two
  real "Moeller" Challenger matches). Trimmed to the fields this toolkit
  reads; values (prices, volumes, timestamps) are as observed.
- `lta_matches_live.json`, `lta_fixtures.json`, `lta_match_completed.json` —
  **constructed to the Live Tennis API's published OpenAPI schema**
  (github.com/livetennisapi/openapi), not captured from the live service.
  They follow the schema's documented edge cases, including completed
  matches carrying null `points` and empty `games`. Player names/scores are
  plausible stand-ins chosen to exercise matching edge cases (diacritics,
  shared surnames, doubles teams).
