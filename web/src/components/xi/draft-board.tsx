"use client";

import { CheckIcon, CircleIcon, TrophyIcon, XIcon } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { fmt, ROLE_LABEL } from "@/lib/api";
import { cn } from "@/lib/utils";
import { BOWLING_ROLES, isOverseas, XI_COPY, xiApi, type Candidate, type Challenge, type SpinSet } from "@/lib/xi";

const MAX_OVERSEAS = 4;

export function DraftBoard({ set, daily, rival }: { set: SpinSet; daily: boolean; rival: Challenge | null }) {
  const router = useRouter();
  const { format, spins } = set;
  const [picks, setPicks] = useState<(Candidate | null)[]>(() => spins.map(() => null));
  const [active, setActive] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t20 = format === "T20I" || format === "IPL";

  const chosen = picks.filter(Boolean) as Candidate[];
  const people = useMemo(() => new Map(picks.map((p, i) => [p?.person, i] as const).filter(([p]) => p)), [picks]);
  const keeper = chosen.some((c) => c.role === "WK");
  const bowlers = chosen.filter((c) => BOWLING_ROLES.includes(c.role)).length;
  const overseas = chosen.filter(isOverseas).length;
  const ready = chosen.length === 11 && keeper && bowlers >= 5 && (format !== "IPL" || overseas <= MAX_OVERSEAS);

  function pick(c: Candidate) {
    const next = [...picks];
    next[active] = c;
    setPicks(next);
    setError(null);
    const empty = next.findIndex((p, i) => !p && i > active);
    const first = next.findIndex((p) => !p);
    setActive(empty >= 0 ? empty : first >= 0 ? first : active);
  }

  function blocked(c: Candidate): string | null {
    const at = people.get(c.person);
    if (at !== undefined && at !== active) return `Already in slot ${at + 1}`;
    const current = picks[active];
    if (format === "IPL" && isOverseas(c) && !(current && isOverseas(current)) && overseas >= MAX_OVERSEAS) {
      return "Overseas limit reached";
    }
    return null;
  }

  async function play() {
    setBusy(true);
    setError(null);
    try {
      const res = await xiApi.series(format, set.seed, picks.map((p) => p!.id), daily);
      router.push(`/xi/c/${res.slug}${rival ? `?vs=${rival.slug}` : ""}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't play the series.");
      setBusy(false);
    }
  }

  const spin = spins[active];
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

      {/* Rules meter */}
      <div className="flex flex-wrap gap-x-6 gap-y-2 font-mono text-xs">
        <Rule ok={chosen.length === 11} label={`${chosen.length}/11 picked`} />
        <Rule ok={keeper} label="Wicketkeeper" />
        <Rule ok={bowlers >= 5} label={`Bowling options ${bowlers}/5`} />
        {format === "IPL" && <Rule ok={overseas <= MAX_OVERSEAS} label={`Overseas ${overseas}/${MAX_OVERSEAS}`} neutral />}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,22rem)_1fr]">
        {/* Team sheet */}
        <ol className="order-2 divide-y border-y lg:order-1 lg:sticky lg:top-20 lg:self-start">
          {spins.map((s, i) => {
            const p = picks[i];
            return (
              <li key={s.slot} style={{ animationDelay: `${i * 45}ms` }}
                className={cn("flex animate-in items-center border-l-2 fade-in slide-in-from-left-2 fill-mode-both",
                  i === active ? "border-signal bg-signal-soft" : "border-transparent hover:bg-muted")}>
                <button type="button" onClick={() => setActive(i)} aria-current={i === active ? "step" : undefined}
                  className="flex min-w-0 flex-1 items-center gap-3 py-2.5 pr-2 pl-3 text-left">
                  <span className="w-5 font-display text-xl font-bold text-muted-foreground tnum">{s.slot}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
                      {s.era} · {s.side}
                    </span>
                    {p ? (
                      <span className="block truncate font-display text-lg leading-tight font-bold uppercase">{p.name}</span>
                    ) : (
                      <span className="block text-sm text-muted-foreground italic">pick a player</span>
                    )}
                  </span>
                  {p && <Badge variant="outline" className="font-mono text-[9px]">{p.role}</Badge>}
                </button>
                {p && (
                  <button type="button" aria-label={`Remove ${p.name}`}
                    onClick={() => { const n = [...picks]; n[i] = null; setPicks(n); setActive(i); }}
                    className="px-2.5 py-3 text-muted-foreground hover:text-foreground"><XIcon className="size-3.5" /></button>
                )}
              </li>
            );
          })}
        </ol>

        {/* Candidates for the active spin */}
        <section className="order-1 min-w-0 lg:order-2">
          {/* On small screens the team sheet sits below; this strip shows progress and jumps between slots. */}
          <div className="mb-4 flex gap-1 overflow-x-auto lg:hidden" aria-label="Slots">
            {spins.map((s, i) => (
              <button key={s.slot} type="button" onClick={() => setActive(i)} aria-label={`Slot ${s.slot}`}
                className={cn("grid size-8 shrink-0 place-items-center border font-mono text-xs",
                  i === active ? "border-signal bg-signal text-signal-foreground"
                    : picks[i] ? "border-foreground/40 bg-muted" : "border-border text-muted-foreground")}>
                {s.slot}
              </button>
            ))}
          </div>
          <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
            <div className="flex items-baseline gap-3">
              <span className="font-mono text-xs text-signal tnum">{String(spin.slot).padStart(2, "0")}</span>
              <h2 className="font-display text-3xl font-extrabold uppercase">{spin.era} {spin.side}</h2>
            </div>
            <span className="label normal-case tracking-normal">
              Figures from that era; legends show career totals
            </span>
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
                {spin.candidates.map((c) => {
                  const why = blocked(c);
                  const mine = picks[active]?.id === c.id;
                  return (
                    <tr key={c.id} className={cn("border-b last:border-0", mine && "bg-signal-soft", why && "opacity-45")}>
                      <td className="px-2 py-2 font-sans">
                        <div className="flex flex-wrap items-center gap-x-2">
                          <span className="font-semibold">{c.name}</span>
                          {c.kind === "legend" && <Badge className="bg-signal text-signal-foreground font-mono text-[9px]">Legend</Badge>}
                          {format === "IPL" && isOverseas(c) && <Badge variant="outline" className="font-mono text-[9px]">OS</Badge>}
                        </div>
                        <div className="font-mono text-[10px] text-muted-foreground">
                          {ROLE_LABEL[c.role]} · {c.years}{format === "IPL" && c.country ? ` · ${c.country}` : ""}
                        </div>
                      </td>
                      <td className="hidden px-2 text-right text-muted-foreground sm:table-cell">{fmt(c.matches)}</td>
                      <td className="px-2 text-right">{fmt(c.runs)}</td>
                      <td className="px-2 text-right">{t20 ? fmt(c.bat_sr, 1) : fmt(c.bat_avg, 1)}</td>
                      <td className="px-2 text-right">{fmt(c.wickets)}</td>
                      <td className="hidden px-2 text-right sm:table-cell">{fmt(c.bowl_econ, 2)}</td>
                      <td className="px-2 py-1.5 text-right">
                        <Button size="sm" variant={mine ? "default" : "outline"} disabled={!!why}
                          title={why ?? undefined} onClick={() => pick(c)} className="font-mono text-[11px] uppercase">
                          {mine ? <><CheckIcon />Picked</> : why ? "—" : "Pick"}
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      </div>

      {/* Play bar */}
      <div className="sticky bottom-0 z-20 -mx-4 flex flex-wrap items-center gap-4 border-t bg-background/95 px-4 py-3 backdrop-blur sm:-mx-6 sm:px-6">
        <div className="min-w-0 flex-1 text-sm">
          {error ? <span className="text-destructive">{error}</span>
            : ready ? <span>Ready. Five matches against the {format === "IPL" ? "IPL All-Stars" : `${XI_COPY[format].title} World XI`}.</span>
            : <span className="text-muted-foreground">
                {chosen.length < 11 ? `${11 - chosen.length} slots to fill.` : !keeper ? "You still need a wicketkeeper."
                  : bowlers < 5 ? `You need ${5 - bowlers} more bowling option${5 - bowlers === 1 ? "" : "s"}.`
                  : "Too many overseas players."}
              </span>}
        </div>
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
