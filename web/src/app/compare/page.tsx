import type { Metadata } from "next";
import Link from "next/link";
import { Bar, Nothing, PageHeader, Section } from "@/components/blocks";
import { CompareRadar } from "@/components/charts";
import { ComparePicker } from "@/components/compare-picker";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  api, displayName, fmt, FORMAT_LABEL, FORMATS, NotFound, overs,
  type Comparison, type Format, type PlayerProfile,
} from "@/lib/api";
import { cn } from "@/lib/utils";

export const metadata: Metadata = { title: "Head to head" };

type SP = Promise<{ a?: string; b?: string; format?: string; from?: string; to?: string }>;
type CP = Comparison["players"][number];

async function who(id?: string): Promise<{ id: string; name: string } | null> {
  if (!id) return null;
  try {
    const p = await api<PlayerProfile>(`/players/${encodeURIComponent(id)}`, { format: "Test" });
    return { id, name: displayName(p.player) };
  } catch (e) {
    if (e instanceof NotFound) return null;
    throw e;
  }
}

export default async function ComparePage({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const format: Format = FORMATS.includes(sp.format as Format) ? (sp.format as Format) : "IPL";
  const from = /^\d{4}$/.test(sp.from ?? "") ? Number(sp.from) : undefined;
  const to = /^\d{4}$/.test(sp.to ?? "") ? Number(sp.to) : undefined;

  let cmp: Comparison | null = null;
  let error: string | null = null;
  if (sp.a && sp.b) {
    try {
      cmp = await api<Comparison>("/compare", { a: sp.a, b: sp.b, format, from_year: from, to_year: to });
    } catch (e) {
      error = e instanceof NotFound ? "One of those players isn’t in the records." : "Couldn’t load that comparison.";
    }
  }
  const [a, b] = cmp
    ? cmp.players.map((p) => ({ id: p.id, name: displayName(p) }))
    : await Promise.all([who(sp.a), who(sp.b)]);

  return (
    <div className="space-y-10">
      <PageHeader
        kicker="Same format · same years · percentiles vs everyone with 500+ balls"
        title={a && b ? <>{a.name} <span className="text-muted-foreground">v</span> <span className="text-chart-2">{b.name}</span></> : "Head to head"}
      />
      <ComparePicker key={`${a?.id}-${b?.id}-${format}-${from}-${to}`} a={a} b={b} format={format} from={from} to={to} />
      {error && <Nothing title="Hmm">{error}</Nothing>}
      {!cmp && !error && <Nothing title="Pick two players">Search above, then pick a format.</Nothing>}
      {cmp && <Result cmp={cmp} />}
    </div>
  );
}

function Result({ cmp }: { cmp: Comparison }) {
  const [A, B] = cmp.players;
  const range = cmp.from_year || cmp.to_year ? `${cmp.from_year ?? "start"}–${cmp.to_year ?? "now"}` : "career";
  const empty = [A, B].filter((p) => !p.totals.matches);
  const radar = A.metrics.map((m, i) => ({ label: m.label, a: m.percentile, b: B.metrics[i].percentile }));

  const totals: [string, (p: CP) => string, (p: CP) => number][] = [
    ["Matches", (p) => fmt(p.totals.matches), (p) => p.totals.matches],
    ["Runs", (p) => fmt(p.totals.runs), (p) => p.totals.runs],
    ["100s / 50s", (p) => `${p.totals.hundreds} / ${p.totals.fifties}`, (p) => p.totals.hundreds * 2 + p.totals.fifties],
    ["Overs", (p) => overs(p.totals.balls_bowled), (p) => p.totals.balls_bowled],
    ["Wickets", (p) => fmt(p.totals.wickets), (p) => p.totals.wickets],
    ["Catches", (p) => fmt(p.totals.catches), (p) => p.totals.catches],
  ];

  return (
    <div className="space-y-10">
      {empty.length > 0 && (
        <Nothing title="Missing innings">
          {empty.map((p) => displayName(p)).join(" and ")} played no {FORMAT_LABEL[cmp.format]} matches in that span.
        </Nothing>
      )}

      <div className="grid gap-12 lg:grid-cols-[1fr_1.15fr]">
        <Section n={1} title="Percentile shape" aside={`${FORMAT_LABEL[cmp.format]} · ${range}`}>
          <CompareRadar data={radar} nameA={displayName(A)} nameB={displayName(B)} />
        </Section>

        <Section n={2} title="Where each one wins">
          <div className="space-y-4">
            {A.metrics.map((m, i) => {
              const mb = B.metrics[i];
              // Only call a winner when both have enough balls to be ranked.
              const better = m.qualified && mb.qualified && m.value != null && mb.value != null && m.value !== mb.value
                ? ((m.value > mb.value) === m.higher_is_better ? "a" : "b") : null;
              const shown = (x: typeof m) => x.value == null ? "–" : `${fmt(x.value, 2)}${x.qualified ? "" : "*"}`;
              return (
                <div key={m.key}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                    <span className={cn("font-mono tnum", better === "a" ? "font-bold text-chart-1" : "text-muted-foreground")}>
                      {shown(m)}
                    </span>
                    <span className="label">{m.label}{!m.higher_is_better && " ↓"}</span>
                    <span className={cn("font-mono tnum", better === "b" ? "font-bold text-chart-2" : "text-muted-foreground")}>
                      {shown(mb)}
                    </span>
                  </div>
                  {/* percentile bars grow outward from the middle */}
                  <div className="grid grid-cols-2 gap-1">
                    <Bar value={m.percentile ?? 0} tone="a" className="[&>div]:ml-auto" />
                    <Bar value={mb.percentile ?? 0} tone="b" />
                  </div>
                  <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground">
                    <span>{m.percentile != null ? `p${Math.round(m.percentile)}` : ""}</span>
                    <span>{mb.percentile != null ? `p${Math.round(mb.percentile)}` : ""}</span>
                  </div>
                </div>
              );
            })}
          </div>
          <p className="mt-4 font-mono text-[11px] text-muted-foreground">
            ↓ lower is better. Bars show percentile among qualified players. * fewer than {cmp.min_sample_to_rank} balls: shown, not ranked.
          </p>
        </Section>
      </div>

      <Section n={3} title="Totals">
        <div className="border-y">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="label h-9" />
                <TableHead className="label h-9 text-right">
                  <Link href={`/players/${A.id}?format=${cmp.format}`} className="text-chart-1 hover:underline">{displayName(A)}</Link>
                </TableHead>
                <TableHead className="label h-9 text-right">
                  <Link href={`/players/${B.id}?format=${cmp.format}`} className="text-chart-2 hover:underline">{displayName(B)}</Link>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="font-mono tnum">
              {totals.map(([label, show, raw]) => {
                const w = raw(A) === raw(B) ? null : raw(A) > raw(B) ? "a" : "b";
                return (
                  <TableRow key={label}>
                    <TableCell className="font-sans text-muted-foreground">{label}</TableCell>
                    <TableCell className={cn("text-right", w === "a" && "font-bold")}>{show(A)}</TableCell>
                    <TableCell className={cn("text-right", w === "b" && "font-bold")}>{show(B)}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </Section>
    </div>
  );
}
