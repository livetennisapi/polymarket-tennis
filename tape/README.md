# Arena tapes

A tape is one `.jsonl` file, one line per poll:

```json
{"ts": "2026-08-18T01:15:00Z", "market": <raw Gamma market>, "match": <Live Tennis API match>}
```

## `synthetic_lehecka_fils.jsonl` — SYNTHETIC, not a recording

This tape is **invented**. It takes the repo's real Gamma market fixture for
`atp-lehecka-fils-2026-08-17` (Cincinnati Open, captured 2026-08-18) and the
schema-constructed live-match fixture (id 90211) and scripts a plausible
10-snapshot sequence: Fils opens as favourite, is broken first at 1-0, recovers,
takes the first set 6-4, leads 5-3 in the second and closes it out. The prices
were chosen by hand to move with that script; the seventh snapshot reproduces
the fixture's real state (`4-6 3-4 (15-40)`, Fils 0.905), the rest are made up.

Use it for tests and for trying the replay CLI. Do not cite it as market data.

## Real tapes

Real tapes are recorded with `pmtennis arena record` on the organisers' own
key and are **not committed to this repo** (`tape/*.jsonl` other than the
synthetic one is git-ignored). Raw venue prices are not redistributed to
entrants — see `docs/ARENA.md`.
