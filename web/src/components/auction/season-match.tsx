"use client";

import { ArrowLeftIcon, ArrowRightIcon } from "@phosphor-icons/react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { MatchStage } from "@/components/xi/match-viewer";
import { loadSeat } from "@/lib/auction";
import { saveProgress, seasonApi, type SeasonView } from "@/lib/season";
import type { FullMatch } from "@/lib/xi";

/** One season match, watched live (the result hidden until the last ball) or as a
 * finished replay. Watching it live counts it as seen in the season view. */
export function SeasonMatch({ code, n, live }: { code: string; n: number; live: boolean }) {
  const [view, setView] = useState<SeasonView | null>(null);
  const [match, setMatch] = useState<FullMatch | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = loadSeat(code)?.token ?? null;
    Promise.all([seasonApi.get(code, token), seasonApi.match(code, n)])
      .then(([v, m]) => { setView(v); setMatch(m); })
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load the match."));
  }, [code, n]);

  const season = view?.season;
  const idOf = useMemo(() => Object.fromEntries((season?.teams ?? []).map((t) => [t.name, t.id])), [season]);
  if (error) return <div className="grid min-h-[40vh] place-items-center text-destructive">{error}</div>;
  if (!season || !match) return <div className="grid min-h-[40vh] place-items-center text-muted-foreground">Loading the match…</div>;

  const summary = season.matches[n - 1];
  const youName = season.teams.find((t) => t.id === view?.you)?.name ?? null;
  const who = (team: string) => idOf[team] ?? team;
  const back = `/auction/${code}/season`;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link href={back} className="label hover:text-foreground">← The season</Link>
        {!live && (
          <div className="flex gap-1">
            {n > 1 && <Button asChild variant="ghost" size="sm"><Link href={`/auction/${code}/season/match/${n - 1}`}><ArrowLeftIcon />Match {n - 1}</Link></Button>}
            {n < season.matches.length && <Button asChild variant="ghost" size="sm"><Link href={`/auction/${code}/season/match/${n + 1}`}>Match {n + 1}<ArrowRightIcon /></Link></Button>}
          </div>
        )}
      </div>
      <MatchStage match={match} format="IPL" live={live} who={who} you={youName}
        kicker={<>Match {n} of {season.matches.length} · {summary?.stage ?? "League"} · {who(match.teams[0])} v {who(match.teams[1])}</>}
        after={
          <div className="flex flex-wrap items-center gap-4 border-l-2 border-signal pl-4">
            <SeenMarker code={code} n={n} />
            <Button asChild size="lg" className="ml-auto font-mono uppercase">
              <Link href={back}>Back to the season<ArrowRightIcon /></Link>
            </Button>
          </div>
        } />
    </div>
  );
}

function SeenMarker({ code, n }: { code: string; n: number }) {
  useEffect(() => saveProgress(code, n), [code, n]);
  return <div className="text-sm text-muted-foreground">Result in. The table has moved on to match {n}.</div>;
}
