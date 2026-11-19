import duckdb
import pytest

from gully_pipeline.aggregate import build
from gully_pipeline.parse import write_parquet
from test_parse import MATCH


@pytest.fixture
def db(tmp_path):
    pq_dir = tmp_path / "pq"
    write_parquet([("1", MATCH)], pq_dir)
    people = tmp_path / "people.csv"
    people.write_text(
        "identifier,name,unique_name,key_cricinfo\n"
        "id_a,A Batter,A Batter,101\n"
        "id_b,B Runner,B Runner,102\n"
        "id_c,C Bowler,C Bowler,103\n"
    )
    db_path = tmp_path / "t.duckdb"
    counts = build(pq_dir, people, db_path)
    assert counts["players"] == 3
    con = duckdb.connect(str(db_path), read_only=True)
    yield con
    con.close()


def row(con, sql):
    cur = con.execute(sql)
    cols = [c[0] for c in cur.description]
    r = cur.fetchone()
    return dict(zip(cols, r)) if r else None


def test_formats_overlap(db):
    # A club T20 in the IPL counts toward both IPL and all-T20, nothing else.
    fmts = db.execute(
        "select list(format order by format) from player_format_stats where player_id='id_a'"
    ).fetchone()[0]
    assert fmts == ["IPL", "T20"]


def test_batting_stats(db):
    a = row(db, "select * from player_format_stats where player_id='id_a' and format='IPL'")
    # four, wide (not a ball faced), bowled
    assert (a["matches"], a["bat_innings"], a["runs"], a["balls_faced"]) == (1, 1, 4, 2)
    assert a["bat_avg"] == 4.0 and a["bat_sr"] == 200.0 and a["fours"] == 1
    assert a["not_outs"] == 0
    b = row(db, "select * from player_format_stats where player_id='id_b' and format='IPL'")
    assert (b["runs"], b["balls_faced"], b["not_outs"]) == (1, 1, 0)  # run out


def test_bowling_stats(db):
    c = row(db, "select * from player_format_stats where player_id='id_c' and format='IPL'")
    # 3 legal balls; 4 + 1 wide + 1 = 6 conceded; run out not credited
    assert (c["balls_bowled"], c["runs_conceded"], c["wickets"]) == (3, 6, 1)
    assert c["bowl_econ"] == 12.0 and c["best_bowling"] == "1/6"
    assert c["bat_innings"] == 0 and c["bat_avg"] is None


def test_phase_stats(db):
    a = row(db, "select * from player_phase_stats where player_id='id_a' and format='T20' "
                "and phase='PP' and role='bat'")
    assert (a["balls"], a["fours"], a["wickets"], a["dots"]) == (2, 1, 1, 1)
    assert a["four_pct"] == 0.5 and a["dismissal_rate"] == 0.5
    c = row(db, "select * from player_phase_stats where player_id='id_c' and format='T20' "
                "and phase='PP' and role='bowl'")
    assert (c["balls"], c["runs"], c["wide_balls"], c["wickets"]) == (2, 5, 1, 1)
    death = row(db, "select * from player_phase_stats where player_id='id_b' and phase='death' "
                    "and format='T20' and role='bat'")
    assert death["wickets"] == 1 and death["ones"] == 1


def test_players(db):
    p = row(db, "select * from players where id='id_c'")
    assert p["name"] == "C Bowler" and p["cricinfo_id"] == "103"
    assert p["role"] == "BOWL" and p["capped"] is False and p["country"] is None
    assert (p["era_start"], p["era_end"], p["source"]) == (2024, 2024, "cricsheet")
    assert row(db, "select role from players where id='id_a'")["role"] == "BAT"


def test_form_weights_by_recency(tmp_path):
    """Same match played in 2024 and 2022: as of 2025 the 2022 copy weighs
    0.5 ** (2 / half_life); as of 2024 only the 2022 copy exists (no look-ahead)."""
    old = {**MATCH, "info": {**MATCH["info"], "dates": ["2022-04-01"], "season": 2022}}
    write_parquet([("1", MATCH), ("2", old)], tmp_path / "pq")
    people = tmp_path / "people.csv"
    people.write_text("identifier,name,unique_name,key_cricinfo\n"
                      "id_a,A Batter,A Batter,1\nid_b,B Runner,B Runner,2\nid_c,C Bowler,C Bowler,3\n")
    build(tmp_path / "pq", people, tmp_path / "t.duckdb")
    with duckdb.connect(str(tmp_path / "t.duckdb"), read_only=True) as con:
        def balls(as_of, h):
            return con.execute(
                "SELECT balls, exp_fours FROM player_phase_form WHERE pid='id_a' AND format='IPL' "
                "AND phase='PP' AND role='bat' AND as_of=? AND half_life=?", [as_of, h]).fetchone()
        assert balls(2025, 0)[0] == pytest.approx(4)          # career: 2 + 2 balls
        assert balls(2025, 2)[0] == pytest.approx(2 + 0.5 * 2)
        assert balls(2025, 1)[0] == pytest.approx(2 + 0.25 * 2)
        assert balls(2024, 2)[0] == pytest.approx(2 ** 0.5)   # only 2022, one year back
        # expected counts are weighted the same way as observed ones
        b0, e0 = balls(2025, 0)
        b2, e2 = balls(2025, 2)
        assert e2 / b2 == pytest.approx(e0 / b0)


def test_season_stats(db):
    s = row(db, "select * from player_season_stats where player_id='id_a' and format='IPL'")
    assert s["season"] == "2024" and s["runs"] == 4
