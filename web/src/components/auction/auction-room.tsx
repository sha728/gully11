"use client";

import { CrownIcon, GavelIcon, HandPalmIcon, RobotIcon, UserIcon, WifiSlashIcon } from "@phosphor-icons/react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ShareBox } from "@/components/xi/share-box";
import { ROLE_LABEL, type Role } from "@/lib/api";
import {
  auctionApi, loadSeat, money, ROLE_ORDER, saveSeat, useRoom,
  type FranchiseView, type RoomState, type Summary,
} from "@/lib/auction";
import { cn } from "@/lib/utils";

export function AuctionRoom({ code }: { code: string }) {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => { setToken(loadSeat(code)?.token ?? null); setReady(true); }, [code]);
  const room = useRoom(code, token, ready);
  const [saved, setSaved] = useState<{ result: Summary } | null | "missing">(null);

  useEffect(() => {
    if (!room.gone) return;
    auctionApi.get(code).then((r) => setSaved(r.result ? { result: r.result } : "missing")).catch(() => setSaved("missing"));
  }, [room.gone, code]);

  if (room.gone) {
    if (saved === null) return <Centered>Looking for room {code}…</Centered>;
    if (saved === "missing") return <Centered><p>No room with code <b className="font-mono">{code}</b>. It may have ended before it was saved.</p><BackLink /></Centered>;
    return <Ended code={code} summary={saved.result} you={null} />;
  }
  const s = room.state;
  if (!s) return <Centered>Connecting to room {code}…</Centered>;

  return (
    <div className="space-y-6">
      {!room.connected && (
        <div className="flex items-center gap-2 border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          <WifiSlashIcon />Connection lost. Reconnecting…
        </div>
      )}
      {s.phase === "lobby" && <Lobby s={s} send={room.send} error={room.error} onJoin={(t) => setToken(t)} />}
      {s.phase === "live" && <Live s={s} send={room.send} error={room.error} serverNow={room.serverNow} />}
      {s.phase === "ended" && s.result && <Ended code={code} summary={s.result} you={s.you ?? null} min={s.rules.squad_min} />}
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return <div className="grid min-h-[40vh] place-items-center text-center text-muted-foreground"><div className="space-y-4">{children}</div></div>;
}

function BackLink() {
  return <Button asChild variant="outline"><Link href="/auction">Back to the auction</Link></Button>;
}

// ---------------------------------------------------------------- lobby

function Lobby({ s, send, error, onJoin }: { s: RoomState; send: (m: object) => void; error: string | null; onJoin: (token: string) => void }) {
  const open = s.franchises.filter((f) => !f.bot && !f.owner).length;
  const [name, setName] = useState("");
  const [joinError, setJoinError] = useState<string | null>(null);
  const seated = !!s.you;
  const canJoin = !seated && open > 0;

  async function join(franchise?: string) {
    setJoinError(null);
    try {
      const seat = await auctionApi.join(s.code, name.trim() || "Player", franchise);
      saveSeat(seat);
      onJoin(seat.token);
    } catch (err) {
      setJoinError(err instanceof Error ? err.message : "Couldn't join.");
    }
  }

  return (
    <div className="space-y-10">
      <div>
        <div className="label mb-2">{s.mode_name} · {s.franchises.length} franchises · {s.total} players · {s.speed} clock</div>
        <h1 className="font-display text-5xl leading-[0.9] font-black uppercase sm:text-7xl">
          Room <span className="font-mono tracking-[0.15em] text-signal">{s.code}</span>
        </h1>
        <div className="seam mt-5" aria-hidden />
      </div>

      <div className="grid gap-10 lg:grid-cols-[1.2fr_1fr]">
        <section className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <div className="label">Franchises</div>
            {(seated || canJoin) && <span className="font-mono text-[11px] text-muted-foreground">Pick the team you want to run</span>}
          </div>
          <ul className="divide-y border-y">
            {s.franchises.map((f) => {
              const mine = f.id === s.you;
              const free = !f.owner;            // a bot or an empty friend's seat
              return (
                <li key={f.id} className={cn("flex items-center gap-3 py-2.5", mine && "bg-signal/10")}>
                  <TeamTag id={f.id} />
                  <span className="min-w-0 flex-1 truncate">{f.name}</span>
                  {s.mode === "mini" && (
                    <span className="hidden font-mono text-[11px] text-muted-foreground tnum sm:inline" title="Purse left after retentions · retained players · overseas">
                      {money(f.purse)} · {f.size} kept · {f.overseas} OS
                    </span>
                  )}
                  <span className={cn("flex items-center gap-1.5 font-mono text-xs", mine ? "text-signal" : "text-muted-foreground")}>
                    {f.owner ? <><UserIcon />{f.owner}{mine ? " (you)" : ""}</> : f.bot ? <><RobotIcon />bot</> : "open seat"}
                  </span>
                  {free && (seated || canJoin) && (
                    <Button size="sm" variant="outline" className="h-7 font-mono text-[11px] uppercase"
                      onClick={() => (seated ? send({ type: "choose", franchise: f.id }) : join(f.id))}>
                      Take
                    </Button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>

        <section className="space-y-5">
          {canJoin && (
            <form onSubmit={(e) => { e.preventDefault(); join(); }} className="space-y-2 border-l-2 border-signal pl-4">
              <div className="label">Join this auction</div>
              <div className="flex gap-2">
                <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={24} placeholder="Your name" className="h-10" />
                <Button type="submit" className="h-10">Join</Button>
              </div>
              <p className="font-mono text-[11px] text-muted-foreground">Then press Take on the franchise you want, or join and get the next free one.</p>
              {joinError && <p className="text-sm text-destructive">{joinError}</p>}
            </form>
          )}
          {!seated && !canJoin && <p className="text-sm text-muted-foreground">Every seat is taken: you&apos;re watching this room.</p>}
          {open > 0 && (
            <div className="space-y-2">
              <div className="label">Invite {open === 1 ? "a friend" : `${open} friends`}</div>
              <ShareBox path={`/auction/${s.code}`} />
              <p className="font-mono text-[11px] text-muted-foreground">They open the link (or enter code {s.code}) and pick a franchise. Open seats nobody takes become bots when the auction starts.</p>
            </div>
          )}
          {s.host ? (
            <Button size="lg" onClick={() => send({ type: "start" })} className="h-12 w-full font-mono uppercase sm:w-auto">
              <GavelIcon weight="fill" />Start the auction
            </Button>
          ) : seated ? (
            <p className="text-sm text-muted-foreground">Waiting for the host to start.</p>
          ) : null}
          {error && <p className="text-sm text-destructive">{error}</p>}
        </section>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- live

function useCountdown(endsAt: number | undefined, serverNow: () => number) {
  const [left, setLeft] = useState(0);
  useEffect(() => {
    if (endsAt == null) return;
    const id = setInterval(() => setLeft(Math.max(0, endsAt - serverNow())), 100);
    setLeft(Math.max(0, endsAt - serverNow()));
    return () => clearInterval(id);
  }, [endsAt, serverNow]);
  return left;
}

/** Same checks as the server, so the button can say why before you press it. */
function whyNot(s: RoomState, me: FranchiseView | undefined): string | null {
  const lot = s.lot;
  if (!lot || !me) return "Watching";
  if (lot.leader === me.id) return "You're the highest bidder";
  if (me.size >= s.rules.squad_max) return "Your squad is full";
  if (lot.player.overseas && me.overseas >= s.rules.overseas_max) return `You have ${s.rules.overseas_max} overseas players`;
  const reserve = Math.max(0, s.rules.squad_min - me.size - 1) * 30;
  if (lot.next > me.purse - reserve) return "Not enough purse left";
  return null;
}

function Live({ s, send, error, serverNow }: { s: RoomState; send: (m: object) => void; error: string | null; serverNow: () => number }) {
  const lot = s.lot!;
  const p = lot.player;
  const me = s.franchises.find((f) => f.id === s.you);
  const byId = useMemo(() => Object.fromEntries(s.franchises.map((f) => [f.id, f])), [s.franchises]);
  const left = useCountdown(lot.ends_at, serverNow);
  const span = lot.bids.length ? (s.speed === "fast" ? 5 : 10) : (s.speed === "fast" ? 8 : 15);
  const reason = whyNot(s, me);
  const passed = me ? lot.passed.includes(me.id) : false;
  const leading = me && lot.leader === me.id;

  // Keyboard: B to bid, P to pass.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.target instanceof HTMLInputElement) return;
      if (e.key === "b" && !reason) send({ type: "bid", amount: lot.next });
      if (e.key === "p" && me && !leading && !passed) send({ type: "pass" });
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [reason, lot.next, send, me, leading, passed]);

  return (
    <div className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <div className="min-w-0 space-y-6">
        {/* the lot */}
        <div className="bg-[oklch(0.17_0.01_150)] text-[oklch(0.93_0.012_85)]">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-5 py-2.5 font-mono text-[10px] tracking-widest uppercase opacity-80">
            <span>{lot.set_label}</span>
            <span>{s.accelerated ? "Accelerated round · " : ""}Player {s.round.n} of {s.round.of} · room {s.code}</span>
          </div>
          <div className="grid gap-px bg-white/10 md:grid-cols-[1.3fr_1fr]">
            <div className="bg-[oklch(0.17_0.01_150)] p-5">
              <div className="flex flex-wrap gap-1.5">
                <Badge variant="outline" className="border-white/30 font-mono text-[10px] text-inherit">{ROLE_LABEL[p.role]}{p.spinner ? " · spin" : ""}</Badge>
                {p.overseas && <Badge className="bg-[oklch(0.67_0.19_27)] font-mono text-[10px] text-white">Overseas</Badge>}
                <Badge variant="outline" className="border-white/30 font-mono text-[10px] text-inherit">{p.capped ? "Capped" : "Uncapped"}</Badge>
              </div>
              <h1 className="mt-3 font-display text-4xl leading-[0.95] font-black uppercase sm:text-6xl">{p.name}</h1>
              <div className="mt-2 font-mono text-xs opacity-70">
                {p.country ?? "India (uncapped)"}{p.last_team ? ` · last IPL: ${p.last_team} ${p.last_ipl}` : ""}
              </div>
              <dl className="mt-4 grid grid-cols-3 gap-3 font-mono text-xs sm:grid-cols-6">
                <Stat k="T20s" v={p.form.matches} />
                <Stat k="Runs" v={p.form.runs} />
                <Stat k="SR" v={p.form.bat_sr ?? "–"} />
                <Stat k="Wkts" v={p.form.wickets} />
                <Stat k="Econ" v={p.form.econ ?? "–"} />
                <Stat k="IPL games" v={p.ipl_matches ?? 0} />
              </dl>
              <div className="mt-1 font-mono text-[10px] opacity-50">
                {p.record === false ? "No ball-by-ball record: an uncapped domestic player" : "All T20s since 2024"}
                {p.overseas && s.rules.overseas_fee_cap ? ` · fee capped at ${money(s.rules.overseas_fee_cap)} (bids can go higher)` : ""}
              </div>
            </div>
            <div className="flex flex-col bg-[oklch(0.17_0.01_150)] p-5">
              <div className="flex justify-between font-mono text-[10px] tracking-widest uppercase opacity-70">
                <span>Base {money(p.base)}</span><span>Fair {money(p.fair)}</span>
              </div>
              <div className="mt-3 font-display text-6xl leading-none font-black text-[oklch(0.67_0.19_27)] tnum sm:text-7xl">
                {lot.price == null ? money(p.base) : money(lot.price)}
              </div>
              <div className="mt-1 font-mono text-xs">
                {lot.leader ? <><CrownIcon weight="fill" className="mr-1 inline text-[oklch(0.67_0.19_27)]" />{byId[lot.leader]?.name}{lot.leader === s.you ? " (you)" : ""}</> : <span className="opacity-70">No bids yet: opens at base</span>}
              </div>
              <div className="mt-auto pt-4">
                <div className="flex justify-between font-mono text-[11px]">
                  <span className="opacity-70">{left > 0 ? "Going…" : "Hammer"}</span>
                  <span className={cn("tnum", left < 3 && "text-[oklch(0.67_0.19_27)]")}>{left.toFixed(1)} s</span>
                </div>
                <div className="mt-1 h-1.5 bg-white/15">
                  <div className="h-full bg-[oklch(0.67_0.19_27)] transition-[width] duration-100 ease-linear" style={{ width: `${Math.min(100, (left / span) * 100)}%` }} />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* actions */}
        {me ? (
          <div className="flex flex-wrap items-center gap-3">
            <Button size="lg" disabled={!!reason} onClick={() => send({ type: "bid", amount: lot.next })} className="h-14 min-w-56 font-mono text-base uppercase">
              <GavelIcon weight="fill" />Bid {money(lot.next)}
            </Button>
            <Button size="lg" variant="outline" disabled={!!leading || passed} onClick={() => send({ type: "pass" })} className="h-14 font-mono uppercase">
              <HandPalmIcon />{passed ? "Passed" : "Pass"}
            </Button>
            <span className="text-sm text-muted-foreground">
              {reason && reason !== "Watching" ? reason : passed ? "Bots settle it once everyone has passed." : <span className="hidden font-mono text-[11px] sm:inline">Keys: B bid · P pass</span>}
            </span>
            {error && <span className="basis-full text-sm text-destructive">{error}</span>}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">You&apos;re watching this auction.</p>
        )}

        <div className="grid gap-8 md:grid-cols-2">
          <section className="space-y-2">
            <div className="label">Bidding</div>
            <ol className="divide-y border-y font-mono text-xs">
              {lot.bids.length === 0 && <li className="py-2 text-muted-foreground">Nobody has bid yet.</li>}
              {[...lot.bids].reverse().map((b, i) => (
                <li key={`${b.at}-${b.franchise}`} className={cn("flex justify-between py-1.5", i === 0 && "font-semibold")}>
                  <span><TeamTag id={b.franchise} small />{" "}{byId[b.franchise]?.name}</span><span className="tnum">{money(b.amount)}</span>
                </li>
              ))}
            </ol>
          </section>
          <section className="space-y-2">
            <div className="label">Up next</div>
            <ol className="divide-y border-y text-xs">
              {s.upcoming.length === 0 && <li className="py-2 text-muted-foreground">Last player of the round.</li>}
              {s.upcoming.map((u) => (
                <li key={u.id} className="flex justify-between gap-2 py-1.5">
                  <span className="truncate">{u.name} <span className="font-mono text-[10px] text-muted-foreground">{u.role}{u.overseas ? " · OS" : ""}</span></span>
                  <span className="font-mono text-muted-foreground tnum">{money(u.base)}</span>
                </li>
              ))}
            </ol>
          </section>
        </div>
      </div>

      {/* side panel */}
      <aside className="space-y-8">
        <Franchises s={s} />
        {me && <MySquad s={s} me={me} />}
        <Feed s={s} />
      </aside>
    </div>
  );
}

function Stat({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[10px] uppercase opacity-60">{k}</dt>
      <dd className="text-base font-semibold tnum">{v}</dd>
    </div>
  );
}

function TeamTag({ id, small }: { id: string; small?: boolean }) {
  return <span className={cn("inline-block bg-foreground text-center font-mono font-bold text-background", small ? "w-9 px-0.5 text-[9px]" : "w-11 px-1 py-0.5 text-[10px]")}>{id}</span>;
}

function Franchises({ s }: { s: RoomState }) {
  const lot = s.lot;
  return (
    <section className="space-y-2">
      <div className="label">Franchises</div>
      <table className="w-full text-xs">
        <thead>
          <tr className="font-mono text-[10px] text-muted-foreground uppercase">
            <th className="py-1 text-left font-normal">Team</th><th className="text-right font-normal">Purse</th>
            <th className="text-right font-normal">Squad</th><th className="text-right font-normal">OS</th>
          </tr>
        </thead>
        <tbody className="divide-y border-y font-mono tnum">
          {s.franchises.map((f) => (
            <tr key={f.id} className={cn(f.id === s.you && "bg-signal/10", lot?.leader === f.id && "font-semibold")}>
              <td className="py-1.5">
                <TeamTag id={f.id} small />{" "}
                <span className={cn("font-sans", lot?.passed.includes(f.id) && "text-muted-foreground line-through")}>{f.id === s.you ? "You" : f.bot ? "Bot" : f.owner}</span>
                {lot?.leader === f.id && <CrownIcon weight="fill" className="ml-1 inline text-signal" />}
              </td>
              <td className="text-right">{money(f.purse)}</td>
              <td className={cn("text-right", f.size < s.rules.squad_min && "text-muted-foreground")}>{f.size}/{s.rules.squad_max}</td>
              <td className="text-right">{f.overseas}/{s.rules.overseas_max}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function MySquad({ s, me }: { s: RoomState; me: FranchiseView }) {
  const players = me.squad.map((x) => ({ ...x, p: s.players[x.id] })).filter((x) => x.p);
  return (
    <section className="space-y-2">
      <div className="flex items-baseline justify-between">
        <div className="label">Your squad · {me.name}</div>
        <span className="font-mono text-[11px] text-muted-foreground">{me.size < s.rules.squad_min ? `${s.rules.squad_min - me.size} more to reach ${s.rules.squad_min}` : "legal squad"}</span>
      </div>
      {players.length === 0 && <p className="border-y py-2 text-xs text-muted-foreground">Nobody yet.</p>}
      {ROLE_ORDER.map((r) => {
        const group = players.filter((x) => x.p.role === r);
        if (!group.length) return null;
        return (
          <div key={r}>
            <div className="font-mono text-[10px] text-muted-foreground uppercase">{ROLE_LABEL[r as Role]}s · {group.length}</div>
            <ul className="divide-y border-y text-xs">
              {group.map((x) => (
                <li key={x.id} className="flex justify-between gap-2 py-1">
                  <span className="truncate">{x.p.name}{x.p.overseas ? <span className="ml-1 font-mono text-[9px] text-signal">OS</span> : null}</span>
                  <span className="font-mono tnum">{x.retained ? <span className="mr-1 text-[9px] text-muted-foreground uppercase">kept</span> : null}{money(x.paid ?? x.price)}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}

function Feed({ s }: { s: RoomState }) {
  return (
    <section className="space-y-2">
      <div className="label">Hammer</div>
      <ol className="max-h-80 divide-y overflow-y-auto border-y text-xs">
        {s.log.length === 0 && <li className="py-2 text-muted-foreground">Nothing sold yet.</li>}
        {[...s.log].reverse().map((e, i) => (
          <li key={`${e.player}-${i}`} className="flex justify-between gap-2 py-1.5">
            <span className="truncate">{e.name}</span>
            {e.result === "sold"
              ? <span className={cn("shrink-0 font-mono tnum", e.franchise === s.you && "text-signal")}>{e.franchise} · {money(e.price)}</span>
              : <span className="shrink-0 font-mono text-muted-foreground">unsold</span>}
          </li>
        ))}
      </ol>
    </section>
  );
}

// ---------------------------------------------------------------- ended

function Ended({ code, summary, you, min = 18 }: { code: string; summary: Summary; you: string | null; min?: number }) {
  const mine = summary.franchises.find((f) => f.id === you);
  const order = [...summary.franchises].sort((a, b) => (a.id === you ? -1 : b.id === you ? 1 : 0));
  return (
    <div className="space-y-10">
      <div>
        <div className="label mb-2">Room {code} · {summary.sold} sold · {summary.unsold} unsold</div>
        <h1 className="font-display text-5xl leading-[0.9] font-black uppercase sm:text-7xl">
          {mine ? <>Your squad: <span className="text-signal">{mine.squad.length} players</span></> : "Auction over"}
        </h1>
        <div className="seam mt-5" aria-hidden />
        {mine && <p className="mt-4 text-muted-foreground">You spent {money(mine.spent)} and kept {money(mine.purse)} for {mine.name}.</p>}
        {mine && mine.squad.length < min && (
          <p className="mt-2 text-sm text-destructive">That&apos;s short of the {min}-player minimum: the players ran out before your squad was legal.</p>
        )}
        <p className="mt-2 font-mono text-xs text-muted-foreground">Next milestone: every squad plays a simulated season on the match engine.</p>
      </div>

      {summary.reality && <Reality rows={summary.reality} you={you} />}

      {summary.best_value.length > 0 && (
        <section className="space-y-2">
          <div className="label">Best value buys (fair price minus what was paid)</div>
          <ul className="grid gap-px border bg-border sm:grid-cols-5">
            {summary.best_value.map((e) => (
              <li key={e.player} className="bg-card p-3 text-xs">
                <div className="truncate font-semibold">{e.name}</div>
                <div className="font-mono text-muted-foreground">{e.franchise} · {money(e.price)}</div>
                <div className="font-mono text-signal">worth {money(e.fair)}</div>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="grid gap-px border bg-border md:grid-cols-2 xl:grid-cols-3">
        {order.map((f) => <SquadCard key={f.id} f={f} you={f.id === you} />)}
      </div>
      <BackLink />
    </div>
  );
}

function Reality({ rows, you }: { rows: NonNullable<Summary["reality"]>; you: string | null }) {
  const [onlyMine, setOnlyMine] = useState(false);
  const shown = rows.filter((r) => !onlyMine || r.team === you || r.real_team === you);
  const same = rows.filter((r) => r.team === r.real_team).length;
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <div className="label">What really happened · Abu Dhabi, 16 December 2025</div>
          <p className="mt-1 text-sm text-muted-foreground">{same} of {rows.length} players went to the same franchise as in the real auction.</p>
        </div>
        {you && (
          <Button variant="outline" size="sm" onClick={() => setOnlyMine((v) => !v)} className="font-mono text-[11px] uppercase">
            {onlyMine ? "Show all" : `Only ${you}`}
          </Button>
        )}
      </div>
      <div className="overflow-x-auto border-y">
        <table className="w-full text-xs">
          <thead>
            <tr className="font-mono text-[10px] text-muted-foreground uppercase">
              <th className="py-1.5 text-left font-normal">Player</th>
              <th className="text-right font-normal">This room</th>
              <th className="text-right font-normal">Real</th>
            </tr>
          </thead>
          <tbody className="divide-y font-mono tnum">
            {shown.map((r) => (
              <tr key={r.player} className={cn((r.team === you || r.real_team === you) && "bg-signal/5")}>
                <td className="py-1.5 font-sans">{r.name}</td>
                <td className={cn("text-right", r.team === you && "text-signal")}>{r.team ? `${r.team} · ${money(r.price)}` : "unsold"}</td>
                <td className={cn("text-right", r.team === r.real_team && "font-semibold")}>{r.real_team} · {money(r.real_price)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function SquadCard({ f, you }: { f: Summary["franchises"][number]; you: boolean }) {
  return (
    <section className={cn("space-y-3 bg-card p-4", you && "ring-2 ring-signal ring-inset")}>
      <div className="flex items-baseline justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-display text-xl font-bold uppercase">{f.name}</div>
          <div className="font-mono text-[11px] text-muted-foreground">{you ? "You" : f.bot ? "Bot" : f.owner} · {f.squad.length} players</div>
        </div>
        <div className="text-right font-mono text-xs tnum">{money(f.spent)}<div className="text-[10px] text-muted-foreground">{money(f.purse)} left</div></div>
      </div>
      {ROLE_ORDER.map((r) => {
        const group = f.squad.filter((x) => x.player?.role === r).sort((a, b) => b.price - a.price);
        if (!group.length) return null;
        return (
          <div key={r}>
            <div className="font-mono text-[10px] text-muted-foreground uppercase">{ROLE_LABEL[r as Role]}s</div>
            <ul className="text-xs">
              {group.map((x) => (
                <li key={x.id} className="flex justify-between gap-2 py-0.5">
                  <span className="truncate">{x.player.name}{x.player.overseas ? <span className="ml-1 font-mono text-[9px] text-signal">OS</span> : null}{x.retained ? <span className="ml-1 font-mono text-[9px] text-muted-foreground uppercase">kept</span> : null}</span>
                  <span className="font-mono tnum">{money(x.price)}</span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
