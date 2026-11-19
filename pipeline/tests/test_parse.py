import pyarrow.parquet as pq

from gully_pipeline.parse import parse_match, phase_for, write_parquet

MATCH = {
    "meta": {"data_version": "1.1.0"},
    "info": {
        "dates": ["2024-04-01"],
        "gender": "male",
        "match_type": "T20",
        "season": 2024,
        "event": {"name": "Indian Premier League"},
        "venue": "Wankhede Stadium",
        "city": "Mumbai",
        "teams": ["Mumbai Indians", "Chennai Super Kings"],
        "toss": {"winner": "Mumbai Indians", "decision": "field"},
        "outcome": {"winner": "Chennai Super Kings", "by": {"runs": 5}},
        "overs": 20,
        "registry": {"people": {"A Batter": "id_a", "B Runner": "id_b", "C Bowler": "id_c"}},
    },
    "innings": [{
        "team": "Mumbai Indians",
        "overs": [
            {"over": 0, "deliveries": [
                {"batter": "A Batter", "bowler": "C Bowler", "non_striker": "B Runner",
                 "runs": {"batter": 4, "extras": 0, "total": 4}},
                {"batter": "A Batter", "bowler": "C Bowler", "non_striker": "B Runner",
                 "runs": {"batter": 0, "extras": 1, "total": 1}, "extras": {"wides": 1}},
                {"batter": "A Batter", "bowler": "C Bowler", "non_striker": "B Runner",
                 "runs": {"batter": 0, "extras": 0, "total": 0},
                 "wickets": [{"player_out": "A Batter", "kind": "bowled"}]},
            ]},
            {"over": 17, "deliveries": [
                {"batter": "B Runner", "bowler": "C Bowler", "non_striker": "A Batter",
                 "runs": {"batter": 1, "extras": 0, "total": 1},
                 "wickets": [{"player_out": "B Runner", "kind": "run out"}]},
            ]},
        ],
    }],
}


def test_phase_boundaries():
    assert phase_for("T20", 0) == "PP"
    assert phase_for("T20", 5) == "PP"
    assert phase_for("T20", 6) == "middle"
    assert phase_for("T20", 15) == "death"
    assert phase_for("ODI", 39) == "middle"
    assert phase_for("ODI", 40) == "death"
    assert phase_for("Test", 10) is None


def test_parse_match_rows():
    match, rows = parse_match("123", MATCH)
    assert match["winner"] == "Chennai Super Kings" and match["result"] == "win"
    assert len(rows) == 4
    four, wide, bowled, runout = rows
    assert four["runs_batter"] == 4 and four["is_legal"] and four["legal_ball_in_over"] == 1
    assert not wide["is_legal"] and wide["wides"] == 1 and wide["legal_ball_in_over"] == 1
    assert bowled["legal_ball_in_over"] == 2 and bowled["bowler_credited"]
    assert bowled["player_out_id"] == "id_a"
    assert runout["is_wicket"] and not runout["bowler_credited"]
    assert runout["phase"] == "death"
    assert four["bowling_team"] == "Chennai Super Kings"
    assert sum(r["runs_total"] for r in rows) == 6


def test_write_parquet_filters_gender(tmp_path):
    female = {**MATCH, "info": {**MATCH["info"], "gender": "female"}}
    n_m, n_d = write_parquet([("1", MATCH), ("2", female)], tmp_path)
    assert (n_m, n_d) == (1, 4)
    t = pq.read_table(tmp_path / "deliveries.parquet")
    assert t.num_rows == 4
    assert pq.read_table(tmp_path / "matches.parquet").num_rows == 1
