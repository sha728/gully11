import type { Metadata } from "next";
import Link from "next/link";
import { Nothing, PageHeader } from "@/components/blocks";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, fmt, type VenueSummary } from "@/lib/api";

export const metadata: Metadata = { title: "Grounds" };

export default async function VenuesPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q: raw } = await searchParams;
  const q = raw && raw.trim().length >= 2 ? raw.trim() : undefined;
  const venues = await api<VenueSummary[]>("/venues", { q, limit: 60 });
  const max = Math.max(1, ...venues.map((v) => v.matches));

  return (
    <div>
      <PageHeader
        kicker={q ? `${venues.length} grounds` : "Most-played grounds first"}
        title={q ? <>“{q}”</> : "Grounds"}
        sub="Scoring levels, chasing records and who has made each ground their own."
      />
      <form action="/venues" className="mb-8 flex max-w-md gap-2">
        <Input name="q" defaultValue={q} placeholder="Ground or city" className="h-10" />
        <Button type="submit" className="h-10 px-5">Search</Button>
      </form>

      {venues.length === 0 ? (
        <Nothing title="No grounds match">Try the city instead.</Nothing>
      ) : (
        <ol className="grid gap-x-10 border-t sm:grid-cols-2 lg:grid-cols-3">
          {venues.map((v, i) => (
            <li key={v.id} className="border-b">
              <Link href={`/venues/${v.id}`} className="group flex items-center gap-4 py-3">
                <span className="w-7 font-display text-2xl font-bold text-muted-foreground/60 tnum">{i + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium group-hover:text-signal">{v.name}</span>
                  <span className="mt-1 flex items-center gap-2">
                    <span className="h-1 bg-signal/70" style={{ width: `${Math.max(4, (60 * v.matches) / max)}%` }} />
                    <span className="label normal-case tracking-normal">{v.city ?? "—"}</span>
                  </span>
                </span>
                <span className="font-mono text-sm tnum">{fmt(v.matches)}</span>
              </Link>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
