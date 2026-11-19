import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { AuctionRoom } from "@/components/auction/auction-room";

type Props = { params: Promise<{ code: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  return { title: `Auction room ${(await params).code.toUpperCase()}` };
}

/** The room runs in the browser over a WebSocket; nothing to render on the server. */
export default async function AuctionRoomPage({ params }: Props) {
  const { code } = await params;
  if (!/^[A-Za-z]{6}$/.test(code)) notFound();
  return <AuctionRoom code={code.toUpperCase()} />;
}
