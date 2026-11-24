"use client";

import { ArrowRightIcon, FastForwardIcon, SparkleIcon, SpinnerGapIcon, TrophyIcon } from "@phosphor-icons/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { MatchStage } from "@/components/xi/match-viewer";
import { ROLE_LABEL } from "@/lib/api";
import { cn } from "@/lib/utils";
import { xiApi, type BowlOption, type LiveMatch, type MatchSummary } from "@/lib/xi";

const YOU = "Your XI";

function score(matches: MatchSummary[]) {
  const w = matches.filter((m) => m.winner === YOU).length;
  const l = matches.filter((m) => m.winner && m.winner !== YOU).length;
  return `${w}–${l}`;
}

/** One match of a series you captain: it plays up to each over your side bowls,
 * then waits for you to choose the bowler. */
export function CaptainMatch({ draftId, format, initial }: { draftId: string; format: string; initial: LiveMatch }) {
  const router = useRouter();
  const [live, setLive] = useState(initial);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const n = live.n;
  const opponent = live.match.teams.find((t) => t !== YOU) ?? "Greats";
  const short = opponent.replace(/^(Test|ODI|T20I|IPL) /, "").replace(/^All-time /, "");
  const who = (team: string) => (team === YOU ? "You" : short);

  async function choose(bowler: string) {
    if (live.status !== "bowl") return;
    setBusy(bowler);
    setError(null);
    try {
      setLive(await xiApi.bowl(draftId, n, live.key, bowler));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send that choice.");
    } finally {
      setBusy(null);
    }
  }

  async function finish() {
    setBusy("finish");
    setError(null);
    try {
      const res = await xiApi.play(draftId);
      router.push(`/xi/c/${res.slug}${res.rival ? `?vs=${res.rival}` : ""}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't finish the series.");
      setBusy(null);
    }
  }

  const done = live.status === "done";
  const after = done ? [...live.series, { match: n, winner: live.match.winner } as MatchSummary] : live.series;

  return (
    <MatchStage key={n} match={live.match} format={format} live who={who} you={YOU}
      kicker={<>Match {n} of 5 · you&apos;re captain · series {score(live.series)}</>}
      pause={live.status === "bowl" && (
        <BowlerPicker options={live.options} suggested={live.suggested} over={live.over}
          batting={who(live.match.innings[live.innings - 1]?.batting ?? "")}
          score={live.match.innings[live.innings - 1]} busy={busy} error={error} onChoose={choose} />
      )}
      after={
        <div className="flex flex-wrap items-center gap-4 border-l-2 border-signal pl-4">
          <div>
            <div className="label">Series after match {n}</div>
            <div className="font-display text-3xl font-black tnum">{score(after)}</div>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          {n < 5 ? (
            <Button asChild size="lg" className="ml-auto font-mono uppercase">
              <Link href={`/xi/d/${draftId}/live/${n + 1}`}>Match {n + 1}<ArrowRightIcon /></Link>
            </Button>
          ) : (
            <Button size="lg" className="ml-auto font-mono uppercase" disabled={busy !== null} onClick={finish}>
              {busy ? <SpinnerGapIcon className="animate-spin" /> : <TrophyIcon />}The series verdict
            </Button>
          )}
        </div>
      } />
  );
}

function figures(o: BowlOption) {
  return o.overs === "0" ? "yet to bowl" : `${o.overs}–${o.runs}–${o.wickets}`;
}

/** Who bowls the next over: the side's bowlers (part-timers folded away), the
 * engine's suggestion marked, "Pick for me" and "Sim the rest of this match". */
export function BowlerPicker({ options, suggested, over, batting, score, busy, error, onChoose }: {
  options: BowlOption[]; suggested: string; over: number; batting: string;
  score?: { runs: number; wickets: number }; busy: string | null;
  error: string | null; onChoose: (bowler: string) => void;
}) {
  const regular = options.filter((o) => o.regular);
  const others = options.filter((o) => !o.regular);
  const button = (o: BowlOption) => (
    <button key={o.id} type="button" disabled={busy !== null} onClick={() => onChoose(o.id)}
      className={cn("flex flex-col gap-1 border bg-card p-3 text-left transition-colors hover:border-signal hover:bg-muted disabled:opacity-60",
        o.id === suggested && "border-signal/60")}>
      <span className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-medium">{o.name}</span>
        {busy === o.id && <SpinnerGapIcon className="size-4 animate-spin" />}
        {o.id === suggested && <span className="font-mono text-[9px] tracking-wide text-signal uppercase">suggested</span>}
      </span>
      <span className="font-mono text-[11px] text-muted-foreground">
        {o.kind ?? ROLE_LABEL[o.role].toLowerCase()} · {figures(o)} · {o.overs_left} left
      </span>
    </button>
  );

  return (
    <section className="space-y-4 border border-signal/50 bg-signal/5 p-5" aria-live="polite">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="label">You&apos;re bowling · {batting} {score?.runs ?? 0}/{score?.wickets ?? 0}</div>
          <h2 className="font-display text-3xl font-black uppercase">Who bowls over {over}?</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" disabled={busy !== null} onClick={() => onChoose("auto")} className="font-mono uppercase">
            {busy === "auto" ? <SpinnerGapIcon className="animate-spin" /> : <SparkleIcon />}Pick for me
          </Button>
          <Button variant="ghost" disabled={busy !== null} onClick={() => onChoose("rest")} className="font-mono uppercase">
            {busy === "rest" ? <SpinnerGapIcon className="animate-spin" /> : <FastForwardIcon />}Sim the rest of this match
          </Button>
        </div>
      </div>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{regular.map(button)}</div>
      {others.length > 0 && (
        <details className="text-sm">
          <summary className="cursor-pointer font-mono text-xs text-muted-foreground uppercase">Part-timers ({others.length})</summary>
          <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{others.map(button)}</div>
        </details>
      )}
      <p className="font-mono text-[11px] text-muted-foreground">
        Figures are overs–runs–wickets this innings. Four overs each; nobody bowls two in a row; the keeper can&apos;t bowl.
      </p>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </section>
  );
}
