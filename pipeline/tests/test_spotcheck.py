import json
import zipfile

import duckdb

from gully_pipeline import spotcheck
from gully_pipeline.aggregate import build
from gully_pipeline.parse import iter_zip_matches, write_parquet
from test_parse import MATCH


def _setup(tmp_path):
    z = tmp_path / "all_json.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("1.json", json.dumps(MATCH))
        zf.writestr("README.txt", "ignored")
    write_parquet(iter_zip_matches(z), tmp_path / "pq")
    people = tmp_path / "people.csv"
    people.write_text("identifier,name,unique_name,key_cricinfo\n"
                      "id_a,A Batter,A Batter,1\nid_b,B Runner,B Runner,2\n"
                      "id_c,C Bowler,C Bowler,3\n")
    db = tmp_path / "t.duckdb"
    build(tmp_path / "pq", people, db)
    return z, db


def test_spotcheck_agrees_on_fixture(tmp_path):
    z, db = _setup(tmp_path)
    rows = spotcheck.run(z, db, ["A Batter", "B Runner", "C Bowler"])
    assert rows and all(r["table"] == r["raw"] for r in rows)
    c_ipl = {r["field"]: r["raw"] for r in rows if r["player"] == "C Bowler" and r["format"] == "IPL"}
    assert (c_ipl["balls_bowled"], c_ipl["runs_conceded"], c_ipl["wickets"]) == (3, 6, 1)


def test_spotcheck_detects_tampering(tmp_path):
    z, db = _setup(tmp_path)
    with duckdb.connect(str(db)) as con:
        con.execute("UPDATE player_format_stats SET runs = runs + 1 "
                    "WHERE player_id = 'id_a' AND format = 'T20'")
    bad = [r for r in spotcheck.run(z, db, ["A Batter"]) if r["table"] != r["raw"]]
    assert [(r["format"], r["field"]) for r in bad] == [("T20", "runs")]
