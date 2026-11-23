from gully_pipeline.styles import parse_styles

BOX = """{{Infobox cricketer
| name = Someone
| batting = {batting}
| bowling = {bowling}
}}
'''Someone''' is a cricketer."""


def styles(batting, bowling):
    return parse_styles(BOX.replace("{batting}", batting).replace("{bowling}", bowling))


def test_hands_and_types():
    assert styles("Left-handed", "Slow left-arm orthodox") == {
        "batting_hand": "L", "bowling_arm": "L", "bowling_type": "left-arm orthodox",
        "bowling_raw": "Slow left-arm orthodox"}
    s = styles("Right-handed", "Right-arm [[fast bowling|fast-medium]]")
    assert (s["batting_hand"], s["bowling_arm"], s["bowling_type"]) == ("R", "R", "fast-medium")
    assert styles("Right-handed", "Left-arm wrist spin")["bowling_type"] == "left-arm wrist-spin"


def test_spin_without_an_arm_is_right_arm():
    s = styles("Right-handed", "[[Leg break]] [[googly]]")
    assert (s["bowling_arm"], s["bowling_type"]) == ("R", "leg-spin")


def test_no_infobox_or_no_bowling():
    assert parse_styles("Just a page.") is None
    s = styles("Left-handed", "")
    assert s["batting_hand"] == "L" and s["bowling_type"] is None
