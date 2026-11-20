import type { Metadata } from "next";
import { PageHeader } from "@/components/blocks";
import { LeaderboardView } from "@/components/xi/leaderboard";
import { XI_FORMATS, type XIFormat } from "@/lib/xi";

export const metadata: Metadata = {
  title: "Daily leaderboard — XI Builder",
  description: "Everyone gets the same eleven spins each day. Who drafted the XI that did best against the Greats?",
};

type Props = { searchParams: Promise<{ format?: string; day?: string }> };

export default async function LeaderboardPage({ searchParams }: Props) {
  const sp = await searchParams;
  const format: XIFormat = (XI_FORMATS as readonly string[]).includes(sp.format ?? "") ? (sp.format as XIFormat) : "IPL";
  const day = /^\d{4}-\d{2}-\d{2}$/.test(sp.day ?? "") ? sp.day : undefined;
  return (
    <div className="space-y-8">
      <PageHeader
        kicker="XI Builder · daily challenge"
        title={<>Today&apos;s <span className="text-signal">table.</span></>}
        sub="Everyone drafts from the same eleven spins each day. Ranked by series points (2 a win, 1 a tie or draw), then runs scored minus conceded across the five matches."
      />
      <LeaderboardView format={format} day={day} />
    </div>
  );
}
