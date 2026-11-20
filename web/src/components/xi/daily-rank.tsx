"use client";

import { TrophyIcon } from "@phosphor-icons/react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { YourEntry } from "@/components/xi/leaderboard";
import { dailyDraft, xiApi, type Leaderboard, type XIFormat } from "@/lib/xi";

/** On a daily series: your place on that day's table if this browser played it,
 * else a link to the table. */
export function DailyRank({ format, day, slug }: { format: XIFormat; day: string; slug: string }) {
  const [board, setBoard] = useState<Leaderboard | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const link = `/xi/leaderboard?format=${format}&day=${day}`;

  const load = useCallback(async () => {
    const mine = dailyDraft(format, day);
    setDraft(mine);
    if (!mine) return;
    try { setBoard(await xiApi.leaderboard(format, { day, draft: mine })); } catch { /* the link still works */ }
  }, [format, day]);
  useEffect(() => { load(); }, [load]);

  if (board?.you && draft && board.you.slug === slug) {
    return <YourEntry you={board.you} total={board.total} draftId={draft} onSaved={load} link={link} />;
  }
  return (
    <Button asChild variant="outline"><Link href={link}><TrophyIcon />The daily leaderboard for {day}</Link></Button>
  );
}
