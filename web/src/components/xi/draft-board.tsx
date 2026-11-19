"use client";

import { ArrowsDownUpIcon, CheckIcon, CircleIcon, CrosshairIcon, SpinnerGapIcon, TrophyIcon, XIcon } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useMemo, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fmt, ROLE_LABEL } from "@/lib/api";
import { cn } from "@/lib/utils";
import { fits, isOverseas, KEEPER_SLOT, XI_COPY, xiApi, type Candidate, type Challenge, type Spin, type SpinSet } from "@/lib/xi";

const MAX_OVERSEAS = 4;
const ROLL_MS = 1100;

type BySlot = (Candidate | null)[];

/** Where a fresh pick goes by default: openers open, keepers keep, bowlers bowl. */
function preference(c: Candidate): number[] {
  const byRole: Record<Candidate["role"], number[]> = {
    WK: [6, 3, 4, 5], BAT: [3, 4, 5, 6], AR: [7, 8, 3, 4, 5, 6, 9, 10, 11],
    BOWL: c.spinner ? [9, 10, 11, 7, 8] : [9, 10, 11],
  };
  return [...new Set([...(c.opener ? [1, 2] : []), ...byRole[c.role]])].filter((s) => c.slots.includes(s));
}

/** Compact batting range, e.g. [3,4,5,6,9,10,11] -> "3–6, 9–11". */
function range(slots: number[]): string {
  const out: string[] = [];
  for (let i = 0; i < slots.length; i++) {
    let j = i;
    while (j + 1 < slots.length && slots[j + 1] === slots[j] + 1) j++;
    out.push(i === j ? `${slots[i]}` : `${slots[i]}–${slots[j]}`);
    i = j;
  }
  return out.join(", ");
}

/** Can the spins still to be filled cover every empty slot? Bipartite matching;
 * slot 6 needs a keeper unless one already bats in the top five. */
function completable(bySlot: BySlot, pending: Spin[], used: Set<string>): boolean {
  const keeperAbove = bySlot.some((p, i) => p?.role === "WK" && i + 1 < KEEPER_SLOT);
  const empty = bySlot.map((p, i) => (p ? 0 : i + 1)).filter(Boolean);
  if (empty.length < pending.length) return false;
  const options = pending.map((s) => empty.filter((slot) => s.candidates.some((c) =>
    !used.has(c.person) && c.slots.includes(slot) && (slot !== KEEPER_SLOT || c.role === "WK" || keeperAbove))));
  const owner = new Map<number, number>();
  const place = (i: number, seen: Set<number>): boolean => {
    for (const slot of options[i]) {
      if (seen.has(slot)) continue;
      seen.add(slot);
      const j = owner.get(slot);
      if (j === undefined || place(j, seen)) { owner.set(slot, i); return true; }
    }
    return false;
  };
  return pending.every((_, i) => place(i, new Set()));
}

export function DraftBoard({ set, daily, rival }: { set: SpinSet; daily: boolean; rival: Challenge | null }) {
  const router = useRouter();
  const { format, spins, positions } = set;
  const n = spins.length;
  const [revealed, setRevealed] = useState(0);
  const [view, setView] = useState<number | null>(null);          // spin whose list is shown
  const [picks, setPicks] = useState<(Candidate | null)[]>(() => spins.map(() => null));
  const [slotOf, setSlotOf] = useState<(number | null)[]>(() => spins.map(() => null));
  const [aim, setAim] = useState<number | null>(null);            // empty slot the next pick should take
  const [moving, setMoving] = useState<number | null>(null);      // slot whose player is being moved
  const [rolling, setRolling] = useState<string | null>(null);    // label shown while the reel spins
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reel = useRef<ReturnType<typeof setInterval> | null>(null);
  const t20 = format === "T20I" || format === "IPL";

  const bySlot: BySlot = useMemo(() => {
    const out: BySlot = Array(11).fill(null);
    slotOf.forEach((s, i) => { if (s) out[s - 1] = picks[i]; });
    return out;
  }, [picks, slotOf]);
  const spinAt = (slot: number) => slotOf.indexOf(slot);
  const chosen = picks.filter(Boolean) as Candidate[];
  const overseas = chosen.filter(isOverseas).length;
  const allFit = bySlot.every((p, i) => !p || fits(p, i + 1, bySlot));
  const keeperTop6 = bySlot.slice(0, KEEPER_SLOT).some((p) => p?.role === "WK");
  const openers = bySlot.slice(0, 2).filter(Boolean).length;
  const ready = chosen.length === 11 && allFit && keeperTop6 && (format !== "IPL" || overseas <= MAX_OVERSEAS);
  const waiting = revealed > 0 && picks.slice(0, revealed).some((p) => !p);  // must pick before spinning on

  /** Spins not yet holding a player once spin ``except`` is filled. */
  const pendingAfter = (except: number) =>
    spins.filter((_, i) => i !== except && !picks[i]);

  function spin() {
    if (revealed >= n || rolling) return;
    setError(null);
    setAim(null);
    setMoving(null);
    const target = revealed;
    const land = () => { setRolling(null); setRevealed(target + 1); setView(target); };
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return land();
    const labels = spins.map((s) => `${s.era} · ${s.side}`);
    let k = target;
    setRolling(labels[k % n]);
    reel.current = setInterval(() => { k = (k + 3) % n; setRolling(labels[k]); }, 70);
    setTimeout(() => { if (reel.current) clearInterval(reel.current); land(); }, ROLL_MS);
  }

  /** The slot ``c`` would take if picked from spin ``i`` now, or why it can't be picked. */
  function placement(c: Candidate, i: number): { slot: number } | { why: string } {
    const owner = picks.findIndex((p, j) => j !== i && p?.person === c.person);
    if (owner >= 0) return { why: `Already in your XI` };
    const current = picks[i];
    if (format === "IPL" && isOverseas(c) && !(current && isOverseas(current)) && overseas >= MAX_OVERSEAS) {
      return { why: "Overseas limit reached" };
    }
    const freed = [...bySlot];
    if (slotOf[i]) freed[slotOf[i]! - 1] = null;
    const used = new Set(picks.filter((p, j) => p && j !== i).map((p) => p!.person));
    used.add(c.person);
    const order = [
      ...(aim ? [aim] : []), ...(slotOf[i] ? [slotOf[i]!] : []), ...preference(c),
    ];
    for (const slot of new Set(order)) {
      if (freed[slot - 1]) continue;
      const next = [...freed];
      next[slot - 1] = c;
      if (fits(c, slot, next) && completable(next, pendingAfter(i), used)) return { slot };
    }
    return { why: c.slots.length ? "No room for this role in your XI" : "Can't bat anywhere" };
  }

  function pick(c: Candidate, i: number) {
    const p = placement(c, i);
    if (!("slot" in p)) return;
    setPicks((x) => x.map((v, j) => (j === i ? c : v)));
    setSlotOf((x) => x.map((v, j) => (j === i ? p.slot : v)));
    setAim(null);
    setError(null);
  }

  function remove(slot: number) {
    const i = spinAt(slot);
    setPicks((x) => x.map((v, j) => (j === i ? null : v)));
    setSlotOf((x) => x.map((v, j) => (j === i ? null : v)));
    setView(i);
    setMoving(null);
  }

  /** Result of moving the player at ``from`` to ``to`` (swapping if occupied), or null if illegal. */
  function moved(from: number, to: number): (number | null)[] | null {
    if (from === to) return null;
    const a = spinAt(from), b = spinAt(to);
    const next = slotOf.map((s, j) => (j === a ? to : j === b ? from : s));
    const board: BySlot = Array(11).fill(null);
    next.forEach((s, j) => { if (s) board[s - 1] = picks[j]; });
    if (!board.every((p, k) => !p || fits(p, k + 1, board))) return null;
    const used = new Set(chosen.map((p) => p.person));
    return completable(board, spins.filter((_, j) => !picks[j]), used) ? next : null;
  }

  function tapSlot(slot: number) {
    setError(null);
    if (moving !== null) {
      const next = moved(moving, slot);
      if (next) setSlotOf(next);
      setMoving(null);
      return;
    }
    if (bySlot[slot - 1]) setMoving(slot);
    else setAim(aim === slot ? null : slot);
  }

  async function play() {
    setBusy(true);
    setError(null);
    try {
      const res = await xiApi.series(format, set.seed, picks.map((p) => p!.id), slotOf.map((s) => s!), daily);
      router.push(`/xi/c/${res.slug}${rival ? `?vs=${rival.slug}` : ""}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't play the series.");
      setBusy(false);
    }
  }

  const shown = view !== null ? spins[view] : null;
  const nextLabel = revealed >= n ? null : `Spin ${revealed + 1} of ${n}`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="label mb-2">
            {daily ? `Daily challenge · ${set.date}` : `Draw #${set.seed}`} · {XI_COPY[format].title}
          </div>
          <h1 className="font-display text-5xl leading-[0.9] font-extrabold uppercase sm:text-6xl">Draft your XI</h1>
        </div>
        {rival && (
          <div className="border-l-2 border-signal pl-3">
            <div className="label">Beat this</div>
            <div className="font-display text-2xl font-bold uppercase">{rival.result.verdict}</div>
          </div>
        )}
      </div>
      <div className="seam" aria-hidden />

      <div className="flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs">
        <Rule ok={chosen.length === 11} label={`${chosen.length}/11 picked`} />
        <Rule ok={openers === 2} label={`Openers ${openers}/2`} />
        <Rule ok={keeperTop6} label="Keeper in the top six" />
        {format === "IPL" && <Rule ok={overseas <= MAX_OVERSEAS} label={`Overseas ${overseas}/${MAX_OVERSEAS}`} neutral />}
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
            {positions.map((pos) => {
              const p = bySlot[pos.slot - 1];
              const i = spinAt(pos.slot);
              const target = moving !== null && moving !== pos.slot && moved(moving, pos.slot) !== null;
              const dead = moving !== null && moving !== pos.slot && !target;
              const label = pos.slot === KEEPER_SLOT && p && p.role !== "WK" ? "No. 6" : pos.label;
              return (
                <li key={pos.slot}
                  className={cn("flex items-center border-l-2 transition-colors",
                    moving === pos.slot ? "border-signal bg-signal-soft"
                      : target ? "border-signal/60 bg-signal-soft/50"
                      : aim === pos.slot ? "border-signal bg-signal-soft"
                      : "border-transparent hover:bg-muted",
                    dead && "opacity-40")}>
                  <button type="button" onClick={() => tapSlot(pos.slot)} disabled={dead}
                    aria-pressed={moving === pos.slot || aim === pos.slot}
                    className="flex min-w-0 flex-1 items-center gap-3 py-2.5 pr-2 pl-3 text-left">
                    <span className="w-5 font-display text-xl font-bold text-muted-foreground tnum">{pos.slot}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
                        {label}{p && i >= 0 ? ` · ${spins[i].era} ${spins[i].side}` : ""}
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
                    <button type="button" aria-label={`Remove ${p.name}`} onClick={() => remove(pos.slot)}
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
                  {rolling ? "Spinning…" : shown ? `Spin ${shown.spin} of ${n}` : "Eleven spins. One player from each."}
                </div>
                <div aria-live="polite"
                  className={cn("font-display text-4xl leading-none font-black text-balance uppercase sm:text-5xl",
                    rolling && "text-muted-foreground blur-[0.5px]")}>
                  {rolling ?? (shown ? `${shown.era} ${shown.side}` : "Ready?")}
                </div>
              </div>
              {nextLabel && (
                <Button size="lg" onClick={spin} disabled={!!rolling || waiting}
                  title={waiting ? "Pick a player from your last spin first" : undefined}
                  className="h-12 w-full px-6 font-mono uppercase sm:w-auto">
                  <SpinnerGapIcon className={cn(rolling && "animate-spin")} weight="bold" />
                  {revealed === 0 ? "Spin" : "Spin again"}
                </Button>
              )}
            </div>
            {/* Spins so far: tap one to re-pick from it */}
            <div className="flex gap-1 overflow-x-auto border-t px-4 py-2 sm:px-5" aria-label="Spins">
              {spins.map((s, i) => {
                const open = i < revealed;
                return (
                  <button key={s.spin} type="button" disabled={!open || !!rolling} onClick={() => setView(i)}
                    aria-label={open ? `Spin ${s.spin}: ${s.era} ${s.side}` : `Spin ${s.spin}, not spun yet`}
                    aria-current={view === i ? "true" : undefined}
                    className={cn("grid size-8 shrink-0 place-items-center border font-mono text-xs",
                      view === i ? "border-signal bg-signal text-signal-foreground"
                        : picks[i] ? "border-foreground/40 bg-muted"
                        : open ? "border-signal/60 text-foreground" : "border-dashed border-border text-muted-foreground/50")}>
                    {picks[i] && view !== i ? <CheckIcon className="size-3" weight="bold" /> : s.spin}
                  </button>
                );
              })}
            </div>
          </div>

          {shown && !rolling ? (
            <>
              <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-sm text-muted-foreground">
                  {waiting && !picks[view!] ? "Pick one player from this spin."
                    : picks[view!] ? `You took ${picks[view!]!.name}. Pick someone else to swap.`
                    : "Pick one player."}
                  {aim ? ` They'll bat at ${aim}.` : ""}
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
                      const place = placement(c, view!);
                      const why = "why" in place ? place.why : null;
                      const mine = picks[view!]?.id === c.id;
                      return (
                        <tr key={c.id} className={cn("border-b last:border-0", mine && "bg-signal-soft", why && !mine && "opacity-45")}>
                          <td className="px-2 py-2 font-sans">
                            <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                              <span className="mr-0.5 font-semibold">{c.name}</span>
                              {c.kind === "legend" && <Badge className="bg-signal font-mono text-[9px] text-signal-foreground">Legend</Badge>}
                              {c.opener && <Badge variant="secondary" className="font-mono text-[9px]">Opener</Badge>}
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
                            <Button size="sm" variant={mine ? "default" : "outline"} disabled={!!why || mine}
                              title={why ?? (mine ? undefined : `Bats at ${"slot" in place ? place.slot : ""}`)}
                              onClick={() => pick(c, view!)} className="font-mono text-[11px] uppercase">
                              {mine ? <><CheckIcon />{slotOf[view!]}</> : why ? "—" : `Pick`}
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
            : ready ? <span>Ready. Five matches against the {format === "IPL" ? "IPL All-Stars" : `${XI_COPY[format].title} World XI`}.</span>
            : <span className="text-muted-foreground">
                {chosen.length < 11 ? `${11 - chosen.length} to pick.`
                  : !keeperTop6 ? "Your keeper has to bat in the top six."
                  : !allFit ? "Someone's batting out of position."
                  : "Too many overseas players."}
              </span>}
        </div>
        {moving !== null && (
          <Button variant="ghost" onClick={() => setMoving(null)} className="font-mono uppercase">
            <ArrowsDownUpIcon />Cancel move
          </Button>
        )}
        <Button size="lg" disabled={!ready || busy} onClick={play} className="h-11 px-6 font-mono uppercase">
          <TrophyIcon />{busy ? "Playing…" : "Play the series"}
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
