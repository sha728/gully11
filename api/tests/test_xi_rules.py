"""XI draft rules and board logic: no database needed."""

import pytest

from gully_api.xi import service
from gully_api.xi.draft import Draft


def c(cid, role, **kw):
    d = {"id": cid, "person": cid, "name": cid, "role": role, "country": "India", **kw}
    return {**d, "slots": service.eligible_slots(d)}


def spin(n, *cands):
    return {"spin": n, "era": "2010s", "side": "India", "candidates": list(cands)}


# One clear player per role across eleven spins.
SPINS = [spin(1, c("o1", "BAT", opener=True)), spin(2, c("o2", "BAT", opener=True)),
         spin(3, c("b3", "BAT")), spin(4, c("b4", "BAT")), spin(5, c("b5", "BAT")),
         spin(6, c("wk", "WK")), spin(7, c("ar7", "AR")), spin(8, c("sp8", "BOWL", spinner=True)),
         spin(9, c("p9", "BOWL")), spin(10, c("p10", "BOWL")), spin(11, c("p11", "BOWL"))]


def test_rules_unit():
    ok = [{"person": str(i), "role": r, "country": "India"}
          for i, r in enumerate(["BAT"] * 5 + ["WK"] + ["BOWL"] * 5)]
    service.check_rules("IPL", ok)
    with pytest.raises(service.DraftError, match="wicketkeeper"):
        service.check_rules("ODI", [dict(r, role="BAT") if r["role"] == "WK" else r for r in ok])
    with pytest.raises(service.DraftError, match="five bowling"):
        service.check_rules("ODI", [dict(r, role="BAT") if i == 6 else r for i, r in enumerate(ok)])
    with pytest.raises(service.DraftError, match="twice"):
        service.check_rules("ODI", ok[:10] + [dict(ok[0])])
    os5 = [dict(r, country="Australia") if i < 5 else r for i, r in enumerate(ok)]
    with pytest.raises(service.DraftError, match="overseas"):
        service.check_rules("IPL", os5)
    service.check_rules("ODI", os5)                              # overseas cap is IPL-only


def test_eligible_slots_unit():
    slots = service.eligible_slots
    assert slots({"role": "BAT", "opener": True}) == [1, 2, 3, 4, 5, 6]
    assert slots({"role": "BAT", "opener": False}) == [3, 4, 5, 6]
    assert slots({"role": "WK", "opener": True}) == [1, 2, 3, 4, 5, 6]
    assert slots({"role": "AR"}) == [3, 4, 5, 6, 7, 8, 9, 10, 11]
    assert slots({"role": "BOWL", "spinner": True}) == [7, 8, 9, 10, 11]
    assert slots({"role": "BOWL", "spinner": False}) == [9, 10, 11]


def test_keeper_must_bat_in_top_six():
    xi = [{"person": str(i), "role": r, "country": "India", "slot": i + 1}
          for i, r in enumerate(["BAT"] * 5 + ["BAT", "AR", "AR"] + ["BOWL"] * 3)]
    with pytest.raises(service.DraftError, match="wicketkeeper"):
        service.check_rules("ODI", xi)
    service.check_rules("ODI", [dict(xi[0], role="WK")] + xi[1:])    # keeper opens, 6 is a batter
    with pytest.raises(service.DraftError, match="top six"):
        service.check_rules("ODI", xi[:8] + [dict(xi[8], role="WK")] + xi[9:])


def test_feasibility_needs_every_slot():
    full = [s["candidates"] for s in SPINS]
    assert service._feasible(full)
    assert not service._feasible([[c("x", "BAT")]] + full[1:])          # only one opener
    assert not service._feasible(full[:5] + [[c("x", "BAT")]] + full[6:])  # no keeper
    assert not service._feasible(full[:8] + [[c("x", "BAT")]] + full[9:])  # a bowler short


def play_all(d: Draft) -> Draft:
    for i in range(11):
        d = Draft("ODI", SPINS, d.picks, i + 1)
        d = Draft("ODI", SPINS, d.pick(i, SPINS[i]["candidates"][0]["id"], None), i + 1)
    return d


def test_picks_go_to_their_natural_slot():
    d = play_all(Draft("ODI", SPINS, [None] * 11, 0))
    assert [p["slot"] for p in d.picks] == list(range(1, 12))
    assert d.status()["ready"]


def test_a_pick_that_strands_later_spins_is_refused():
    # Spin 1 is an all-rounder who opens. Openers also come at spins 2 and 7, but
    # 7-8 need an all-rounder or spinner and only spins 1 and 8 offer one, so spin
    # 1's player has to bat at 7 or 8.
    spins = ([spin(1, c("ao", "AR", opener=True))] + SPINS[1:6]
             + [spin(7, c("o3", "BAT", opener=True))] + SPINS[7:])
    d = Draft("ODI", spins, [None] * 11, 1)
    options, why = d.options(0, spins[0]["candidates"][0])
    assert why is None and options == [7, 8]
    with pytest.raises(service.DraftError, match="impossible"):
        d.pick(0, "ao", 1)


def test_view_hides_unrevealed_spins():
    d = Draft("ODI", SPINS, [None] * 11, 1)
    v = d.view()
    assert len(v["spins"]) == 1 and v["waiting"] and not v["can_spin"]
    assert "o2" not in str(v) and "wk" not in str(v)


def test_moves_respect_positions():
    d = play_all(Draft("ODI", SPINS, [None] * 11, 0))
    assert d.moved(3, 4) is not None                 # batters swap freely
    assert d.moved(11, 1) is None                    # a pace bowler can't open
    assert d.moved(8, 9) is None                     # ...or bat at 8 (spinner to 9 alone is fine)
    assert d.moved(6, 1) is None                     # this keeper isn't an opener
    keeper_up = d.moved(6, 3)                        # keeper to 3, batter to 6: keeper still top six
    assert keeper_up is not None
    with pytest.raises(service.DraftError):
        d.move(11, 1)
