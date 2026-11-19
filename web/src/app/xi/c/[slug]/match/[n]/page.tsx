import { ArrowLeftIcon, ArrowRightIcon } from "@phosphor-icons/react/ssr";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Scoreboard } from "@/components/blocks";
import { Button } from "@/components/ui/button";
import { MatchViewer } from "@/components/xi/match-viewer";
import { NotFound } from "@/lib/api";
import { cn } from "@/lib/utils";
import { XI_COPY, xiApi } from "@/lib/xi";

type Props = { params: Promise<{ slug: string; n: string }> };

export const metadata: Metadata = { title: "Match — XI Builder" };

export default async function MatchPage({ params }: Props) {
  const { slug, n: raw } = await params;
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
  const headline = match.result === "draw" ? "Match drawn" : match.result === "tie" ? "Match tied"
    : `${youWon ? "You" : "World XI"} ${match.margin}`;

  return (
    <div className="space-y-10">
      <div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link href={`/xi/c/${slug}`} className="label hover:text-foreground">
            ← {challenge.result.verdict} · {XI_COPY[challenge.format].title}{isTest ? " (beta)" : ""}
          </Link>
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
        </div>
        <div className="label mt-4 mb-2">Match {n} of 5 · v {challenge.opponent}</div>
        <h1 className={cn("font-display text-5xl leading-[0.9] font-black uppercase sm:text-7xl", youWon && "text-signal")}>
          {headline}
        </h1>
        <div className="seam mt-5" aria-hidden />
      </div>

      <Scoreboard items={match.innings.map((inn, i) => ({
        label: `${inn.batting === "Your XI" ? "You" : "World XI"} · ${isTest ? `inns ${i + 1}` : i === 0 ? "batting first" : "chasing"}`,
        value: `${inn.runs}/${inn.wickets}${inn.declared ? "d" : ""}`,
        hint: `${inn.overs} overs${inn.target ? ` · target ${inn.target}` : ""}`,
        emphasis: inn.batting === "Your XI" && youWon && i === match.innings.length - 1,
      }))} />

      <MatchViewer match={match} isTest={isTest} />
    </div>
  );
}
