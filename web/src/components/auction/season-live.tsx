"use client";

import { ArrowLeftIcon, PlayIcon } from "@phosphor-icons/react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Nothing } from "@/components/blocks";
import { Button } from "@/components/ui/button";
import { BowlerPicker } from "@/components/xi/captain-match";
import { MatchStage } from "@/components/xi/match-viewer";
import { loadSeat } from "@/lib/auction";
import { seasonApi, type SeasonLive } from "@/lib/season";

/** The season match waiting on a captain's bowling change. The franchise whose
 * over it is chooses here; everyone else watches it fill in. */
export function SeasonLiveMatch({ code }: { code: string }) {
  const [token, setToken] = useState<string | null>(null);
  const [live, setLive] = useState<SeasonLive | null>(null);
  const [finished, setFinished] = useState<number | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (t: string | null) => {
    try {
      setLive(await seasonApi.live(code, t));
    } catch {
      // Nothing waiting any more: the match is over (or never paused).
      const v = await seasonApi.get(code, t).catch(() => null);
      setFinished(v?.season?.matches.length ?? 0);
      setLive(null);
    }
  }, [code]);

  useEffect(() => {
    const t = loadSeat(code)?.token ?? null;
    setToken(t);
    load(t);
  }, [code, load]);

  // Not your over: look again every few seconds while the other captain decides.
  useEffect(() => {
    if (!live || live.yours) return;
    const id = setInterval(() => load(token), 4000);
    return () => clearInterval(id);
  }, [live, token, load]);

  async function choose(bowler: string) {
    if (!live || !token) return;
    setBusy(bowler);
    setError(null);
    try {
      const v = await seasonApi.bowl(code, token, live.key, bowler);
      if (v.season?.live && v.season.live.match === live.match) await load(token);
      else {
        setFinished(live.match);
        setLive(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't send that choice.");
    } finally {
      setBusy(null);
    }
  }

  if (finished !== null) {
    return (
      <div className="space-y-6">
        <Link href={`/auction/${code}/season`} className="label hover:text-foreground"><ArrowLeftIcon className="inline" /> The season</Link>
        <Nothing title="That match is finished">
          <Button asChild className="mt-2 font-mono uppercase">
            <Link href={`/auction/${code}/season/match/${finished}?live=1`}><PlayIcon weight="fill" />Watch how it ended</Link>
          </Button>
        </Nothing>
      </div>
    );
  }
  if (!live) return <p className="py-10 font-mono text-sm text-muted-foreground">Loading the match…</p>;

  const m = live.match_json;
  const who = (team: string) => team;
  const inn = live.innings ? m.innings[live.innings - 1] : undefined;
  return (
    <div>
      <Link href={`/auction/${code}/season`} className="label hover:text-foreground"><ArrowLeftIcon className="inline" /> The season</Link>
      <MatchStage key={live.match} match={m} format="IPL" live who={who} you={null}
        kicker={<>Match {live.match}{live.stage !== "League" ? ` · ${live.stage}` : ""} · waiting on a captain</>}
        pause={live.yours && live.options && live.suggested ? (
          <BowlerPicker options={live.options} suggested={live.suggested} over={live.over}
            batting={inn?.batting ?? ""} score={inn} busy={busy} error={error} onChoose={choose} />
        ) : (
          <p className="border-l-2 border-signal pl-4 font-mono text-sm text-muted-foreground">
            Waiting for the other captain to choose who bowls over {live.over}. This page follows along.
          </p>
        )} />
    </div>
  );
}
