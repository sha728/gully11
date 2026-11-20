"use client";

import { ArrowLeftIcon, ArrowRightIcon, CalendarDotIcon, CheckIcon } from "@phosphor-icons/react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { dailyDraft, recordText, XI_COPY, XI_FORMATS, xiApi, type BoardRow, type Leaderboard, type XIFormat } from "@/lib/xi";

const shift = (day: string, by: number) => {
  const d = new Date(`${day}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + by);
  return d.toISOString().slice(0, 10);
};
const signed = (n: number) => (n > 0 ? `+${n}` : String(n));

/** The daily leaderboard for one format and day, with your own entry picked out. */
export function LeaderboardView({ format, day }: { format: XIFormat; day?: string }) {
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      // First ask without a draft to learn the day, then with this browser's draft for it.
      const first = await xiApi.leaderboard(format, { day });
      const mine = dailyDraft(format, first.day);
      setDraft(mine);
      setBoard(mine ? await xiApi.leaderboard(format, { day: first.day, draft: mine }) : first);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load the leaderboard.");
    }
  }, [format, day]);

  useEffect(() => { load(); }, [load]);

  const href = (f: XIFormat, d?: string) => `/xi/leaderboard?format=${f}${d ? `&day=${d}` : ""}`;
  const shown = board?.day ?? day;
  const isToday = board ? board.day === board.today : !day;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <nav className="flex flex-wrap gap-1" aria-label="Format">
          {XI_FORMATS.map((f) => (
            <Button key={f} asChild size="sm" variant={f === format ? "default" : "outline"} className="font-mono uppercase">
              <Link href={href(f, day)}>{XI_COPY[f].title}</Link>
            </Button>
          ))}
        </nav>
        {shown && (
          <div className="flex items-center gap-1 font-mono text-xs">
            <Button asChild variant="ghost" size="sm"><Link href={href(format, shift(shown, -1))}><ArrowLeftIcon />Previous day</Link></Button>
            <span className="px-2 tnum">{isToday ? `Today · ${shown}` : shown}</span>
            {!isToday && <Button asChild variant="ghost" size="sm"><Link href={href(format, board && shift(shown, 1) < board.today ? shift(shown, 1) : undefined)}>Next day<ArrowRightIcon /></Link></Button>}
          </div>
        )}
      </div>

      {error && <p className="border-l-2 border-signal pl-3 text-sm">{error}</p>}
      {!board && !error && <p className="font-mono text-xs text-muted-foreground">Loading the table…</p>}

      {board && (
        <>
          {board.you && draft && <YourEntry you={board.you} total={board.total} draftId={draft} onSaved={load} />}
          {isToday && !board.you && (
            <div className="flex flex-wrap items-center justify-between gap-3 border bg-card p-4">
              <p className="text-sm">{board.total ? `${board.total} played today. Your spins are waiting.` : "Nobody has played today's challenge yet. Be first on the table."}</p>
              <Button asChild><Link href={`/xi/${format}/draft?daily=1`}><CalendarDotIcon />Play today&apos;s {XI_COPY[format].title}</Link></Button>
            </div>
          )}
          {(board.rows.length > 0 || !isToday) && <Table rows={board.rows} />}
          {board.total > board.rows.length && (
            <p className="font-mono text-[11px] text-muted-foreground">Top {board.rows.length} of {board.total}.</p>
          )}
        </>
      )}
    </div>
  );
}

function Table({ rows }: { rows: BoardRow[] }) {
  if (!rows.length) return <p className="border-y py-8 text-center text-sm text-muted-foreground">No entries for this day.</p>;
  return (
    <div className="overflow-x-auto border-y">
      <table className="w-full min-w-[30rem] font-mono text-sm tnum">
        <colgroup><col className="w-14" /><col /><col className="w-28" /><col className="w-16" /><col className="w-20" /><col className="w-20" /></colgroup>
        <thead>
          <tr className="label border-b text-left [&>th]:h-9 [&>th]:px-2 [&>th]:font-normal">
            <th>#</th><th>Player</th><th>Series</th><th className="text-right">Pts</th><th className="text-right">Runs ±</th><th />
          </tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((r, i) => (
            <tr key={`${r.slug}-${i}`} className={cn("[&>td]:px-2 [&>td]:py-2", r.you && "bg-signal/10")}>
              <td className={cn("font-display text-xl font-black", r.rank <= 3 ? "text-signal" : "text-muted-foreground")}>{r.rank}</td>
              <td className="truncate font-sans font-medium">
                {r.name ?? <span className="text-muted-foreground">Anonymous</span>}
                {r.you && <span className="ml-2 bg-signal px-1.5 py-0.5 font-mono text-[9px] text-signal-foreground uppercase">you</span>}
              </td>
              <td>{recordText(r)}</td>
              <td className="text-right font-semibold">{r.points}</td>
              <td className={cn("text-right", r.run_diff < 0 && "text-muted-foreground")}>{signed(r.run_diff)}</td>
              <td className="text-right"><Link href={`/xi/c/${r.slug}`} className="text-xs text-muted-foreground hover:text-signal">XI →</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Where you stand, and a box to put your name on it. */
export function YourEntry({ you, total, draftId, onSaved, link }: {
  you: BoardRow; total: number; draftId: string; onSaved?: () => void; link?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-3 border-l-2 border-signal bg-card p-4">
      <div>
        <div className="label">Your rank today</div>
        <div className="font-display text-4xl font-black tnum">#{you.rank} <span className="text-base font-bold text-muted-foreground">of {total}</span></div>
      </div>
      <NameForm draftId={draftId} current={you.name} onSaved={onSaved} />
      {link && <Button asChild variant="outline" className="ml-auto"><Link href={link}>Full table<ArrowRightIcon /></Link></Button>}
    </div>
  );
}

function NameForm({ draftId, current, onSaved }: { draftId: string; current: string | null; onSaved?: () => void }) {
  const [name, setName] = useState(current ?? "");
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");
  const [error, setError] = useState<string | null>(null);
  useEffect(() => setName(current ?? ""), [current]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setState("saving");
    setError(null);
    try {
      await xiApi.nameEntry(draftId, name.trim());
      setState("saved");
      onSaved?.();
    } catch (err) {
      setState("idle");
      setError(err instanceof Error && !/^API|^\[/.test(err.message) ? err.message : "Use 2–20 letters, numbers, spaces, dots, dashes or underscores.");
    }
  }

  return (
    <form onSubmit={save} className="min-w-0 flex-1 space-y-1">
      <label htmlFor="entry-name" className="label">{current ? "Your name on the table" : "Put your name on the table"}</label>
      <div className="flex max-w-sm gap-2">
        <Input id="entry-name" value={name} maxLength={20} placeholder="Nickname" autoComplete="nickname"
          onChange={(e) => { setName(e.target.value); setState("idle"); }} className="h-9" />
        <Button type="submit" disabled={state === "saving" || name.trim().length < 2 || name.trim() === current} className="h-9">
          {state === "saved" ? <><CheckIcon />Saved</> : "Save"}
        </Button>
      </div>
      {error && <p className="text-xs text-signal">{error}</p>}
    </form>
  );
}
