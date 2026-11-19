import { CalendarDotIcon, ShuffleIcon } from "@phosphor-icons/react/ssr";
import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader, Section } from "@/components/blocks";
import { Button } from "@/components/ui/button";
import { XI_COPY, XI_FORMATS } from "@/lib/xi";

export const metadata: Metadata = {
  title: "XI Builder",
  description: "Spin for an era and a nation, draft an XI, then play five matches against the Greats.",
};

const STEPS = [
  ["Spin", "Hit spin eleven times. Each lands on a decade and a nation, or an IPL franchise and era."],
  ["Draft", "Take one player per spin and set the batting order: openers at the top, the keeper in the top six, spinners and all-rounders at 7–8, bowlers at the tail."],
  ["Play", "Watch five matches against the Greats, ball by ball, on the same engine as the rest of the site."],
] as const;

export default function XIPage() {
  return (
    <div className="space-y-14">
      <PageHeader
        kicker="XI Builder · same spins for everyone each day"
        title={<>Take on <span className="text-signal">the Greats.</span></>}
        sub="Draft across eras: 1990s Pakistan for one slot, 2010s Australia for the next. Legends from before 2001 come from their career records."
      />

      <ol className="grid gap-px border-y bg-border sm:grid-cols-3">
        {STEPS.map(([t, d], i) => (
          <li key={t} className="bg-background py-5 pr-4 sm:px-5 sm:first:pl-0">
            <div className="font-display text-5xl leading-none font-black text-signal tnum">{i + 1}</div>
            <div className="mt-2 font-mono text-xs font-semibold tracking-[0.12em] uppercase">{t}</div>
            <p className="mt-1.5 text-sm text-muted-foreground">{d}</p>
          </li>
        ))}
      </ol>

      <Section n={1} title="Pick a format">
        <div className="grid gap-px border bg-border md:grid-cols-2">
          {XI_FORMATS.map((f) => (
            <div key={f} className="flex flex-col justify-between gap-6 bg-card p-6">
              <div>
                <div className="flex items-baseline justify-between">
                  <h2 className="font-display text-5xl font-black uppercase">{XI_COPY[f].title}</h2>
                  <span className="label">draws by {XI_COPY[f].unit}</span>
                </div>
                <p className="mt-2 max-w-sm text-sm text-muted-foreground">{XI_COPY[f].blurb}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button asChild size="lg">
                  <Link href={`/xi/${f}/draft?daily=1`}><CalendarDotIcon />Today&apos;s challenge</Link>
                </Button>
                <Button asChild size="lg" variant="outline">
                  <Link href={`/xi/${f}/draft`}><ShuffleIcon />Random draw</Link>
                </Button>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <p className="font-mono text-[11px] text-muted-foreground">
        Tests run on a beta engine: two innings each, declarations, follow-on and weather. Legends&apos;
        strike rates are estimated where none was recorded.
      </p>
    </div>
  );
}
