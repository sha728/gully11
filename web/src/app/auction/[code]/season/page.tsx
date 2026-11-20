import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SeasonRoom } from "@/components/auction/season-room";

type Props = { params: Promise<{ code: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return { title: `Season · room ${(await params).code.toUpperCase()}` };
}

export default async function SeasonPage({ params }: Props) {
  const { code } = await params;
  if (!/^[A-Za-z]{6}$/.test(code)) notFound();
  return <SeasonRoom code={code.toUpperCase()} />;
}
