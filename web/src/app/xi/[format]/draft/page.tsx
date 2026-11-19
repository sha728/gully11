import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { DraftBoard } from "@/components/xi/draft-board";
import { NotFound } from "@/lib/api";
import { XI_FORMATS, xiApi, type Challenge, type SpinSet, type XIFormat } from "@/lib/xi";

export const metadata: Metadata = { title: "Draft your XI" };

type Props = {
  params: Promise<{ format: string }>;
  searchParams: Promise<{ seed?: string; daily?: string; vs?: string }>;
};

export default async function DraftPage({ params, searchParams }: Props) {
  const { format: raw } = await params;
  const sp = await searchParams;
  if (!XI_FORMATS.includes(raw as XIFormat)) notFound();
  const format = raw as XIFormat;

  let set: SpinSet;
  if (sp.daily) {
    set = await xiApi.daily(format);
  } else if (sp.seed && /^\d+$/.test(sp.seed) && Number(sp.seed) < 2 ** 32) {
    set = await xiApi.spin(format, Number(sp.seed));
  } else {
    // A random draw gets its seed in the URL, so it can be shared or replayed.
    redirect(`/xi/${format}/draft?seed=${Math.floor(Math.random() * 2 ** 32)}`);
  }

  // Playing someone's shared challenge: show their result as the target.
  let rival: Challenge | null = null;
  if (sp.vs) {
    try {
      const c = await xiApi.challenge(sp.vs);
      if (c.format === format && c.seed === set.seed) rival = c;
    } catch (e) {
      if (!(e instanceof NotFound)) throw e;
    }
  }

  return <DraftBoard set={set} daily={!!sp.daily} rival={rival} />;
}
