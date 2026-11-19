import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { DraftBoard } from "@/components/xi/draft-board";
import { NotFound } from "@/lib/api";
import { xiApi, type Challenge, type DraftView } from "@/lib/xi";

export const metadata: Metadata = { title: "Draft your XI" };

type Props = { params: Promise<{ id: string }> };

export default async function DraftByIdPage({ params }: Props) {
  const { id } = await params;
  let draft: DraftView;
  try {
    draft = await xiApi.draft(id);
  } catch (e) {
    if (e instanceof NotFound) notFound();
    throw e;
  }
  if (draft.challenge) redirect(`/xi/c/${draft.challenge}${draft.rival ? `?vs=${draft.rival}` : ""}`);

  // Chasing someone's challenge: show their result as the target.
  let rival: Challenge | null = null;
  if (draft.rival) {
    try {
      rival = await xiApi.challenge(draft.rival);
    } catch (e) {
      if (!(e instanceof NotFound)) throw e;
    }
  }
  return <DraftBoard initial={draft} rival={rival} />;
}
