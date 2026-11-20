"""Parsing captain tables (trimmed copies of the pages' markup)."""

from gully_pipeline.captains import _sections, parse_ipl, parse_section

TEST_TABLE = """
===Test===
{|class="wikitable"
! Number !! Name !! Year !! Opposition !! Location !! Played !! Won !! Lost !! Drawn
|-
| rowspan=3 | 13
| rowspan=3 | [[Imran Khan]]<br />[[File:Imran.jpg|100px]]
| 1982 || [[England cricket team|England]] || England || 3 || 1 || 2 || 0
|-
|| 1988/89 || [[New Zealand]] || New Zealand || 2 || 0 || 0 || 2
|-
|| 1992 || [[England cricket team|England]] || England{{refn|[[Javed Miandad]] led in one Test}} || 5 || 2 || 1 || 2
|-bgcolor="#F5DEB3"
| colspan=3 | '''Total''' || '''10''' || '''3''' || '''3''' || '''4'''
|-
| rowspan=2 | 14
| rowspan=2 | [[Zaheer Abbas]]
|| 1983/84 || [[India national cricket team|India]] || India || 3 || 0 || 0 || 3
|-bgcolor="#F5DEB3"
| colspan=3 | '''Total''' || '''3''' || '''0''' || '''0''' || '''3'''
|-
| rowspan=2 | 15
| rowspan=2 | [[Javed Miandad]]
|| 1984 || [[Centenary Test]] || India || 2 || 1 || 0 || 1
|-bgcolor="#F5DEB3"
| colspan=3 | '''Total''' || '''2''' || '''1''' || '''0''' || '''1'''
|-
| colspan=5 | '''Grand total''' || '''15''' || '''4''' || '''3''' || '''8'''
|}

===One Day International captains===
{| class="wikitable"
! No. !! Name !! Period !! Played !! Won !! Tied !! Lost !! No<br />Result
|-
| 1 || [[Paul Collingwood]] || 2007–2010 || 30 || 17 || 0 || 11 || 2
|-
| 2 || [[Eoin Morgan]] || 2012–2022 || 72 || 42 || 2 || 27 || 1
|-
| colspan=3 | Total || 102 || 59 || 2 || 38 || 3
|}

==Women's==
===Test===
{| class="wikitable"
! Name !! Played !! Won
|-
| [[Someone Else]] || 9 || 9
|}
"""

IPL = """
{| class="wikitable"
! scope="col" | Player
! scope="col" | Nationality
! scope="col" | First
! scope="col" | Last
! scope="col" | Matches
! scope="col" | Team(s)
! scope="col" | Won
! scope="col" | Lost
! scope="col" | Tied
! scope="col" | NR
|-
! scope="row" | [[MS Dhoni]]
| {{cr|IND}} || 2008 || 2025
! 235
|| [[Chennai Super Kings|CSK]]
! 136
|| 97 || 0 || 2
|-
! scope="row" | {{sortname|David|Warner|dab=cricketer}}
| {{cr|AUS}} || 2013 || 2023
! 83
|| [[Delhi Capitals|DC]]
! 40
|| 41 || 2 || 0
|}
"""


def test_test_tables_read_each_captains_total():
    sections = dict(_sections(TEST_TABLE))
    assert set(sections) == {"Test", "ODI"}                         # women's section skipped
    tests = parse_section(sections["Test"])
    # Series rows, country links ([[New Zealand]]), footnotes naming someone else and
    # event links ([[Centenary Test]]) don't change who the total belongs to; the
    # grand total belongs to nobody.
    assert tests == {
        "Imran Khan": {"name": "Imran Khan", "matches": 10, "won": 3, "lost": 3, "tied": 0, "drawn": 4, "nr": 0},
        "Zaheer Abbas": {"name": "Zaheer Abbas", "matches": 3, "won": 0, "lost": 0, "tied": 0, "drawn": 3, "nr": 0},
        "Javed Miandad": {"name": "Javed Miandad", "matches": 2, "won": 1, "lost": 0, "tied": 0, "drawn": 1, "nr": 0},
    }


def test_odi_tables_read_columns_by_their_headings():
    odis = parse_section(dict(_sections(TEST_TABLE))["ODI"])
    assert odis["Eoin Morgan"] == {"name": "Eoin Morgan", "matches": 72, "won": 42, "lost": 27, "tied": 2, "drawn": 0, "nr": 1}
    assert len(odis) == 2                                           # the team total isn't a captain


def test_ipl_rows_and_sortname():
    ipl = parse_ipl(IPL)
    assert ipl["MS Dhoni"]["matches"] == 235 and ipl["MS Dhoni"]["lost"] == 97
    assert ipl["David Warner (cricketer)"]["won"] == 40 and ipl["David Warner (cricketer)"]["name"] == "David Warner"
