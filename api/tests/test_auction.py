"""Auction engine: rules, clock, passing, bots. No database: a synthetic pool."""

import random

import pytest

from gully_api.auction.pool import RULES, make_sets
from gully_api.auction.room import AuctionError, Room, increment

R = RULES["mega"]


def pool(n=120, seed=1):
    rng = random.Random(seed)
    roles = ["BAT"] * 30 + ["WK"] * 10 + ["AR"] * 25 + ["BOWL"] * 35
    out = []
    for i in range(n):
        role = roles[i % len(roles)]
        fair = max(30, int(2000 * 0.96 ** i))
        capped = i < n * 0.7
        out.append({"id": f"p{i}", "name": f"Player {i}", "short_name": f"P{i}", "role": role,
                    "country": "Australia" if i % 3 == 0 else "India", "overseas": i % 3 == 0,
                    "capped": capped, "spinner": False, "category": {"BAT": "BA", "WK": "WK", "AR": "AL", "BOWL": rng.choice(["FA", "SP"])}[role],
                    "fair": fair, "base": 200 if fair > 700 else 75 if capped else 30, "rank": i, "form": {}})
    return out


def room(teams=4, humans=1, n=120, speed="normal", seed=7):
    return Room("ABCDEF", "mega", R, pool(n), teams=teams, humans=humans, speed=speed, seed=seed)


def test_increments_follow_the_slabs():
    assert [increment(p, R) for p in (30, 95, 100, 190, 200, 480, 500, 2000)] == [5, 5, 10, 10, 20, 20, 25, 25]


def test_sets_marquee_first_then_categories():
    sets = make_sets(pool(), R)
    assert [c for c, _ in sets[:2]] == ["M1", "M2"]
    assert sum(len(s) for _, s in sets[:2]) == R["marquee"]
    assert all(len(s) <= R["set_size"] for _, s in sets)
    first_uncapped = next(i for i, (c, _) in enumerate(sets) if c.startswith("U"))
    assert all(not c.startswith("U") for c, _ in sets[:first_uncapped])


def test_only_host_starts_and_joiners_get_free_seats():
    r = room(teams=3, humans=2)
    guest = r.claim("Asha")
    assert not guest.bot and guest.owner == "Asha"
    with pytest.raises(AuctionError, match="taken"):
        r.claim("Late")
    with pytest.raises(AuctionError, match="host"):
        r.start(0, guest.token)
    r.start(0, r.host_token)
    assert r.phase == "live" and r.lot is not None


def me(r):
    return r.by_token(r.host_token)


def test_bidding_rules():
    r = room(teams=2, humans=2)
    other = r.claim("B")
    r.start(0, r.host_token)
    you = me(r)
    base = r.pool[r.lot.player]["base"]
    assert r.next_amount() == base
    r.bid(you.id, base, 1)
    with pytest.raises(AuctionError, match="already the highest"):
        r.bid(you.id, r.next_amount(), 2)
    with pytest.raises(AuctionError, match="next bid"):
        r.bid(other.id, base, 2)                         # stale amount: someone got in first
    r.bid(other.id, base + increment(base, R), 2)
    assert r.lot.leader == other.id and r.lot.ends_at == 2 + R["timers"]["normal"]["bid"]
    with pytest.raises(AuctionError, match="Too late"):
        r.bid(you.id, r.next_amount(), 100)


def test_hammer_sells_to_the_leader_and_charges_the_purse():
    r = room(teams=2, humans=2)
    r.claim("B")
    r.start(0, r.host_token)
    you, pid = me(r), r.lot.player
    r.bid(you.id, r.next_amount(), 1)
    price = r.lot.price
    r.tick(1 + R["timers"]["normal"]["bid"])
    assert you.squad == [{"id": pid, "price": price}] and you.purse == R["purse_lakh"] - price
    assert r.log[-1]["result"] == "sold" and r.lot.player != pid


def test_no_bid_means_unsold_then_accelerated_round():
    r = room(teams=2, humans=2, n=20)
    r.claim("B")
    r.start(0, r.host_token)
    t = 0
    while r.phase == "live" and not r.accelerated:
        t += 100
        r.tick(t)                                      # nobody bids anything
    assert r.accelerated and len(r.log) == 20 and all(e["result"] == "unsold" for e in r.log)
    while r.phase == "live":
        t += 100
        r.tick(t)
    assert r.phase == "ended" and len(r.log) == 40      # each player once more, then done


def test_overseas_cap_and_purse_reserve():
    r = room(teams=2, humans=2)
    r.claim("B")
    r.start(0, r.host_token)
    you = me(r)
    os_ids = [p for p in r.pool if r.pool[p]["overseas"]][: R["overseas_max"]]
    you.squad = [{"id": p, "price": 30} for p in os_ids]
    r.lot.player = next(p for p in r.pool if r.pool[p]["overseas"] and p not in os_ids)
    assert "overseas" in r.why_not(you)
    you.squad = []
    you.purse = (R["squad_min"] - 1) * min(R["base_prices"]) + 10   # just enough for the rest of the squad
    r.lot.player = next(p for p in r.pool if r.pool[p]["base"] == 200)
    assert "purse" in r.why_not(you)


def test_passing_lets_bots_settle_at_once():
    r = room(teams=4, humans=1)
    r.start(0, r.host_token)
    first = r.lot.player
    r.pass_(me(r).id)
    r.tick(0.1)                                        # no waiting for the clock
    assert r.lot.player != first and r.log[-1]["player"] == first


def test_leader_cannot_pass():
    r = room(teams=2, humans=2)
    r.claim("B")
    r.start(0, r.host_token)
    r.bid(me(r).id, r.next_amount(), 1)
    with pytest.raises(AuctionError, match="can't pass"):
        r.pass_(me(r).id)


def run_all_bots(teams, n, seed):
    """Host passes every lot: a whole auction settled by bots."""
    r = Room("ZZZZZZ", "mega", R, pool(n, seed), teams=teams, humans=1, seed=seed)
    r.start(0, r.host_token)
    t, steps = 0.0, 0
    while r.phase == "live":
        if r.lot and me(r).id not in r.lot.passed and r.lot.leader != me(r).id:
            r.pass_(me(r).id)
        t += 0.5
        r.tick(t)
        steps += 1
        assert steps < 100_000
    return r


@pytest.mark.parametrize("teams,n,seed", [(10, 280, 1), (6, 180, 2), (4, 120, 3)])
def test_bots_never_break_the_rules(teams, n, seed):
    r = run_all_bots(teams, n, seed)
    assert r.phase == "ended"
    sold = [e["player"] for e in r.log if e["result"] == "sold"]
    assert len(sold) == len(set(sold))                 # nobody bought twice
    for f in r.franchises.values():
        assert f.purse >= 0
        assert len(f.squad) <= R["squad_max"]
        assert f.count(r.pool, overseas=True) <= R["overseas_max"]
        assert f.purse == R["purse_lakh"] - sum(s["price"] for s in f.squad)
    bots = [f for f in r.franchises.values() if f.bot]
    assert sum(len(f.squad) >= R["squad_min"] for f in bots) >= len(bots) - 1   # bots fill their squads
    assert max(e["price"] for e in r.log if e["result"] == "sold") > 500           # stars still go for crores


def test_view_hides_secrets():
    r = room(teams=3, humans=2)
    r.claim("B")
    r.start(0, r.host_token)
    v = str(r.view())
    assert r.host_token not in v and "token" not in v


def test_offline_friends_dont_hold_up_lots():
    r = room(teams=3, humans=2)
    r.claim("Away")
    r.start(0, r.host_token)
    r.online = {me(r).id}                              # the friend has closed the tab
    first = r.lot.player
    r.pass_(me(r).id)
    r.tick(0.1)
    assert r.lot.player != first


def test_summary_counts_each_unsold_player_once():
    r = room(teams=2, humans=2, n=20)
    r.claim("B")
    r.start(0, r.host_token)
    t = 0
    while r.phase == "live":
        t += 100
        r.tick(t)
    assert r.summary()["unsold"] == 20 and r.summary()["sold"] == 0


def test_humans_choose_from_the_rooms_franchises():
    r = room(teams=4, humans=2)
    you = me(r)
    bot_team = next(f.id for f in r.franchises.values() if f.bot)
    old = you.id
    r.choose(you, bot_team)                            # swap with a bot
    assert you.id == bot_team and not r.franchises[bot_team].bot
    assert r.franchises[old].bot and len(r.franchises) == 4
    with pytest.raises(AuctionError, match="isn't in this room"):
        r.choose(you, next(fid for fid, _ in __import__("gully_api.auction.room", fromlist=["FRANCHISES"]).FRANCHISES
                           if fid not in r.franchises))
    friend = r.claim("Asha", old)                       # join straight into a chosen team
    assert friend.id == old
    with pytest.raises(AuctionError, match="already taken by Asha"):
        r.choose(you, old)
    r.start(0, r.host_token)
    with pytest.raises(AuctionError, match="fixed"):
        r.choose(you, friend.id)


def test_view_does_not_reveal_bot_personalities():
    r = room(teams=4, humans=1)
    assert "personality" not in str(r.view()) and "aggressive" not in str(r.view())
