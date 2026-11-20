import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { SeasonMatch } from "@/components/auction/season-match";

type Props = { params: Promise<{ code: string; n: string }>; searchParams: Promise<{ live?: string }> };

export const metadata: Metadata = { title: "Season match" };

export default async function SeasonMatchPage({ params, searchParams }: Props) {
  const { code, n } = await params;
  const num = Number(n);
  if (!/^[A-Za-z]{6}$/.test(code) || !Number.isInteger(num) || num < 1) notFound();
  return <SeasonMatch code={code.toUpperCase()} n={num} live={!!(await searchParams).live} />;
}
