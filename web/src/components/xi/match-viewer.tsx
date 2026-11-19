"use client";

import { ArrowCounterClockwiseIcon, PauseIcon, PlayIcon, SkipForwardIcon } from "@phosphor-icons/react";
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
import { Table, TableBody, TableCell, TableFooter, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { cn } from "@/lib/utils";
import type { BallEvent, FullMatch, InningsCard } from "@/lib/xi";

const YOU = "Your XI";
const who = (team: string) => (team === YOU ? "You" : "World XI");

export function MatchViewer({ match, isTest }: { match: FullMatch; isTest: boolean }) {
  return (
    <Tabs defaultValue="replay" className="gap-6">
      <TabsList variant="line" className="w-full justify-start border-b">
        <TabsTrigger value="replay" className="font-mono text-xs uppercase">Ball by ball</TabsTrigger>
        <TabsTrigger value="card" className="font-mono text-xs uppercase">Scorecard</TabsTrigger>
        {!isTest && <TabsTrigger value="worm" className="font-mono text-xs uppercase">Worm</TabsTrigger>}
      </TabsList>
      <TabsContent value="replay"><Replay match={match} isTest={isTest} /></TabsContent>
      <TabsContent value="card" className="space-y-12">
        {match.innings.map((inn, i) => <InningsTable key={i} inn={inn} n={i + 1} isTest={isTest} />)}
      </TabsContent>
      {!isTest && <TabsContent value="worm"><Worm match={match} /></TabsContent>}
    </Tabs>
  );
}

// ---------------------------------------------------------------- replay

type Filter = "all" | "wickets" | "boundaries";
const SPEEDS = [{ label: "1×", ms: 700 }, { label: "4×", ms: 175 }, { label: "16×", ms: 45 }];

function isBoundary(e: BallEvent) {
  return e.kind !== "wicket" && (e.bat_runs === 4 || e.bat_runs === 6);
}

function Replay({ match, isTest }: { match: FullMatch; isTest: boolean }) {
  const balls = match.commentary;
  const [cursor, setCursor] = useState(balls.length);   // start with the whole match shown
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    if (!playing) return;
    if (cursor >= balls.length) {
      setPlaying(false);
      return;
    }
    const t = setTimeout(() => setCursor((c) => c + 1), SPEEDS[speed].ms);
    return () => clearTimeout(t);
  }, [playing, cursor, speed, balls.length]);

  const shown = balls.slice(0, cursor);
  const now = shown[shown.length - 1];
  const feed = useMemo(() => {
    const keep = shown.filter((e) => filter === "all" || (filter === "wickets" ? e.kind === "wicket" : isBoundary(e)));
    return keep.slice(-250).reverse();     // newest first; the full match can be thousands of balls in a Test
  }, [shown, filter]);
  const innings = match.innings;
  const curInns = now?.inns ?? 1;
  const winProb = !isTest && match.win_prob.length ? match.win_prob[Math.max(0, cursor - 1)]?.[1] : null;
  const firstBatting = innings[0]?.batting;
  const youFirst = firstBatting === YOU;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_20rem]">
      <div className="min-w-0 space-y-4">
        <div className="flex flex-wrap items-center gap-2">
          {cursor >= balls.length && !playing ? (
            <Button onClick={() => { setCursor(0); setPlaying(true); }} className="font-mono uppercase">
              <PlayIcon weight="fill" />Watch from the first ball
            </Button>
          ) : (
            <Button onClick={() => setPlaying((p) => !p)} className="font-mono uppercase">
              {playing ? <><PauseIcon weight="fill" />Pause</> : <><PlayIcon weight="fill" />Play</>}
            </Button>
          )}
          <ToggleGroup type="single" value={String(speed)} onValueChange={(v) => v && setSpeed(Number(v))} variant="outline" size="sm">
            {SPEEDS.map((s, i) => <ToggleGroupItem key={s.label} value={String(i)} className="font-mono text-[11px]">{s.label}</ToggleGroupItem>)}
          </ToggleGroup>
          <Button variant="ghost" size="sm" onClick={() => { setPlaying(false); setCursor(balls.length); }}>
            <SkipForwardIcon />End
          </Button>
          <Button variant="ghost" size="sm" onClick={() => { setPlaying(false); setCursor(0); }}>
            <ArrowCounterClockwiseIcon />Reset
          </Button>
          <ToggleGroup type="single" value={filter} onValueChange={(v) => v && setFilter(v as Filter)} variant="outline" size="sm" className="ml-auto">
            <ToggleGroupItem value="all" className="font-mono text-[11px] uppercase">All</ToggleGroupItem>
            <ToggleGroupItem value="wickets" className="font-mono text-[11px] uppercase">Wickets</ToggleGroupItem>
            <ToggleGroupItem value="boundaries" className="font-mono text-[11px] uppercase">4s & 6s</ToggleGroupItem>
          </ToggleGroup>
        </div>

        {/* scrubber */}
        <input type="range" min={0} max={balls.length} value={cursor} aria-label="Position in the match"
          onChange={(e) => { setPlaying(false); setCursor(Number(e.target.value)); }}
          className="h-1 w-full cursor-pointer accent-[var(--signal)]" />

        <ol className="max-h-[32rem] divide-y overflow-y-auto border-y" aria-live="polite">
          {feed.length === 0 && <li className="py-6 text-center text-sm text-muted-foreground">Nothing yet.</li>}
          {feed.map((e, i) => (
            <li key={`${e.inns}-${e.ball}-${i}-${e.score}`}
              className={cn("flex gap-3 py-2 text-sm", i === 0 && playing && "animate-in fade-in slide-in-from-top-1")}>
              <span className="w-14 shrink-0 font-mono text-[11px] text-muted-foreground tnum">
                {isTest ? `${e.inns}·` : ""}{e.ball}
              </span>
              <span className={cn("w-7 shrink-0 text-center font-display text-lg leading-5 font-bold",
                e.kind === "wicket" ? "bg-signal text-signal-foreground" : isBoundary(e) ? "text-signal" : "text-muted-foreground")}>
                {e.kind === "wicket" ? "W" : e.kind === "wide" ? "wd" : e.kind === "noball" ? "nb" : e.runs}
              </span>
              <span className={cn("min-w-0 flex-1", e.kind === "wicket" && "font-semibold")}>
                {e.text.replace(/^\S+ /, "")}
              </span>
              <span className="shrink-0 font-mono text-[11px] text-muted-foreground tnum">{e.score}</span>
            </li>
          ))}
        </ol>
      </div>

      {/* live board */}
      <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
        <div className="bg-[oklch(0.17_0.01_150)] p-5 text-[oklch(0.93_0.012_85)]">
          <div className="flex justify-between font-mono text-[10px] tracking-widest uppercase opacity-70">
            <span>{now ? `${who(innings[curInns - 1]?.batting ?? "")} batting` : "Toss"}</span>
            <span>{isTest ? `Innings ${curInns}` : curInns === 1 ? "1st innings" : "Chase"}</span>
          </div>
          <div className="mt-3 font-display text-7xl leading-none font-black text-[oklch(0.67_0.19_27)] tnum">
            {now ? now.score : "0/0"}
          </div>
          <div className="mt-1 font-mono text-xs opacity-70">
            {now ? `over ${now.ball}` : "yet to start"}
            {!isTest && curInns === 2 && innings[1]?.target ? ` · need ${Math.max(0, innings[1].target - Number(now?.score.split("/")[0] ?? 0))}` : ""}
          </div>
          {now && (
            <div className="mt-4 space-y-1 border-t border-white/10 pt-3 font-mono text-xs">
              <div className="flex justify-between"><span className="opacity-60">On strike</span><span>{now.batter}</span></div>
              <div className="flex justify-between"><span className="opacity-60">Bowling</span><span>{now.bowler}</span></div>
            </div>
          )}
        </div>
        {winProb != null && (
          <div>
            <div className="mb-1.5 flex justify-between font-mono text-[11px] uppercase">
              <span className={youFirst ? "text-signal" : ""}>{youFirst ? "You" : "World XI"} {Math.round(winProb * 100)}%</span>
              <span className={!youFirst ? "text-signal" : ""}>{youFirst ? "World XI" : "You"} {Math.round((1 - winProb) * 100)}%</span>
            </div>
            <div className="flex h-2 w-full bg-chart-2">
              <div className={cn("h-full transition-[width] duration-300", "bg-chart-1")} style={{ width: `${winProb * 100}%` }} />
            </div>
            <div className="mt-1 font-mono text-[10px] text-muted-foreground">Win chance for the side batting first</div>
          </div>
        )}
        <div className="font-mono text-[11px] text-muted-foreground">
          {cursor} of {balls.length} deliveries
        </div>
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------- scorecard

function InningsTable({ inn, n, isTest }: { inn: InningsCard; n: number; isTest: boolean }) {
  const batted = inn.batting_card.filter((b) => b.how_out);
  const dnb = inn.batting_card.filter((b) => !b.how_out);
  const extras = inn.extras.wides + inn.extras.noballs + inn.extras.byes;
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <span className="font-mono text-xs text-signal tnum">{String(n).padStart(2, "0")}</span>
        <h3 className="font-display text-3xl font-extrabold uppercase">{who(inn.batting)} {isTest ? `· innings ${n}` : ""}</h3>
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

function Worm({ match }: { match: FullMatch }) {
  const data = useMemo(() => {
    const byOver: Record<number, { over: number; a?: number; b?: number }> = {};
    for (const e of match.commentary) {
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
