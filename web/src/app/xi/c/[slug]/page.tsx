import { ArrowRightIcon, ShuffleIcon } from "@phosphor-icons/react/ssr";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Scoreboard, Section } from "@/components/blocks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DailyRank } from "@/components/xi/daily-rank";
import { ShareBox } from "@/components/xi/share-box";
import { fmt, NotFound, ROLE_LABEL } from "@/lib/api";
import { cn } from "@/lib/utils";
import { captainText, XI_COPY, xiApi, type CaptainInfo, type Challenge, type MatchSummary } from "@/lib/xi";

type Props = { params: Promise<{ slug: string }>; searchParams: Promise<{ vs?: string }> };

async function load(slug: string): Promise<Challenge> {
  try {
    return await xiApi.challenge(slug);
  } catch (e) {
    if (e instanceof NotFound) notFound();
    throw e;
  }
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const c = await load((await params).slug);
  return { title: `${c.result.verdict} — XI Builder`, description: `An XI drafted across eras, ${c.result.verdict.toLowerCase()} against the ${c.opponent}.` };
}

const MINE = "Your XI";

export default async function SeriesPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const { vs } = await searchParams;
  const c = await load(slug);
  let rival: Challenge | null = null;
  if (vs && vs !== slug) {
    try {
      const r = await xiApi.challenge(vs);
      if (r.format === c.format && r.seed === c.seed) rival = r;
    } catch (e) {
      if (!(e instanceof NotFound)) throw e;
    }
  }
  const { result: r } = c;
  const won = r.won > r.lost;
  const lost = r.lost > r.won;
  const spread = (x: Challenge) => x.result.won - x.result.lost;
  const replay = `/xi/${c.format}/draft?seed=${c.seed}&vs=${c.slug}`;

  return (
    <div className="space-y-12">
      <div>
        <div className="label mb-2">
          {XI_COPY[c.format].title} · {c.daily ? `daily challenge ${c.daily}` : `draw #${c.seed}`} · v {c.opponent}
        </div>
        <h1 className={cn("font-display text-6xl leading-[0.85] font-black uppercase sm:text-8xl", won && "text-signal")}>
          {r.verdict}
        </h1>
        <div className="seam mt-5" aria-hidden />
      </div>

      {rival && (
        <div className={cn("grid gap-px border sm:grid-cols-[1fr_auto_1fr]",
          spread(c) > spread(rival) ? "bg-signal" : "bg-border")}>
          <div className="bg-card p-5">
            <div className="label">You</div>
            <div className="font-display text-3xl font-bold uppercase">{r.verdict}</div>
          </div>
          <div className="grid place-items-center bg-card px-6 font-display text-2xl font-black text-muted-foreground">v</div>
          <div className="bg-card p-5 text-right">
            <div className="label">The XI you were chasing</div>
            <div className="font-display text-3xl font-bold uppercase">{rival.result.verdict}</div>
          </div>
          <div className="bg-card px-5 py-3 font-mono text-xs sm:col-span-3">
            {spread(c) > spread(rival) ? "You beat their XI on the same spins."
              : spread(c) < spread(rival) ? "Their XI did better from the same spins."
              : "Dead level: same series margin."}
          </div>
        </div>
      )}

      <Scoreboard items={[
        { label: "Won", value: String(r.won), emphasis: r.won > 0 },
        { label: "Lost", value: String(r.lost) },
        ...(c.format === "Test" ? [{ label: "Drawn", value: String(r.drawn) }] : []),
        ...(r.tied ? [{ label: "Tied", value: String(r.tied) }] : []),
        { label: "Opponent", value: c.opponent.replace(/^All-time /, ""), hint: XI_COPY[c.format].title },
      ]} />

      {c.daily && <DailyRank format={c.format} day={c.daily} slug={c.slug} />}

      <Section n={1} title="The series" aside={<Link href={`/xi/c/${c.slug}/match/1`} className="hover:text-foreground">watch it ball by ball →</Link>}>
        <div className="grid gap-px border bg-border sm:grid-cols-2 lg:grid-cols-5">
          {c.matches.map((m) => <MatchCard key={m.match} m={m} slug={c.slug} them={c.opponent.replace(/^(Test|ODI|T20I|IPL) /, "").replace(/^All-time /, "")} />)}
        </div>
      </Section>

      <div className="grid gap-12 lg:grid-cols-[1.3fr_1fr]">
        <Section n={2} title="Your XI" aside="batting order · C = captain">
          <ol className="divide-y border-y">
            {c.xi.map((p) => (
              <li key={p.id} className="flex items-center gap-3 py-2.5">
                <span className="w-6 font-display text-xl font-bold text-muted-foreground tnum">{p.order}</span>
                <span className="min-w-0 flex-1">
                  {p.kind === "modern" ? (
                    <Link href={`/players/${p.id}`} className="block truncate font-medium hover:text-signal">{p.name}</Link>
                  ) : (
                    <span className="block truncate font-medium">{p.name}</span>
                  )}
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {ROLE_LABEL[p.role]} · {p.country ?? "—"} · {p.years}
                  </span>
                </span>
                {c.captains?.mine.id === p.id && <Badge className="bg-foreground font-mono text-[9px] text-background">C</Badge>}
                {p.kind === "legend" && <Badge className="bg-signal font-mono text-[9px] text-signal-foreground">Legend</Badge>}
                <span className="shrink-0 text-right font-mono text-xs text-muted-foreground tnum">
                  {keyStats(p.role, p.runs, p.wickets)}
                </span>
              </li>
            ))}
          </ol>
          {c.captains && <Captains mine={c.captains.mine} them={c.captains.them} opponent={c.opponent} />}
        </Section>

        <Section n={3} title="Challenge a friend">
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Send this link. They get exactly the same eleven spins and try to top <b className="text-foreground">{r.verdict.toLowerCase()}</b>.
            </p>
            <ShareBox path={replay} />
            <div className="flex flex-wrap gap-2">
              <Button asChild variant="outline"><Link href={replay}>Redraft these spins <ArrowRightIcon /></Link></Button>
              <Button asChild variant="ghost"><Link href={`/xi/${c.format}/draft`}><ShuffleIcon />New draw</Link></Button>
            </div>
            {lost && (
              <p className="font-mono text-[11px] text-muted-foreground">
                Tip: the Greats bat deep. Strong top-order batters and a fifth genuine bowler usually swing a series.
              </p>
            )}
          </div>
        </Section>
      </div>
    </div>
  );
}

function Captains({ mine, them, opponent }: { mine: CaptainInfo; them: CaptainInfo; opponent: string }) {
  const row = (label: string, x: CaptainInfo) => (
    <div className="flex flex-wrap items-baseline justify-between gap-x-3 py-1.5 text-xs">
      <span><span className="label mr-2">{label}</span><span className="font-semibold">{x.name ?? "—"}</span></span>
      <span className="font-mono text-muted-foreground">{x.record ? captainText(x.record) : "no captaincy record"}</span>
    </div>
  );
  return (
    <div className="mt-4 divide-y border-y">
      {row("Your captain", mine)}
      {row(`${opponent}`, them)}
      <p className="py-1.5 font-mono text-[10px] text-muted-foreground">Captains call the toss and run the bowling; a better real record means fewer bad calls.</p>
    </div>
  );
}

/** The numbers that matter for the role: runs for batters and keepers, wickets
 * for bowlers, both for all-rounders. */
function keyStats(role: string, runs: number | null, wickets: number | null) {
  const r = `${fmt(runs)} runs`;
  const w = `${fmt(wickets)} wkts`;
  return role === "BOWL" ? w : role === "AR" ? `${r} · ${w}` : r;
}

function MatchCard({ m, slug, them }: { m: MatchSummary; slug: string; them: string }) {
  const mine = m.winner === MINE;
  return (
    <Link href={`/xi/c/${slug}/match/${m.match}`} className="group flex flex-col gap-3 bg-card p-4 hover:bg-muted">
      <div className="flex items-baseline justify-between">
        <span className="label">Match {m.match}</span>
        <span className={cn("font-mono text-[11px] font-semibold uppercase",
          m.winner ? (mine ? "text-signal" : "text-muted-foreground") : "text-chart-2")}>
          {m.winner ? (mine ? "Won" : "Lost") + (m.result === "super over" ? " · super over" : "") : m.result === "draw" ? "Drawn" : "Tied"}
        </span>
      </div>
      <div className="space-y-1 font-mono text-xs tnum">
        {m.scores.map((s, i) => (
          <div key={i} className="flex justify-between gap-2">
            <span className={cn("truncate", s.team === MINE ? "text-foreground" : "text-muted-foreground")}>
              {s.team === MINE ? "You" : them}
            </span>
            <span>{s.runs}/{s.wickets}{s.declared ? "d" : ""} <span className="text-muted-foreground">({s.overs})</span></span>
          </div>
        ))}
      </div>
      <div className="mt-auto border-t pt-2 text-[11px] leading-snug text-muted-foreground">
        <div className="truncate">{m.margin}</div>
        <div className="truncate">Top score: {m.top_scorer.name} {m.top_scorer.runs} ({m.top_scorer.balls})</div>
      </div>
    </Link>
  );
}
