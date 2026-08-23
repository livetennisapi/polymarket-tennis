# Fixtures (offline)

- `lta_matches_live.json`, `lta_fixtures.json` — copied verbatim from the
  package's `tests/fixtures/` (constructed to the Live Tennis API OpenAPI
  schema, not live captures).
- `gamma_events_tennis.json` — copied from the package's real Gamma capture
  (2026-08-18), with ONE addition: a `description` string on each moneyline
  market, clearly labelled `[FIXTURE TEXT, not Polymarket's wording]`, so the
  settlement-text path can be exercised offline. The trimmed upstream capture
  carries no `description`.
