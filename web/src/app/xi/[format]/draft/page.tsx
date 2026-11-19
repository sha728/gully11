import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { StartDraft } from "@/components/xi/start-draft";
import { XI_FORMATS, type XIFormat } from "@/lib/xi";

export const metadata: Metadata = { title: "Draft your XI" };

type Props = {
  params: Promise<{ format: string }>;
  searchParams: Promise<{ seed?: string; daily?: string; vs?: string }>;
};

/** Starts a draft and moves to its own URL (/xi/d/{id}), so a reload keeps your
 * picks. Created from the browser, never during render, so prefetches can't. */
export default async function DraftPage({ params, searchParams }: Props) {
  const { format: raw } = await params;
  const sp = await searchParams;
  if (!XI_FORMATS.includes(raw as XIFormat)) notFound();
  const seed = sp.seed && /^\d+$/.test(sp.seed) && Number(sp.seed) < 2 ** 32 ? Number(sp.seed) : undefined;
  return <StartDraft format={raw as XIFormat} seed={seed} daily={!!sp.daily} vs={sp.vs} />;
}
