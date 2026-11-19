/** Ball-by-ball replay state, rebuilt from a match's commentary. Pure functions:
 * the state after any number of deliveries, and the match's key moments. */

import type { BallEvent, FullMatch } from "@/lib/xi";

export interface AtCrease {
  name: string;
  runs: number;
  balls: number;
  fours: number;
  sixes: number;
  striker: boolean;
}

export interface BowlerFigures {
  name: string;
  overs: string;
  runs: number;
  wickets: number;
}

export interface LiveState {
  started: boolean;
  inns: number;
  batting: string;
  bowling: string;
  runs: number;
  wickets: number;
  overs: string;
  crease: AtCrease[];
  bowler: BowlerFigures | null;
  thisOver: string[];
  partnership: { runs: number; balls: number };
  target: number | null;
  need: { runs: number; balls: number } | null;
  lastWicket: string | null;
  ended: boolean;
}

export interface Moment {
  at: number;          // cursor value that shows this ball (index + 1)
  inns: number;
  ball: string;
  kind: "wicket" | "milestone" | "spell" | "hunch" | "innings";
  label: string;
}

const overOf = (e: BallEvent) => Number(e.ball.split(".")[0]);
const legal = (e: BallEvent) => e.kind !== "wide" && e.kind !== "noball";
const oversText = (balls: number) => (balls % 6 ? `${Math.floor(balls / 6)}.${balls % 6}` : String(balls / 6));
const credited = (e: BallEvent) => e.kind === "wicket" && e.wicket_kind !== "run out";
const conceded = (e: BallEvent) => e.runs - (e.kind === "runs" ? e.byes ?? 0 : 0);

export function glyph(e: BallEvent): string {
  if (e.kind === "wicket") return "W";
  if (e.kind === "wide") return e.runs > 1 ? `${e.runs}wd` : "wd";
  if (e.kind === "noball") return e.runs > 1 ? `${e.runs}nb` : "nb";
  return e.runs === 0 ? "·" : String(e.runs);
}

/** State after ``cursor`` deliveries. ``ballsPerInnings``: 120 / 300 for limited
 * overs (to show what a chase needs), null for Tests. */
export function liveState(match: FullMatch, cursor: number, ballsPerInnings: number | null): LiveState {
  const balls = match.commentary.slice(0, cursor);
  const inns = balls.length ? balls[balls.length - 1].inns : 1;
  const card = match.innings[inns - 1];
  const order = card?.batting_card.map((b) => b.name) ?? [];
  const bat: Record<string, AtCrease> = {};
  const enter = (name: string) => (bat[name] ??= { name, runs: 0, balls: 0, fours: 0, sixes: 0, striker: false });
  let crease = order.slice(0, 2).map(enter);
  let next = 2;
  const bowl: Record<string, { balls: number; runs: number; wickets: number }> = {};
  let runs = 0, wickets = 0, legalBalls = 0, pRuns = 0, pBalls = 0;
  let lastWicket: string | null = null;
  let thisOver: string[] = [];
  let curOver = -1;

  for (const e of balls) {
    if (e.inns !== inns) continue;
    if (overOf(e) !== curOver) { curOver = overOf(e); thisOver = []; }
    thisOver.push(glyph(e));
    const b = (bowl[e.bowler] ??= { balls: 0, runs: 0, wickets: 0 });
    b.runs += conceded(e);
    runs += e.runs;
    pRuns += e.runs;
    if (legal(e)) { b.balls += 1; legalBalls += 1; pBalls += 1; }
    const striker = enter(e.batter);
    if (e.kind !== "wide") {
      striker.balls += 1;
      const r = e.bat_runs ?? 0;
      striker.runs += r;
      if (r === 4) striker.fours += 1;
      if (r === 6) striker.sixes += 1;
    }
    if (e.kind === "wicket") {
      wickets += 1;
      if (credited(e)) b.wickets += 1;
      const out = bat[e.out ?? ""] ?? striker;
      lastWicket = `${out.name} ${out.runs} (${out.balls}) · ${e.how ?? "out"}`;
      crease = crease.filter((c) => c.name !== out.name);
      if (wickets < 10 && next < order.length) crease.push(enter(order[next++]));
      pRuns = 0; pBalls = 0;
    }
    // Whoever faced this ball stays visible at the crease even if the card order differs.
    if (!crease.includes(striker) && e.kind !== "wicket") crease = [striker, ...crease].slice(0, 2);
  }

  const now = balls.filter((e) => e.inns === inns);
  const last = now[now.length - 1];
  const nextBall = match.commentary[cursor];
  const onStrike = nextBall && nextBall.inns === inns ? nextBall.batter : last?.batter;
  crease.forEach((c) => (c.striker = c.name === onStrike));
  const bowler = last ? { name: last.bowler, ...bowl[last.bowler] } : null;
  const target = card?.target ?? null;
  const ended = cursor >= match.commentary.length;
  return {
    started: cursor > 0,
    inns,
    batting: card?.batting ?? "",
    bowling: card?.bowling ?? "",
    runs, wickets,
    overs: oversText(legalBalls),
    crease,
    bowler: bowler && { name: bowler.name, overs: oversText(bowler.balls), runs: bowler.runs, wickets: bowler.wickets },
    thisOver,
    partnership: { runs: pRuns, balls: pBalls },
    target,
    need: target && ballsPerInnings ? { runs: Math.max(0, target - runs), balls: Math.max(0, ballsPerInnings - legalBalls) } : null,
    lastWicket,
    ended,
  };
}

/** Wickets, fifties and hundreds, big spells, captain's hunches and innings ends. */
export function keyMoments(match: FullMatch, isTest: boolean): Moment[] {
  const out: Moment[] = [];
  const spellMark = isTest ? 5 : match.env.startsWith("ODI") ? 4 : 3;
  let runsBy: Record<string, number> = {};
  let wktsBy: Record<string, number> = {};
  let inns = 0;
  const ev = match.commentary;
  ev.forEach((e, i) => {
    if (e.inns !== inns) { inns = e.inns; runsBy = {}; wktsBy = {}; }
    const at = i + 1;
    if (e.text.startsWith("Captain's hunch")) out.push({ at, inns, ball: e.ball, kind: "hunch", label: `Hunch: ${e.bowler} has a bowl` });
    const before = runsBy[e.batter] ?? 0;
    const after = before + (e.kind === "wide" ? 0 : e.bat_runs ?? 0);
    runsBy[e.batter] = after;
    for (const mark of [50, 100, 150, 200, 250, 300]) {
      if (before < mark && after >= mark) out.push({ at, inns, ball: e.ball, kind: "milestone", label: `${e.batter} ${mark === 50 ? "fifty" : mark === 100 ? "hundred" : mark}` });
    }
    if (e.kind === "wicket") {
      out.push({ at, inns, ball: e.ball, kind: "wicket", label: `${e.out} ${e.how ?? "out"}` });
      if (credited(e)) {
        wktsBy[e.bowler] = (wktsBy[e.bowler] ?? 0) + 1;
        if (wktsBy[e.bowler] === spellMark) out.push({ at, inns, ball: e.ball, kind: "spell", label: `${e.bowler}: ${spellMark} wickets` });
      }
    }
    if (!ev[i + 1] || ev[i + 1].inns !== e.inns) {
      const card = match.innings[e.inns - 1];
      out.push({ at, inns, ball: e.ball, kind: "innings", label: `End of innings: ${card?.runs}/${card?.wickets}${card?.declared ? "d" : ""}` });
    }
  });
  return out;
}

/** Index after which an over finished (for "end of over" lines in the feed). */
export function overEnds(match: FullMatch): Map<number, string> {
  const ev = match.commentary;
  const ends = new Map<number, string>();
  let overRuns = 0;
  ev.forEach((e, i) => {
    overRuns += e.runs;
    const n = ev[i + 1];
    if (!n || n.inns !== e.inns || overOf(n) !== overOf(e)) {
      ends.set(i, `End of over ${overOf(e) + 1}: ${e.score} · ${overRuns} from the over`);
      overRuns = 0;
    }
  });
  return ends;
}
