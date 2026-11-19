import csv

from gully_pipeline import legends
from gully_pipeline.legends import bowling, num, role, rows_for

WIKITEXT = """
{{Short description|Cricketer}}
{{Infobox cricketer
| name = Test Legend
| batting = Left-handed
| bowling = {{ubl|Right-arm [[off break]]|Right-arm medium}}
| role = [[All-rounder]]
| test_debut_year = 1975
| last_test_year = 1990
| odi_debut_year = 1979
| columns = 3
| column1 = [[Test cricket|Tests]]
| matches1 = 100
| runs1 = 5,000
| bat avg1 = 40.00
| 100s/50s1 = 10/25
| top score1 = 250[[not out|*]]
| deliveries1 = 6,000
| wickets1 = 200
| bowl avg1 = 25.50
| best bowling1 = 7/40
| catches/stumpings1 = 80/–
| column2 = [[One Day International|ODI]]
| matches2 = 1
| runs2 = 12
| bat avg2 = 12.00
| 100s/50s2 = 0/0
| top score2 = 12
| deliveries2 = –
| wickets2 = –
| bowl avg2 = –
| best bowling2 = –
| catches/stumpings2 = 0/–
| column3 = [[First-class cricket|FC]]
| matches3 = 300
}}
"""


def test_helpers():
    assert num("15,921") == 15921 and num("248[[not out|*]]") == 248 and num("–") is None
    assert bowling("Right-arm [[off break]]") == ("R", "off-spin")
    assert bowling("Slow left arm orthodox") == ("L", "left-arm orthodox")
    assert bowling("Left-arm unorthodox spin") == ("L", "left-arm wrist-spin")
    assert bowling("Right-arm fast-medium") == ("R", "fast-medium")
    assert bowling("Right arm fast") == ("R", "fast")
    assert bowling("Right-arm slow seam; off-break") == ("R", "medium")
    assert role("Wicket-keeper-batter") == "WK" and role("Batting all-rounder") == "AR"
    assert role("Bowler") == "BOWL" and role("Opening batsman") == "BAT" and role("") is None


def test_rows_for_infobox():
    rows = rows_for({"title": "Test Legend (cricketer)", "revid": 42, "wikitext": WIKITEXT},
                    "Nowhere")
    assert [r["format"] for r in rows] == ["Test", "ODI"]  # FC column ignored
    t, o = rows
    assert t["name"] == "Test Legend" and t["matches"] == 100 and t["runs"] == 5000
    assert (t["hundreds"], t["fifties"], t["highest"], t["highest_not_out"]) == (10, 25, 250, True)
    assert (t["catches"], t["stumpings"]) == (80, None)
    assert t["bowl_econ"] == 5.1 and t["bowl_sr"] == 30.0  # 6*25.5*200/6000
    assert t["derived_fields"] == "bowl_econ;bowl_sr"
    assert (t["role"], t["role_source"], t["batting_hand"]) == ("AR", "wikipedia", "L")
    assert (t["bowling_arm"], t["bowling_type"]) == ("R", "off-spin")
    assert (t["era_start"], t["era_end"]) == (1975, 1990)
    assert o["format_end"] == 1979  # single ODI: no last year, falls back to debut
    assert o["wickets"] is None and o["bowl_econ"] is None
    assert t["source_url"].endswith("oldid=42")


def test_role_override_only_fills_gaps():
    no_role = WIKITEXT.replace("| role = [[All-rounder]]\n", "")
    page = {"title": "X", "revid": 1, "wikitext": no_role}
    assert rows_for(page, "N", "BAT")[0]["role_source"] == "manual"
    page = {"title": "X", "revid": 1, "wikitext": WIKITEXT}
    assert rows_for(page, "N", "BAT")[0]["role"] == "AR"  # sourced value wins


def test_committed_csv_is_complete():
    with legends.LEGENDS_CSV.open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    with legends.SEED_CSV.open(encoding="utf-8") as f:
        seeds = list(csv.DictReader(f))
    assert len({r["name"] for r in rows}) == len(seeds) >= 50
    assert all(r["source_url"].startswith("https://en.wikipedia.org/w/index.php?oldid=")
               for r in rows)
    assert all(r["role"] and r["matches"] and r["era_start"] for r in rows)
