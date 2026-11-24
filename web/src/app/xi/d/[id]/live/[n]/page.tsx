import type { Metadata } from "next";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { Nothing } from "@/components/blocks";
import { CaptainMatch } from "@/components/xi/captain-match";
import { NotFound } from "@/lib/api";
import { XI_COPY, xiApi, type DraftView, type LiveMatch } from "@/lib/xi";

export const metadata: Metadata = { title: "Captain your XI — XI Builder" };

type Props = { params: Promise<{ id: string; n: string }> };

export default async function CaptainPage({ params }: Props) {
  const { id, n: raw } = await params;
  const n = Number(raw);
  if (!Number.isInteger(n) || n < 1 || n > 5) notFound();
  let draft: DraftView;
  try {
    draft = await xiApi.draft(id);
  } catch (e) {
    if (e instanceof NotFound) notFound();
    throw e;
  }
  if (draft.challenge) redirect(`/xi/c/${draft.challenge}`);

  let live: LiveMatch;
  try {
    live = await xiApi.live(id, n);
  } catch (e) {
    if (e instanceof NotFound) notFound();
    const message = e instanceof Error ? e.message : "Couldn’t load this match.";
    return (
      <Nothing title="Not yet">
        {message} <Link href={`/xi/d/${id}${n > 1 ? `/live/${n - 1}` : ""}`} className="underline">Go back</Link>
      </Nothing>
    );
  }

  return (
    <div>
      <Link href={`/xi/d/${id}`} className="label hover:text-foreground">← Your XI · {XI_COPY[draft.format].title}</Link>
      <CaptainMatch draftId={id} format={draft.format} initial={live} />
    </div>
  );
}
