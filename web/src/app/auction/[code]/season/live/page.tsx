import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SeasonLiveMatch } from "@/components/auction/season-live";

type Props = { params: Promise<{ code: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return { title: `Your over · room ${(await params).code.toUpperCase()}` };
}

export default async function SeasonLivePage({ params }: Props) {
  const { code } = await params;
  if (!/^[A-Za-z]{6}$/.test(code)) notFound();
  return <SeasonLiveMatch code={code.toUpperCase()} />;
}
