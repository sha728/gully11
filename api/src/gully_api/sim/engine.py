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
from dataclasses import dataclass, field

from .commentary import describe
from .profiles import Profile, expected
from .rates import RUNS, Env, load_env

CREDITED = {"caught", "bowled", "lbw", "caught and bowled", "stumped", "hit wicket"}
RUN_OUT_NON_STRIKER = 0.4  # share of run outs that dismiss the non-striker


@dataclass
class Team:
    name: str
    players: list[Profile]               # 11, in batting order
    bowlers: list[str] | None = None     # ids of designated bowlers (auto if None)
    keeper: str | None = None            # id (auto: first WK, else last batter)
    # Bowling-only substitutes (IPL Impact Player): can bowl, never bat.
    impact: list[Profile] = field(default_factory=list)

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
    # phase -> counts over OUTCOMES for balls faced (used by calibration/validation)
    outcomes: dict[str, list[int]] = field(
        default_factory=lambda: {p: [0] * 7 for p in ("PP", "middle", "death")})

    @property
    def overs(self) -> str:
        b = self.legal_balls
        return f"{b // 6}.{b % 6}" if b % 6 else str(b // 6)

    def to_dict(self) -> dict:
        return {
            "batting": self.batting, "bowling": self.bowling,
            "runs": self.runs, "wickets": self.wickets, "overs": self.overs,
            "target": self.target, "extras": self.extras,
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
    winner: str | None          # None = tie
    margin: str
    commentary: list[dict]
    win_prob: list[tuple[str, float]]   # (ball label, P(team batting first wins))

    def to_dict(self) -> dict:
        return {
            "seed": self.seed, "env": self.env, "teams": list(self.teams),
            "innings": [i.to_dict() for i in self.innings],
            "winner": self.winner, "margin": self.margin,
            "commentary": self.commentary, "win_prob": self.win_prob,
        }


# ------------------------------------------------------------------ helpers

def _pick(rng: random.Random, probs) -> int:
    u = rng.random()
    acc = 0.0
    for i, p in enumerate(probs):
        acc += p
        if u < acc:
            return i
    return len(probs) - 1


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
        self.with_commentary = commentary
        self.commentary: list[dict] = []
        self.win_prob: list[tuple[str, float]] = []
        self._combo: dict[tuple, list[float]] = {}
        # Match conditions (pitch, ground size, dew): one draw per match scaling
        # boundary rates for both sides; mean 1, spread fitted in calibration.
        sd = env.conditions_sd
        self.conditions = math.exp(self.rng.gauss(-sd * sd / 2, sd)) if sd else 1.0

    # -- probabilities ---------------------------------------------------
    def combined(self, bat: Profile, bowl: Profile, phase: str) -> list[float]:
        key = (bat.id, bowl.id, phase)
        v = self._combo.get(key)
        if v is None:
            env = self.env
            br, wr = bat.bat_ratio(phase, env), bowl.bowl_ratio(phase, env)
            cal = env.calibration[phase]
            raw = [br[i] * wr[i] * env.bat_env[phase][i] * cal[i] for i in range(7)]
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
                      over: int, last: str | None, left: dict[str, int]) -> str:
        env = self.env
        phase = env.phase(over)
        options = team.bowling_options()
        overs_left = env.overs - over
        eligible = [b for b in options if left[b] > 0 and b != last]
        if not eligible:  # quotas exhausted: any fielder except the keeper
            keeper = team.keeper_id()
            eligible = [p.id for p in team.players + team.impact
                        if p.id not in (last, keeper) and left[p.id] > 0]

        def value(pid: str, ph: str) -> float:
            p = by_id[pid]
            rpb, wk = expected(p.bowl[ph])
            return 20 * wk - rpb - (p.wide[ph] + p.noball[ph])

        # Keep the two best death bowlers' last overs for the death.
        if phase != "death":
            death_first = env.phase_starts[-1][0]
            reserve = max(1, (env.overs - death_first) // 4)
            best_death = sorted(options, key=lambda b: value(b, "death"), reverse=True)[:2]
            kept = [b for b in eligible if not (b in best_death and left[b] <= reserve)]
            eligible = kept or eligible

        scores = [value(b, phase) + 0.5 * left[b] / overs_left for b in eligible]
        top = max(scores)
        weights = [math.exp((s - top) / 0.12) for s in scores]
        total = sum(weights)
        return eligible[_pick(self.rng, [w / total for w in weights])]

    # -- one innings -----------------------------------------------------
    def innings(self, bat_team: Team, bowl_team: Team, innings_no: int,
                target: int | None) -> Innings:
        env, rng = self.env, self.rng
        inn = Innings(batting=bat_team.name, bowling=bowl_team.name, target=target)
        batters = bat_team.players
        for p in batters:
            inn.bat[p.id] = BatLine(p.name)
        squad = bowl_team.players + bowl_team.impact
        for p in squad:
            inn.bowl[p.id] = BowlLine(p.name)
        by_id = {p.id: p for p in squad}
        striker, non_striker, next_in = 0, 1, 2
        inn.bat[batters[0].id].how_out = "not out"
        inn.bat[batters[1].id].how_out = "not out"
        quota = env.max_overs_per_bowler
        left = {p.id: quota for p in squad}
        keeper = bowl_team.keeper_id()
        fielders = [p for p in bowl_team.players]
        last_bowler = None
        n_balls = env.overs * 6

        def done() -> bool:
            return (inn.wickets >= 10 or inn.legal_balls >= n_balls
                    or (target is not None and inn.runs >= target))

        for over in range(env.overs):
            if done():
                break
            phase = env.phase(over)
            bid = self.choose_bowler(bowl_team, by_id, inn, over, last_bowler, left)
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
                    if target is not None:
                        v = _aggression(v, self._chase_aggression(inn, target))
                    o = _pick(rng, v)
                    line.balls += 1
                    inn.outcomes[phase][1 if (noball and o == 0) else o] += 1
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
                            if inn.wickets < 10 and next_in < 11:
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
                    self.commentary.append(event)
                    self.win_prob.append(
                        (f"{innings_no}:{ball_label}", round(self.p_first_wins(inn, innings_no), 4)))

            if legal_in_over == 6 and runs_in_over == 0:
                bl.maidens += 1
            left[bid] -= 1
            last_bowler = bid
            striker, non_striker = non_striker, striker
        return inn

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


def simulate_match(team_a: Team, team_b: Team, env: Env | str, seed: int,
                   bat_first: int | None = None, commentary: bool = True) -> MatchResult:
    """Simulate one limited-overs match. ``bat_first``: 0 = team_a, 1 = team_b,
    None = decided by a seeded toss."""
    if isinstance(env, str):
        env = load_env(env)
    m = _Match(env, seed, commentary)
    if bat_first is None:
        bat_first = m.rng.randrange(2)
    first, second = (team_a, team_b) if bat_first == 0 else (team_b, team_a)
    i1 = m.innings(first, second, 1, None)
    i2 = m.innings(second, first, 2, i1.runs + 1)

    if i2.runs > i1.runs:
        balls_left = env.overs * 6 - i2.legal_balls
        winner, margin = second.name, f"won by {10 - i2.wickets} wickets ({balls_left} balls left)"
    elif i1.runs > i2.runs:
        winner, margin = first.name, f"won by {i1.runs - i2.runs} runs"
    else:
        winner, margin = None, "match tied"
    return MatchResult(seed=seed, env=env.name, teams=(first.name, second.name),
                       innings=[i1, i2], winner=winner, margin=margin,
                       commentary=m.commentary, win_prob=m.win_prob)
