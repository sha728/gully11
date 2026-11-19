import type { Metadata } from "next";
import { PageHeader, Section } from "@/components/blocks";
import { CreateRoom, JoinRoom } from "@/components/auction/room-forms";

export const metadata: Metadata = {
  title: "IPL Auction",
  description: "Run an IPL mega auction with friends or against AI franchises: real purse, squad and overseas rules, live bidding.",
};

const RULES = [
  ["₹120 cr", "purse per franchise"],
  ["18–25", "players per squad"],
  ["8", "overseas players at most"],
  ["₹5–25 L", "bid steps, rising with the price"],
] as const;

export default function AuctionPage() {
  return (
    <div className="space-y-14">
      <PageHeader
        kicker="IPL Auction · mega auction or the real 2026 auction"
        title={<>Build a squad. <span className="text-signal">Outbid the room.</span></>}
        sub="Every player who has played the IPL in the last three seasons goes under the hammer, priced from their recent T20 form. Play with friends using a room code, or against AI franchises that bid by need and budget."
      />

      <dl className="grid grid-cols-2 gap-px border-y bg-border sm:grid-cols-4">
        {RULES.map(([v, l]) => (
          <div key={l} className="bg-background py-4 pr-4 sm:px-5 sm:first:pl-0">
            <dt className="sr-only">{l}</dt>
            <dd className="font-display text-4xl leading-none font-black tnum">{v}</dd>
            <dd className="mt-1.5 font-mono text-[11px] tracking-wide text-muted-foreground uppercase">{l}</dd>
          </div>
        ))}
      </dl>

      <div className="grid gap-14 lg:grid-cols-[1.3fr_1fr]">
        <Section n={1} title="Host a room">
          <CreateRoom />
        </Section>
        <Section n={2} title="Join with a code">
          <JoinRoom />
        </Section>
      </div>

      <p className="max-w-2xl font-mono text-[11px] leading-relaxed text-muted-foreground">
        IPL 2026 replay: squads, purses, sets and results from Wikipedia&apos;s record of the 16 December 2025 auction
        (CC BY-SA 4.0). Purses are ₹125 cr minus the retained salaries listed there.
      </p>
      <p className="max-w-2xl font-mono text-[11px] leading-relaxed text-muted-foreground">
        Fair prices are a stats estimate, not real auction history: recent T20 form, scored against others in the same role,
        plus IPL and international experience, scaled to the money in the room. Bots bid up to what a player is worth to them:
        more when their squad is short of that role, more when they hold a lot of money per open slot.
      </p>
    </div>
  );
}
