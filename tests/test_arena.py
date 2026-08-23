"""Arena: replay, scoring, paper-book math — offline, fixtures + synthetic tape.

The tape under tape/ is SYNTHETIC (see tape/README.md): a scripted score and
price sequence built from the repo fixtures, never a capture.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polymarket_tennis import cli
from polymarket_tennis.arena import (
    FadeFirstBreak,
    ForbiddenImportError,
    HoldFavourite,
    NeverTrade,
    PaperBook,
    Strategy,
    TapeLine,
    baseline_strategies,
    check_strategy_source,
    load_strategies,
    rank,
    read_tape,
    replay,
    write_leaderboard,
)
from polymarket_tennis.arena.replay import settlement_prices, views_from_tape

TAPE = Path(__file__).parent.parent / "tape" / "synthetic_lehecka_fils.jsonl"


@pytest.fixture
def tape():
    return read_tape(TAPE)


class TestPaperBookMath:
    def test_hand_computed_mark_to_market(self):
        book = PaperBook()
        entry = book.enter("t0", "m", "A", 0.40, 10.0, "test")
        assert entry is not None
        assert entry.shares == pytest.approx(25.0)
        assert book.pnl({"A": 0.50}) == pytest.approx(2.5)
        assert book.pnl({"A": 0.30}) == pytest.approx(-2.5)
        assert book.pnl({"A": 1.0}) == pytest.approx(15.0)
        assert book.pnl({"A": 0.0}) == pytest.approx(-10.0)
        assert book.pnl({"B": 0.9}) == 0.0  # unknown side marks at cost

    def test_rejects_bad_price_size_and_caps(self):
        book = PaperBook(max_entries=1)
        assert book.enter("t", "m", "A", None, 10, "x") is None
        assert book.enter("t", "m", "A", 1.0, 10, "x") is None
        assert book.enter("t", "m", "A", 0.5, 0, "x") is None
        assert book.enter("t", "m", "A", 0.5, 10, "x") is not None
        assert book.enter("t", "m", "A", 0.5, 10, "x") is None  # full
        assert len(book.entries) == 1


class TestReplay:
    def test_tape_reads_and_builds_views(self, tape):
        assert len(tape) == 10
        views = views_from_tape(tape)
        assert views[6].score_line == "4-6 3-4 (15-40)"
        assert views[6].break_point is True
        assert views[-1].match_status == "completed"

    def test_settlement_only_for_plain_completed(self, tape):
        views = views_from_tape(tape)
        assert settlement_prices(views[0]) is None
        assert settlement_prices(views[-1]) == {
            "Jiri Lehecka": 0.0, "Arthur Fils": 1.0
        }
        retired = dict(tape[-1].match, event_status="Retired", outcome="retired")
        last = tape[-1]
        retired_view = views_from_tape([TapeLine("t", last.market, retired)])[0]
        assert settlement_prices(retired_view) is None  # venue rule, never ours

    def test_baselines_are_deterministic(self, tape):
        a = [replay(s, tape, "t").to_dict() for s in baseline_strategies()]
        b = [replay(s, tape, "t").to_dict() for s in baseline_strategies()]
        assert a == b
        by_name = {r["strategy"]: r for r in a}
        # hold-favourite: $10 at 0.72 -> 13.889 shares -> +3.89 at settlement
        assert by_name["hold-favourite"]["pnl"] == pytest.approx(3.8889, abs=1e-3)
        assert by_name["hold-favourite"]["max_drawdown"] == pytest.approx(
            1.1111, abs=1e-3
        )
        assert by_name["hold-favourite"]["entries"] == 1
        # fade-first-break: Fils broken at 2-0 -> buys Lehecka at 0.36 -> settles 0
        fade = by_name["fade-first-break"]
        assert fade["entries"] == 1
        assert fade["book"][0]["side"] == "Jiri Lehecka"
        assert fade["book"][0]["price"] == pytest.approx(0.36)
        assert fade["pnl"] == pytest.approx(-10.0)
        assert by_name["never-trade"] == {
            **by_name["never-trade"], "pnl": 0.0, "max_drawdown": 0.0, "entries": 0
        }
        assert all(r["settled"] for r in a)

    def test_fade_does_not_fire_on_a_hold(self, tape):
        # cut the tape before the break: Fils serving at 1-0 30-40 then nothing
        result = replay(FadeFirstBreak(), tape[:2], "t")
        assert result.entries == 0


class TestScoreboard:
    def test_rank_and_write(self, tape, tmp_path):
        results = [replay(s, tape, TAPE.name) for s in baseline_strategies()]
        ordered = [r.strategy for r in rank(results)]
        assert ordered == ["hold-favourite", "never-trade", "fade-first-break"]
        json_path, md_path = write_leaderboard(results, tmp_path, "Season 0")
        data = json.loads(json_path.read_text())
        assert data["paper_only"] is True
        assert [row["rank"] for row in data["rows"]] == [1, 2, 3]
        assert "price" not in json.dumps(data["rows"])  # scores only, no tape data
        md = md_path.read_text()
        assert "| 1 | hold-favourite | +3.89 | 1.11 | 1 |" in md
        assert "Not advice" in md


class TestStrategyContract:
    def test_baselines_satisfy_protocol(self):
        for s in (HoldFavourite(), FadeFirstBreak(), NeverTrade()):
            assert isinstance(s, Strategy)

    def test_entrant_file_loads(self, tmp_path):
        src = tmp_path / "mine.py"
        src.write_text(
            "class Mine:\n"
            "    name = 'mine'\n"
            "    def on_view(self, view, book):\n"
            "        pass\n"
            "STRATEGIES = [Mine()]\n"
        )
        assert [s.name for s in load_strategies(str(src))] == ["mine"]

    def test_order_client_import_is_refused(self, tmp_path):
        src = tmp_path / "cheat.py"
        src.write_text(
            "from py_clob_client.client import ClobClient\nSTRATEGIES = []\n"
        )
        with pytest.raises(ForbiddenImportError):
            check_strategy_source(src)
        with pytest.raises(ForbiddenImportError):
            load_strategies(str(src))

    def test_unknown_spec(self):
        with pytest.raises(ValueError):
            load_strategies("nope")


class TestCLI:
    def test_replay_command(self, capsys, tmp_path):
        code = cli.main(
            ["arena", "replay", "--tape", str(TAPE), "--strategies", "baselines",
             "--out", str(tmp_path)]
        )
        out = capsys.readouterr().out
        assert code == 0
        assert "paper only" in out
        assert "1. hold-favourite" in out
        assert (tmp_path / "leaderboard.md").exists()

    def test_record_writes_tape_offline(self, capsys, tmp_path, monkeypatch):
        import httpx

        from polymarket_tennis.gamma import GammaClient
        from polymarket_tennis.livetennis import LiveTennisClient

        from .conftest import _gamma_handler, _lta_handler

        monkeypatch.setattr(
            cli, "GammaClient",
            lambda *a, **k: GammaClient(
                client=httpx.Client(transport=httpx.MockTransport(_gamma_handler))
            ),
        )
        monkeypatch.setattr(
            cli, "LiveTennisClient",
            lambda *a, **k: LiveTennisClient(
                api_key="test-key",
                client=httpx.Client(transport=httpx.MockTransport(_lta_handler)),
            ),
        )
        monkeypatch.setattr(cli.time, "sleep", lambda s: None)
        out_path = tmp_path / "t.jsonl"
        code = cli.main(
            ["arena", "record", "--market", "atp-lehecka-fils-2026-08-17",
             "--out", str(out_path), "--count", "2"]
        )
        text = capsys.readouterr().out
        assert code == 0
        assert "100 req/day" in text
        lines = read_tape(out_path)
        assert len(lines) == 2
        assert lines[0].match["id"] == 90211
        assert lines[0].market["slug"] == "atp-lehecka-fils-2026-08-17"
