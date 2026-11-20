"use client";

import {
  ArrowDownIcon, ArrowUpIcon, CrownIcon, FastForwardIcon, PlayIcon, PlusIcon, SkipForwardIcon, TrophyIcon, XIcon,
} from "@phosphor-icons/react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ROLE_LABEL } from "@/lib/api";
import { loadSeat, money } from "@/lib/auction";
import {
  loadProgress, pointsTable, saveProgress, seasonApi,
  type MatchSummary, type Season, type SeasonPlayer, type SeasonView, type SetupTeam,
} from "@/lib/season";
import { cn } from "@/lib/utils";

export function SeasonRoom({ code }: { code: string }) {
  const [token, setToken] = useState<string | null>(null);
  const [view, setView] = useState<SeasonView | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (t: string | null) => {
    try {
      setView(await seasonApi.get(code, t));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load the season.");
    }
  }, [code]);

  useEffect(() => {
    const t = loadSeat(code)?.token ?? null;
    setToken(t);
    load(t);
  }, [code, load]);

  // Waiting for the host: look again every few seconds.
  useEffect(() => {
    if (!view || view.played || view.host) return;
    const id = setInterval(() => load(token), 5000);
    return () => clearInterval(id);
  }, [view, token, load]);

  if (error) return <div className="grid min-h-[40vh] place-items-center text-destructive">{error}</div>;
  if (!view) return <div className="grid min-h-[40vh] place-items-center text-muted-foreground">Loading the season…</div>;
  if (view.played && view.season) return <SeasonBoard code={code} season={view.season} you={view.you} />;
  return <Setup code={code} view={view} token={token} onPlayed={() => load(token)} />;
}

// ---------------------------------------------------------------- setup

function Setup({ code, view, token, onPlayed }: { code: string; view: SeasonView; token: string | null; onPlayed: () => void }) {
  const teams = view.teams ?? [];
  const mine = teams.find((t) => t.id === view.you);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function play() {
    setBusy(true);
    setError(null);
    try {
      await seasonApi.play(code, token);
      onPlayed();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't play the season.");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-10">
      <div>
        <div className="label mb-2">Room {code} · season · {teams.length === 10 ? "IPL format: 14 matches each, then the playoffs" : "double round robin, then the playoffs"}</div>
        <h1 className="font-display text-5xl leading-[0.9] font-black uppercase sm:text-7xl">Pick your <span className="text-signal">XI</span></h1>
        <div className="seam mt-5" aria-hidden />
        <p className="mt-4 max-w-2xl text-muted-foreground">
          Every franchise plays the season with the same eleven and an Impact sub: a bench bowler who bowls but doesn&apos;t bat.
          Bots pick their best XI; yours starts as the engine&apos;s pick, so change it or keep it.
        </p>
      </div>

      <div className="grid gap-10 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {mine ? <XiEditor code={code} team={mine} token={token!} /> : (
          <p className="text-sm text-muted-foreground">You didn&apos;t run a franchise in this auction: every XI is picked by the engine.</p>
        )}
        <section className="space-y-4">
          <div className="label">Starting the season</div>
          {view.host ? (
            <>
              <p className="text-sm text-muted-foreground">Everyone ready? The whole season is simulated at once (a few seconds); then you go through it match by match.</p>
              <Button size="lg" disabled={busy} onClick={play} className="h-12 font-mono uppercase">
                <PlayIcon weight="fill" />{busy ? "Playing 74 matches…" : "Play the season"}
              </Button>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Waiting for the host to start the season. This page updates by itself.</p>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
          <div className="label pt-4">Every XI</div>
          <ul className="divide-y border-y text-xs">
            {teams.map((t) => (
              <li key={t.id} className="py-2">
                <div className="flex justify-between gap-2">
                  <span className="font-semibold">{t.name}</span>
                  <span className="font-mono text-[10px] text-muted-foreground uppercase">{t.id === view.you ? "you" : t.bot ? "bot" : t.owner}{t.picked ? " · picked" : " · auto"}</span>
                </div>
                <div className="mt-0.5 text-muted-foreground">
                  {t.xi.map((id) => t.players.find((p) => p.id === id)?.name).join(", ")}
                  {t.impact && <> · <span className="text-foreground">sub {t.players.find((p) => p.id === t.impact)?.name}</span></>}
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}

function XiEditor({ code, team, token }: { code: string; team: SetupTeam; token: string }) {
  const byId = useMemo(() => Object.fromEntries(team.players.map((p) => [p.id, p])), [team.players]);
  const [xi, setXi] = useState<string[]>(team.xi);
  const [impact, setImpact] = useState<string | null>(team.impact);
  const [state, setState] = useState<{ kind: "idle" | "saving" | "saved" | "error"; msg?: string }>({ kind: "idle" });
  const bench = team.players.filter((p) => !xi.includes(p.id));
  const os = xi.filter((id) => byId[id]?.overseas).length;
  const bowling = xi.filter((id) => ["BOWL", "AR"].includes(byId[id]?.role)).length + (impact && ["BOWL", "AR"].includes(byId[impact]?.role) ? 1 : 0);
  const keeper = xi.some((id) => byId[id]?.role === "WK");
  const squadHasKeeper = team.players.some((p) => p.role === "WK");
  const bowlersAvailable = team.players.filter((p) => ["BOWL", "AR"].includes(p.role)).length;
  const bowlingNeeded = Math.min(5, bowlersAvailable);
  const short = team.players.length < 11;

  const move = (i: number, d: number) => setXi((x) => { const y = [...x]; [y[i], y[i + d]] = [y[i + d], y[i]]; return y; });
  const changed = () => setState({ kind: "idle" });

  async function save() {
    setState({ kind: "saving" });
    try {
      await seasonApi.lineup(code, token, xi, impact);
      setState({ kind: "saved" });
    } catch (e) {
      setState({ kind: "error", msg: e instanceof Error ? e.message : "Couldn't save." });
    }
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="label">{team.name} · batting order</div>
        <div className="flex gap-3 font-mono text-[11px] text-muted-foreground">
          <span className={cn(xi.length !== 11 && "text-destructive")}>{xi.length}/11</span>
          <span className={cn(os > 4 && "text-destructive")}>{os}/4 overseas</span>
          <span className={cn(!keeper && squadHasKeeper && "text-destructive")}>{keeper ? "keeper ✓" : squadHasKeeper ? "no keeper" : "no keeper in squad: a batter keeps"}</span>
          <span className={cn(bowling < bowlingNeeded && "text-destructive")}>{bowling} bowling options</span>
        </div>
      </div>
      {short && <p className="text-sm text-muted-foreground">Your squad has fewer than eleven players, so the engine fields replacements for you.</p>}
      <ol className="divide-y border-y">
        {xi.map((id, i) => {
          const p = byId[id];
          return (
            <li key={id} className="flex items-center gap-2 py-1.5">
              <span className="w-6 font-display text-lg font-bold text-muted-foreground tnum">{i + 1}</span>
              <PlayerName p={p} />
              <Button variant="ghost" size="icon" className="size-7" disabled={i === 0} onClick={() => { move(i, -1); changed(); }} aria-label={`Move ${p.name} up`}><ArrowUpIcon /></Button>
              <Button variant="ghost" size="icon" className="size-7" disabled={i === xi.length - 1} onClick={() => { move(i, 1); changed(); }} aria-label={`Move ${p.name} down`}><ArrowDownIcon /></Button>
              <Button variant="ghost" size="icon" className="size-7" onClick={() => { setXi((x) => x.filter((y) => y !== id)); changed(); }} aria-label={`Drop ${p.name}`}><XIcon /></Button>
            </li>
          );
        })}
      </ol>
      <div className="space-y-2">
        <div className="label">Bench · pick the Impact sub (a bowler)</div>
        <ul className="divide-y border-y">
          {bench.map((p) => (
            <li key={p.id} className="flex items-center gap-2 py-1.5">
              <PlayerName p={p} />
              {["BOWL", "AR"].includes(p.role) && (
                <Button size="sm" variant={impact === p.id ? "default" : "outline"} className="h-7 font-mono text-[10px] uppercase"
                  onClick={() => { setImpact(impact === p.id ? null : p.id); changed(); }}>
                  {impact === p.id ? "Impact sub" : "Make sub"}
                </Button>
              )}
              <Button size="sm" variant="ghost" className="h-7 font-mono text-[10px] uppercase" disabled={xi.length >= 11}
                onClick={() => { setXi((x) => [...x, p.id]); if (impact === p.id) setImpact(null); changed(); }}>
                <PlusIcon />XI
              </Button>
            </li>
          ))}
        </ul>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={short || xi.length !== 11 || state.kind === "saving"} className="font-mono uppercase">
          {state.kind === "saving" ? "Saving…" : "Save my XI"}
        </Button>
        <Button variant="ghost" onClick={() => { setXi(team.xi); setImpact(team.impact); changed(); }}>Undo changes</Button>
        {state.kind === "saved" && <span className="text-sm text-signal">Saved.</span>}
        {state.kind === "error" && <span className="text-sm text-destructive">{state.msg}</span>}
      </div>
    </section>
  );
}

function PlayerName({ p }: { p: SeasonPlayer }) {
  return (
    <span className="min-w-0 flex-1">
      <span className="block truncate text-sm font-medium">{p.name}
        {p.overseas && <span className="ml-1 font-mono text-[9px] text-signal">OS</span>}
        {p.opener && <span className="ml-1 font-mono text-[9px] text-muted-foreground uppercase">opener</span>}
      </span>
      <span className="font-mono text-[10px] text-muted-foreground">{ROLE_LABEL[p.role]} · {money(p.price)}{p.retained ? " · kept" : ""}</span>
    </span>
  );
}

// ---------------------------------------------------------------- the season

function SeasonBoard({ code, season, you }: { code: string; season: Season; you: string | null }) {
  const total = season.matches.length;
  const [seen, setSeen] = useState(0);
  useEffect(() => setSeen(loadProgress(code)), [code]);
  const advance = (n: number) => { const v = Math.min(total, n); saveProgress(code, v); setSeen(v); };

  const idOf = useMemo(() => Object.fromEntries(season.teams.map((t) => [t.name, t.id])), [season.teams]);
  const youName = season.teams.find((t) => t.id === you)?.name ?? null;
  const shown = season.matches.slice(0, seen);
  const leagueCount = season.matches.filter((m) => m.stage === "League").length;
  const table = pointsTable(shown, season.teams.map((t) => t.name));
  const next = season.matches[seen];
  const yourNext = youName ? season.matches.findIndex((m, i) => i >= seen && m.teams.includes(youName)) : -1;
  const done = seen >= total;

  return (
    <div className="space-y-10">
      <div>
        <div className="label mb-2">Room {code} · {season.format} · match {Math.min(seen, total)} of {total}</div>
        {done ? (
          <h1 className="font-display text-5xl leading-[0.9] font-black uppercase sm:text-7xl">
            <TrophyIcon weight="fill" className="mr-2 inline text-signal" />
            <span className={cn(season.champion.id === you && "text-signal")}>{season.champion.name}</span> win the title
          </h1>
        ) : (
          <h1 className="font-display text-5xl leading-[0.9] font-black uppercase sm:text-7xl">The season</h1>
        )}
        <div className="seam mt-5" aria-hidden />
        {done && <p className="mt-4 text-muted-foreground">They beat {season.runner_up.name} in the final.{season.champion.id === you ? " That's your franchise." : ""}</p>}
      </div>

      {!done && next && (
        <div className="flex flex-wrap items-center gap-3 border-l-2 border-signal pl-4">
          <div className="min-w-0 flex-1">
            <div className="label">Next · match {seen + 1}{next.stage !== "League" ? ` · ${next.stage}` : ""}</div>
            <div className="font-display text-2xl font-bold uppercase">{idOf[next.teams[0]]} <span className="text-muted-foreground">v</span> {idOf[next.teams[1]]}</div>
          </div>
          {youName && next.teams.includes(youName) ? (
            <>
              <Button asChild size="lg" className="font-mono uppercase">
                <Link href={`/auction/${code}/season/match/${seen + 1}?live=1`}><PlayIcon weight="fill" />Watch live</Link>
              </Button>
              <Button variant="outline" size="lg" onClick={() => advance(seen + 1)} className="font-mono uppercase">Result</Button>
            </>
          ) : (
            <>
              <Button size="lg" onClick={() => advance(seen + 1)} className="font-mono uppercase"><FastForwardIcon />Next result</Button>
              {yourNext > seen && (
                <Button variant="outline" size="lg" onClick={() => advance(yourNext)} className="font-mono uppercase">To your next match</Button>
              )}
            </>
          )}
          <Button variant="ghost" onClick={() => advance(total)}><SkipForwardIcon />Skip to the end</Button>
        </div>
      )}

      <div className="grid gap-10 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <section className="space-y-2">
          <div className="label">Points table{seen < leagueCount ? ` · after ${shown.filter((m) => m.stage === "League").length} of ${leagueCount} league matches` : ""}</div>
          <table className="w-full text-sm">
            <thead>
              <tr className="font-mono text-[10px] text-muted-foreground uppercase">
                {["#", "Team", "P", "W", "L", "T", "Pts", "NRR"].map((h, i) => <th key={h} className={cn("py-1.5 font-normal", i > 1 ? "text-right" : "text-left")}>{h}</th>)}
              </tr>
            </thead>
            <tbody className="divide-y border-y font-mono tnum">
              {table.map((r, i) => (
                <tr key={r.team} className={cn(idOf[r.team] === you && "bg-signal/10", i === 3 && "border-b-2 border-b-signal/60")}>
                  <td className="py-1.5 text-muted-foreground">{i + 1}</td>
                  <td className="font-sans">{r.team}{idOf[r.team] === you && <span className="ml-1 font-mono text-[10px] text-signal">YOU</span>}</td>
                  <td className="text-right">{r.played}</td><td className="text-right">{r.won}</td><td className="text-right">{r.lost}</td>
                  <td className="text-right">{r.tied}</td><td className="text-right font-semibold">{r.points}</td>
                  <td className="text-right">{r.nrr >= 0 ? "+" : ""}{r.nrr.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="font-mono text-[10px] text-muted-foreground">Top four reach the playoffs. 2 points a win, 1 a tie; net run rate breaks ties.</p>
        </section>

        <section className="space-y-2">
          <div className="label">Results</div>
          <ol className="max-h-[32rem] divide-y overflow-y-auto border-y">
            {shown.length === 0 && <li className="py-3 text-sm text-muted-foreground">No matches yet.</li>}
            {[...shown].reverse().map((m) => <ResultRow key={m.match} code={code} m={m} idOf={idOf} youName={youName} />)}
          </ol>
        </section>
      </div>

      {done && <Caps season={season} idOf={idOf} />}
      <YourXi season={season} you={you} />
    </div>
  );
}

function ResultRow({ code, m, idOf, youName }: { code: string; m: MatchSummary; idOf: Record<string, string>; youName: string | null }) {
  const mine = youName && m.teams.includes(youName);
  const won = mine && m.winner === youName;
  return (
    <li>
      <Link href={`/auction/${code}/season/match/${m.match}`} className={cn("flex items-center gap-3 px-1 py-2 text-xs hover:bg-muted", mine && "bg-signal/5")}>
        <span className="w-14 shrink-0 font-mono text-[10px] text-muted-foreground">{m.stage === "League" ? `#${m.match}` : m.stage}</span>
        <span className="min-w-0 flex-1">
          <span className="font-mono tnum">
            {m.scores.map((s) => `${idOf[s.team]} ${s.runs}/${s.wickets}`).join(" · ")}
          </span>
          <span className="block truncate text-muted-foreground">{m.winner ? `${idOf[m.winner]} ${m.margin}` : m.margin || "Tied"}</span>
        </span>
        {mine && <Badge variant={won ? "default" : "outline"} className="font-mono text-[9px]">{won ? "WON" : m.winner ? "LOST" : "TIED"}</Badge>}
      </Link>
    </li>
  );
}

function Caps({ season, idOf }: { season: Season; idOf: Record<string, string> }) {
  const list = (title: string, rows: Season["caps"]["orange"], stat: (r: Season["caps"]["orange"][number]) => string) => (
    <section className="space-y-2">
      <div className="label"><CrownIcon weight="fill" className="mr-1 inline" />{title}</div>
      <ol className="divide-y border-y text-sm">
        {rows.map((r, i) => (
          <li key={r.id} className="flex justify-between gap-2 py-1.5">
            <span className="truncate"><span className="mr-2 font-mono text-muted-foreground">{i + 1}</span>{r.name} <span className="font-mono text-[10px] text-muted-foreground">{idOf[r.team] ?? r.team}</span></span>
            <span className="font-mono font-semibold tnum">{stat(r)}</span>
          </li>
        ))}
      </ol>
    </section>
  );
  return (
    <div className="grid gap-10 md:grid-cols-2">
      {list("Orange Cap · most runs", season.caps.orange, (r) => `${r.runs} (${r.balls})`)}
      {list("Purple Cap · most wickets", season.caps.purple, (r) => `${r.wickets} wkts`)}
    </div>
  );
}

function YourXi({ season, you }: { season: Season; you: string | null }) {
  if (!you) return null;
  const l = season.lineups[you];
  if (!l) return null;
  return (
    <p className="font-mono text-[11px] text-muted-foreground">
      Your XI ({l.picked ? "your pick" : "engine's pick"}): batting order as named on the scorecards; Impact sub {l.impact ? "set" : "none"}.
    </p>
  );
}
