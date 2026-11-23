import { ScalesIcon } from "@phosphor-icons/react/ssr";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Bar, FormatTabs, Nothing, PageHeader, Scoreboard, Section, type ScoreItem } from "@/components/blocks";
import { SeasonChart } from "@/components/charts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  api, displayName, fmt, FORMAT_LABEL, FORMATS, mainFormat, NotFound, overs, ROLE_LABEL, span,
  type Format, type FormatStats, type PlayerProfile, type VenueSplit,
} from "@/lib/api";
import { cn } from "@/lib/utils";

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
    description: `${displayName(p.player)}: ${p.formats.map((f) => FORMAT_LABEL[f.format]).join(", ")} numbers, ball by ball.`,
  };
}

const PHASE = { PP: "Powerplay", middle: "Middle", death: "Death" } as const;
const OUT: Record<string, string> = {
  caught: "Caught", bowled: "Bowled", lbw: "LBW", "run out": "Run out", "caught and bowled": "Caught & bowled",
  stumped: "Stumped", "hit wicket": "Hit wicket", "obstructing the field": "Obstructing", "handled the ball": "Handled ball",
};

const th = "label h-9";

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
  const batVenues = venues.filter((v) => v.bat_innings >= 3).sort((a, b) => b.runs - a.runs).slice(0, 6);
  const bowlVenues = venues.filter((v) => v.balls_bowled >= 60).sort((a, b) => b.wickets - a.wickets).slice(0, 6);

  // Lead with the player's main suit: bowlers show the ball first and only it is
  // highlighted; everyone else leads with the bat.
  const bowlerFirst = bowls && (player.role === "BOWL" || !bats);
  const plural = (n: number, one: string, many: string) => `${fmt(n)} ${n === 1 ? one : many}`;
  const board: ScoreItem[] = [];
  if (cur) {
    const batting: ScoreItem[] = bats ? [
      { label: "Runs", value: fmt(cur.runs), hint: `HS ${cur.highest ?? "–"}`, emphasis: !bowlerFirst },
      { label: "Average", value: fmt(cur.bat_avg, 2), hint: `${cur.hundreds}×100  ${cur.fifties}×50` },
      { label: "Strike rate", value: fmt(cur.bat_sr, 1),
        hint: `${plural(cur.fours, "four", "fours")} · ${plural(cur.sixes, "six", "sixes")}` },
    ] : [];
    const bowling: ScoreItem[] = bowls ? [
      { label: "Wickets", value: fmt(cur.wickets), hint: cur.wickets ? `Best ${cur.best_bowling}` : undefined, emphasis: bowlerFirst },
      { label: "Economy", value: fmt(cur.bowl_econ, 2), hint: `Avg ${fmt(cur.bowl_avg, 2)}` },
      ...(bowlerFirst ? [{ label: "Balls per wicket", value: fmt(cur.bowl_sr, 1), hint: `${fmt(cur.bowl_dot_pct, 1)}% dots` }] : []),
    ] : [];
    board.push({ label: "Matches", value: fmt(cur.matches) });
    // A specialist bowler's batting shrinks to runs only.
    board.push(...(bowlerFirst ? [...bowling, ...batting.slice(0, 1)] : [...batting, ...bowling]));
    if (player.role === "WK") board.push({ label: "Dismissals", value: fmt(cur.catches + cur.stumpings), hint: `${cur.stumpings} stumpings` });
  }

  return (
    <div className="space-y-12">
      <div>
        <PageHeader
          kicker={[player.country, ROLE_LABEL[player.role], span(player.era_start, player.era_end)].filter(Boolean).join(" · ")}
          title={displayName(player)}
          sub={
            <div className="flex flex-wrap items-center gap-2">
              {player.full_name && player.full_name !== player.name && (
                <span className="font-mono text-xs">{player.name} on the scorecard</span>
              )}
              <Badge variant="outline" className="font-mono text-[10px] uppercase">{player.capped ? "International" : "Uncapped"}</Badge>
              {player.batting_hand && <Badge variant="outline">{player.batting_hand === "L" ? "Left-hand bat" : "Right-hand bat"}</Badge>}
              {(player.bowling_type || player.bowling_style) && <Badge variant="outline">{bowlingText(player)}</Badge>}
            </div>
          }
          actions={format && (
            <Button asChild variant="outline" size="lg">
              <Link href={`/compare?a=${player.id}&format=${format}`}><ScalesIcon />Compare</Link>
            </Button>
          )}
          className="mb-0"
        />
        {available.length > 0 && (
          <FormatTabs formats={available} active={format} hrefFor={(f) => `/players/${player.id}?format=${f}`} className="mt-6" />
        )}
      </div>

      {!cur ? (
        <Nothing title="No ball-by-ball record">This player has no deliveries in the Cricsheet data.</Nothing>
      ) : (
        <>
          <Scoreboard items={board} />

          <div className="grid gap-12 lg:grid-cols-[1.7fr_1fr]">
            <Section n={1} title="Season by season" aside={FORMAT_LABEL[format!]}>
              {seasons.length > 1 ? (
                <SeasonChart showBowling={bowls} initial={bowlerFirst ? "bowl" : "bat"}
                  data={seasons.map((s) => ({ season: s.season!, runs: s.runs, bat_avg: s.bat_avg,
                    bat_sr: s.bat_sr, wickets: s.wickets, bowl_econ: s.bowl_econ }))} />
              ) : <Nothing title="One season">Only one season in this format so far.</Nothing>}
            </Section>

            <Section n={2} title="How they get out" aside={outs ? `${outs} dismissals` : undefined}>
              {dismissals.length ? (
                <ul className="space-y-3.5">
                  {dismissals.map((d, i) => (
                    <li key={d.kind}>
                      <div className="mb-1.5 flex items-baseline justify-between text-sm">
                        <span className={cn(i === 0 && "font-semibold")}>{OUT[d.kind] ?? d.kind}</span>
                        <span className="font-mono text-xs text-muted-foreground tnum">
                          {d.n} <span className="ml-1 text-foreground">{Math.round((100 * d.n) / outs)}%</span>
                        </span>
                      </div>
                      <Bar value={d.n} max={outs} tone={i === 0 ? "signal" : "muted"} />
                    </li>
                  ))}
                </ul>
              ) : <Nothing title="Never out">Not dismissed in this format.</Nothing>}
            </Section>
          </div>

          {phases.length > 0 && (
            <div className="grid gap-12 lg:grid-cols-2">
              {(bowlerFirst ? (["bowl", "bat"] as const) : (["bat", "bowl"] as const)).map((role, k) => {
                const rows = phases.filter((p) => p.role === role);
                if (!rows.length || (role === "bowl" && !bowls) || (role === "bat" && !bats)) return null;
                return (
                  <Section key={role} n={3 + k} title={role === "bat" ? "Batting by phase" : "Bowling by phase"}>
                    <div className="border-y">
                      <Table>
                        <TableHeader>
                          <TableRow className="hover:bg-transparent">
                            <TableHead className={th}>Phase</TableHead>
                            <TableHead className={`${th} text-right`}>Balls</TableHead>
                            <TableHead className={`${th} text-right`}>{role === "bat" ? "Runs" : "Wkts"}</TableHead>
                            <TableHead className={`${th} text-right`}>{role === "bat" ? "SR" : "Econ"}</TableHead>
                            <TableHead className={`${th} text-right`}>Dot %</TableHead>
                            <TableHead className={`${th} text-right`}>4/6 %</TableHead>
                            <TableHead className={`${th} text-right`}>{role === "bat" ? "Balls/out" : "Balls/wkt"}</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody className="font-mono tnum">
                          {rows.map((p) => (
                            <TableRow key={p.phase}>
                              <TableCell className="font-sans font-medium">{PHASE[p.phase]}</TableCell>
                              <TableCell className="text-right text-muted-foreground">{fmt(p.balls)}</TableCell>
                              <TableCell className="text-right">{role === "bat" ? fmt(p.runs) : fmt(p.wickets)}</TableCell>
                              <TableCell className="text-right font-semibold">{role === "bat" ? fmt(p.strike_rate, 1) : fmt(p.economy, 2)}</TableCell>
                              <TableCell className="text-right">{fmt((p.dot_pct ?? 0) * 100, 1)}</TableCell>
                              <TableCell className="text-right">{fmt(((p.four_pct ?? 0) + (p.six_pct ?? 0)) * 100, 1)}</TableCell>
                              <TableCell className="text-right">{p.wickets ? fmt(p.balls / p.wickets, 1) : "–"}</TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                  </Section>
                );
              })}
            </div>
          )}

          {(batVenues.length > 0 || bowlVenues.length > 0) && (
            <div className="grid gap-12 lg:grid-cols-2">
              {bats && batVenues.length > 0 && (
                <Section n={5} title="Best grounds · bat" aside="3+ innings">
                  <VenueTable rows={batVenues} cols={["Inns", "Runs", "Avg", "SR"]} hot={1}
                    cells={(v) => [fmt(v.bat_innings), fmt(v.runs), fmt(v.bat_avg, 2), fmt(v.bat_sr, 1)]} />
                </Section>
              )}
              {bowls && bowlVenues.length > 0 && (
                <Section n={6} title="Best grounds · ball" aside="10+ overs">
                  <VenueTable rows={bowlVenues} cols={["Overs", "Wkts", "Econ"]} hot={1}
                    cells={(v) => [overs(v.balls_bowled), fmt(v.wickets), fmt(v.bowl_econ, 2)]} />
                </Section>
              )}
            </div>
          )}
        </>
      )}

      <Career formats={prof.formats} active={format} />
    </div>
  );
}

function VenueTable({ rows, cols, cells, hot }: {
  rows: VenueSplit[]; cols: string[]; cells: (r: VenueSplit) => string[]; hot: number;
}) {
  return (
    <div className="border-y">
      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className={th}>Ground</TableHead>
            {cols.map((c) => <TableHead key={c} className={`${th} text-right`}>{c}</TableHead>)}
          </TableRow>
        </TableHeader>
        <TableBody className="font-mono tnum">
          {rows.map((r) => (
            <TableRow key={r.venue_id}>
              <TableCell className="max-w-56 truncate font-sans">
                <Link href={`/venues/${r.venue_id}`} className="font-medium hover:text-signal">{r.venue_name}</Link>
              </TableCell>
              {cells(r).map((c, i) => (
                <TableCell key={i} className={cn("text-right", i === hot && "font-semibold")}>{c}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

function Career({ formats, active }: { formats: FormatStats[]; active?: Format }) {
  if (!formats.length) return null;
  const bowled = formats.filter((f) => f.balls_bowled > 0);
  const row = (f: FormatStats) => cn(f.format === active && "bg-signal-soft hover:bg-signal-soft");
  return (
    <div className="space-y-10">
      <Section n={7} title="Career · batting">
        <div className="border-y">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {["Format", "Mat", "Inns", "NO", "Runs", "HS", "Avg", "SR", "100", "50", "4s", "6s", "Ct", "St"].map((h, i) => (
                  <TableHead key={h} className={cn(th, i > 0 && "text-right")}>{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody className="font-mono tnum">
              {formats.map((f) => (
                <TableRow key={f.format} className={row(f)}>
                  <TableCell className="font-sans font-semibold">{FORMAT_LABEL[f.format]}</TableCell>
                  {[fmt(f.matches), fmt(f.bat_innings), fmt(f.not_outs), fmt(f.runs), String(f.highest ?? "–"),
                    fmt(f.bat_avg, 2), fmt(f.bat_sr, 1), String(f.hundreds), String(f.fifties), fmt(f.fours),
                    fmt(f.sixes), String(f.catches), String(f.stumpings)].map((v, i) => (
                    <TableCell key={i} className={cn("text-right", i === 3 && "font-semibold")}>{v}</TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Section>
      {bowled.length > 0 && (
        <Section n={8} title="Career · bowling">
          <div className="border-y">
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  {["Format", "Inns", "Overs", "Runs", "Wkts", "Best", "Avg", "Econ", "SR", "Dot %", "5w"].map((h, i) => (
                    <TableHead key={h} className={cn(th, i > 0 && "text-right")}>{h}</TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody className="font-mono tnum">
                {bowled.map((f) => (
                  <TableRow key={f.format} className={row(f)}>
                    <TableCell className="font-sans font-semibold">{FORMAT_LABEL[f.format]}</TableCell>
                    {[fmt(f.bowl_innings), overs(f.balls_bowled), fmt(f.runs_conceded), fmt(f.wickets),
                      f.wickets ? f.best_bowling ?? "–" : "–", fmt(f.bowl_avg, 2), fmt(f.bowl_econ, 2),
                      fmt(f.bowl_sr, 1), fmt(f.bowl_dot_pct, 1), String(f.five_wkts)].map((v, i) => (
                      <TableCell key={i} className={cn("text-right", i === 3 && "font-semibold")}>{v}</TableCell>
                    ))}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Section>
      )}
      <p className="font-mono text-[11px] text-muted-foreground">
        Source: Cricsheet ball-by-ball records. Figures cover the matches Cricsheet holds and can sit below official career totals.
      </p>
    </div>
  );
}

/** "Right-arm fast-medium", "Slow left-arm orthodox", "Leg-spin"; else "Pace" / "Spin". */
function bowlingText(p: { bowling_type?: string | null; bowling_arm?: string | null; bowling_style: string | null }): string {
  const t = p.bowling_type;
  if (!t) return p.bowling_style === "spin" ? "Spin" : "Pace";
  if (t.startsWith("left-arm")) return t === "left-arm orthodox" ? "Slow left-arm orthodox" : "Left-arm wrist-spin";
  if (t === "off-spin" || t === "leg-spin") return t === "off-spin" ? "Off-spin" : "Leg-spin";
  return `${p.bowling_arm === "L" ? "Left" : "Right"}-arm ${t}`;
}
