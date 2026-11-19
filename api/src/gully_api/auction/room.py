"""Auction room: the rules engine and bots, with no I/O.

Time is passed in (``now``, seconds), so the whole auction can be driven by a test
clock. The live layer (``live.py``) calls ``tick`` a few times a second and
broadcasts ``view()`` to everyone in the room.

Flow: lobby → live (lot after lot, set by set) → accelerated round (unsold players
again, shorter clock) → ended. Each lot opens at the player's base price; any
franchise can bid the next increment; each bid resets the clock. When it runs
out, the player is sold to the highest bidder or goes unsold.

Every bid is checked: not already leading, squad not full, overseas cap, and
enough purse left to fill the rest of the minimum squad at the lowest base price.

A franchise can **pass** on a lot. Once every human has passed (or can't bid),
the bots settle the lot at once, so a game with bots only takes time on the
players people actually want.
"""

from __future__ import annotations

import random
import secrets
import string
from dataclasses import dataclass, field

from .pool import make_sets, set_label

FRANCHISES = [
    ("CSK", "Chennai Super Kings"), ("MI", "Mumbai Indians"), ("RCB", "Royal Challengers Bengaluru"),
    ("KKR", "Kolkata Knight Riders"), ("SRH", "Sunrisers Hyderabad"), ("RR", "Rajasthan Royals"),
    ("DC", "Delhi Capitals"), ("PBKS", "Punjab Kings"), ("GT", "Gujarat Titans"), ("LSG", "Lucknow Super Giants"),
]

# How bots build a squad (players per role) and how freely they spend.
SQUAD_PLAN = {"BAT": 6, "WK": 2, "AR": 5, "BOWL": 8}
PERSONALITIES = {"aggressive": 1.25, "balanced": 1.0, "value": 0.82}
RICH_PER_SLOT = 560        # lakh per open squad slot that counts as an ordinary budget (120 cr / 21)
MAX_OVER_FAIR = 1.3        # bots pay at most this times the fair price, plus their richness
# Chance a bot has a player on its shortlist: by how short it is of that role.
INTEREST = {"short": 0.5, "some": 0.35, "covered": 0.12}


class AuctionError(ValueError):
    """A move the rules don't allow (message says why)."""


def increment(price: int, rules: dict) -> int:
    for limit, step in rules["increments"]:
        if limit is None or price < limit:
            return step
    raise AssertionError("increments must end with an open slab")


@dataclass
class Franchise:
    id: str
    name: str
    bot: bool
    purse: int
    start_purse: int = 0                 # purse going into the auction (after retentions in mini mode)
    personality: str = "balanced"
    owner: str | None = None             # nickname of the human who claimed it
    token: str | None = None             # secret the human's client holds
    squad: list[dict] = field(default_factory=list)   # {"id", "price", "retained"?}

    def count(self, pool: dict, role: str | None = None, overseas: bool | None = None) -> int:
        return sum(1 for s in self.squad
                   if (role is None or pool[s["id"]]["role"] == role)
                   and (overseas is None or pool[s["id"]]["overseas"] == overseas))


@dataclass
class Lot:
    player: str
    set_code: str
    accelerated: bool
    ends_at: float
    price: int | None = None             # current highest bid; None until someone bids
    leader: str | None = None
    bids: list[dict] = field(default_factory=list)
    passed: set[str] = field(default_factory=set)


class Room:
    def __init__(self, code: str, mode: str, rules: dict, pool: list[dict], teams: int, humans: int,
                 speed: str = "normal", seed: int | None = None, host: str = "Host",
                 replay: dict | None = None):
        """``replay`` (mini mode, from ``mini.build_mini``): fixed lots in real order,
        all ten franchises with their retained squads and purses, and the real
        outcomes, which stay hidden until the summary."""
        if replay:
            teams = len(FRANCHISES)
        if not 2 <= teams <= len(FRANCHISES):
            raise AuctionError(f"Between 2 and {len(FRANCHISES)} franchises.")
        if not 1 <= humans <= teams:
            raise AuctionError("At least one franchise has to be yours.")
        self.code, self.mode, self.rules, self.speed = code, mode, rules, speed
        self.rng = random.Random(seed)
        self.real: dict[str, dict] = {}
        if replay:
            pool = [e for _, e in replay["lots"]]
            self.pool = {p["id"]: p for p in pool} | replay["players"]
            self.queue: list[tuple[str, str]] = [(c, e["id"]) for c, e in replay["lots"]]
            self.real = replay["real"]
        else:
            self.pool = {p["id"]: p for p in pool}
            # Sets in order; players shuffled within each set, as at the real auction.
            self.queue = []
            for set_code, players in make_sets(pool, rules):
                ids = [p["id"] for p in players]
                self.rng.shuffle(ids)
                self.queue += [(set_code, pid) for pid in ids]
        self.fair_total = sum(p["fair"] for p in pool) or 1
        self.fair_seen = 0                   # fair value of the lots shown so far (bots pace spending on it)
        self.total_lots = len(self.queue)
        picks = FRANCHISES if replay else self.rng.sample(FRANCHISES, teams)
        kinds = list(PERSONALITIES)
        self.franchises: dict[str, Franchise] = {}
        for i, (fid, name) in enumerate(picks):
            purse = replay["purse"][fid] if replay else rules["purse_lakh"]
            self.franchises[fid] = Franchise(fid, name, bot=i >= humans, purse=purse, start_purse=purse,
                                             personality=self.rng.choice(kinds),
                                             squad=[dict(s) for s in replay["squads"][fid]] if replay else [])
        self.phase = "lobby"
        self.lot: Lot | None = None
        self.accelerated = False
        self.log: list[dict] = []            # sold / unsold, newest last
        self.unsold: list[str] = []
        self.presented = 0
        self.main_presented = 0              # lots shown before the accelerated round
        self.version = 0
        self.host_token: str | None = None
        self.online: set[str] | None = None  # franchises with someone connected (None = assume all)
        self._bot_due: dict[str, float] = {}
        self._noise: dict[tuple[str, str], float] = {}
        self._interest: dict[tuple[str, str], float] = {}
        first = self.claim(host)
        self.host_token = first.token

    # ------------------------------------------------------------ people
    def claim(self, nickname: str, want: str | None = None) -> Franchise:
        """A human joins and takes a free seat; ``want`` picks which of the room's
        franchises it is (see ``choose``)."""
        nickname = nickname.strip()[:24] or "Player"
        if want:
            self._check_choice(want)
        f = next((f for f in self.franchises.values() if not f.bot and f.owner is None), None)
        if f is None:
            raise AuctionError("Every franchise is taken. Ask the host to add more seats.")
        f.owner, f.token = nickname, secrets.token_urlsafe(16)
        if want:
            self.choose(f, want)
        self._touch()
        return f

    def _check_choice(self, fid: str) -> Franchise:
        if self.phase != "lobby":
            raise AuctionError("Teams are fixed once the auction starts.")
        other = self.franchises.get(fid)
        if other is None:
            raise AuctionError("That franchise isn't in this room.")
        if other.owner:
            raise AuctionError(f"{other.name} is already taken by {other.owner}.")
        return other

    def choose(self, f: Franchise, fid: str) -> None:
        """Before the start, a human picks which of the room's franchises they are:
        they swap with the bot (or empty friend's seat) that holds it."""
        if fid == f.id:
            return
        other = self._check_choice(fid)
        other.id, other.name, f.id, f.name = f.id, f.name, other.id, other.name
        self.franchises = {x.id: x for x in self.franchises.values()}
        self._touch()

    def by_token(self, token: str | None) -> Franchise | None:
        return next((f for f in self.franchises.values() if token and f.token == token), None)

    # ------------------------------------------------------------ timing
    def _timer(self, kind: str) -> float:
        t = self.rules["timers"][self.speed]
        return t[f"accelerated_{kind}" if self.accelerated else kind]

    def start(self, now: float, token: str | None) -> None:
        if token != self.host_token:
            raise AuctionError("Only the host can start the auction.")
        if self.phase != "lobby":
            raise AuctionError("The auction has already started.")
        for f in self.franchises.values():           # empty human seats become bots
            if not f.bot and f.owner is None:
                f.bot = True
        self.phase = "live"
        self._next_lot(now)

    def _next_lot(self, now: float) -> None:
        self.lot = None
        if all(len(f.squad) >= self.rules["squad_max"] for f in self.franchises.values()):
            return self._end()
        while not self.queue:
            needy = any(len(f.squad) < self.rules["squad_min"] for f in self.franchises.values())
            if self.accelerated or not self.unsold or not needy:
                return self._end()
            # Accelerated round: the unsold players again, best first, shorter clock.
            self.accelerated = True
            self.main_presented = self.presented
            again = sorted(self.unsold, key=lambda pid: -self.pool[pid]["fair"])
            self.unsold = []
            self.queue = [("ACC", pid) for pid in again]
        if self.queue[0][0] == "ACC" and not self.accelerated:
            # The real auction's accelerated round (mini mode): players unsold so far
            # come back at the end of it.
            self.accelerated = True
            self.main_presented = self.presented
            self.queue += [("ACC", pid) for pid in self.unsold]
            self.unsold = []
        set_code, pid = self.queue.pop(0)
        self.presented += 1
        if not self.accelerated:
            self.fair_seen += self.pool[pid]["fair"]
        self.lot = Lot(pid, set_code, self.accelerated, ends_at=now + self._timer("open"))
        self._bot_due = {}
        self._touch()

    def _end(self) -> None:
        self.phase = "ended"
        self.lot = None
        self._touch()

    def _touch(self) -> None:
        self.version += 1

    # ------------------------------------------------------------ bidding
    def next_amount(self) -> int:
        lot = self._open_lot()
        base = self.pool[lot.player]["base"]
        return base if lot.price is None else lot.price + increment(lot.price, self.rules)

    def _open_lot(self) -> Lot:
        if self.phase != "live" or self.lot is None:
            raise AuctionError("No player is up right now.")
        return self.lot

    def why_not(self, f: Franchise, amount: int | None = None) -> str | None:
        """Why this franchise can't bid ``amount`` on the current lot, or None."""
        lot = self._open_lot()
        amount = self.next_amount() if amount is None else amount
        p = self.pool[lot.player]
        r = self.rules
        if lot.leader == f.id:
            return "You're already the highest bidder."
        if len(f.squad) >= r["squad_max"]:
            return f"Your squad is full ({r['squad_max']})."
        if p["overseas"] and f.count(self.pool, overseas=True) >= r["overseas_max"]:
            return f"You already have {r['overseas_max']} overseas players."
        still_needed = max(0, r["squad_min"] - len(f.squad) - 1)
        reserve = still_needed * min(r["base_prices"])
        if self.charge(lot.player, amount) > f.purse - reserve:
            return (f"Not enough purse: you need to keep ₹{reserve / 100:g} cr to fill your squad."
                    if reserve else "Not enough purse.")
        return None

    def charge(self, pid: str, price: int) -> int:
        """What the franchise pays: an overseas player's fee is capped in mini mode
        (bids can go higher; the team doesn't pay the excess)."""
        cap = self.rules.get("overseas_fee_cap")
        return min(price, cap) if cap and self.pool[pid]["overseas"] else price

    def bid(self, fid: str, amount: int, now: float) -> None:
        lot = self._open_lot()
        f = self.franchises[fid]
        if now >= lot.ends_at:
            raise AuctionError("Too late: the hammer has come down.")
        want = self.next_amount()
        if amount != want:
            raise AuctionError(f"The next bid is ₹{want / 100:g} cr.")   # someone got in first
        reason = self.why_not(f, amount)
        if reason:
            raise AuctionError(reason)
        self._apply(fid, amount, now)

    def _apply(self, fid: str, amount: int, now: float) -> None:
        lot = self.lot
        lot.price, lot.leader = amount, fid
        lot.bids.append({"franchise": fid, "amount": amount, "at": now})
        lot.passed.discard(fid)
        lot.ends_at = now + self._timer("bid")
        self._bot_due = {}
        self._touch()

    def pass_(self, fid: str) -> None:
        lot = self._open_lot()
        if lot.leader == fid:
            raise AuctionError("You're the highest bidder: you can't pass.")
        lot.passed.add(fid)
        self._touch()

    # ------------------------------------------------------------ bots
    def bot_limit(self, f: Franchise, pid: str) -> int:
        """The most this bot will pay for the player (0 = not interested)."""
        p = self.pool[pid]
        r = self.rules
        have = f.count(self.pool, role=p["role"])
        plan = SQUAD_PLAN[p["role"]]
        level = "short" if have < plan / 2 else "some" if have < plan else "covered"
        need = {"short": 1.1, "some": 1.0, "covered": 0.45}[level]
        slots_left = r["squad_max"] - len(f.squad)
        short = r["squad_min"] - len(f.squad)
        filling = short > 0 and self.lots_left() <= short * 3   # running out of players
        if filling:
            need = max(need, 1.2)
        if slots_left <= 0:
            return 0
        key = (f.id, pid)
        if key not in self._noise:
            # Each bot rates each player its own way and only chases its shortlist,
            # so a lot draws a few keen bidders, not the whole room.
            self._noise[key] = self.rng.uniform(0.65, 1.15)
            self._interest[key] = self.rng.random()
        # Money burns a hole: plenty of purse per slot still to fill means bidding harder
        # and on more players.
        planned = max(1, sum(SQUAD_PLAN.values()) - len(f.squad))
        rich = min(max((f.purse / planned) / RICH_PER_SLOT, 0.8), 5.0) ** 0.85
        rich *= self._pace(f)
        if self._interest[key] > min(0.95, INTEREST[level] * rich) and not filling:
            return 0
        limit = p["fair"] * need * rich * PERSONALITIES[f.personality] * self._noise[key]
        limit = min(limit, p["fair"] * (MAX_OVER_FAIR + rich - 1))
        if filling:
            limit = max(limit, p["base"])     # short of a legal squad late on: anyone at base
        reserve = max(0, r["squad_min"] - len(f.squad) - 1) * min(r["base_prices"])
        # Don't blow the purse on one player while the squad is still thin.
        spread = (f.purse - reserve) / max(1, min(short, 6)) * 2 if short > 1 else f.purse - reserve
        return int(min(limit, f.purse - reserve, max(spread, p["base"])))

    def _pace(self, f: Franchise) -> float:
        """Above 1 when a bot has spent a smaller share of its purse than the share of
        the pool's value already auctioned: it chases more players, harder."""
        seen = self.fair_seen / self.fair_total
        if seen < 0.15:
            return 1.0
        spent = 1 - f.purse / max(1, f.start_purse)
        return min(max((seen + 0.05) / (spent + 0.05), 1.0), 1.8) ** 0.7

    def lots_left(self) -> int:
        return len(self.queue) + (len(self.unsold) if not self.accelerated else 0)

    def _bot_wants(self, f: Franchise) -> bool:
        if not f.bot or self.lot is None:
            return False
        amount = self.next_amount()
        return self.why_not(f, amount) is None and self.bot_limit(f, self.lot.player) >= amount

    def _bots_act(self, now: float) -> None:
        lot = self.lot
        for f in self.franchises.values():
            if not self._bot_wants(f):
                self._bot_due.pop(f.id, None)
                continue
            if f.id not in self._bot_due:
                self._bot_due[f.id] = now + self._bot_delay()
        due = [(t, fid) for fid, t in self._bot_due.items() if t <= now and t < lot.ends_at]
        if due:
            _, fid = min(due)
            self.bid(fid, self.next_amount(), now)

    def _bot_delay(self) -> float:
        """Bots answer quickly when only bots are in the bidding (a human isn't
        watching for a chance to come in), and more like a person otherwise."""
        lot = self.lot
        humans_in = any(not self.franchises[b["franchise"]].bot for b in lot.bids)
        fast = self.speed == "fast"
        if not humans_in and lot.bids:
            return self.rng.uniform(0.25, 0.7) if fast else self.rng.uniform(0.4, 1.0)
        return self.rng.uniform(0.6, 1.8) if fast else self.rng.uniform(1.0, 3.0)

    def _humans_done(self) -> bool:
        """No human can still act on this lot: settle it with the bots at once."""
        lot = self.lot
        for f in self.franchises.values():
            if f.bot:
                continue
            if lot.leader == f.id:
                return False
            if self.online is not None and f.id not in self.online:
                continue                     # nobody at this franchise's table right now
            if f.id not in lot.passed and self.why_not(f) is None:
                return False
        return True

    def _settle_with_bots(self, now: float) -> None:
        while True:
            wanting = [f for f in self.franchises.values() if self._bot_wants(f)]
            if not wanting:
                return
            f = self.rng.choice(wanting)
            self._apply(f.id, self.next_amount(), now)

    # ------------------------------------------------------------ clock
    def tick(self, now: float) -> None:
        if self.phase != "live" or self.lot is None:
            return
        if self._humans_done():
            self._settle_with_bots(now)
            return self._hammer(now)
        if now >= self.lot.ends_at:
            return self._hammer(now)
        self._bots_act(now)

    def _hammer(self, now: float) -> None:
        lot = self.lot
        p = self.pool[lot.player]
        if lot.leader:
            f = self.franchises[lot.leader]
            paid = self.charge(lot.player, lot.price)
            f.purse -= paid
            f.squad.append({"id": lot.player, "price": lot.price, **({"paid": paid} if paid != lot.price else {})})
            self.log.append({"player": lot.player, "name": p["name"], "result": "sold", "franchise": f.id,
                             "price": lot.price, "fair": p["fair"], "bids": len(lot.bids)})
        else:
            if not lot.accelerated:
                self.unsold.append(lot.player)
            self.log.append({"player": lot.player, "name": p["name"], "result": "unsold", "base": p["base"]})
        self._next_lot(now)

    # ------------------------------------------------------------ views
    def view(self) -> dict:
        """Everything a client may see (no tokens, no bot limits)."""
        lot = self.lot
        upcoming = [pid for _, pid in self.queue[:6]]
        out = {
            "code": self.code, "mode": self.mode, "mode_name": self.rules.get("name", self.mode),
            "phase": self.phase, "speed": self.speed,
            "version": self.version, "accelerated": self.accelerated,
            "presented": self.presented, "total": self.total_lots,
            # Position within the current round: main pass, or the accelerated round.
            "round": ({"n": self.presented - self.main_presented, "of": self.presented - self.main_presented + len(self.queue)}
                      if self.accelerated else {"n": self.presented, "of": self.total_lots}),
            "rules": {k: self.rules.get(k) for k in ("purse_lakh", "squad_min", "squad_max", "overseas_max",
                                                      "increments", "overseas_fee_cap")},
            "franchises": [{
                "id": f.id, "name": f.name, "bot": f.bot, "owner": f.owner,
                "purse": f.purse, "start_purse": f.start_purse, "squad": f.squad, "size": len(f.squad),
                "overseas": f.count(self.pool, overseas=True),
                "roles": {r: f.count(self.pool, role=r) for r in SQUAD_PLAN},
            } for f in self.franchises.values()],
            "lot": None if lot is None else {
                "player": self.pool[lot.player], "set": lot.set_code,
                "set_label": "Accelerated round" if lot.accelerated else set_label(lot.set_code),
                "price": lot.price, "leader": lot.leader, "ends_at": lot.ends_at,
                "next": self.next_amount(), "bids": lot.bids[-8:], "passed": sorted(lot.passed),
            },
            "upcoming": [self.pool[pid] for pid in upcoming],
            "log": self.log[-30:],
            "players": {s["id"]: self.pool[s["id"]] for f in self.franchises.values() for s in f.squad},
        }
        if self.phase == "ended":
            out["result"] = self.summary()
        return out

    def summary(self) -> dict:
        """The finished auction: squads, spend and the best value buys."""
        sold = [e for e in self.log if e["result"] == "sold"]
        value = sorted(sold, key=lambda e: e["fair"] - e["price"], reverse=True)[:5]
        out = {
            "franchises": [{"id": f.id, "name": f.name, "bot": f.bot, "owner": f.owner,
                            "spent": f.start_purse - f.purse, "purse": f.purse,
                            "squad": [{**s, "player": self.pool[s["id"]]} for s in f.squad]}
                           for f in self.franchises.values()],
            "sold": len(sold),
            # Players never sold (one passed over twice, main and accelerated round, counts once).
            "unsold": len({e["player"] for e in self.log if e["result"] == "unsold"} - {e["player"] for e in sold}),
            "best_value": value,
        }
        if self.real:
            # Mini mode: every lot next to what really happened in Abu Dhabi.
            final = {}
            for e in self.log:
                final[e["player"]] = e
            out["reality"] = [{
                "player": pid, "name": self.pool[pid]["name"],
                "real_team": real["team"], "real_price": real["price"],
                "team": final[pid].get("franchise") if pid in final else None,
                "price": final[pid].get("price") if pid in final else None,
            } for pid, real in self.real.items()]
        return out


def room_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase.replace("O", "").replace("I", "")) for _ in range(6))
