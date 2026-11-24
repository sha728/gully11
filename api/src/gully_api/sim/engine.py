"""Ball-by-ball limited-overs match engine (T20 and ODI share it).

Per delivery:
1. extras check: wide / no-ball from the bowler's (shrunk) rates;
2. outcome from {W, 0, 1, 2, 3, 4, 6} using the log5 (odds-ratio) combination
       p_i  ∝  (bat_i / L_bat_i) * (bowl_i / L_bowl_i) * E_i
   where L are the league baselines player rates were measured against and E is
   the environment being simulated (e.g. IPL 2024-26 scoring levels);
3. game-state aggression in a chase (required rate vs. par for resources left);
4. byes on otherwise-dot balls; wicket kind and fielder; strike rotation.

Every match takes a seed: the same seed, teams and env reproduce the same match.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field

from .awards import player_of_match
from .commentary import describe
from .profiles import WICKET_ROLES, Profile, expected
from .rates import RUNS, Env, load_env

CREDITED = {"caught", "bowled", "lbw", "caught and bowled", "stumped", "hit wicket"}
RUN_OUT_NON_STRIKER = 0.4  # share of run outs that dismiss the non-striker
# A batter with a real bowling record (wickets in this format) gets a one-over
# "captain's hunch" in the middle overs this often per limited-overs innings.
PART_TIMER_CHANCE = 0.1
PART_TIMER_MIN_WICKETS = 10


def _coverable(quota: dict[str, int], overs: int, last: str) -> bool:
    """Can these quotas bowl ``overs`` more overs, never the same bowler twice in a
    row, when ``last`` bowled the over just gone? Nobody can bowl more than every
    other over: ceil(n/2) of n, or floor(n/2) for the bowler who has just bowled."""
    cap = {b: (overs // 2 if b == last else (overs + 1) // 2) for b in quota}
    return sum(min(max(q, 0), cap[b]) for b, q in quota.items()) >= overs


@dataclass
class Team:
    name: str
    players: list[Profile]               # 11, in batting order
    bowlers: list[str] | None = None     # ids of designated bowlers (auto if None)
    keeper: str | None = None            # id (auto: first WK, else last batter)
    # Bowling-only substitutes (IPL Impact Player): can bowl, never bat.
    impact: list[Profile] = field(default_factory=list)
    captain: str | None = None           # id of the captain (in the XI)
    # Tactical skill of the captain, 0..1 (from their captaincy record; 0 = never
    # captained): the toss call and bowling changes. See sim/captaincy.py.
    captaincy: float = 0.0

    def __post_init__(self):
        if len(self.players) != 11:
            raise ValueError(f"{self.name}: need 11 players, got {len(self.players)}")
        ids = [p.id for p in self.players + self.impact]
        if len(set(ids)) != len(ids):
            raise ValueError(f"{self.name}: duplicate players")
        if self.bowlers is not None:
            unknown = set(self.bowlers) - set(ids)
            if unknown:
                raise ValueError(f"{self.name}: bowlers not in XI: {sorted(unknown)}")
            if len(set(self.bowlers)) < 5:
                raise ValueError(f"{self.name}: need at least 5 bowling options")

    def keeper_id(self) -> str:
        if self.keeper:
            return self.keeper
        return next((p.id for p in self.players if p.role == "WK"), self.players[-1].id)

    def bowling_options(self) -> list[str]:
        if self.bowlers:
            return list(dict.fromkeys(self.bowlers))
        keeper = self.keeper_id()
        ranked = sorted((p for p in self.players + self.impact if p.id != keeper),
                        key=lambda p: (p.role in ("BOWL", "AR"), p.balls_bowled), reverse=True)
        return [p.id for p in ranked[:6]]


@dataclass
class BatLine:
    name: str
    runs: int = 0
    balls: int = 0
    fours: int = 0
    sixes: int = 0
    how_out: str | None = None   # None = did not bat; "not out" once batted


@dataclass
class BowlLine:
    name: str
    balls: int = 0
    runs: int = 0
    wickets: int = 0
    wides: int = 0
    noballs: int = 0
    maidens: int = 0

    @property
    def overs(self) -> str:
        return f"{self.balls // 6}.{self.balls % 6}" if self.balls % 6 else str(self.balls // 6)


@dataclass
class Innings:
    batting: str
    bowling: str
    runs: int = 0
    wickets: int = 0
    legal_balls: int = 0
    extras: dict = field(default_factory=lambda: {"wides": 0, "noballs": 0, "byes": 0})
    bat: dict[str, BatLine] = field(default_factory=dict)
    bowl: dict[str, BowlLine] = field(default_factory=dict)
    fall_of_wickets: list[str] = field(default_factory=list)
    target: int | None = None
    declared: bool = False
    # phase -> counts over OUTCOMES for balls faced (used by calibration/validation)
    outcomes: dict[str, list[int]] = field(
        default_factory=lambda: {p: [0] * 7 for p in ("PP", "middle", "death")})
    # The same by bowling kind: "death:pace", "middle:spin", ... (known kinds only)
    kind_outcomes: dict[str, list[int]] = field(default_factory=dict)

    @property
    def overs(self) -> str:
        b = self.legal_balls
        return f"{b // 6}.{b % 6}" if b % 6 else str(b // 6)

    def to_dict(self) -> dict:
        return {
            "batting": self.batting, "bowling": self.bowling,
            "runs": self.runs, "wickets": self.wickets, "overs": self.overs,
            "target": self.target, "declared": self.declared, "extras": self.extras,
            "batting_card": [{"id": pid, **vars(b)} for pid, b in self.bat.items()],
            "bowling_card": [{"id": pid, **vars(b), "overs": b.overs}
                             for pid, b in self.bowl.items() if b.balls or b.runs],
            "fall_of_wickets": self.fall_of_wickets,
        }


@dataclass
class MatchResult:
    seed: int
    env: str
    teams: tuple[str, str]
    innings: list[Innings]
    winner: str | None          # None = tie or draw
    margin: str
    commentary: list[dict]
    win_prob: list[tuple[str, float]]   # (ball label, P(team batting first wins)); limited overs only
    result: str = "win"         # win / tie / draw / super over
    toss: dict | None = None    # {"winner", "decision", "captain", "called_right"}
    super_overs: list[Innings] = field(default_factory=list)   # in order played (pairs)

    def to_dict(self) -> dict:
        d = {
            "seed": self.seed, "env": self.env, "teams": list(self.teams),
            "innings": [i.to_dict() for i in self.innings],
            "winner": self.winner, "margin": self.margin, "result": self.result,
            "commentary": self.commentary, "win_prob": self.win_prob, "toss": self.toss,
            "super_overs": [i.to_dict() for i in self.super_overs],
        }
        d["player_of_match"] = player_of_match(d, load_env(self.env).is_test)
        return d


# ------------------------------------------------------------------ helpers

def _pick(rng: random.Random, probs) -> int:
    u = rng.random()
    acc = 0.0
    for i, p in enumerate(probs):
        acc += p
        if u < acc:
            return i
    return len(probs) - 1


def _n(count: int, word: str) -> str:
    """'1 run', '2 runs'."""
    return f"{count} {word}{'' if count == 1 else 's'}"


def _phi(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def _aggression(v: list[float], a: float) -> list[float]:
    """Chase intent. Behind the rate (a > 1): more boundaries, fewer dots, some
    extra wicket risk. Ahead (a < 1): protect wickets and rotate strike, without
    shutting down. Tuned so equal sides chasing win ~52% (knowing the target helps)."""
    if a == 1.0:
        return v
    if a > 1:
        w = [v[0] * a ** 0.5, v[1] * a ** -0.5, v[2], v[3], v[4], v[5] * a, v[6] * a ** 1.3]
    else:
        w = [v[0] * a, v[1], v[2] * a ** -0.5, v[3], v[4], v[5] * a ** 0.3, v[6] * a ** 0.5]
    s = sum(w)
    return [x / s for x in w]


class _Match:
    def __init__(self, env: Env, seed: int, commentary: bool):
        self.env = env
        self.rng = random.Random(seed)
        self.toss: dict | None = None
        self.with_commentary = commentary
        self.commentary: list[dict] = []
        self.win_prob: list[tuple[str, float]] = []
        self._combo: dict[tuple, list[float]] = {}
        # Match conditions (pitch, ground size, dew): one draw per match scaling
        # boundary rates for both sides; mean 1, spread fitted in calibration.
        sd = env.conditions_sd
        self.conditions = math.exp(self.rng.gauss(-sd * sd / 2, sd)) if sd else 1.0
        # Test pitch wear: per-innings wicket and scoring factors measured from real
        # Tests (balls per wicket 65 -> 61 -> 55 -> 53 across the four innings).
        self.wear: dict[int, tuple[float, float]] = {}
        if env.is_test and env.test_shape:
            rows = env.test_shape["innings"]
            weight = [r["n"] * r["overs"] for r in rows]
            w_mean = sum(r["wicket_rate"] * x for r, x in zip(rows, weight)) / sum(weight)
            r_mean = sum(r["run_rate"] * x for r, x in zip(rows, weight)) / sum(weight)
            self.wear = {r["innings"]: (r["wicket_rate"] / w_mean, r["run_rate"] / r_mean) for r in rows}

    def _worn(self, v: list[float], innings_no: int) -> list[float]:
        wf, rf = self.wear.get(innings_no, (1.0, 1.0))
        if wf == 1.0 and rf == 1.0:
            return v
        w = [v[0] * wf, v[1], v[2] * rf, v[3] * rf, v[4] * rf, v[5] * rf, v[6] * rf]
        s = sum(w)
        return [x / s for x in w]

    # -- probabilities ---------------------------------------------------
    def combined(self, bat: Profile, bowl: Profile, phase: str) -> list[float]:
        key = (bat.id, bowl.id, phase)
        v = self._combo.get(key)
        if v is None:
            env = self.env
            br, wr = bat.bat_ratio(phase, env), bowl.bowl_ratio(phase, env)
            # Calibration per phase and bowling kind where fitted, else per phase.
            cal = env.calibration.get(f"{phase}:{bowl.kind}") or env.calibration[phase]
            raw = [br[i] * wr[i] * env.bat_env[phase][i] * cal[i] for i in range(7)]
            # Matchups: this batter against this kind of bowling, this bowler
            # against this batting hand (factors are 1 when unknown).
            vs_bowl = bat.bat_vs.get(bowl.kind) if bowl.kind else None
            vs_hand = bowl.bowl_vs.get(bat.hand) if bat.hand else None
            for m in (vs_bowl, vs_hand):
                if m:
                    raw = [r * f for r, f in zip(raw, m)]
            raw[5] *= self.conditions
            raw[6] *= self.conditions
            s = sum(raw)
            v = self._combo[key] = [x / s for x in raw]
        return v

    def p_first_wins(self, inn: Innings, innings_no: int) -> float:
        """P(team batting first wins), from the remaining-runs table: normal
        approximation of (first total - second total), or of runs still to come
        against runs needed in the chase."""
        env = self.env
        mu, sd = env.remaining(inn.legal_balls, inn.wickets)
        if innings_no == 1:
            mu2, sd2 = env.remaining(0, 0)
            return _phi((inn.runs + mu - mu2) / math.sqrt(sd ** 2 + sd2 ** 2 + 1e-9))
        need = inn.target - inn.runs
        if need <= 0:
            return 0.0
        if sd == 0:
            return 1.0
        return _phi((need - 0.5 - mu) / sd)

    # -- bowling plan ----------------------------------------------------
    def choose_bowler(self, team: Team, by_id: dict[str, Profile], inn: Innings,
                      over: int, last: str | None, left: dict[str, int], max_overs: int,
                      spell: dict[str, int] | None = None) -> str:
        env = self.env
        phase = env.phase(over)
        options = team.bowling_options()
        overs_left = max(1, max_overs - over)
        eligible = [b for b in options if left[b] > 0 and b != last]
        if not eligible:  # quotas exhausted: any fielder except the keeper
            keeper = team.keeper_id()
            eligible = [p.id for p in team.players + team.impact
                        if p.id not in (last, keeper) and left[p.id] > 0]
        elif not env.is_test:
            # Plan the rest of the innings: prefer bowlers who leave the specialists
            # (bowlers and all-rounders) able to bowl out the remaining overs, so a
            # batter only turns his arm over when the specialists can't.
            main = [b for b in options if by_id[b].role in WICKET_ROLES]
            for pool in (main, options):
                ok = [b for b in eligible if b in pool
                      and _coverable({o: left[o] - (o == b) for o in pool}, overs_left - 1, b)]
                if ok:
                    eligible = ok
                    break

        def value(pid: str, ph: str) -> float:
            p = by_id[pid]
            rpb, wk = expected(p.bowl[ph])
            return 20 * wk - rpb - (p.wide[ph] + p.noball[ph])

        # Keep the two best death bowlers' last overs for the death (limited overs).
        # A good captain does it reliably; a poor one sometimes burns them early.
        if phase != "death" and not env.is_test and self.rng.random() < 0.6 + 0.4 * team.captaincy:
            death_first = env.phase_starts[-1][0]
            reserve = max(1, (env.overs - death_first) // 4)
            best_death = sorted(options, key=lambda b: value(b, "death"), reverse=True)[:2]
            kept = [b for b in eligible if not (b in best_death and left[b] <= reserve)]
            eligible = kept or eligible

        if env.is_test:
            # No quotas in Tests: rest bowlers between spells. Each over beyond five in
            # the current spell, and each over beyond 25 in the innings, costs a little.
            scores = [value(b, phase) - 0.06 * max(0, (spell or {}).get(b, 0) - 5)
                      - 0.01 * max(0, inn.bowl[b].balls // 6 - 25) for b in eligible]
        else:
            scores = [value(b, phase) + 0.5 * left[b] / overs_left for b in eligible]
        top = max(scores)
        # How far the choice strays from the best option: tighter for a better
        # captain (0.12, the engine's old fixed value, is a middling captain).
        temp = BOWLING_TEMP * (1.6 - 1.2 * team.captaincy)
        weights = [math.exp((s - top) / temp) for s in scores]
        total = sum(weights)
        return eligible[_pick(self.rng, [w / total for w in weights])]

    # -- one innings -----------------------------------------------------
    def innings(self, bat_team: Team, bowl_team: Team, innings_no: int,
                target: int | None, max_overs: int | None = None,
                declare: "Callable[[Innings], bool] | None" = None,
                super_over: tuple[list[Profile], str] | None = None) -> Innings:
        """One innings. Limited overs: ``max_overs`` = the format's overs and bowler
        quotas apply. Tests: ``max_overs`` = time left in the match, no quotas, and
        ``declare`` is asked at the end of each over. ``super_over`` = (the three
        batters sent in, the bowler's id): one over, two wickets, death-overs rates."""
        env, rng = self.env, self.rng
        max_overs = env.overs if max_overs is None else max_overs
        inn = Innings(batting=bat_team.name, bowling=bowl_team.name, target=target)
        batters = super_over[0] if super_over else bat_team.players
        max_wickets = len(batters) - 1
        for p in batters:
            inn.bat[p.id] = BatLine(p.name)
        squad = bowl_team.players + bowl_team.impact
        for p in squad:
            inn.bowl[p.id] = BowlLine(p.name)
        by_id = {p.id: p for p in squad}
        striker, non_striker, next_in = 0, 1, 2
        inn.bat[batters[0].id].how_out = "not out"
        inn.bat[batters[1].id].how_out = "not out"
        quota = env.max_overs_per_bowler if not env.is_test else 10_000
        left = {p.id: quota for p in squad}
        spell: dict[str, int] = {p.id: 0 for p in squad}   # consecutive spell length (Tests)
        rested: dict[str, int] = {p.id: 99 for p in squad}
        keeper = bowl_team.keeper_id()
        fielders = [p for p in bowl_team.players]
        last_bowler = None
        n_balls = max_overs * 6

        def done() -> bool:
            return (inn.wickets >= max_wickets or inn.legal_balls >= n_balls
                    or (target is not None and inn.runs >= target))

        # Luck: now and then the captain gives a batter who can bowl a middle over.
        hunch, hunch_over, announced = None, -1, False
        if not env.is_test and not super_over:
            arms = [p.id for p in bowl_team.players
                    if p.role not in WICKET_ROLES and p.id != keeper and p.wickets >= PART_TIMER_MIN_WICKETS]
            middle = [o for o in range(max_overs) if env.phase(o) == "middle"]
            if arms and middle and rng.random() < PART_TIMER_CHANCE:
                hunch, hunch_over = rng.choice(arms), rng.choice(middle)

        for over in range(max_overs):
            if done():
                break
            phase = "death" if super_over else env.phase(over)
            if super_over:
                bid = super_over[1]
            elif over == hunch_over and hunch != last_bowler and left[hunch] > 0:
                bid = hunch
            else:
                bid = self.choose_bowler(bowl_team, by_id, inn, over, last_bowler, left, max_overs, spell)
            bowler = by_id[bid]
            bl = inn.bowl[bid]
            legal_in_over, runs_in_over = 0, 0
            while legal_in_over < 6 and not done():
                bat = batters[striker]
                line = inn.bat[bat.id]
                ball_label = f"{over}.{legal_in_over + 1}"
                u = rng.random()
                event: dict = {"inns": innings_no, "ball": ball_label, "bowler": bowler.name,
                               "batter": bat.name}

                if u < bowler.wide[phase]:                       # wide
                    w = env.wide_runs[0][_pick(rng, env.wide_runs[1])]
                    inn.runs += w
                    inn.extras["wides"] += w
                    bl.runs += w
                    bl.wides += 1
                    runs_in_over += w
                    if w != 5 and (w - 1) % 2 == 1:
                        striker, non_striker = non_striker, striker
                    event.update(kind="wide", runs=w)
                else:
                    noball = u < bowler.wide[phase] + bowler.noball[phase]
                    v = self.combined(bat, bowler, phase)
                    if self.wear:
                        v = self._worn(v, innings_no)
                    if super_over:
                        v = _aggression(v, self._super_over_intent(inn, target))
                    elif target is not None:
                        a = (self._test_chase_intent(inn, target, max_overs) if env.is_test
                             else self._chase_aggression(inn, target))
                        v = _aggression(v, a)
                    o = _pick(rng, v)
                    line.balls += 1
                    inn.outcomes[phase][1 if (noball and o == 0) else o] += 1
                    if bowler.kind:
                        inn.kind_outcomes.setdefault(f"{phase}:{bowler.kind}", [0] * 7)[1 if (noball and o == 0) else o] += 1
                    if noball:
                        r = RUNS[o]  # wicket outcomes become dots: can't be out (bar run out)
                        inn.runs += 1 + r
                        inn.extras["noballs"] += 1
                        bl.runs += 1 + r
                        bl.noballs += 1
                        runs_in_over += 1 + r
                        self._bat_runs(line, r)
                        if r % 2 == 1:
                            striker, non_striker = non_striker, striker
                        event.update(kind="noball", runs=1 + r, bat_runs=r)
                    else:
                        legal_in_over += 1
                        inn.legal_balls += 1
                        bl.balls += 1
                        if o == 0:                                   # wicket
                            kind = env.wicket_kinds[0][_pick(rng, env.wicket_kinds[1])]
                            out_idx = striker
                            if kind == "run out" and rng.random() < RUN_OUT_NON_STRIKER:
                                out_idx = non_striker
                            out = batters[out_idx]
                            how, fielder = self._how_out(kind, bowler, fielders, keeper, by_id)
                            inn.bat[out.id].how_out = how
                            inn.wickets += 1
                            if kind in CREDITED:
                                bl.wickets += 1
                            inn.fall_of_wickets.append(
                                f"{inn.runs}-{inn.wickets} ({out.name}, {inn.overs} ov)")
                            event.update(kind="wicket", runs=0, out=out.name, how=how,
                                         wicket_kind=kind, fielder=fielder)
                            if inn.wickets < max_wickets and next_in < len(batters):
                                inn.bat[batters[next_in].id].how_out = "not out"
                                if out_idx == striker:
                                    striker = next_in
                                else:
                                    non_striker = next_in
                                next_in += 1
                        else:
                            r = RUNS[o]
                            byes = 0
                            if r == 0 and rng.random() < env.bye_prob:
                                byes = env.bye_runs[0][_pick(rng, env.bye_runs[1])]
                            inn.runs += r + byes
                            inn.extras["byes"] += byes
                            bl.runs += r
                            runs_in_over += r + byes
                            self._bat_runs(line, r)
                            moved = r + (byes if byes != 4 else 0)
                            if moved % 2 == 1:
                                striker, non_striker = non_striker, striker
                            event.update(kind="runs", runs=r + byes, bat_runs=r, byes=byes)

                event["score"] = f"{inn.runs}/{inn.wickets}"
                if self.with_commentary:
                    event["text"] = describe(event, len(self.commentary))
                    if bid == hunch and not announced:
                        announced = True
                        event["text"] = f"Captain's hunch: {bowler.name} has a bowl. " + event["text"]
                    self.commentary.append(event)
                    if not env.is_test and not super_over:
                        self.win_prob.append(
                            (f"{innings_no}:{ball_label}", round(self.p_first_wins(inn, innings_no), 4)))

            if legal_in_over == 6 and runs_in_over == 0:
                bl.maidens += 1
            left[bid] -= 1
            last_bowler = bid
            # Spells: a bowler's spell continues while they bowl every other over.
            for pid in spell:
                rested[pid] = 0 if pid == bid else rested[pid] + 1
                if rested[pid] >= 3:
                    spell[pid] = 0
            spell[bid] += 1
            striker, non_striker = non_striker, striker
            if declare is not None and not done() and declare(inn):
                inn.declared = True
                break
        return inn

    def _test_chase_intent(self, inn: Innings, target: int, overs_cap: int) -> float:
        """Fourth-innings intent in a Test: go for it when the rate is gettable,
        shut up shop for the draw when it isn't and wickets are falling."""
        need = target - inn.runs
        overs_left = max(1.0, overs_cap - inn.legal_balls / 6)
        rate = need / overs_left
        par = 3.3   # Test runs per over since 2001
        if rate <= par:
            return 1.0
        if rate > 5.0 or (inn.wickets >= 6 and rate > 4.0):
            return 0.75    # bat for the draw
        return min((rate / par) ** 0.5, 1.3)

    @staticmethod
    def _super_over_intent(inn: Innings, target: int | None) -> float:
        """Six balls, two wickets: go hard. Setting a total, flat out; chasing,
        by the rate needed (about 2 a ball is par for a super over)."""
        if target is None:
            return SUPER_OVER_INTENT
        balls_left = max(1, 6 - inn.legal_balls)
        rate = (target - inn.runs) / balls_left
        return min(max(rate / 2.0, 0.8), 1.8) ** 0.5 * SUPER_OVER_INTENT ** 0.5

    def _chase_aggression(self, inn: Innings, target: int) -> float:
        need = target - inn.runs
        mu, _ = self.env.remaining(inn.legal_balls, inn.wickets)
        if mu <= 0:
            return 1.0
        return min(max(need / mu, 0.7), 1.6) ** 0.5

    @staticmethod
    def _bat_runs(line: BatLine, r: int) -> None:
        line.runs += r
        if r == 4:
            line.fours += 1
        elif r == 6:
            line.sixes += 1

    def _how_out(self, kind: str, bowler: Profile, fielders: list[Profile], keeper: str,
                 by_id: dict[str, Profile]) -> tuple[str, str | None]:
        rng = self.rng
        b = bowler.name
        if kind == "caught":
            pool = [f for f in fielders if f.id != bowler.id]
            weights = [4.0 if f.id == keeper else 1.0 for f in pool]
            s = sum(weights)
            f = pool[_pick(rng, [w / s for w in weights])]
            return f"c {f.name} b {b}", f.name
        if kind == "caught and bowled":
            return f"c & b {b}", b
        if kind == "stumped":
            return f"st {by_id[keeper].name} b {b}", by_id[keeper].name
        if kind == "run out":
            f = fielders[_pick(rng, [1 / len(fielders)] * len(fielders))]
            return f"run out ({f.name})", f.name
        if kind in ("bowled", "lbw", "hit wicket"):
            return {"bowled": f"b {b}", "lbw": f"lbw b {b}", "hit wicket": f"hit wicket b {b}"}[kind], None
        return kind, None


BOWLING_TEMP = 0.12      # spread of bowling choices for a middling captain
SUPER_OVER_INTENT = 1.9  # aggression in a super over (see _aggression)
MAX_SUPER_OVERS = 4      # repeat tied super overs; past this, most boundaries in the match wins


def _toss(rng, a: Team, b: Team, env: Env) -> tuple[int, dict]:
    """A coin decides who wins the toss; their captain chooses. In this engine the
    stronger choice is to bowl first in limited-overs cricket (chasing sides win
    55% of T20s, 61% of ODIs) and to bat first in Tests (60% to 37%); a captain
    makes it with probability 0.5 + 0.45 * captaincy. Returns (team batting first:
    0 = a, 1 = b) and what happened."""
    won = rng.randrange(2)
    team = (a, b)[won]
    right = rng.random() < 0.5 + 0.45 * team.captaincy
    bat = env.is_test == right                  # Tests: bat if right; limited overs: bowl if right
    captain = next((p.name for p in team.players if p.id == team.captain), None)
    return (won if bat else 1 - won), {"winner": team.name, "decision": "bat" if bat else "bowl",
                                        "captain": captain, "called_right": right}


def _super_over_picks(m: "_Match", bat: Team, bowl: Team, out_before: set[str],
                      bowled_before: set[str]) -> tuple[list[Profile], str]:
    """The captains' choices for a super over: three batters (best death-overs
    hitters, never anyone dismissed in an earlier super over) and one bowler (best
    death bowler, never the bowler of an earlier one). A sharper captain picks
    closer to the best, as with bowling changes."""
    def hit(p: Profile) -> float:
        rpb, wk = expected(p.bat["death"])
        return rpb - 2 * wk

    def bowl_value(p: Profile) -> float:
        rpb, wk = expected(p.bowl["death"])
        return 20 * wk - rpb - (p.wide["death"] + p.noball["death"])

    def choose(pool: list[Profile], score, team: Team, n: int) -> list[Profile]:
        temp = BOWLING_TEMP * (1.6 - 1.2 * team.captaincy)
        pool, out = list(pool), []
        for _ in range(min(n, len(pool))):
            s = [score(p) for p in pool]
            top = max(s)
            w = [math.exp((x - top) / temp) for x in s]
            out.append(pool.pop(_pick(m.rng, [x / sum(w) for x in w])))
        return out

    batters = choose([p for p in bat.players if p.id not in out_before], hit, bat, 3)
    by_id = {p.id: p for p in bowl.players + bowl.impact}
    options = [by_id[b] for b in bowl.bowling_options() if b not in bowled_before]
    if not options:
        options = [p for p in bowl.players if p.id not in bowled_before and p.id != bowl.keeper_id()]
    return batters, choose(options, bowl_value, bowl, 1)[0].id


def _super_overs(m: "_Match", first: Team, second: Team, i1: Innings, i2: Innings
                 ) -> tuple[str, str, list[Innings]]:
    """Settle a tie: the side that batted second bats first in the super over.
    A tied super over is played again (dismissed batters and the previous bowler
    can't take part, ICC rules). Returns (winner, margin, the super-over innings)."""
    played: list[Innings] = []
    out: dict[str, set[str]] = {first.name: set(), second.name: set()}
    bowled: dict[str, set[str]] = {first.name: set(), second.name: set()}
    a, b = second, first
    for k in range(MAX_SUPER_OVERS):
        pa = _super_over_picks(m, a, b, out[a.name], bowled[b.name])
        sa = m.innings(a, b, 3 + 2 * k, None, max_overs=1, super_over=pa)
        pb = _super_over_picks(m, b, a, out[b.name], bowled[a.name])
        sb = m.innings(b, a, 4 + 2 * k, sa.runs + 1, max_overs=1, super_over=pb)
        played += [sa, sb]
        for inn, team in ((sa, a), (sb, b)):
            out[team.name] |= {pid for pid, line in inn.bat.items() if line.how_out not in (None, "not out")}
        bowled[b.name].add(pa[1])
        bowled[a.name].add(pb[1])
        again = "" if k == 0 else f" (super over {k + 1})"
        if sb.runs > sa.runs:
            return b.name, f"won the super over{again} ({sb.runs}/{sb.wickets} to {sa.runs}/{sa.wickets})", played
        if sa.runs > sb.runs:
            return a.name, f"won the super over{again} ({sa.runs}/{sa.wickets} to {sb.runs}/{sb.wickets})", played
        a, b = b, a     # the next super over: the other side bats first
    fours = {t.name: sum(line.fours + line.sixes for inn in (i1, i2, *played)
                         if inn.batting == t.name for line in inn.bat.values()) for t in (first, second)}
    win = max((first, second), key=lambda t: (fours[t.name], t is second)).name
    return win, f"won on boundary count ({fours[win]}) after {MAX_SUPER_OVERS} tied super overs", played


def simulate_match(team_a: Team, team_b: Team, env: Env | str, seed: int,
                   bat_first: int | None = None, commentary: bool = True,
                   super_over: bool | None = None) -> MatchResult:
    """Simulate one limited-overs match. ``bat_first``: 0 = team_a, 1 = team_b,
    None = decided by a seeded toss. ``super_over``: settle a tie with a super over
    (default: in T20s, as in the IPL and T20Is; ODI ties stand)."""
    if isinstance(env, str):
        env = load_env(env)
    if env.is_test:
        raise ValueError(f"{env.name} is a Test environment; use simulate_test")
    m = _Match(env, seed, commentary)
    if bat_first is None:
        bat_first, m.toss = _toss(m.rng, team_a, team_b, env)
    first, second = (team_a, team_b) if bat_first == 0 else (team_b, team_a)
    i1 = m.innings(first, second, 1, None)
    i2 = m.innings(second, first, 2, i1.runs + 1)

    if i2.runs > i1.runs:
        balls_left = env.overs * 6 - i2.legal_balls
        winner, margin = second.name, f"won by {_n(10 - i2.wickets, 'wicket')} ({_n(balls_left, 'ball')} left)"
    elif i1.runs > i2.runs:
        winner, margin = first.name, f"won by {_n(i1.runs - i2.runs, 'run')}"
    else:
        winner, margin = None, "match tied"
    result, extra = ("win" if winner else "tie"), []
    if winner is None and (env.overs <= 20 if super_over is None else super_over):
        winner, margin, extra = _super_overs(m, first, second, i1, i2)
        result = "super over"
    return MatchResult(toss=m.toss, seed=seed, env=env.name, teams=(first.name, second.name),
                       innings=[i1, i2], winner=winner, margin=margin, result=result,
                       commentary=m.commentary, win_prob=m.win_prob, super_overs=extra)


# ---------------------------------------------------------------- Tests (beta)

TEST_MATCH_OVERS = 450      # five days of 90 overs
FOLLOW_ON_LEAD = 200


def _overs_used(inn: Innings) -> int:
    return -(-inn.legal_balls // 6)  # whole overs, rounding a part over up


def _first_innings_declare(inn: Innings) -> bool:
    """Batting first: declare on a big total, or a large one after a long day."""
    return inn.runs >= 600 or (inn.runs >= 500 and inn.legal_balls >= 140 * 6)


def simulate_test(team_a: Team, team_b: Team, env: Env | str, seed: int,
                  bat_first: int | None = None, commentary: bool = True) -> MatchResult:
    """Simulate a Test (beta): two innings each inside 450 overs, simple
    declarations, follow-on at a 200-run lead, draws when time runs out.

    Declaration rules and the follow-on decision are design choices, not taken
    from any source; see docs/simulator.md.
    """
    if isinstance(env, str):
        env = load_env(env)
    if not env.is_test:
        raise ValueError(f"{env.name} is a limited-overs environment; use simulate_match")
    m = _Match(env, seed, commentary)
    if bat_first is None:
        bat_first, m.toss = _toss(m.rng, team_a, team_b, env)
    first, second = (team_a, team_b) if bat_first == 0 else (team_b, team_a)
    # Weather and bad light: some matches lose overs. How often is fitted to the real
    # draw rate (validate_test_sim.py --fit); a design choice, not from any source.
    p_loss, max_lost = env.test_weather
    rain, amount = m.rng.random(), m.rng.random()   # always drawn, so seeds stay stable
    lost = int(amount * max_lost) if rain < p_loss else 0
    left = TEST_MATCH_OVERS - lost

    i1 = m.innings(first, second, 1, None, max_overs=left, declare=_first_innings_declare)
    left -= _overs_used(i1)
    innings = [i1]

    def draw() -> MatchResult:
        why = f"{lost} overs lost to rain and bad light" if lost >= 20 else "time ran out"
        return MatchResult(toss=m.toss, seed=seed, env=env.name, teams=(first.name, second.name), innings=innings,
                           winner=None, margin=f"match drawn: {why}", commentary=m.commentary,
                           win_prob=[], result="draw")

    def won(team: Team, margin: str) -> MatchResult:
        return MatchResult(toss=m.toss, seed=seed, env=env.name, teams=(first.name, second.name), innings=innings,
                           winner=team.name, margin=margin, commentary=m.commentary, win_prob=[])

    if left <= 0:
        return draw()

    # Second innings: declare once well ahead.
    i2 = m.innings(second, first, 2, None, max_overs=left,
                   declare=lambda inn: inn.runs - i1.runs >= 250 and inn.runs >= 450)
    left -= _overs_used(i2)
    innings.append(i2)
    if left <= 0:
        return draw()

    lead = i1.runs - i2.runs
    follow_on = lead >= FOLLOW_ON_LEAD and left >= 150
    third, fourth = (second, first) if follow_on else (first, second)

    def third_declare(inn: Innings) -> bool:
        # Declare when the lead would need a chase above ~3.6 an over in the time left.
        lead_now = (i1.runs + inn.runs - i2.runs) if not follow_on else -1
        time_left = left - _overs_used(inn)
        return not follow_on and lead_now >= max(200, 3.6 * time_left) or lead_now >= 450

    i3 = m.innings(third, fourth, 3, None, max_overs=left, declare=third_declare)
    left -= _overs_used(i3)
    innings.append(i3)

    totals = {first.name: i1.runs, second.name: i2.runs}
    totals[third.name] += i3.runs
    need = totals[third.name] - totals[fourth.name] + 1
    if need <= 0:
        # The side batting third is still behind: beaten by an innings.
        return won(fourth, f"won by an innings and {_n(1 - need, 'run')}")
    if left <= 0:
        return draw()

    i4 = m.innings(fourth, third, 4, need, max_overs=left)
    innings.append(i4)
    if i4.runs >= need:
        return won(fourth, f"won by {_n(10 - i4.wickets, 'wicket')}")
    if i4.wickets >= 10:
        if i4.runs == need - 1:
            return MatchResult(toss=m.toss, seed=seed, env=env.name, teams=(first.name, second.name), innings=innings,
                               winner=None, margin="match tied", commentary=m.commentary,
                               win_prob=[], result="tie")
        return won(third, f"won by {_n(need - 1 - i4.runs, 'run')}")
    return draw()
