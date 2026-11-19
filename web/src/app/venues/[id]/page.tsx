import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Bar, FormatTabs, Nothing, PageHeader, Scoreboard, Section } from "@/components/blocks";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  api, displayName, fmt, FORMAT_LABEL, FORMATS, mainFormat, NotFound, overs, type Format, type VenuePage,
} from "@/lib/api";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ format?: string }> };

async function load(id: string, format?: Format): Promise<VenuePage> {
  try {
    return await api<VenuePage>(`/venues/${encodeURIComponent(id)}`, { format });
  } catch (e) {
    if (e instanceof NotFound) notFound();
    throw e;
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const v = await load((await params).id);
  return { title: v.venue.name, description: `Scoring, chasing and the leading players at ${v.venue.name}.` };
}

const th = "label h-9";

export default async function VenueView({ params, searchParams }: Props) {
  const { id } = await params;
  const sp = await searchParams;
  const base = await load(id);
  const available = FORMATS.filter((f) => base.formats.some((x) => x.format === f));
  const busiest = mainFormat([...base.formats]);
  const format = available.includes(sp.format as Format) ? (sp.format as Format) : busiest;
  const page = format === busiest ? base : await load(id, format);
  const cur = page.formats.find((f) => f.format === format);
  const { venue } = page;
  const recentDelta = cur?.avg_first_innings && cur.avg_first_innings_recent
    ? cur.avg_first_innings_recent - cur.avg_first_innings : null;

  return (
    <div className="space-y-12">
      <div>
        <PageHeader
          kicker={[venue.city, `${fmt(venue.matches)} matches`, `${venue.first_match.slice(0, 4)}–${venue.last_match.slice(0, 4)}`].filter(Boolean).join(" · ")}
          title={venue.name}
          className="mb-0"
        />
        {available.length > 0 && (
          <FormatTabs formats={available} active={format} hrefFor={(f) => `/venues/${venue.id}?format=${f}`} className="mt-6" />
        )}
      </div>

      {cur && (
        <div className="space-y-6">
          <Scoreboard items={[
            { label: "Matches", value: fmt(cur.matches), hint: `${cur.first_year}–${cur.last_year}` },
            { label: "Avg 1st innings", value: fmt(cur.avg_first_innings, 0), emphasis: true,
              hint: cur.avg_first_innings_recent != null
                ? `${fmt(cur.avg_first_innings_recent, 0)} lately (${recentDelta! >= 0 ? "+" : ""}${fmt(recentDelta, 0)})` : undefined },
            ...(cur.chasing_win_pct != null ? [{ label: "Chasing wins", value: `${fmt(cur.chasing_win_pct, 0)}%` }] : []),
            { label: "Toss winner wins", value: `${fmt(cur.toss_winner_wins_pct, 0)}%`, hint: `${fmt(cur.toss_choose_field_pct, 0)}% chose to field` },
            { label: "Highest total", value: fmt(cur.highest_total) },
            { label: "Lowest all out", value: fmt(cur.lowest_all_out_first_innings), hint: "batting first" },
          ]} />
          {cur.chasing_win_pct != null && (
            <div>
              <div className="mb-1.5 flex justify-between font-mono text-[11px] uppercase">
                <span>Batting first {fmt(100 - cur.chasing_win_pct, 0)}%</span>
                <span className="text-signal">Chasing {fmt(cur.chasing_win_pct, 0)}%</span>
              </div>
              <Bar value={cur.chasing_win_pct} className="h-2.5 [&>div]:ml-auto" />
            </div>
          )}
        </div>
      )}

      <div className="grid gap-12 lg:grid-cols-2">
        <Section n={1} title="Most runs here" aside={format && FORMAT_LABEL[format]}>
          {page.top_batters.length ? (
            <div className="border-y">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className={th}>#</TableHead>
                    <TableHead className={th}>Player</TableHead>
                    {["Inns", "Runs", "HS", "Avg", "SR"].map((h) => <TableHead key={h} className={`${th} text-right`}>{h}</TableHead>)}
                  </TableRow>
                </TableHeader>
                <TableBody className="font-mono tnum">
                  {page.top_batters.map((p, i) => (
                    <TableRow key={p.id}>
                      <TableCell className="text-muted-foreground">{i + 1}</TableCell>
                      <TableCell className="font-sans"><Link href={`/players/${p.id}?format=${p.format}`} className="font-medium hover:text-signal">{displayName(p)}</Link></TableCell>
                      <TableCell className="text-right">{p.bat_innings}</TableCell>
                      <TableCell className="text-right font-semibold">{fmt(p.runs)}</TableCell>
                      <TableCell className="text-right">{p.highest ?? "–"}</TableCell>
                      <TableCell className="text-right">{fmt(p.bat_avg, 2)}</TableCell>
                      <TableCell className="text-right">{fmt(p.bat_sr, 1)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : <Nothing title="No batting yet" />}
        </Section>
        <Section n={2} title="Most wickets here" aside={format && FORMAT_LABEL[format]}>
          {page.top_bowlers.length ? (
            <div className="border-y">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className={th}>#</TableHead>
                    <TableHead className={th}>Player</TableHead>
                    {["Overs", "Wkts", "Runs", "Econ"].map((h) => <TableHead key={h} className={`${th} text-right`}>{h}</TableHead>)}
                  </TableRow>
                </TableHeader>
                <TableBody className="font-mono tnum">
                  {page.top_bowlers.map((p, i) => (
                    <TableRow key={p.id}>
                      <TableCell className="text-muted-foreground">{i + 1}</TableCell>
                      <TableCell className="font-sans"><Link href={`/players/${p.id}?format=${p.format}`} className="font-medium hover:text-signal">{displayName(p)}</Link></TableCell>
                      <TableCell className="text-right">{overs(p.balls_bowled)}</TableCell>
                      <TableCell className="text-right font-semibold">{p.wickets}</TableCell>
                      <TableCell className="text-right">{fmt(p.runs_conceded)}</TableCell>
                      <TableCell className="text-right">{fmt(p.bowl_econ, 2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : <Nothing title="No bowling yet" />}
        </Section>
      </div>

      <p className="font-mono text-[11px] text-muted-foreground">
        Averages and chasing figures use uninterrupted matches only (no rain-rule results). Pace v spin shares arrive once bowling styles are in.
      </p>
    </div>
  );
}
