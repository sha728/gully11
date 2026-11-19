import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { SeasonChart } from "@/components/charts";
import { Card, Chip, Empty, FormatTabs, Stat } from "@/components/ui";
import {
  api, displayName, fmt, FORMAT_LABEL, FORMATS, mainFormat, NotFound, overs, ROLE_LABEL, span,
  type Format, type FormatStats, type PlayerProfile,
} from "@/lib/api";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ format?: string }> };

async function load(id: string): Promise<PlayerProfile> {
  try {
    return await api<PlayerProfile>(`/players/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof NotFound) notFound();
    throw e;
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const p = await load((await params).id);
  return {
    title: displayName(p.player),
    description: `${displayName(p.player)} career stats: ${p.formats.map((f) => FORMAT_LABEL[f.format]).join(", ")}.`,
  };
}

const PHASE_LABEL = { PP: "Powerplay", middle: "Middle overs", death: "Death overs" } as const;
const DISMISSAL_LABEL: Record<string, string> = {
  caught: "Caught", bowled: "Bowled", lbw: "LBW", "run out": "Run out",
  "caught and bowled": "Caught & bowled", stumped: "Stumped", "hit wicket": "Hit wicket",
  "obstructing the field": "Obstructing the field", "handled the ball": "Handled the ball",
};

export default async function PlayerPage({ params, searchParams }: Props) {
  const { id } = await params;
  const sp = await searchParams;
  const prof = await load(id);
  const { player } = prof;
  const available = FORMATS.filter((f) => prof.formats.some((s) => s.format === f));
  const format: Format | undefined =
    available.includes(sp.format as Format) ? (sp.format as Format) : mainFormat(prof.formats);
  const cur = prof.formats.find((f) => f.format === format);
  const bowls = (cur?.balls_bowled ?? 0) >= 60;
  const bats = (cur?.bat_innings ?? 0) > 0;

  const seasons = prof.seasons.filter((s) => s.format === format);
  const phases = prof.phases.filter((p) => p.format === format);
  const dismissals = prof.dismissals.filter((d) => d.format === format);
  const venues = prof.venues.filter((v) => v.format === format);
  const outs = dismissals.reduce((a, d) => a + d.n, 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">{displayName(player)}</h1>
          {player.full_name && player.full_name !== player.name && (
            <p className="mt-0.5 text-sm text-muted">{player.name} on scorecards</p>
          )}
          <div className="mt-2 flex flex-wrap gap-2">
            {player.country && <Chip>{player.country}</Chip>}
            <Chip>{ROLE_LABEL[player.role]}</Chip>
            <Chip>{span(player.era_start, player.era_end)}</Chip>
            <Chip>{player.capped ? "International" : "Uncapped"}</Chip>
            {player.batting_hand && <Chip>{player.batting_hand}</Chip>}
            {player.bowling_style && <Chip>{player.bowling_style}</Chip>}
          </div>
        </div>
        {format && (
          <Link href={`/compare?a=${player.id}&format=${format}`}
            className="rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium hover:border-accent">
            Compare with…
          </Link>
        )}
      </div>

      {available.length > 0 && (
        <FormatTabs formats={available} active={format} hrefFor={(f) => `/players/${player.id}?format=${f}`} />
      )}

      {cur ? (
        <>
          {/* Headline numbers */}
          <div className="grid grid-cols-2 gap-6 rounded-xl border border-border bg-surface p-5 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Matches" value={fmt(cur.matches)} />
            {bats && <Stat label="Runs" value={fmt(cur.runs)} hint={`HS ${cur.highest ?? "–"}`} />}
            {bats && <Stat label="Average" value={fmt(cur.bat_avg, 2)} hint={`${cur.hundreds} × 100 · ${cur.fifties} × 50`} />}
            {bats && <Stat label="Strike rate" value={fmt(cur.bat_sr, 1)} />}
            {bowls && <Stat label="Wickets" value={fmt(cur.wickets)} hint={cur.wickets && cur.best_bowling ? `Best ${cur.best_bowling}` : undefined} />}
            {bowls && <Stat label="Economy" value={fmt(cur.bowl_econ, 2)} hint={`Avg ${fmt(cur.bowl_avg, 2)}`} />}
            {player.role === "WK" && <Stat label="Dismissals" value={fmt(cur.catches + cur.stumpings)} hint={`${cur.stumpings} stumpings`} />}
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card title="Season by season" aside={FORMAT_LABEL[format!]} className="lg:col-span-2">
              {seasons.length > 1 ? (
                <SeasonChart showBowling={bowls}
                  data={seasons.map((s) => ({ season: s.season!, runs: s.runs, bat_avg: s.bat_avg,
                    bat_sr: s.bat_sr, wickets: s.wickets, bowl_econ: s.bowl_econ }))} />
              ) : <Empty>Only one season in this format.</Empty>}
            </Card>

            <Card title="How they get out" aside={outs ? `${outs} dismissals` : undefined}>
              {dismissals.length ? (
                <ul className="space-y-2.5">
                  {dismissals.map((d) => (
                    <li key={d.kind}>
                      <div className="flex justify-between text-sm">
                        <span>{DISMISSAL_LABEL[d.kind] ?? d.kind}</span>
                        <span className="num text-muted">{d.n} · {Math.round((100 * d.n) / outs)}%</span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-surface-2">
                        <div className="h-1.5 rounded-full bg-accent" style={{ width: `${(100 * d.n) / outs}%` }} />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : <Empty>Never dismissed in this format.</Empty>}
            </Card>
          </div>

          {phases.length > 0 && (
            <div className="grid gap-6 lg:grid-cols-2">
              {(["bat", "bowl"] as const).map((role) => {
                const rows = phases.filter((p) => p.role === role);
                if (!rows.length || (role === "bowl" && !bowls)) return null;
                return (
                  <Card key={role} title={role === "bat" ? "Batting by phase" : "Bowling by phase"}>
                    <div className="-mx-4 overflow-x-auto">
                      <table className="stats">
                        <thead>
                          <tr>
                            <th>Phase</th><th>Balls</th>
                            {role === "bat"
                              ? <><th>Runs</th><th>SR</th><th>Dot %</th><th>4s+6s %</th><th>Balls/out</th></>
                              : <><th>Wkts</th><th>Econ</th><th>Dot %</th><th>4s+6s %</th><th>Balls/wkt</th></>}
                          </tr>
                        </thead>
                        <tbody>
                          {rows.map((p) => (
                            <tr key={p.phase}>
                              <td>{PHASE_LABEL[p.phase]}</td>
                              <td>{fmt(p.balls)}</td>
                              {role === "bat" ? <td>{fmt(p.runs)}</td> : <td>{fmt(p.wickets)}</td>}
                              <td>{role === "bat" ? fmt(p.strike_rate, 1) : fmt(p.economy, 2)}</td>
                              <td>{fmt((p.dot_pct ?? 0) * 100, 1)}</td>
                              <td>{fmt(((p.four_pct ?? 0) + (p.six_pct ?? 0)) * 100, 1)}</td>
                              <td>{p.wickets ? fmt(p.balls / p.wickets, 1) : "–"}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>
                );
              })}
            </div>
          )}

          {venues.length > 0 && (
            <div className="grid gap-6 lg:grid-cols-2">
              {bats && (
                <Card title="Best venues: batting" aside="3+ innings">
                  <VenueTable rows={[...venues].filter((v) => v.bat_innings >= 3).sort((a, b) => b.runs - a.runs).slice(0, 8)}
                    cols={["Inns", "Runs", "Avg", "SR"]}
                    cells={(v) => [fmt(v.bat_innings), fmt(v.runs), fmt(v.bat_avg, 2), fmt(v.bat_sr, 1)]} />
                </Card>
              )}
              {bowls && venues.some((v) => v.balls_bowled >= 60) && (
                <Card title="Best venues: bowling" aside="10+ overs">
                  <VenueTable rows={[...venues].filter((v) => v.balls_bowled >= 60).sort((a, b) => b.wickets - a.wickets).slice(0, 8)}
                    cols={["Overs", "Wkts", "Econ"]}
                    cells={(v) => [overs(v.balls_bowled), fmt(v.wickets), fmt(v.bowl_econ, 2)]} />
                </Card>
              )}
            </div>
          )}
        </>
      ) : (
        <Card><Empty>No ball-by-ball records for this player.</Empty></Card>
      )}

      <CareerTables formats={prof.formats} />
    </div>
  );
}

function VenueTable<T extends { venue_id: string; venue_name: string }>({ rows, cols, cells }: {
  rows: T[]; cols: string[]; cells: (r: T) => string[];
}) {
  if (!rows.length) return <Empty>Not enough matches at any venue.</Empty>;
  return (
    <div className="-mx-4 overflow-x-auto">
      <table className="stats">
        <thead><tr><th>Venue</th>{cols.map((c) => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.venue_id}>
              <td><Link href={`/venues/${r.venue_id}`} className="hover:text-accent">{r.venue_name}</Link></td>
              {cells(r).map((c, i) => <td key={i}>{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CareerTables({ formats }: { formats: FormatStats[] }) {
  if (!formats.length) return null;
  const bowled = formats.filter((f) => f.balls_bowled > 0);
  return (
    <div className="grid gap-6">
      <Card title="Career batting">
        <div className="-mx-4 overflow-x-auto">
          <table className="stats">
            <thead>
              <tr><th>Format</th><th>Mat</th><th>Inns</th><th>NO</th><th>Runs</th><th>HS</th><th>Avg</th>
                <th>SR</th><th>100</th><th>50</th><th>4s</th><th>6s</th><th>Ct</th><th>St</th></tr>
            </thead>
            <tbody>
              {formats.map((f) => (
                <tr key={f.format}>
                  <td>{FORMAT_LABEL[f.format]}</td><td>{fmt(f.matches)}</td><td>{fmt(f.bat_innings)}</td>
                  <td>{fmt(f.not_outs)}</td><td className="font-medium">{fmt(f.runs)}</td><td>{f.highest ?? "–"}</td>
                  <td>{fmt(f.bat_avg, 2)}</td><td>{fmt(f.bat_sr, 1)}</td><td>{f.hundreds}</td><td>{f.fifties}</td>
                  <td>{fmt(f.fours)}</td><td>{fmt(f.sixes)}</td><td>{f.catches}</td><td>{f.stumpings}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      {bowled.length > 0 && (
        <Card title="Career bowling">
          <div className="-mx-4 overflow-x-auto">
            <table className="stats">
              <thead>
                <tr><th>Format</th><th>Inns</th><th>Overs</th><th>Runs</th><th>Wkts</th><th>Best</th>
                  <th>Avg</th><th>Econ</th><th>SR</th><th>Dot %</th><th>5w</th></tr>
              </thead>
              <tbody>
                {bowled.map((f) => (
                  <tr key={f.format}>
                    <td>{FORMAT_LABEL[f.format]}</td><td>{fmt(f.bowl_innings)}</td><td>{overs(f.balls_bowled)}</td>
                    <td>{fmt(f.runs_conceded)}</td><td className="font-medium">{fmt(f.wickets)}</td>
                    <td>{f.wickets ? f.best_bowling : "–"}</td><td>{fmt(f.bowl_avg, 2)}</td><td>{fmt(f.bowl_econ, 2)}</td>
                    <td>{fmt(f.bowl_sr, 1)}</td><td>{fmt(f.bowl_dot_pct, 1)}</td><td>{f.five_wkts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      <p className="text-xs text-muted">
        Source: Cricsheet ball-by-ball records. Figures cover the matches Cricsheet holds and can
        differ from official career totals.
      </p>
    </div>
  );
}
