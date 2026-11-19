"""Parsing the IPL 2026 auction tables (a trimmed copy of the page's markup)."""

from gully_pipeline.auction_wiki import parse

PAGE = """
{| class="wikitable plainrowheaders"
|+ style="background:#{{IPL Team colors 1|kkr}}" | [[Kolkata Knight Riders|<span style="color:{{IPL Team colors 2|kkr}}">Kolkata Knight Riders</span>]]
|-
! scope="col" | No.
! scope="col" | Player
! scope="col" | Nationality
! scope="col" | Salary
|-
| 1
! scope="row" | {{sortname|Rinku|Singh}}
| {{cr|IND}} || {{INRConvert|13|c|lk=on}}
|-
| 2
! scope="row" | {{sortname|Anukul|Roy}}
| {{cr|IND}} || {{INRConvert|40|l|lk=on}}
|}

{| class="wikitable sortable plainrowheaders defaultcenter col2left col3left" style="font-size:85%;"
|+ Set 1: capped batters (BA1)
! scope="col" | No.
! scope="col" | Name
! scope="col" | Country
! scope="col" | No. of IPL matches
! scope="col" | Base price<br>({{INR|link=yes}}{{nbsp}}[[lakh]]s)
! scope="col" | 2026 IPL team
! scope="col" | Auctioned price<br>({{INR|link=yes}}{{nbsp}}[[lakh]]s)
! scope="col" | 2025 IPL team
|-
| 5
! scope="row" | {{sortname|David|Miller|dab=South African cricketer}}
| {{cr|SA}} || 141 || 200 || [[Delhi Capitals]] || 200 || [[Lucknow Super Giants]]
|-
| 3
! scope="row" | {{sortname|Cameron|Green}}
| {{cr|AUS}} || 29 || 200 || [[Kolkata Knight Riders]] || 2520 || {{N/A}}
|}

{| class="wikitable"
|+ Accelerated round
! scope="col" | No.
|-
| 81
! scope="row" | {{sortname|Ben|Dwarshuis}}
| {{cr|AUS}} || All-rounder || {{N/A}} || Capped || 100 || [[Punjab Kings]] || 440 || {{N/A}}
|}
"""


def test_parse_retentions_sets_and_accelerated_round():
    retained, sold = parse(PAGE)
    assert retained == [
        {"team": "KKR", "name": "Rinku Singh", "article": "Rinku Singh", "country": "India", "salary_lakh": 1300},
        {"team": "KKR", "name": "Anukul Roy", "article": "Anukul Roy", "country": "India", "salary_lakh": 40},
    ]
    assert [s["no"] for s in sold] == [3, 5, 81]                    # registration order
    green, miller, dwarshuis = sold
    assert green == {"no": 3, "set": "BA1", "name": "Cameron Green", "article": "Cameron Green",
                     "country": "Australia", "role": "BAT", "capped": True, "base_lakh": 200,
                     "team": "KKR", "price_lakh": 2520, "prev_team": None}
    assert miller["article"] == "David Miller (South African cricketer)" and miller["prev_team"] == "LSG"
    assert dwarshuis["set"] == "ACC" and dwarshuis["role"] == "AR" and dwarshuis["price_lakh"] == 440
