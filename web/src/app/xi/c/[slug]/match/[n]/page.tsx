import { ArrowLeftIcon, ArrowRightIcon } from "@phosphor-icons/react/ssr";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Scoreboard } from "@/components/blocks";
import { Button } from "@/components/ui/button";
import { MatchDay } from "@/components/xi/match-viewer";
import { NotFound } from "@/lib/api";
import { XI_COPY, xiApi } from "@/lib/xi";

type Props = { params: Promise<{ slug: string; n: string }>; searchParams: Promise<{ live?: string; vs?: string }> };

export const metadata: Metadata = { title: "Match day — XI Builder" };

export default async function MatchPage({ params, searchParams }: Props) {
  const { slug, n: raw } = await params;
  const sp = await searchParams;
  const live = !!sp.live;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 1 || n > 5) notFound();
  let challenge, match;
  try {
    [challenge, match] = await Promise.all([xiApi.challenge(slug), xiApi.match(slug, n)]);
  } catch (e) {
    if (e instanceof NotFound) notFound();
    throw e;
  }
  const isTest = challenge.format === "Test";
  const youWon = match.winner === "Your XI";
  const short = (team: string) => (team === "Your XI" ? "You" : challenge.opponent.replace(/^(Test|ODI|T20I|IPL) /, ""));

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        {live ? (
          <span className="label">Match day · {XI_COPY[challenge.format].title}{isTest ? " (beta)" : ""}</span>
        ) : (
          <Link href={`/xi/c/${slug}${sp.vs ? `?vs=${sp.vs}` : ""}`} className="label hover:text-foreground">
            ← {challenge.result.verdict} · {XI_COPY[challenge.format].title}{isTest ? " (beta)" : ""}
          </Link>
        )}
        {!live && (
          <div className="flex gap-1">
            {n > 1 && (
              <Button asChild variant="ghost" size="sm">
                <Link href={`/xi/c/${slug}/match/${n - 1}`}><ArrowLeftIcon />Match {n - 1}</Link>
              </Button>
            )}
            {n < 5 && (
              <Button asChild variant="ghost" size="sm">
                <Link href={`/xi/c/${slug}/match/${n + 1}`}>Match {n + 1}<ArrowRightIcon /></Link>
              </Button>
            )}
          </div>
        )}
      </div>

      <MatchDay challenge={challenge} match={match} n={n} live={live} vs={sp.vs}
        summary={
          <Scoreboard items={match.innings.map((inn, i) => ({
            label: `${short(inn.batting)} · ${isTest ? `inns ${i + 1}` : i === 0 ? "batting first" : "chasing"}`,
            value: `${inn.runs}/${inn.wickets}${inn.declared ? "d" : ""}`,
            hint: `${inn.overs} overs${inn.target ? ` · target ${inn.target}` : ""}`,
            emphasis: inn.batting === "Your XI" && youWon && i === match.innings.length - 1,
          }))} />
        } />
    </div>
  );
}
