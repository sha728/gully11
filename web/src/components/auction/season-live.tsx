"use client";

import { ArrowLeftIcon, PlayIcon } from "@phosphor-icons/react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Nothing } from "@/components/blocks";
import { Button } from "@/components/ui/button";
import { BowlerPicker } from "@/components/xi/captain-match";
import { MatchStage } from "@/components/xi/match-viewer";
import { loadSeat } from "@/lib/auction";
import { ROLE_LABEL } from "@/lib/api";
import { seasonApi, type ImpactOffer, type SeasonLive } from "@/lib/season";

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

  async function choose(bowler: string | null, impactIn?: string, impactOut?: string) {
    if (!live || !token) return;
    setBusy(impactIn ? "impact" : bowler);
    setError(null);
    try {
      const v = await seasonApi.bowl(code, token, live.key, bowler, impactIn, impactOut);
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
        pause={live.yours ? (
          <div className="space-y-4">
            {live.impact && (
              <ImpactPanel key={live.key} offer={live.impact} kind={live.kind} wickets={live.wickets} busy={busy}
                onBring={(sub, out) => choose(null, sub, out)} onSkip={() => choose("none")} />
            )}
            {live.kind === "bowl" && live.options && live.suggested && (
              <BowlerPicker options={live.options} suggested={live.suggested} over={live.over}
                batting={inn?.batting ?? ""} score={inn} busy={busy} error={error} onChoose={choose} />
            )}
            {live.kind === "bat" && error && <p className="text-sm text-destructive">{error}</p>}
          </div>
        ) : (
          <p className="border-l-2 border-signal pl-4 font-mono text-sm text-muted-foreground">
            {live.kind === "bat" ? "Waiting for the other captain to decide on their Impact Player."
              : `Waiting for the other captain to choose who bowls over ${live.over}.`} This page follows along.
          </p>
        )} />
    </div>
  );
}

/** Bring on your Impact Player now (or, at a batting break, carry on without him). */
function ImpactPanel({ offer, kind, wickets, busy, onBring, onSkip }: {
  offer: ImpactOffer; kind: "bowl" | "bat"; wickets: number; busy: string | null;
  onBring: (sub: string, out: string) => void; onSkip: () => void;
}) {
  const [sub, setSub] = useState(offer.subs[0]?.id ?? "");
  const [out, setOut] = useState(offer.replace[kind === "bat" ? offer.replace.length - 1 : 0]?.id ?? "");
  const moment = kind === "bowl" ? "before this over" : wickets === 0 ? "at the start of your innings" : "with a wicket just fallen";
  return (
    <section className="space-y-3 border border-signal/50 bg-signal/5 p-5" aria-live="polite">
      <div>
        <div className="label">Impact Player · {moment}</div>
        <h2 className="font-display text-2xl font-black uppercase">
          {kind === "bat" ? "Send in your Impact Player?" : "Bring on your Impact Player?"}
        </h2>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="space-y-1 text-sm">
          <span className="label block">Impact Player</span>
          <select value={sub} onChange={(e) => setSub(e.target.value)} className="h-9 w-full border bg-background px-2">
            {offer.subs.map((p) => <option key={p.id} value={p.id}>{p.name} · {(p.role === "BOWL" || p.role === "AR") && p.kind ? p.kind : ROLE_LABEL[p.role].toLowerCase()}</option>)}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="label block">{kind === "bat" ? "Instead of (yet to bat)" : "Comes on for"}</span>
          <select value={out} onChange={(e) => setOut(e.target.value)} className="h-9 w-full border bg-background px-2">
            {offer.replace.map((p) => <option key={p.id} value={p.id}>{p.name} · {ROLE_LABEL[p.role].toLowerCase()}</option>)}
          </select>
        </label>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button disabled={busy !== null || !sub || !out} onClick={() => onBring(sub, out)} className="font-mono uppercase">
          {kind === "bat" ? "Send him in" : "Bring him on"}
        </Button>
        {kind === "bat" && (
          <Button variant="ghost" disabled={busy !== null} onClick={onSkip} className="font-mono uppercase">Not now</Button>
        )}
      </div>
      <p className="font-mono text-[11px] text-muted-foreground">
        One change a match. The player he replaces takes no further part{kind === "bat" ? "; he bats next" : "; he can bowl a full four overs"}.
      </p>
    </section>
  );
}
