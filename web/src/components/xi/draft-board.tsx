"use client";

import { ArrowsDownUpIcon, CheckIcon, CircleIcon, CrosshairIcon, SpinnerGapIcon, TrophyIcon, XIcon } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fmt, ROLE_LABEL } from "@/lib/api";
import { cn } from "@/lib/utils";
import { captainText, isOverseas, KEEPER_SLOT, XI_COPY, xiApi, type Challenge, type DraftCandidate, type DraftView, type LineupSlot, type XIFormat, rememberDaily } from "@/lib/xi";

const MAX_OVERSEAS = 4;
const ROLL_MS = 1100;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Compact batting range, e.g. [3,4,5,6,9,10,11] -> "3–6, 9–11". */
function range(slots: number[]): string {
  const s = [...slots].sort((a, b) => a - b);
  const out: string[] = [];
  for (let i = 0; i < s.length; i++) {
    let j = i;
    while (j + 1 < s.length && s[j + 1] === s[j] + 1) j++;
    out.push(i === j ? `${s[i]}` : `${s[i]}–${s[j]}`);
    i = j;
  }
  return out.join(", ");
}

/**
 * The draft is held by the API: this board shows what it returns and sends each
 * spin, pick and move back. Spins arrive only as they are revealed, and the legal
 * slots for each candidate and move come from the server, which checks them
 * against spins the browser never sees.
 */
export function DraftBoard({ initial, rival }: { initial: DraftView; rival: Challenge | null }) {
  const router = useRouter();
  const [d, setD] = useState(initial);
  const [view, setView] = useState<number | null>(initial.revealed ? initial.revealed - 1 : null);
  const [aim, setAim] = useState<number | null>(null);            // empty slot the next pick should take
  const [moving, setMoving] = useState<number | null>(null);      // slot whose player is being moved
  const [rolling, setRolling] = useState<string | null>(null);    // reel label while spinning
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { format, status } = d;
  const t20 = format === "T20I" || format === "IPL";

  async function act(fn: () => Promise<DraftView>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      setD(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function spin() {
    if (!d.can_spin || busy) return;
    setBusy(true);
    setError(null);
    setAim(null);
    setMoving(null);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const { eras, sides } = d.reel;
    const label = () => `${eras[Math.floor(Math.random() * eras.length)]} · ${sides[Math.floor(Math.random() * sides.length)]}`;
    let timer: ReturnType<typeof setInterval> | null = null;
    if (!reduced) {
      setRolling(label());
      timer = setInterval(() => setRolling(label()), 70);
    }
    try {
      const [next] = await Promise.all([xiApi.spin(d.id), reduced ? null : sleep(ROLL_MS)]);
      setD(next);
      setView(next.revealed - 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't spin.");
    } finally {
      if (timer) clearInterval(timer);
      setRolling(null);
      setBusy(false);
    }
  }

  function pick(c: DraftCandidate, spinNo: number) {
    const slot = aim && c.options.includes(aim) ? aim : undefined;
    setAim(null);
    act(() => xiApi.pick(d.id, spinNo, c.id, slot));
  }

  function tapSlot(slot: number) {
    setError(null);
    const here = d.lineup[slot - 1];
    if (moving !== null) {
      const from = moving;
      setMoving(null);
      if (from !== slot && d.lineup[from - 1].targets.includes(slot)) act(() => xiApi.move(d.id, from, slot));
      return;
    }
    if (here.player) {
      if (here.targets.length) setMoving(slot);
      else setError(`${here.player.name} has nowhere else to bat.`);
    } else {
      setAim(aim === slot ? null : slot);
    }
  }

  function remove(slot: number) {
    const spinNo = d.lineup[slot - 1].spin;
    if (!spinNo) return;
    setMoving(null);
    setView(spinNo - 1);
    act(() => xiApi.unpick(d.id, spinNo));
  }

  async function play() {
    setBusy(true);
    setError(null);
    try {
      const res = await xiApi.play(d.id);
      if (d.daily) rememberDaily(format, d.daily, d.id);
      // Straight into match day: the series plays out live, one match at a time.
      router.push(`/xi/c/${res.slug}/match/1?live=1${res.rival ? `&vs=${res.rival}` : ""}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't play the series.");
      setBusy(false);
    }
  }

  const shown = view !== null && view < d.spins.length ? d.spins[view] : null;
  const captainId = d.captain ?? d.captain_auto;
  const latest = d.spins[d.spins.length - 1];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="label mb-2">
            {d.daily ? `Daily challenge · ${d.daily}` : `Draw #${d.seed}`} · {XI_COPY[format].title}
          </div>
          <h1 className="font-display text-5xl leading-[0.9] font-extrabold uppercase sm:text-6xl">Draft your XI</h1>
        </div>
        {rival && (
          <div className="border-l-2 border-signal pl-3">
            <div className="label">Score to top</div>
            <div className="font-display text-2xl font-bold uppercase">{rival.result.verdict}</div>
          </div>
        )}
      </div>
      <div className="seam" aria-hidden />

      <div className="flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs">
        <Rule ok={status.picked === 11} label={`${status.picked}/11 picked`} />
        <Rule ok={status.openers === 2} label={`Openers ${status.openers}/2`} />
        <Rule ok={status.keeper_top6} label="Keeper in the top six" />
        {status.overseas !== null && (
          <Rule ok={status.overseas <= MAX_OVERSEAS} label={`Overseas ${status.overseas}/${MAX_OVERSEAS}`} neutral />
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,23rem)_1fr]">
        {/* Team sheet: batting order */}
        <div className="order-2 lg:order-1 lg:sticky lg:top-20 lg:self-start">
          <div className="mb-2 flex items-baseline justify-between">
            <span className="label">Batting order</span>
            <span className="font-mono text-[10px] text-muted-foreground">
              {moving ? "tap a highlighted spot" : "tap a player to move"}
            </span>
          </div>
          <ol className="divide-y border-y">
            {d.lineup.map((pos) => {
              const p = pos.player;
              const origin = pos.spin ? d.spins[pos.spin - 1] : null;
              const target = moving !== null && moving !== pos.slot && d.lineup[moving - 1].targets.includes(pos.slot);
              const dead = moving !== null && moving !== pos.slot && !target;
              const label = pos.slot === KEEPER_SLOT && p && p.role !== "WK" ? "No. 6" : pos.label;
              return (
                <li key={pos.slot}
                  className={cn("flex items-center border-l-2 transition-colors",
                    moving === pos.slot || aim === pos.slot ? "border-signal bg-signal-soft"
                      : target ? "border-signal/60 bg-signal-soft/50"
                      : "border-transparent hover:bg-muted",
                    dead && "opacity-40")}>
                  <button type="button" onClick={() => tapSlot(pos.slot)} disabled={dead || busy}
                    aria-pressed={moving === pos.slot || aim === pos.slot}
                    className="flex min-w-0 flex-1 items-center gap-3 py-2.5 pr-2 pl-3 text-left">
                    <span className="w-5 font-display text-xl font-bold text-muted-foreground tnum">{pos.slot}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
                        {label}{origin ? ` · ${origin.era} ${origin.side}` : ""}
                      </span>
                      {p ? (
                        <span className="block truncate font-display text-lg leading-tight font-bold uppercase">{p.name}</span>
                      ) : (
                        <span className="block text-sm text-muted-foreground italic">
                          {aim === pos.slot ? "next pick goes here" : "empty"}
                        </span>
                      )}
                    </span>
                    {target && <span className="font-mono text-[10px] text-signal uppercase">{p ? "swap" : "move"}</span>}
                    {!target && p && <Badge variant="outline" className="font-mono text-[9px]">{p.role}</Badge>}
                    {!p && !moving && <CrosshairIcon className={cn("size-3.5", aim === pos.slot ? "text-signal" : "text-muted-foreground/50")} />}
                  </button>
                  {p && !moving && (
                    <button type="button" onClick={() => act(() => xiApi.captain(d.id, d.captain === p.id ? null : p.id))} disabled={busy}
                      aria-pressed={captainId === p.id} title={captainId === p.id ? (d.captain ? "Your captain (tap to let the engine choose)" : "Leads if you don't choose: best captaincy record in your XI") : "Make captain"}
                      className={cn("grid size-6 shrink-0 place-items-center font-mono text-[10px] font-bold",
                        d.captain === p.id ? "bg-signal text-signal-foreground"
                          : captainId === p.id ? "border border-signal text-signal"
                          : "border border-transparent text-muted-foreground/60 hover:border-border hover:text-foreground")}>
                      C
                    </button>
                  )}
                  {p && !moving && (
                    <button type="button" aria-label={`Remove ${p.name}`} onClick={() => remove(pos.slot)} disabled={busy}
                      className="px-2.5 py-3 text-muted-foreground hover:text-foreground"><XIcon className="size-3.5" /></button>
                  )}
                  {moving === pos.slot && (
                    <button type="button" aria-label="Cancel move" onClick={() => setMoving(null)}
                      className="px-2.5 py-3 text-muted-foreground hover:text-foreground"><XIcon className="size-3.5" /></button>
                  )}
                </li>
              );
            })}
          </ol>
          <CaptainLine lineup={d.lineup} chosen={d.captain} captainId={captainId} format={format} />
          <p className="mt-2 font-mono text-[10px] leading-relaxed text-muted-foreground">
            1–2 openers · 3–6 batters, keepers, all-rounders · 6 is the keeper&apos;s unless one bats higher ·
            7–8 all-rounders or spinners · 9–11 bowlers or all-rounders
          </p>
        </div>

        {/* Spin machine and the list for the shown spin */}
        <section className="order-1 min-w-0 lg:order-2">
          <div className="relative mb-4 overflow-hidden border bg-card">
            <div className="flex flex-wrap items-center gap-4 p-4 sm:p-5">
              <div className="min-w-0 flex-1 basis-56">
                <div className="label mb-1">
                  {rolling ? "Spinning…" : shown ? `Spin ${shown.spin} of ${d.total}` : "Eleven spins. One player from each."}
                </div>
                <div aria-live="polite"
                  className={cn("font-display text-4xl leading-none font-black text-balance uppercase sm:text-5xl",
                    rolling && "text-muted-foreground blur-[0.5px]")}>
                  {rolling ?? (shown ? `${shown.era} ${shown.side}` : "Ready?")}
                </div>
              </div>
              {d.revealed < d.total && (
                <Button size="lg" onClick={spin} disabled={!d.can_spin || busy}
                  title={d.waiting ? "Pick a player from your last spin first" : undefined}
                  className="h-12 w-full px-6 font-mono uppercase sm:w-auto">
                  <SpinnerGapIcon className={cn(rolling && "animate-spin")} weight="bold" />
                  {d.revealed === 0 ? "Spin" : "Spin again"}
                </Button>
              )}
            </div>
            {/* Spins so far: tap one to re-pick from it */}
            <div className="flex gap-1 overflow-x-auto border-t px-4 py-2 sm:px-5" aria-label="Spins">
              {Array.from({ length: d.total }, (_, i) => {
                const s = d.spins[i];
                return (
                  <button key={i} type="button" disabled={!s || !!rolling} onClick={() => setView(i)}
                    aria-label={s ? `Spin ${i + 1}: ${s.era} ${s.side}` : `Spin ${i + 1}, not spun yet`}
                    aria-current={view === i ? "true" : undefined}
                    className={cn("grid size-8 shrink-0 place-items-center border font-mono text-xs",
                      view === i ? "border-signal bg-signal text-signal-foreground"
                        : s?.pick ? "border-foreground/40 bg-muted"
                        : s ? "border-signal/60 text-foreground" : "border-dashed border-border text-muted-foreground/50")}>
                    {s?.pick && view !== i ? <CheckIcon className="size-3" weight="bold" /> : i + 1}
                  </button>
                );
              })}
            </div>
          </div>

          {shown && !rolling ? (
            <>
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-sm text-muted-foreground">
                  {shown.pick ? `You took ${shown.candidates.find((c) => c.id === shown.pick!.id)?.name}. Pick someone else to swap.`
                    : "Pick one player from this spin."}
                  {aim ? ` They'll bat at ${aim} if they can.` : ""}
                </span>
                <span className="label normal-case tracking-normal">Figures from that era; legends show career totals</span>
              </div>
              <div className="border-y">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left">
                      <th className="label h-9 px-2 font-normal">Player</th>
                      <th className="label hidden h-9 px-2 text-right font-normal sm:table-cell">M</th>
                      <th className="label h-9 px-2 text-right font-normal">Runs</th>
                      <th className="label h-9 px-2 text-right font-normal">{t20 ? "SR" : "Avg"}</th>
                      <th className="label h-9 px-2 text-right font-normal">Wkts</th>
                      <th className="label hidden h-9 px-2 text-right font-normal sm:table-cell">Econ</th>
                      <th className="h-9 w-20" />
                    </tr>
                  </thead>
                  <tbody className="font-mono tnum">
                    {shown.candidates.map((c) => {
                      const mine = shown.pick?.id === c.id;
                      const lands = aim && c.options.includes(aim) ? aim : c.options[0];
                      return (
                        <tr key={c.id} className={cn("border-b last:border-0", mine && "bg-signal-soft", c.why && !mine && "opacity-45")}>
                          <td className="px-2 py-2 font-sans">
                            <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                              <span className="mr-0.5 font-semibold">{c.name}</span>
                              {c.kind === "legend" && <Badge className="bg-signal font-mono text-[9px] text-signal-foreground">Legend</Badge>}
                              {c.opener && <Badge variant="secondary" className="font-mono text-[9px]">Opener</Badge>}
                              {c.captaincy && c.captaincy.matches >= 5 && (
                                <Badge variant="outline" className="border-signal/50 font-mono text-[9px] text-signal" title={captainText(c.captaincy)}>Capt</Badge>
                              )}
                              {c.spinner && <Badge variant="secondary" className="font-mono text-[9px]">Spin</Badge>}
                              {format === "IPL" && isOverseas(c) && <Badge variant="outline" className="font-mono text-[9px]">OS</Badge>}
                            </div>
                            <div className="font-mono text-[10px] text-muted-foreground">
                              {ROLE_LABEL[c.role]} · {c.years}{format === "IPL" && c.country ? ` · ${c.country}` : ""} · bats {range(c.slots)}
                            </div>
                          </td>
                          <td className="hidden px-2 text-right text-muted-foreground sm:table-cell">{fmt(c.matches)}</td>
                          <td className="px-2 text-right">{fmt(c.runs)}</td>
                          <td className="px-2 text-right">{t20 ? fmt(c.bat_sr, 1) : fmt(c.bat_avg, 1)}</td>
                          <td className="px-2 text-right">{fmt(c.wickets)}</td>
                          <td className="hidden px-2 text-right sm:table-cell">{fmt(c.bowl_econ, 2)}</td>
                          <td className="px-2 py-1.5 text-right">
                            <Button size="sm" variant={mine ? "default" : "outline"} disabled={!!c.why || mine || busy}
                              title={c.why ?? (mine ? undefined : `Bats at ${lands}`)}
                              onClick={() => pick(c, shown.spin)} className="font-mono text-[11px] uppercase">
                              {mine ? <><CheckIcon />{shown.pick!.slot}</> : c.why ? "—" : "Pick"}
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          ) : !rolling && (
            <div className="grid min-h-48 place-items-center border border-dashed p-8 text-center text-sm text-muted-foreground">
              <div className="max-w-sm space-y-2">
                <p>Each spin lands on an era and a {XI_COPY[format].unit}. Pick one player from it, then spin again.</p>
                <p className="font-mono text-[11px]">Openers open, the keeper bats in the top six, spinners and all-rounders at 7–8, bowlers at the tail.</p>
              </div>
            </div>
          )}
        </section>
      </div>

      <div className="sticky bottom-0 z-20 -mx-4 flex flex-wrap items-center gap-4 border-t bg-background/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="min-w-0 flex-1 text-sm">
          {error ? <span className="text-destructive">{error}</span>
            : status.ready ? <span>Ready. Five matches against the {XI_COPY[format].title} Greats.</span>
            : <span className="text-muted-foreground">
                {d.waiting && latest && !latest.pick ? "Pick a player from this spin, then spin again."
                  : status.picked < 11 ? `${11 - status.picked} to pick.`
                  : !status.keeper_top6 ? "Your keeper has to bat in the top six."
                  : "Too many overseas players."}
              </span>}
        </div>
        {moving !== null && (
          <Button variant="ghost" onClick={() => setMoving(null)} className="font-mono uppercase">
            <ArrowsDownUpIcon />Cancel move
          </Button>
        )}
        <Button size="lg" disabled={!status.ready || busy} onClick={play} className="h-11 px-6 font-mono uppercase">
          <TrophyIcon />{busy && status.ready ? "Playing…" : "Play the series"}
        </Button>
      </div>
    </div>
  );
}

function Rule({ ok, label, neutral }: { ok: boolean; label: string; neutral?: boolean }) {
  return (
    <span className={cn("flex items-center gap-1.5", ok ? "text-foreground" : neutral ? "text-destructive" : "text-muted-foreground")}>
      {ok ? <CheckIcon className="size-3.5 text-signal" weight="bold" /> : <CircleIcon className="size-3.5" />}
      {label}
    </span>
  );
}


/** Who leads, and why: their real captaincy record drives the toss call and bowling changes. */
function CaptainLine({ lineup, chosen, captainId, format }: { lineup: LineupSlot[]; chosen: string | null; captainId: string | null; format: XIFormat }) {
  const p = lineup.find((s) => s.player?.id === captainId)?.player;
  return (
    <div className="mt-3 border-l-2 border-signal/60 pl-3 text-xs">
      <div className="label">Captain{chosen ? "" : " · engine's pick"}</div>
      {p ? (
        <div>
          <span className="font-semibold">{p.name}</span>{" "}
          <span className="text-muted-foreground">{p.captaincy ? captainText(p.captaincy) : `no ${XI_COPY[format].title} captaincy record`}</span>
        </div>
      ) : (
        <div className="text-muted-foreground">Picks the best captaincy record in your XI. Tap C on a player to choose.</div>
      )}
      <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">Calls the toss and runs the bowling: a better record, fewer bad calls.</div>
    </div>
  );
}
