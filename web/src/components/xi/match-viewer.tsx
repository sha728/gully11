"use client";

import {
  ArrowCounterClockwiseIcon, ArrowRightIcon, FastForwardIcon, PauseIcon, PlayIcon, SkipForwardIcon,
} from "@phosphor-icons/react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { glyph, keyMoments, liveState, overEnds, type LiveState, type Moment } from "@/lib/replay";
import { cn } from "@/lib/utils";
import { superOverNo, type BallEvent, type Challenge, type FullMatch, type InningsCard } from "@/lib/xi";

const YOU = "Your XI";
const BALLS: Record<string, number | null> = { Test: null, ODI: 300, T20I: 120, IPL: 120 };
const SPEEDS = [{ label: "1×", ms: 700 }, { label: "4×", ms: 175 }, { label: "16×", ms: 45 }, { label: "64×", ms: 12 }];

/** "You" for your side, the opponent's short name ("Greats") for theirs. */
function useWho(opponent: string) {
  const short = opponent.replace(/^(Test|ODI|T20I|IPL) /, "").replace(/^All-time /, "");
  return (team: string) => (team === YOU ? "You" : short);
}

function isBoundary(e: BallEvent) {
  return e.kind !== "wicket" && (e.bat_runs === 4 || e.bat_runs === 6);
}

/** The whole match page below the back link: header, replay and the cards.
 * ``live``: the series is being played for the first time, so nothing about the
 * result shows until the last ball (or "Skip to result"). */
export function MatchDay({ challenge, match, n, live, vs, summary }: {
  challenge: Challenge; match: FullMatch; n: number; live: boolean; vs?: string; summary: React.ReactNode;
}) {
  const who = useWho(challenge.opponent);
  const before = challenge.matches.slice(0, n - 1);
  const sofar = (upto: typeof before) => {
    const w = upto.filter((m) => m.winner === YOU).length;
    const l = upto.filter((m) => m.winner && m.winner !== YOU).length;
    return `${w}–${l}`;
  };
  const q = (extra: string) => `?${[live ? "live=1" : "", vs ? `vs=${vs}` : "", extra].filter(Boolean).join("&")}`;
  const nextHref = n < 5 ? `/xi/c/${challenge.slug}/match/${n + 1}${q("")}` : `/xi/c/${challenge.slug}${vs ? `?vs=${vs}` : ""}`;
  return (
    <MatchStage match={match} format={challenge.format} live={live} who={who} you={YOU} summary={summary}
      kicker={<>Match {n} of 5 · v {challenge.opponent}{live && <> · series {sofar(before)}</>}</>}
      after={
        <div className="flex flex-wrap items-center gap-4 border-l-2 border-signal pl-4">
          <div>
            <div className="label">Series after match {n}</div>
            <div className="font-display text-3xl font-black tnum">{sofar(challenge.matches.slice(0, n))}</div>
          </div>
          <Button asChild size="lg" className="ml-auto font-mono uppercase">
            <Link href={nextHref}>{n < 5 ? <>Match {n + 1}<ArrowRightIcon /></> : <>The series verdict<ArrowRightIcon /></>}</Link>
          </Button>
        </div>
      } />
  );
}

/** One match: heading, live replay, scorecard and worm. ``who`` turns a team name
 * into its label ("You", "Greats", "RCB"); ``you`` is the viewer's team, if any.
 * ``live`` hides the result (heading, cards, ``summary``) until the last ball;
 * ``after`` shows once it's revealed in a live match (what comes next). */
export function MatchStage({ match, format, live, who, you, kicker, summary, after }: {
  match: FullMatch; format: string; live: boolean; who: (team: string) => string; you: string | null;
  kicker: React.ReactNode; summary?: React.ReactNode; after?: React.ReactNode;
}) {
  const isTest = format === "Test";
  const balls = match.commentary;
  const [cursor, setCursor] = useState(live ? 0 : balls.length);
  const [playing, setPlaying] = useState(live);
  const [speed, setSpeed] = useState(isTest ? 3 : 1);
  const revealed = !live || cursor >= balls.length;

  useEffect(() => {
    if (!playing) return;
    if (cursor >= balls.length) { setPlaying(false); return; }
    const t = setTimeout(() => setCursor((c) => c + 1), SPEEDS[speed].ms);
    return () => clearTimeout(t);
  }, [playing, cursor, speed, balls.length]);

  const youWon = !!you && match.winner === you;
  const headline = match.result === "draw" ? "Match drawn" : match.result === "tie" ? "Match tied"
    : `${who(match.winner ?? "")} ${match.margin}`;
  const [a, b] = match.teams;
  const mine = you && (a === you || b === you);
  const other = mine ? (a === you ? b : a) : b;

  return (
    <div className="space-y-8">
      <div>
        <div className="label mt-4 mb-2">{kicker}</div>
        {revealed ? (
          <h1 className={cn("font-display text-5xl leading-[0.9] font-black uppercase sm:text-7xl", youWon && "text-signal")}>{headline}</h1>
        ) : (
          <h1 className="font-display text-5xl leading-[0.9] font-black uppercase sm:text-7xl">
            {who(mine ? you : a)} <span className="text-muted-foreground">v</span> {who(other)}
            <span className="ml-3 inline-block translate-y-[-0.35em] bg-signal px-2 py-0.5 align-middle font-mono text-xs tracking-widest text-signal-foreground">LIVE</span>
          </h1>
        )}
        <div className="seam mt-5" aria-hidden />
        {match.toss && (
          <p className="mt-3 font-mono text-xs text-muted-foreground">
            Toss: {who(match.toss.winner)} won it{match.toss.captain ? ` (captain ${match.toss.captain})` : ""} and chose to {match.toss.decision} first.
          </p>
        )}
        {revealed && match.result === "draw" && match.margin.includes(": ") && (
          <p className="mt-1 font-mono text-xs text-muted-foreground">Drawn: {match.margin.split(": ")[1]}.</p>
        )}
        {revealed && match.player_of_match && (
          <p className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <span className="label">Player of the match</span>
            <span className="font-display text-2xl font-bold uppercase">{match.player_of_match.name}</span>
            <span className="font-mono text-xs text-muted-foreground">
              {who(match.player_of_match.team)} · {match.player_of_match.figures}
            </span>
          </p>
        )}
      </div>

      {revealed && live && after}

      {revealed && summary}

      <Tabs defaultValue="replay" className="gap-6">
        <TabsList variant="line" className="w-full justify-start border-b">
          <TabsTrigger value="replay" className="font-mono text-xs uppercase">Ball by ball</TabsTrigger>
          {revealed && <TabsTrigger value="card" className="font-mono text-xs uppercase">Scorecard</TabsTrigger>}
          {revealed && !isTest && <TabsTrigger value="worm" className="font-mono text-xs uppercase">Worm</TabsTrigger>}
        </TabsList>
        <TabsContent value="replay">
          <Replay match={match} isTest={isTest} ballsPerInnings={format in BALLS ? BALLS[format] : 120} who={who} live={live}
            cursor={cursor} setCursor={setCursor} playing={playing} setPlaying={setPlaying} speed={speed} setSpeed={setSpeed} />
        </TabsContent>
        {revealed && (
          <TabsContent value="card" className="space-y-12">
            {match.innings.map((inn, i) => <InningsTable key={i} inn={inn} n={i + 1} isTest={isTest} who={who} />)}
            {match.super_overs?.map((inn, i) => (
              <InningsTable key={`so${i}`} inn={inn} n={match.innings.length + i + 1} isTest={false} who={who}
                note={match.super_overs!.length > 2 ? `super over ${Math.floor(i / 2) + 1}` : "super over"} />
            ))}
          </TabsContent>
        )}
        {revealed && !isTest && <TabsContent value="worm"><Worm match={match} who={who} /></TabsContent>}
      </Tabs>
    </div>
  );
}

// ---------------------------------------------------------------- replay

type Filter = "all" | "wickets" | "boundaries";

function Replay({ match, isTest, ballsPerInnings, who, live, cursor, setCursor, playing, setPlaying, speed, setSpeed }: {
  match: FullMatch; isTest: boolean; ballsPerInnings: number | null; who: (t: string) => string; live: boolean;
  cursor: number; setCursor: (f: number | ((c: number) => number)) => void;
  playing: boolean; setPlaying: (f: boolean | ((p: boolean) => boolean)) => void;
  speed: number; setSpeed: (s: number) => void;
}) {
  const balls = match.commentary;
  const [filter, setFilter] = useState<Filter>("all");
  const state = useMemo(() => liveState(match, cursor, ballsPerInnings), [match, cursor, ballsPerInnings]);
  const moments = useMemo(() => keyMoments(match, isTest), [match, isTest]);
  const ends = useMemo(() => overEnds(match), [match]);
  const done = cursor >= balls.length;
  // In a live match only what has happened is listed; afterwards, every moment.
  const seen = moments.filter((m) => m.at <= cursor);
  const upcoming = moments.find((m) => m.at > cursor);

  const feed = useMemo(() => {
    const rows: ({ type: "ball"; e: BallEvent; i: number } | { type: "over"; text: string; i: number })[] = [];
    const from = Math.max(0, cursor - 300);    // a Test can run to thousands of balls
    for (let i = from; i < cursor; i++) {
      const e = balls[i];
      if (filter === "all" || (filter === "wickets" ? e.kind === "wicket" : isBoundary(e))) rows.push({ type: "ball", e, i });
      if (filter === "all" && ends.has(i)) rows.push({ type: "over", text: ends.get(i)!, i });
    }
    return rows.reverse();
  }, [balls, cursor, filter, ends]);

  const winProb = !isTest && match.win_prob.length && cursor > 0 ? match.win_prob[cursor - 1]?.[1] : null;
  const firstBatting = match.innings[0]?.batting;
  const secondBatting = match.teams.find((t) => t !== firstBatting) ?? "";

  const jump = (to: number) => { setPlaying(false); setCursor(to); };

  return (
    <div className="space-y-5">
      <Board state={state} who={who} isTest={isTest} winProb={winProb ?? null} firstBatting={firstBatting} secondBatting={secondBatting}
        superOver={superOverNo(match, state.inns)} />

      <div className="flex flex-wrap items-center gap-2">
        {done && !playing ? (
          <Button onClick={() => { setCursor(0); setPlaying(true); }} className="font-mono uppercase">
            <PlayIcon weight="fill" />{cursor === 0 ? "Start" : "Watch from the first ball"}
          </Button>
        ) : (
          <Button onClick={() => setPlaying((p) => !p)} className="font-mono uppercase">
            {playing ? <><PauseIcon weight="fill" />Pause</> : <><PlayIcon weight="fill" />Play</>}
          </Button>
        )}
        <ToggleGroup type="single" value={String(speed)} onValueChange={(v) => v && setSpeed(Number(v))} variant="outline" size="sm" aria-label="Speed">
          {SPEEDS.map((s, i) => <ToggleGroupItem key={s.label} value={String(i)} className="font-mono text-[11px]">{s.label}</ToggleGroupItem>)}
        </ToggleGroup>
        <Button variant="outline" size="sm" disabled={!upcoming} onClick={() => upcoming && jump(upcoming.at)}>
          <FastForwardIcon />Next moment
        </Button>
        <Button variant="ghost" size="sm" disabled={done} onClick={() => jump(balls.length)}>
          <SkipForwardIcon />{live ? "Skip to result" : "End"}
        </Button>
        <Button variant="ghost" size="sm" onClick={() => jump(0)}>
          <ArrowCounterClockwiseIcon />Restart
        </Button>
      </div>

      <input type="range" min={0} max={balls.length} value={cursor} aria-label="Position in the match"
        onChange={(e) => jump(Number(e.target.value))}
        className="h-1 w-full cursor-pointer accent-[var(--signal)]" />

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0 space-y-3">
          <ToggleGroup type="single" value={filter} onValueChange={(v) => v && setFilter(v as Filter)} variant="outline" size="sm">
            <ToggleGroupItem value="all" className="font-mono text-[11px] uppercase">All</ToggleGroupItem>
            <ToggleGroupItem value="wickets" className="font-mono text-[11px] uppercase">Wickets</ToggleGroupItem>
            <ToggleGroupItem value="boundaries" className="font-mono text-[11px] uppercase">4s & 6s</ToggleGroupItem>
          </ToggleGroup>
          <ol className="max-h-[32rem] divide-y overflow-y-auto border-y" aria-live={playing ? "off" : "polite"}>
            {feed.length === 0 && <li className="py-6 text-center text-sm text-muted-foreground">{cursor === 0 ? "Waiting for the first ball." : "Nothing yet."}</li>}
            {feed.map((row, k) => row.type === "over" ? (
              <li key={`o${row.i}`} className="bg-muted/50 px-2 py-1.5 font-mono text-[11px] text-muted-foreground uppercase">{row.text}</li>
            ) : (
              <li key={`b${row.i}`} className={cn("flex gap-3 py-2 text-sm", k === 0 && playing && "animate-in fade-in slide-in-from-top-1",
                row.e.text.startsWith("Captain's hunch") && "bg-signal/5")}>
                <span className="w-14 shrink-0 font-mono text-[11px] text-muted-foreground tnum">
                  {isTest ? `${row.e.inns}·` : superOverNo(match, row.e.inns) ? "SO·" : ""}{row.e.ball}
                </span>
                <span className={cn("w-8 shrink-0 text-center font-display text-lg leading-5 font-bold",
                  row.e.kind === "wicket" ? "bg-signal text-signal-foreground" : isBoundary(row.e) ? "text-signal" : "text-muted-foreground")}>
                  {glyph(row.e)}
                </span>
                <span className={cn("min-w-0 flex-1", row.e.kind === "wicket" && "font-semibold")}>
                  {row.e.text.replace(/^Captain's hunch: [^.]+\. /, "").replace(/^\S+ /, "")}
                  {row.e.text.startsWith("Captain's hunch") && <span className="ml-2 font-mono text-[10px] text-signal uppercase">captain&apos;s hunch</span>}
                </span>
                <span className="shrink-0 font-mono text-[11px] text-muted-foreground tnum">{row.e.score}</span>
              </li>
            ))}
          </ol>
        </div>
        <Moments moments={seen} cursor={cursor} onJump={jump} isTest={isTest} live={live && !done} />
      </div>
    </div>
  );
}

function Board({ state: s, who, isTest, winProb, firstBatting, secondBatting, superOver }: {
  state: LiveState; who: (t: string) => string; isTest: boolean; winProb: number | null; firstBatting?: string; secondBatting: string;
  superOver: number;
}) {
  return (
    <div className="bg-[oklch(0.17_0.01_150)] text-[oklch(0.93_0.012_85)]">
      <div className="grid gap-px bg-white/10 md:grid-cols-[1.1fr_1.4fr_1fr]">
        {/* score */}
        <div className="bg-[oklch(0.17_0.01_150)] p-5">
          <div className="flex justify-between font-mono text-[10px] tracking-widest uppercase opacity-70">
            <span>{s.started ? `${who(s.batting)} batting` : "Toss done"}</span>
            <span className={cn(superOver > 0 && "font-bold text-[oklch(0.67_0.19_27)] opacity-100")}>
              {isTest ? `Innings ${s.inns}` : superOver ? (superOver % 2 ? "Super over" : "Super over · chase") : s.inns === 1 ? "1st innings" : "Chase"}
            </span>
          </div>
          <div className="mt-3 font-display text-7xl leading-none font-black text-[oklch(0.67_0.19_27)] tnum">
            {s.runs}/{s.wickets}
          </div>
          <div className="mt-1 font-mono text-xs opacity-70">
            {s.started ? `${s.overs} ${s.overs === "1" ? "over" : "overs"}` : "yet to start"}
            {s.need && s.started ? ` · need ${s.need.runs}${s.need.balls == null ? "" : ` from ${s.need.balls}`}` : ""}
            {isTest && s.target ? ` · target ${s.target}` : ""}
          </div>
        </div>
        {/* crease */}
        <div className="bg-[oklch(0.17_0.01_150)] p-5 font-mono text-xs">
          <div className="mb-2 text-[10px] tracking-widest uppercase opacity-60">At the crease</div>
          {s.crease.map((c) => (
            <div key={c.name} className="flex items-baseline justify-between gap-3 py-0.5">
              <span className={cn("truncate", c.striker && "font-semibold")}>{c.name}{c.striker && <span className="text-[oklch(0.67_0.19_27)]"> *</span>}</span>
              <span className="tnum"><b className="text-sm">{c.runs}</b> <span className="opacity-60">({c.balls})</span></span>
            </div>
          ))}
          <div className="mt-2 flex justify-between border-t border-white/10 pt-2 opacity-70">
            <span>Partnership</span><span className="tnum">{s.partnership.runs} ({s.partnership.balls})</span>
          </div>
          {s.lastWicket && <div className="mt-1 truncate opacity-60">Last out: {s.lastWicket}</div>}
        </div>
        {/* bowler + this over */}
        <div className="bg-[oklch(0.17_0.01_150)] p-5 font-mono text-xs">
          <div className="mb-2 text-[10px] tracking-widest uppercase opacity-60">Bowling</div>
          {s.bowler ? (
            <div className="flex items-baseline justify-between gap-3">
              <span className="truncate">{s.bowler.name}</span>
              <span className="tnum">{s.bowler.overs}-{s.bowler.runs}-<b className="text-sm">{s.bowler.wickets}</b></span>
            </div>
          ) : <div className="opacity-60">—</div>}
          <div className="mt-3 text-[10px] tracking-widest uppercase opacity-60">This over</div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {s.thisOver.map((g, i) => (
              <span key={i} className={cn("grid h-7 min-w-7 place-items-center px-1 text-[11px] font-bold tnum",
                g === "W" ? "bg-[oklch(0.67_0.19_27)] text-white" : g === "4" || g === "6" ? "border border-[oklch(0.67_0.19_27)] text-[oklch(0.67_0.19_27)]" : "bg-white/10")}>
                {g}
              </span>
            ))}
          </div>
        </div>
      </div>
      {winProb != null && !superOver && (
        <div className="px-5 pt-3 pb-4">
          <div className="mb-1.5 flex justify-between font-mono text-[11px] uppercase">
            <span>{who(firstBatting ?? "")} {Math.round(winProb * 100)}%</span>
            <span>{Math.round((1 - winProb) * 100)}% {who(secondBatting)}</span>
          </div>
          <div className="flex h-1.5 w-full bg-white/15">
            <div className="h-full bg-[oklch(0.67_0.19_27)] transition-[width] duration-300" style={{ width: `${winProb * 100}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}

function Moments({ moments, cursor, onJump, isTest, live }: {
  moments: Moment[]; cursor: number; onJump: (at: number) => void; isTest: boolean; live: boolean;
}) {
  const listRef = useRef<HTMLOListElement>(null);
  useEffect(() => { listRef.current?.scrollTo({ top: listRef.current.scrollHeight }); }, [moments.length]);
  return (
    <aside className="space-y-2 lg:sticky lg:top-20 lg:self-start">
      <div className="label">Key moments{live ? " so far" : ""}</div>
      <ol ref={listRef} className="max-h-[32rem] space-y-px overflow-y-auto">
        {moments.length === 0 && <li className="py-3 text-sm text-muted-foreground">None yet.</li>}
        {moments.map((m) => (
          <li key={`${m.at}-${m.kind}-${m.label}`}>
            <button type="button" onClick={() => onJump(m.at)}
              className={cn("flex w-full items-baseline gap-2 border-l-2 px-2 py-1.5 text-left text-xs hover:bg-muted",
                m.kind === "wicket" ? "border-signal" : m.kind === "innings" ? "border-foreground" : "border-chart-2",
                m.at === cursor && "bg-muted")}>
              <span className="w-12 shrink-0 font-mono text-[10px] text-muted-foreground tnum">{isTest ? `${m.inns}·` : m.inns > 2 ? "SO·" : ""}{m.ball}</span>
              <span className={cn("min-w-0 flex-1", (m.kind === "milestone" || m.kind === "innings") && "font-semibold")}>{m.label}</span>
            </button>
          </li>
        ))}
      </ol>
    </aside>
  );
}

// ---------------------------------------------------------------- scorecard

function InningsTable({ inn, n, isTest, who, note }: {
  inn: InningsCard; n: number; isTest: boolean; who: (t: string) => string; note?: string;
}) {
  const batted = inn.batting_card.filter((b) => b.how_out);
  const dnb = inn.batting_card.filter((b) => !b.how_out);
  const extras = inn.extras.wides + inn.extras.noballs + inn.extras.byes;
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="font-mono text-xs text-signal tnum">{String(n).padStart(2, "0")}</span>
        <h3 className="font-display text-3xl font-extrabold uppercase">{who(inn.batting)} {isTest ? `· innings ${n}` : ""}</h3>
        {note && <span className="bg-signal px-2 py-0.5 font-mono text-[10px] tracking-widest text-signal-foreground uppercase">{note}</span>}
        <span className="ml-auto font-display text-3xl font-bold tnum">
          {inn.runs}/{inn.wickets}{inn.declared ? "d" : ""} <span className="font-mono text-sm text-muted-foreground">({inn.overs})</span>
        </span>
      </div>
      <div className="grid gap-8 xl:grid-cols-[1.4fr_1fr]">
        <div className="border-y">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {["Batter", "", "R", "B", "4s", "6s", "SR"].map((h, i) => (
                  <TableHead key={i} className={cn("label h-9", i > 1 && "text-right")}>{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody className="font-mono tnum">
              {batted.map((b) => (
                <TableRow key={b.id}>
                  <TableCell className="font-sans font-medium">{b.name}</TableCell>
                  <TableCell className="max-w-48 truncate font-sans text-xs text-muted-foreground">{b.how_out}</TableCell>
                  <TableCell className="text-right font-semibold">{b.runs}</TableCell>
                  <TableCell className="text-right">{b.balls}</TableCell>
                  <TableCell className="text-right">{b.fours}</TableCell>
                  <TableCell className="text-right">{b.sixes}</TableCell>
                  <TableCell className="text-right">{b.balls ? (100 * b.runs / b.balls).toFixed(1) : "–"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
            <TableFooter className="bg-transparent font-mono text-xs">
              <TableRow className="hover:bg-transparent">
                <TableCell className="font-sans">Extras</TableCell>
                <TableCell className="font-sans text-muted-foreground">w {inn.extras.wides}, nb {inn.extras.noballs}, b/lb {inn.extras.byes}</TableCell>
                <TableCell className="text-right">{extras}</TableCell>
                <TableCell colSpan={4} />
              </TableRow>
            </TableFooter>
          </Table>
        </div>
        <div className="space-y-4">
          <div className="border-y">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  {["Bowler", "O", "M", "R", "W", "Econ"].map((h, i) => (
                    <TableHead key={h} className={cn("label h-9", i > 0 && "text-right")}>{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody className="font-mono tnum">
                {inn.bowling_card.map((b) => {
                  const balls = Math.floor(Number(b.overs)) * 6 + Math.round((Number(b.overs) % 1) * 10);
                  return (
                    <TableRow key={b.id}>
                      <TableCell className="font-sans font-medium">{b.name}</TableCell>
                      <TableCell className="text-right">{b.overs}</TableCell>
                      <TableCell className="text-right">{b.maidens}</TableCell>
                      <TableCell className="text-right">{b.runs}</TableCell>
                      <TableCell className="text-right font-semibold">{b.wickets}</TableCell>
                      <TableCell className="text-right">{balls ? (6 * b.runs / balls).toFixed(2) : "–"}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
          {dnb.length > 0 && (
            <p className="text-xs text-muted-foreground"><span className="label mr-2">Did not bat</span>{dnb.map((b) => b.name).join(", ")}</p>
          )}
          {inn.fall_of_wickets.length > 0 && (
            <p className="text-xs leading-relaxed text-muted-foreground">
              <span className="label mr-2">Fall of wickets</span>{inn.fall_of_wickets.join(" · ")}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- worm

function Worm({ match, who }: { match: FullMatch; who: (t: string) => string }) {
  const data = useMemo(() => {
    const byOver: Record<number, { over: number; a?: number; b?: number }> = {};
    for (const e of match.commentary) {
      if (e.inns > 2) continue;     // super overs aren't part of the worm
      const over = Number(e.ball.split(".")[0]) + 1;
      const runs = Number(e.score.split("/")[0]);
      const row = (byOver[over] ??= { over });
      if (e.inns === 1) row.a = runs; else row.b = runs;
    }
    return Object.values(byOver).sort((x, y) => x.over - y.over);
  }, [match.commentary]);
  const config = {
    a: { label: `${who(match.innings[0]?.batting ?? "")} (1st)`, color: "var(--chart-1)" },
    b: { label: `${who(match.innings[1]?.batting ?? "")} (chase)`, color: "var(--chart-2)" },
  } satisfies ChartConfig;
  return (
    <ChartContainer config={config} className="aspect-auto h-80 w-full">
      <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 4 }}>
        <CartesianGrid vertical={false} strokeDasharray="2 4" />
        <XAxis dataKey="over" tickLine={false} axisLine={false} tick={{ fontFamily: "var(--font-mono)", fontSize: 10 }} />
        <YAxis tickLine={false} axisLine={false} width={36} tick={{ fontFamily: "var(--font-mono)", fontSize: 10 }} />
        <ChartTooltip content={<ChartTooltipContent labelFormatter={(_, p) => `Over ${p?.[0]?.payload?.over}`} />} />
        <ChartLegend content={<ChartLegendContent />} />
        <Line isAnimationActive={false} dataKey="a" type="monotone" stroke="var(--color-a)" strokeWidth={2.25} dot={false} connectNulls />
        <Line isAnimationActive={false} dataKey="b" type="monotone" stroke="var(--color-b)" strokeWidth={2.25} dot={false} connectNulls />
      </LineChart>
    </ChartContainer>
  );
}
