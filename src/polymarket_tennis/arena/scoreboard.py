"""Rank replay results and publish a leaderboard (JSON + markdown).

Published fields are ranks and derived scores only: P&L, max drawdown and
entry count. The tape itself (raw venue prices) is never written here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .replay import ReplayResult

__all__ = ["rank", "leaderboard_markdown", "write_leaderboard"]


def rank(results: list[ReplayResult]) -> list[ReplayResult]:
    """Highest P&L first; ties broken by smaller drawdown, then fewer entries,
    then name — so the order is fully deterministic."""
    return sorted(
        results,
        key=lambda r: (
            -round(r.pnl, 6), round(r.max_drawdown, 6), r.entries, r.strategy
        ),
    )


def _rows(results: list[ReplayResult]) -> list[dict[str, Any]]:
    return [
        {
            "rank": i,
            "strategy": r.strategy,
            "pnl_usd": round(r.pnl, 2),
            "max_drawdown_usd": round(r.max_drawdown, 2),
            "entries": r.entries,
            "settled": r.settled,
        }
        for i, r in enumerate(rank(results), start=1)
    ]


def leaderboard_markdown(results: list[ReplayResult], title: str = "") -> str:
    rows = _rows(results)
    tapes = sorted({r.tape for r in results if r.tape})
    lines = []
    if title:
        lines.append(f"## {title}")
        lines.append("")
    lines.append("| rank | strategy | paper P&L (USD) | max drawdown (USD) | entries |")
    lines.append("|---:|---|---:|---:|---:|")
    for row in rows:
        lines.append(
            f"| {row['rank']} | {row['strategy']} | {row['pnl_usd']:+.2f} | "
            f"{row['max_drawdown_usd']:.2f} | {row['entries']} |"
        )
    lines.append("")
    lines.append(
        f"Tape(s): {', '.join(tapes) if tapes else 'n/a'}. Paper only — no "
        "orders were sent by anything in this repo. Not advice."
    )
    return "\n".join(lines) + "\n"


def write_leaderboard(
    results: list[ReplayResult], out_dir: str | Path, title: str = ""
) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "leaderboard.json"
    md_path = out / "leaderboard.md"
    json_path.write_text(
        json.dumps(
            {
                "title": title,
                "paper_only": True,
                "tapes": sorted({r.tape for r in results if r.tape}),
                "rows": _rows(results),
            },
            indent=2,
        )
        + "\n"
    )
    md_path.write_text(leaderboard_markdown(results, title))
    return json_path, md_path
