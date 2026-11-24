"use client";

import {
  CaretDownIcon, CrownIcon, FastForwardIcon, GavelIcon, PlayIcon, PlusIcon, SkipForwardIcon, TrophyIcon, XIcon,
} from "@phosphor-icons/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { ROLE_LABEL } from "@/lib/api";
import { loadSeat, money } from "@/lib/auction";
import { captainText } from "@/lib/xi";
import { seasonApi, watched, type CapRow, type ImpactWhen, type MatchSummary, type Season, type SeasonPlayer, type SeasonView, type SetupTeam } from "@/lib/season";
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

  // Everyone but the host follows along: look again every few seconds.
  useEffect(() => {
    if (!view || view.host || view.finished) return;
    const id = setInterval(() => load(token), 4000);
    return () => clearInterval(id);
  }, [view, token, load]);

  if (error) return <div className="grid min-h-[40vh] place-items-center text-destructive">{error}</div>;
  if (!view) return <div className="grid min-h-[40vh] place-items-center text-muted-foreground">Loading the season…</div>;
  if (view.started && view.season) return <SeasonBoard code={code} view={view} token={token} setView={setView} />;
  return <Setup code={code} view={view} token={token} setView={setView} />;
}

// ---------------------------------------------------------------- setup

function Setup({ code, view, token, setView }: { code: string; view: SeasonView; token: string | null; setView: (v: SeasonView) => void }) {
  const teams = view.teams;
  const [justSaved, setJustSaved] = useState(false);
  const saved = () => { setJustSaved(true); seasonApi.get(code, token).then(setView).catch(() => {}); };
  const mine = teams.find((t) => t.id === view.you);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      setView(await seasonApi.start(code, token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start the season.");
      setBusy(false);
    }
  }

  return (
    <div className="space-y-10">
      <div>
        <Link href={`/auction/${code}`} className="label hover:text-foreground">← Auction room {code}</Link>
        <div className="label mt-4 mb-2">Season · {teams.length === 10 ? "IPL format: 14 matches each, then the playoffs" : "double round robin, then the playoffs"}</div>
        <h1 className="font-display text-5xl leading-[0.9] font-black uppercase sm:text-7xl">Pick your <span className="text-signal">XI</span></h1>
        <div className="seam mt-5" aria-hidden />
        <p className="mt-4 max-w-2xl text-muted-foreground">
          Every franchise fields an XI and an Impact Player: a bench player who comes on for one of the XI. Bots pick their best;
          yours starts as the engine&apos;s pick. You can change it now or between any of your matches.
        </p>
      </div>

      <div className="grid gap-10 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {mine ? <XiEditor key={xiKey(mine)} code={code} team={mine} token={token!} onSaved={saved} justSaved={justSaved} /> : (
          <p className="text-sm text-muted-foreground">You didn&apos;t run a franchise in this auction: every XI is picked by the engine.</p>
        )}
        <section className="space-y-4">
          <div className="label">Starting the season</div>
          {view.host ? (
            <>
              <p className="text-sm text-muted-foreground">You&apos;re the host: you move the season on, a match at a time or further. Everyone else follows along.</p>
              <Button size="lg" disabled={busy} onClick={start} className="h-12 font-mono uppercase">
                <PlayIcon weight="fill" />{busy ? "Drawing the fixtures…" : "Start the season"}
              </Button>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Waiting for the host to start the season. This page updates by itself.</p>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
          <EveryXi teams={teams} you={view.you} />
        </section>
      </div>
    </div>
  );
}

const xiKey = (t: SetupTeam) => `${t.xi.join(",")}|${t.subs.join(",")}|${t.impact ?? ""}|${t.impact_out ?? ""}|${t.impact_when}|${t.captain ?? ""}`;
const MAX_SUBS = 5;

function EveryXi({ teams, you }: { teams: SetupTeam[]; you: string | null }) {
  return (
    <div>
      <div className="label pt-4">Every XI</div>
      <ul className="divide-y border-y text-xs">
        {teams.map((t) => (
          <li key={t.id} className="py-2">
            <div className="flex justify-between gap-2">
              <span className="font-semibold">{t.name}</span>
              <span className="font-mono text-[10px] text-muted-foreground uppercase">{t.id === you ? "you" : t.bot ? "bot" : t.owner}{t.picked ? " · picked" : " · auto"}</span>
            </div>
            <div className="mt-0.5 text-muted-foreground">
              {t.xi.map((id) => `${t.players.find((p) => p.id === id)?.name ?? ""}${id === t.captain ? " (c)" : ""}`).join(", ")}
              {t.subs.length > 0 && <> · <span className="text-foreground">subs {t.subs.map((s) => t.players.find((p) => p.id === s)?.name).join(", ")}</span></>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Your XI. Starts from the saved one (``team.xi``); after a save the page reloads
 * the season, and a new saved XI re-opens the editor from it (see the ``key`` where
 * it's used), so what you see is always what the next match will use. */
function XiEditor({ code, team, token, onSaved, justSaved = false }: {
  code: string; team: SetupTeam; token: string; onSaved: () => void; justSaved?: boolean;
}) {
  const byId = useMemo(() => Object.fromEntries(team.players.map((p) => [p.id, p])), [team.players]);
  const [xi, setXi] = useState<string[]>(team.xi);
  const [impact, setImpact] = useState<string | null>(team.impact);
  const [subs, setSubs] = useState<string[]>(team.subs);
  const dropSub = (id: string) => { setSubs((s) => s.filter((x) => x !== id)); if (impact === id) setImpact(null); };
  const [impactOut, setImpactOut] = useState<string | null>(team.impact_out);
  const [impactWhen, setImpactWhen] = useState<ImpactWhen>(team.impact_when);
  const [captain, setCaptain] = useState<string | null>(team.captain);
  const [choose, setChoose] = useState(team.choose);
  const [chooseBusy, setChooseBusy] = useState(false);
  const [state, setState] = useState<{ kind: "idle" | "saving" | "saved" | "error"; msg?: string }>({ kind: justSaved ? "saved" : "idle" });
  const bench = team.players.filter((p) => !xi.includes(p.id));
  const os = xi.filter((id) => byId[id]?.overseas).length;
  const bowling = xi.filter((id) => ["BOWL", "AR"].includes(byId[id]?.role)).length
    + ((impact ? [impact] : subs).some((id) => ["BOWL", "AR"].includes(byId[id]?.role)) ? 1 : 0);
  const keeper = xi.some((id) => byId[id]?.role === "WK");
  const squadHasKeeper = team.players.some((p) => p.role === "WK");
  const bowlingNeeded = Math.min(5, team.players.filter((p) => ["BOWL", "AR"].includes(p.role)).length);
  const short = team.players.length < 11;

  const changed = () => setState({ kind: "idle" });
  // Tap a player, then tap where they should go (as in the XI Builder): two XI
  // players swap batting positions; a bench player takes an XI player's place.
  const [held, setHeld] = useState<{ xi: number } | { bench: string } | null>(null);
  function tapXi(i: number) {
    if (held === null) return setHeld({ xi: i });
    if ("xi" in held) {
      if (held.xi !== i) setXi((x) => { const y = [...x]; [y[held.xi], y[i]] = [y[i], y[held.xi]]; return y; });
    } else {
      const incoming = held.bench;
      setXi((x) => x.map((id, k) => (k === i ? incoming : id)));
      dropSub(incoming);
    }
    setHeld(null);
    changed();
  }
  function tapBench(id: string) {
    if (held === null) return setHeld({ bench: id });
    if ("xi" in held) {
      const at = held.xi;
      setXi((x) => x.map((y, k) => (k === at ? id : y)));
      dropSub(id);
      setHeld(null);
      changed();
      return;
    }
    setHeld(held.bench === id ? null : { bench: id });
  }
  const heldName = held && ("xi" in held ? byId[xi[held.xi]]?.name : byId[held.bench]?.name);

  async function save() {
    setState({ kind: "saving" });
    try {
      const named = subs.filter((s) => !xi.includes(s));
      await seasonApi.lineup(code, token, xi, impact && named.includes(impact) ? impact : null,
        captain && xi.includes(captain) ? captain : null,
        named.length && impactOut && xi.includes(impactOut) ? impactOut : null, named.length ? impactWhen : "auto", named);
      setState({ kind: "saved" });
      onSaved();
    } catch (e) {
      setState({ kind: "error", msg: e instanceof Error ? e.message : "Couldn't save." });
    }
  }

  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div className="label">{team.name} · batting order</div>
        <div className="flex flex-wrap gap-3 font-mono text-[11px] text-muted-foreground">
          <span className={cn(xi.length !== 11 && "text-destructive")}>{xi.length}/11</span>
          <span className={cn(os > 4 && "text-destructive")}>{os}/4 overseas</span>
          <span className={cn(!keeper && squadHasKeeper && "text-destructive")}>{keeper ? "keeper ✓" : squadHasKeeper ? "no keeper" : "no keeper in squad: a batter keeps"}</span>
          <span className={cn(bowling < bowlingNeeded && "text-destructive")}>{bowling} bowling options</span>
        </div>
      </div>
      {short && <p className="text-sm text-muted-foreground">Your squad has fewer than eleven players, so the engine fields replacements for you.</p>}
      <div className="border-l-2 border-signal/60 pl-3 text-xs">
        <span className="label mr-2">Captain</span>
        {captain && byId[captain] ? (
          <><span className="font-semibold">{byId[captain].name}</span>{" "}
            <span className="text-muted-foreground">{byId[captain].captaincy ? captainText(byId[captain].captaincy!) : "no IPL or T20I captaincy record"}</span></>
        ) : <span className="text-muted-foreground">tap C on a player (calls the toss and runs the bowling; a better real record, fewer bad calls)</span>}
      </div>
      <p className={cn("font-mono text-[11px]", held ? "text-signal" : "text-muted-foreground")} aria-live="polite">
        {held ? <>Moving {heldName}: tap the spot {"xi" in held ? "to swap with" : "they should take"}, or tap them again to cancel.</>
          : "Tap a player, then tap where they should bat. Tap a bench player, then the player they replace."}
      </p>
      <ol className="divide-y border-y">
        {xi.map((id, i) => {
          const p = byId[id];
          const isHeld = held !== null && "xi" in held && held.xi === i;
          return (
            <li key={id} className={cn("flex items-center gap-2 py-1.5", isHeld && "bg-signal-soft", held && !isHeld && "hover:bg-muted")}>
              <button type="button" onClick={() => tapXi(i)} aria-pressed={isHeld}
                aria-label={held && !isHeld ? `Put ${heldName} at number ${i + 1}` : `Move ${p.name}`}
                className="flex min-w-0 flex-1 items-center gap-2 text-left">
                <span className={cn("w-6 font-display text-lg font-bold tnum", isHeld ? "text-signal" : "text-muted-foreground")}>{i + 1}</span>
                <PlayerName p={p} />
              </button>
              <Button variant={captain === id ? "default" : "ghost"} size="icon" className="size-7 font-mono text-[10px] font-bold"
                onClick={() => { setCaptain(captain === id ? null : id); changed(); }} aria-pressed={captain === id}
                title={captain === id ? "Captain" : "Make captain"} aria-label={`Make ${p.name} captain`}>C</Button>
              <Button variant="ghost" size="icon" className="size-7" onClick={() => { setXi((x) => x.filter((y) => y !== id)); setHeld(null); changed(); }} aria-label={`Drop ${p.name}`}><XIcon /></Button>
            </li>
          );
        })}
      </ol>
      <div className="space-y-2">
        <div className="label">Bench · name up to {MAX_SUBS} substitutes ({subs.length}/{MAX_SUBS})</div>
        <ul className="divide-y border-y">
          {bench.map((p) => {
            const isHeld = held !== null && "bench" in held && held.bench === p.id;
            return (
            <li key={p.id} className={cn("flex items-center gap-2 py-1.5", isHeld && "bg-signal-soft", held && "xi" in held && "hover:bg-muted")}>
              <button type="button" onClick={() => tapBench(p.id)} aria-pressed={isHeld}
                aria-label={held && "xi" in held ? `Bring ${p.name} in for ${heldName}` : `Move ${p.name} into the XI`}
                className="flex min-w-0 flex-1 items-center gap-2 text-left">
                <PlayerName p={p} />
              </button>
              <Button size="sm" variant={subs.includes(p.id) ? "default" : "outline"} className="h-7 font-mono text-[10px] uppercase"
                disabled={!subs.includes(p.id) && subs.length >= MAX_SUBS} aria-pressed={subs.includes(p.id)}
                onClick={() => { if (subs.includes(p.id)) dropSub(p.id); else setSubs((s) => [...s, p.id]); changed(); }}>
                {subs.includes(p.id) ? "Sub ✓" : "Name as sub"}
              </Button>
              <Button size="sm" variant="ghost" className="h-7 font-mono text-[10px] uppercase" disabled={xi.length >= 11}
                onClick={() => { setXi((x) => [...x, p.id]); dropSub(p.id); changed(); }}>
                <PlusIcon />XI
              </Button>
            </li>
            );
          })}
        </ul>
        {subs.length > 0 && choose && (
          <p className="border border-signal/40 bg-signal/5 p-3 text-sm">
            You&apos;re captaining live: at the start of each innings, after each wicket while you bat and before each over you bowl,
            you can bring on one of these subs as your Impact Player. He replaces a player of your choice, who takes no further part.
          </p>
        )}
        {subs.length > 0 && !choose && (
          <div className="space-y-3 border border-signal/40 bg-signal/5 p-3 text-sm">
            <label className="block space-y-1">
              <span className="label block">Impact Player</span>
              <select value={impact && subs.includes(impact) ? impact : ""} className="h-9 w-full border bg-background px-2"
                onChange={(e) => { setImpact(e.target.value || null); changed(); }}>
                <option value="">Let the engine pick after the toss (a bowler if you bat first, a batter if you chase)</option>
                {subs.map((id) => <option key={id} value={id}>{byId[id]?.name} · {ROLE_LABEL[byId[id]?.role].toLowerCase()}</option>)}
              </select>
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1">
                <span className="label block">Comes on for</span>
                <select value={impactOut && xi.includes(impactOut) ? impactOut : ""} className="h-9 w-full border bg-background px-2"
                  onChange={(e) => { setImpactOut(e.target.value || null); changed(); }}>
                  <option value="">Let the engine pick</option>
                  {xi.map((id) => <option key={id} value={id}>{byId[id]?.name}</option>)}
                </select>
              </label>
              <label className="space-y-1">
                <span className="label block">When</span>
                <select value={impactWhen} className="h-9 w-full border bg-background px-2"
                  onChange={(e) => { setImpactWhen(e.target.value as ImpactWhen); changed(); }}>
                  <option value="auto">When he&apos;s needed (engine decides)</option>
                  <option value="start">From the first ball</option>
                  <option value="break">At the innings break</option>
                </select>
              </label>
            </div>
            <p className="text-xs text-muted-foreground">
              IPL rule: you name up to five substitutes and one of them may come on as the Impact Player. He replaces one of your XI,
              who takes no further part; he can bat and bowl a full four overs, and only eleven of your players bat. With four overseas
              players in your XI he must be Indian. &ldquo;When he&apos;s needed&rdquo; plays it like IPL sides do: a bowler comes on for the
              innings you bowl, a batter for the innings you bat.
            </p>
          </div>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={short || xi.length !== 11 || state.kind === "saving"} className="font-mono uppercase">
          {state.kind === "saving" ? "Saving…" : "Save my XI"}
        </Button>
        <Button variant="ghost" onClick={() => { setXi(team.xi); setSubs(team.subs); setImpact(team.impact); setImpactOut(team.impact_out); setImpactWhen(team.impact_when); setCaptain(team.captain); changed(); }}>Undo changes</Button>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={choose} disabled={chooseBusy} className="size-4 accent-[var(--signal)]"
            onChange={async (e) => {
              const box = e.target, on = box.checked;
              setChooseBusy(true);
              setState({ kind: "idle" });
              try { await seasonApi.choose(code, token, on); setChoose(on); onSaved(); }
              catch (err) {
                box.checked = !on;                       // didn't save: show it as it was
                setState({ kind: "error", msg: err instanceof Error ? err.message : "Couldn't change that." });
              }
              finally { setChooseBusy(false); }
            }} />
          Captain my matches live: choose my bowler every over and when my Impact Player comes on
        </label>
        {state.kind === "saved" && <span className="text-sm text-signal">Saved: used from your next match.</span>}
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
        {p.captaincy && p.captaincy.matches >= 5 && <span className="ml-1 font-mono text-[9px] text-signal uppercase" title={captainText(p.captaincy)}>capt</span>}
      </span>
      <span className="font-mono text-[10px] text-muted-foreground">{ROLE_LABEL[p.role]} · {money(p.price)}{p.retained ? " · kept" : ""}</span>
    </span>
  );
}

// ---------------------------------------------------------------- the season

function SeasonBoard({ code, view, token, setView }: { code: string; view: SeasonView; token: string | null; setView: (v: SeasonView) => void }) {
  const router = useRouter();
  const season = view.season as Season;
  const [justSaved, setJustSaved] = useState(false);
  const saved = () => { setJustSaved(true); seasonApi.get(code, token).then(setView).catch(() => {}); };
  const you = view.you;
  const total = view.total ?? season.matches.length;
  const played = season.matches.length;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [seen, setSeen] = useState<number[]>([]);
  useEffect(() => setSeen(watched(code)), [code, played]);

  const idOf = useMemo(() => Object.fromEntries(season.teams.map((t) => [t.name, t.id])), [season.teams]);
  const nameOf = useMemo(() => Object.fromEntries(season.teams.map((t) => [t.id, t.name])), [season.teams]);
  const youName = you ? nameOf[you] : null;
  const next = view.next;
  const nextIsMine = !!(next && you && (next.home === you || next.away === you));
  const mineTeam = view.teams.find((t) => t.id === you);
  // Your most recent match, if it's the latest result and you haven't watched it.
  const fresh = youName ? [...season.matches].reverse().find((m) => m.teams.includes(youName)) : undefined;
  const unwatched = fresh && !season.champion && !seen.includes(fresh.match) && fresh.match === played ? fresh : undefined;

  // The XI panel opens when you ask: "Change XI", or arriving from "Change your
  // XI" at the end of a match (…/season?xi=1).
  const openXi = () => {
    setEditing(true);
    requestAnimationFrame(() => document.getElementById("your-xi")?.scrollIntoView({ behavior: "smooth", block: "start" }));
  };
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("xi")) openXi();
  }, []);
  const xiNames = mineTeam ? mineTeam.xi.map((id) => `${mineTeam.players.find((p) => p.id === id)?.name ?? ""}${id === mineTeam.captain ? " (c)" : ""}`) : [];
  const subName = mineTeam?.impact ? mineTeam.players.find((p) => p.id === mineTeam.impact)?.name
    : mineTeam?.subs.length ? "engine picks" : null;

  async function step(how: "next" | "mine" | "end", thenWatch = false) {
    setBusy(true);
    setError(null);
    try {
      const v = await seasonApi.advance(code, token, how);
      setView(v);
      if (v.season?.live && v.season.live.waiting === you) router.push(`/auction/${code}/season/live`);
      else if (thenWatch && !v.season?.live) router.push(`/auction/${code}/season/match/${v.season!.matches.length}?live=1`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't move the season on.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-10">
      <div>
        <Link href={`/auction/${code}`} className="label hover:text-foreground">← Auction room {code}</Link>
        <div className="label mt-4 mb-2">{season.format} · {played} of {total} played</div>
        {season.champion ? (
          <h1 className="font-display text-5xl leading-[0.9] font-black uppercase sm:text-7xl">
            <TrophyIcon weight="fill" className="mr-2 inline text-signal" />
            <span className={cn(season.champion.id === you && "text-signal")}>{season.champion.name}</span> win the title
          </h1>
        ) : (
          <h1 className="font-display text-5xl leading-[0.9] font-black uppercase sm:text-7xl">The season</h1>
        )}
        <div className="seam mt-5" aria-hidden />
        {season.champion && season.runner_up && (
          <p className="mt-4 text-muted-foreground">They beat {season.runner_up.name} in the final.{season.champion.id === you ? " That's your franchise." : ""}</p>
        )}
        {season.champion && (
          <div className="mt-6 flex flex-wrap gap-2">
            <Button asChild size="lg" className="font-mono uppercase">
              <Link href={`/auction/${code}/season/match/${played}`}><PlayIcon weight="fill" />Watch the final</Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="font-mono uppercase">
              <Link href={`/auction/${code}`}>Auction summary</Link>
            </Button>
            <Button asChild variant="outline" size="lg" className="font-mono uppercase">
              <Link href="/auction"><GavelIcon />New auction</Link>
            </Button>
            <Button asChild variant="ghost" size="lg" className="font-mono uppercase">
              <Link href="/xi">XI Builder</Link>
            </Button>
          </div>
        )}
      </div>

      {unwatched && (
        <div className="flex flex-wrap items-center gap-3 border border-signal/50 bg-signal/5 px-4 py-3">
          <span className="flex-1 text-sm">Your match against <b>{idOf[unwatched.teams.find((t) => t !== youName)!]}</b> has been played.</span>
          <Button asChild className="font-mono uppercase"><Link href={`/auction/${code}/season/match/${unwatched.match}?live=1`}><PlayIcon weight="fill" />Watch it live</Link></Button>
        </div>
      )}

      {season.live && (
        <div className="flex flex-wrap items-center gap-3 border border-signal/50 bg-signal/5 px-4 py-3">
          <span className="flex-1 text-sm">
            Match {season.live.match}: {season.live.waiting === you ? <b>your</b> : <b>{idOf[season.live.waiting] ?? "a"}</b>}{" "}
            captain {season.live.kind === "bat" ? "to decide on the Impact Player" : `to choose who bowls over ${season.live.over}`}.
            The season waits until they do.
          </span>
          <Button asChild className="font-mono uppercase">
            <Link href={`/auction/${code}/season/live`}>{season.live.waiting === you ? (season.live.kind === "bat" ? "Decide" : "Choose your bowler") : "Watch"}</Link>
          </Button>
          {view.host && season.live.waiting !== you && (
            <Button variant="ghost" disabled={busy} className="font-mono uppercase" onClick={async () => {
              if (!token || !season.live) return;
              setBusy(true);
              setError(null);
              try { setView(await seasonApi.bowl(code, token, season.live.key, "rest")); }
              catch (e) { setError(e instanceof Error ? e.message : "Couldn't sim it."); }
              finally { setBusy(false); }
            }}>Sim it for them</Button>
          )}
        </div>
      )}

      {next && (
        <div className="flex flex-wrap items-center gap-3 border-l-2 border-signal pl-4">
          <div className="min-w-0 flex-1">
            <div className="label">Next · match {next.match}{next.stage !== "League" ? ` · ${next.stage}` : ""}</div>
            <div className="font-display text-2xl font-bold uppercase">{next.home} <span className="text-muted-foreground">v</span> {next.away}</div>
          </div>
          {nextIsMine && mineTeam && token && (
            <Button variant="outline" size="lg" onClick={openXi} className="font-mono uppercase">Change XI</Button>
          )}
          {view.host ? (
            <>
              {nextIsMine ? (
                <Button size="lg" disabled={busy} onClick={() => step("next", true)} className="font-mono uppercase"><PlayIcon weight="fill" />Play my match</Button>
              ) : (
                <Button size="lg" disabled={busy} onClick={() => step("next")} className="font-mono uppercase"><FastForwardIcon />Next match</Button>
              )}
              {you && !nextIsMine && (
                <Button variant="outline" size="lg" disabled={busy} onClick={() => step("mine")} className="font-mono uppercase">To my next match</Button>
              )}
              <Button variant="ghost" disabled={busy} onClick={() => step("end")}><SkipForwardIcon />{busy ? "Playing…" : "Skip to the end"}</Button>
            </>
          ) : (
            <span className="text-sm text-muted-foreground">The host moves the season on. This page follows along.</span>
          )}
          {error && <span className="basis-full text-sm text-destructive">{error}</span>}
        </div>
      )}

      {mineTeam && !season.champion && token && (
        <section id="your-xi" className={cn("scroll-mt-20 border", nextIsMine && "border-signal/60")}>
          <button type="button" onClick={() => setEditing((e) => !e)} aria-expanded={editing}
            className="flex w-full items-start justify-between gap-4 px-4 py-3 text-left hover:bg-muted/40">
            <span className="min-w-0">
              <span className="label">Your XI · {mineTeam.name}</span>
              <span className="mt-1 block text-sm">
                {xiNames.map((n, i) => <span key={i}>{i > 0 && <span className="text-muted-foreground"> · </span>}<span className="font-mono text-[10px] text-muted-foreground">{i + 1}</span> {n}</span>)}
                {subName && <span className="text-muted-foreground"> · sub {subName}</span>}
              </span>
            </span>
            <span className="flex shrink-0 items-center gap-1.5 font-mono text-[11px] text-signal uppercase">
              {editing ? "Close" : nextIsMine ? "Change for this match" : "Change XI"}
              <CaretDownIcon className={cn("transition-transform", editing && "rotate-180")} />
            </span>
          </button>
          {editing && <div className="border-t p-4"><XiEditor key={xiKey(mineTeam)} code={code} team={mineTeam} token={token} onSaved={saved} justSaved={justSaved} /></div>}
        </section>
      )}

      <div className="grid gap-10 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <section className="space-y-2">
          <div className="label">Points table</div>
          {/* Fixed column widths: the numbers line up under their headings. */}
          <table className="w-full table-fixed text-sm">
            <colgroup>
              <col className="w-7" /><col />
              <col className="w-9" /><col className="w-9" /><col className="w-9" /><col className="w-9" />
              <col className="w-11" /><col className="w-[4.5rem]" />
            </colgroup>
            <thead>
              <tr className="font-mono text-[10px] text-muted-foreground uppercase">
                <th className="py-1.5 text-left font-normal">#</th>
                <th className="text-left font-normal">Team</th>
                {[["P", "Played"], ["W", "Won"], ["L", "Lost"], ["T", "Tied"], ["Pts", "Points"], ["NRR", "Net run rate"]].map(([h, title]) => (
                  <th key={h} title={title} className="text-right font-normal">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y border-y font-mono tnum">
              {season.table.map((r, i) => (
                <tr key={r.team} className={cn(idOf[r.team] === you && "bg-signal/10", i === 3 && "border-b-2 border-b-signal/60")}>
                  <td className="py-1.5 text-muted-foreground">{i + 1}</td>
                  <td className="truncate font-sans">{r.team}{idOf[r.team] === you && <span className="ml-1 font-mono text-[10px] text-signal">YOU</span>}</td>
                  <td className="text-right">{r.played}</td>
                  <td className="text-right">{r.won}</td>
                  <td className="text-right">{r.lost}</td>
                  <td className="text-right">{r.tied}</td>
                  <td className="text-right font-semibold">{r.points}</td>
                  <td className="text-right">{r.nrr >= 0 ? "+" : ""}{r.nrr.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="font-mono text-[10px] text-muted-foreground">Top four reach the playoffs. 2 points a win, 1 a tie; net run rate breaks ties.</p>
        </section>

        <LatestResults code={code} matches={season.matches} rows={season.table.length} idOf={idOf} youName={youName} />
      </div>

      {played > 0 && <Caps season={season} idOf={idOf} youName={youName} />}
      {!season.champion && <EveryXi teams={view.teams} you={you} />}
    </div>
  );
}

const STAGE_SHORT: Record<string, string> = { "Qualifier 1": "Q1", Eliminator: "EL", "Qualifier 2": "Q2", Final: "Final" };

/** The latest results, one line each, as many as the points table has rows so the
 * two boxes line up; every result in a side panel. */
function LatestResults({ code, matches, rows, idOf, youName }: {
  code: string; matches: MatchSummary[]; rows: number; idOf: Record<string, string>; youName: string | null;
}) {
  const latest = [...matches].reverse().slice(0, rows);
  return (
    <section className="space-y-2">
      <div className="label">Latest results</div>
      <table className="w-full table-fixed text-sm">
        <thead>
          <tr className="font-mono text-[10px] text-muted-foreground uppercase">
            <th className="w-12 py-1.5 text-left font-normal">#</th>
            <th className="text-left font-normal">Match</th>
            <th className="w-24 text-right font-normal">Result</th>
          </tr>
        </thead>
        <tbody className="divide-y border-y font-mono tnum">
          {latest.length === 0 && <tr><td colSpan={3} className="py-1.5 font-sans text-muted-foreground">No matches yet.</td></tr>}
          {latest.map((m) => {
            const mine = youName && m.teams.includes(youName);
            const outcome = !mine ? null : m.winner === youName ? "W" : m.winner ? "L" : "T";
            return (
              <tr key={m.match} className={cn("hover:bg-muted", mine && "bg-signal/5")}>
                <td className="py-1.5 text-muted-foreground">{m.stage === "League" ? m.match : STAGE_SHORT[m.stage]}</td>
                <td className="truncate">
                  <Link href={`/auction/${code}/season/match/${m.match}`} className="hover:text-signal">
                    {m.scores.map((sc) => `${idOf[sc.team]} ${sc.runs}/${sc.wickets}`).join(" v ")}
                  </Link>
                </td>
                <td className="text-right">
                  {m.winner ? `${idOf[m.winner]} won${m.result === "super over" ? " (SO)" : ""}` : "Tied"}
                  {outcome && <span className={cn("ml-1.5 inline-block w-4 text-center text-[10px] font-bold", outcome === "W" ? "bg-signal text-signal-foreground" : "border")}>{outcome}</span>}
                </td>
              </tr>
            );
          })}
          {/* Early in the season: blank rows keep the box the size of the points table. */}
          {Array.from({ length: Math.max(0, rows - Math.max(latest.length, 1)) }, (_, i) => (
            <tr key={`pad${i}`} aria-hidden><td colSpan={3} className="py-1.5">&nbsp;</td></tr>
          ))}
        </tbody>
      </table>
      {matches.length > 0 && (
        <Sheet>
          <SheetTrigger asChild>
            <Button variant="outline" size="sm" className="font-mono text-[11px] uppercase">All results ({matches.length})</Button>
          </SheetTrigger>
          <SheetContent side="right" className="w-full gap-0 sm:max-w-md">
            <SheetHeader className="border-b">
              <SheetTitle>All results</SheetTitle>
            </SheetHeader>
            <ol className="divide-y overflow-y-auto px-2">
              {[...matches].reverse().map((m) => <ResultRow key={m.match} code={code} m={m} idOf={idOf} youName={youName} />)}
            </ol>
          </SheetContent>
        </Sheet>
      )}
    </section>
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
          <span className="font-mono tnum">{m.scores.map((s) => `${idOf[s.team]} ${s.runs}/${s.wickets}`).join(" · ")}</span>
          <span className="block truncate text-muted-foreground">{m.winner ? `${idOf[m.winner]} ${m.margin}` : m.margin || "Tied"}</span>
          {m.player_of_match && (
            <span className="block truncate text-muted-foreground">Player of the match: {m.player_of_match.name} {m.player_of_match.figures}</span>
          )}
        </span>
        {mine && <Badge variant={won ? "default" : "outline"} className="font-mono text-[9px]">{won ? "WON" : m.winner ? "LOST" : "TIED"}</Badge>}
      </Link>
    </li>
  );
}

/** Orange and Purple Caps: the race while the season runs (top five so far),
 * the winners once it's over. Runs with strike rate; wickets with economy. Your
 * players are marked. */
function Caps({ season, idOf, youName }: { season: Season; idOf: Record<string, string>; youName: string | null }) {
  const over = !!season.champion;
  const list = (title: string, color: string, rows: CapRow[], heads: [string, string], stats: (r: CapRow) => [string, string]) => (
    <section className="space-y-2">
      <div className="label"><CrownIcon weight="fill" className="mr-1 inline" style={{ color }} />{title}{over ? "" : " · so far"}</div>
      <table className="w-full text-sm">
        <thead>
          <tr className="font-mono text-[10px] text-muted-foreground uppercase">
            <th className="w-6 py-1 text-left font-normal">#</th>
            <th className="text-left font-normal">Player</th>
            <th className="w-16 text-right font-normal">{heads[0]}</th>
            <th className="w-16 text-right font-normal">{heads[1]}</th>
          </tr>
        </thead>
        <tbody className="divide-y border-y">
          {rows.length === 0 && <tr><td colSpan={4} className="py-2 text-muted-foreground">Nobody yet.</td></tr>}
          {rows.map((r, i) => {
            const [a, b] = stats(r);
            return (
              <tr key={r.id} className={cn(r.team === youName && "bg-signal/5")}>
                <td className="py-1.5 font-mono text-muted-foreground">{i + 1}</td>
                <td className="max-w-0 truncate">
                  {i === 0 && <CrownIcon weight="fill" className="mr-1 inline" style={{ color }} aria-label="holds the cap" />}
                  {r.name} <span className="font-mono text-[10px] text-muted-foreground">{idOf[r.team] ?? r.team}</span>
                  {r.team === youName && <span className="ml-1 font-mono text-[10px] text-signal">YOURS</span>}
                </td>
                <td className="text-right font-mono font-semibold tnum">{a}</td>
                <td className="text-right font-mono text-muted-foreground tnum">{b}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
  return (
    <div className="grid gap-10 md:grid-cols-2 xl:grid-cols-3">
      {season.caps.mvp && list("Player of the season · most impact", "oklch(0.8 0.15 90)", season.caps.mvp, ["Impact", "PoM"],
        (r) => [String(Math.round(r.score ?? 0)), String(r.awards ?? 0)])}
      {list("Orange Cap · most runs", "oklch(0.75 0.17 60)", season.caps.orange, ["Runs", "SR"],
        (r) => [String(r.runs ?? 0), r.sr != null ? r.sr.toFixed(1) : "–"])}
      {list("Purple Cap · most wickets", "oklch(0.6 0.2 300)", season.caps.purple, ["Wkts", "Econ"],
        (r) => [String(r.wickets ?? 0), r.econ != null ? r.econ.toFixed(2) : "–"])}
    </div>
  );
}
