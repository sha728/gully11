import type { Metadata } from "next";
import Link from "next/link";
import { CompareRadar } from "@/components/charts";
import ComparePicker from "@/components/ComparePicker";
import { Card, Empty } from "@/components/ui";
import {
  api, displayName, fmt, FORMAT_LABEL, FORMATS, NotFound, overs,
  type Comparison, type Format, type PlayerProfile,
} from "@/lib/api";

export const metadata: Metadata = { title: "Compare players" };

type SP = Promise<{ a?: string; b?: string; format?: string; from?: string; to?: string }>;

async function name(id?: string): Promise<{ id: string; name: string } | null> {
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
      error = e instanceof NotFound ? "One of those players wasn't found." : "Couldn't load the comparison.";
    }
  }
  const [a, b] = cmp
    ? cmp.players.map((p) => ({ id: p.id, name: displayName(p) }))
    : await Promise.all([name(sp.a), name(sp.b)]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Compare players</h1>
        <p className="mt-1 text-sm text-muted">
          Same format, same years. Percentiles rank each figure against everyone with 500+ balls
          faced (batting) or bowled (bowling) in that format.
        </p>
      </div>

      <ComparePicker key={`${a?.id}-${b?.id}-${format}-${from}-${to}`} a={a} b={b} format={format} from={from} to={to} />

      {error && <Card><Empty>{error}</Empty></Card>}
      {!cmp && !error && <Card><Empty>Pick two players to compare.</Empty></Card>}

      {cmp && <Result cmp={cmp} />}
    </div>
  );
}

function Result({ cmp }: { cmp: Comparison }) {
  const [A, B] = cmp.players;
  const range = cmp.from_year || cmp.to_year
    ? ` · ${cmp.from_year ?? "start"}–${cmp.to_year ?? "now"}` : "";
  const noData = (p: typeof A) => !p.totals.matches;
  const radar = A.metrics.map((m, i) => ({
    label: m.label, a: m.percentile, b: B.metrics[i].percentile,
  }));

  const totals: [string, (p: typeof A) => string][] = [
    ["Matches", (p) => fmt(p.totals.matches)],
    ["Runs", (p) => fmt(p.totals.runs)],
    ["100s / 50s", (p) => `${p.totals.hundreds} / ${p.totals.fifties}`],
    ["Overs", (p) => overs(p.totals.balls_bowled)],
    ["Wickets", (p) => fmt(p.totals.wickets)],
    ["Catches", (p) => fmt(p.totals.catches)],
  ];

  return (
    <>
      {(noData(A) || noData(B)) && (
        <Card>
          <Empty>
            {[A, B].filter(noData).map((p) => displayName(p)).join(" and ")} played no {FORMAT_LABEL[cmp.format]}
            {" "}matches{range ? " in that range" : ""}.
          </Empty>
        </Card>
      )}
      <div className="grid gap-6 lg:grid-cols-5">
        <Card title="Percentile profile" aside={`${FORMAT_LABEL[cmp.format]}${range}`} className="lg:col-span-2">
          <CompareRadar data={radar} nameA={displayName(A)} nameB={displayName(B)} />
        </Card>
        <Card title="Head to head" className="lg:col-span-3">
          <div className="-mx-4 overflow-x-auto">
            <table className="stats">
              <thead>
                <tr>
                  <th></th>
                  <th><Link href={`/players/${A.id}?format=${cmp.format}`} className="text-a">{displayName(A)}</Link></th>
                  <th><Link href={`/players/${B.id}?format=${cmp.format}`} className="text-b">{displayName(B)}</Link></th>
                </tr>
              </thead>
              <tbody>
                {totals.map(([label, f]) => (
                  <tr key={label}><td className="text-muted">{label}</td><td>{f(A)}</td><td>{f(B)}</td></tr>
                ))}
                {A.metrics.map((m, i) => {
                  const mb = B.metrics[i];
                  const better = m.value != null && mb.value != null && m.value !== mb.value
                    ? ((m.value > mb.value) === m.higher_is_better ? "a" : "b") : null;
                  const cell = (x: typeof m, side: "a" | "b") => (
                    <td className={better === side ? "font-semibold" : ""}>
                      {fmt(x.value, 2)}
                      {x.percentile != null && <span className="ml-1.5 text-xs font-normal text-muted">p{Math.round(x.percentile)}</span>}
                    </td>
                  );
                  return (
                    <tr key={m.key}>
                      <td className="text-muted">{m.label}{!m.higher_is_better && <span className="text-xs"> (lower is better)</span>}</td>
                      {cell(m, "a")}{cell(mb, "b")}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </>
  );
}
