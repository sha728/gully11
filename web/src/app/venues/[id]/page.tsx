import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, Empty, FormatTabs, Stat } from "@/components/ui";
import { api, displayName, fmt, FORMAT_LABEL, FORMATS, mainFormat, NotFound, overs, type Format, type VenuePage } from "@/lib/api";

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
  return { title: v.venue.name, description: `Scoring, chasing and leading players at ${v.venue.name}.` };
}

export default async function VenuePageView({ params, searchParams }: Props) {
  const { id } = await params;
  const sp = await searchParams;
  const base = await load(id);
  const available = FORMATS.filter((f) => base.formats.some((x) => x.format === f));
  const busiest = mainFormat(base.formats);
  const format = available.includes(sp.format as Format) ? (sp.format as Format) : busiest;
  const page = format === busiest ? base : await load(id, format);
  const cur = page.formats.find((f) => f.format === format);
  const { venue } = page;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold tracking-tight">{venue.name}</h1>
        <p className="mt-1 text-sm text-muted">
          {[venue.city, `${fmt(venue.matches)} matches`, `${venue.first_match.slice(0, 4)}–${venue.last_match.slice(0, 4)}`]
            .filter(Boolean).join(" · ")}
        </p>
      </div>

      {available.length > 0 && (
        <FormatTabs formats={available} active={format} hrefFor={(f) => `/venues/${venue.id}?format=${f}`} />
      )}

      {cur && (
        <div className="grid grid-cols-2 gap-6 rounded-xl border border-border bg-surface p-5 sm:grid-cols-3 lg:grid-cols-6">
          <Stat label="Matches" value={fmt(cur.matches)} hint={`${cur.first_year}–${cur.last_year}`} />
          <Stat label="Avg 1st innings" value={fmt(cur.avg_first_innings, 0)}
            hint={cur.avg_first_innings_recent != null ? `${fmt(cur.avg_first_innings_recent, 0)} in last 3 yrs (${cur.matches_recent})` : undefined} />
          {cur.chasing_win_pct != null && <Stat label="Chasing wins" value={`${fmt(cur.chasing_win_pct, 0)}%`} />}
          <Stat label="Toss winner wins" value={`${fmt(cur.toss_winner_wins_pct, 0)}%`}
            hint={`${fmt(cur.toss_choose_field_pct, 0)}% chose to field`} />
          <Stat label="Highest total" value={fmt(cur.highest_total)} />
          <Stat label="Lowest all-out" value={fmt(cur.lowest_all_out_first_innings)} hint="first innings" />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Leading run scorers" aside={format && FORMAT_LABEL[format]}>
          {page.top_batters.length ? (
            <div className="-mx-4 overflow-x-auto">
              <table className="stats">
                <thead><tr><th>Player</th><th>Inns</th><th>Runs</th><th>HS</th><th>Avg</th><th>SR</th></tr></thead>
                <tbody>
                  {page.top_batters.map((p) => (
                    <tr key={p.id}>
                      <td><Link href={`/players/${p.id}?format=${p.format}`} className="font-medium hover:text-accent">{displayName(p)}</Link></td>
                      <td>{p.bat_innings}</td><td className="font-medium">{fmt(p.runs)}</td><td>{p.highest ?? "–"}</td>
                      <td>{fmt(p.bat_avg, 2)}</td><td>{fmt(p.bat_sr, 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <Empty>No batting records.</Empty>}
        </Card>
        <Card title="Leading wicket takers" aside={format && FORMAT_LABEL[format]}>
          {page.top_bowlers.length ? (
            <div className="-mx-4 overflow-x-auto">
              <table className="stats">
                <thead><tr><th>Player</th><th>Overs</th><th>Wkts</th><th>Runs</th><th>Econ</th></tr></thead>
                <tbody>
                  {page.top_bowlers.map((p) => (
                    <tr key={p.id}>
                      <td><Link href={`/players/${p.id}?format=${p.format}`} className="font-medium hover:text-accent">{displayName(p)}</Link></td>
                      <td>{overs(p.balls_bowled)}</td><td className="font-medium">{p.wickets}</td>
                      <td>{fmt(p.runs_conceded)}</td><td>{fmt(p.bowl_econ, 2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <Empty>No bowling records.</Empty>}
        </Card>
      </div>

      <p className="text-xs text-muted">
        Averages and chasing figures use uninterrupted matches only (no rain-rule results). Pace
        vs spin wicket shares need bowling styles and are coming later.
      </p>
    </div>
  );
}
