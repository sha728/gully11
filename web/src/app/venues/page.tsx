import type { Metadata } from "next";
import Link from "next/link";
import { Card, Empty } from "@/components/ui";
import { api, fmt, type VenueSummary } from "@/lib/api";

export const metadata: Metadata = { title: "Venues" };

export default async function VenuesPage({ searchParams }: { searchParams: Promise<{ q?: string }> }) {
  const { q: raw } = await searchParams;
  const q = raw && raw.trim().length >= 2 ? raw.trim() : undefined;
  const venues = await api<VenueSummary[]>("/venues", { q, limit: 60 });
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">{q ? <>Venues matching “{q}”</> : "Venues"}</h1>
      <form action="/venues" className="flex gap-2 text-sm">
        <input name="q" defaultValue={q} placeholder="Ground or city"
          className="w-64 rounded-lg border border-border bg-surface px-3 py-2" />
        <button className="rounded-lg bg-accent px-4 py-2 font-medium text-accent-text">Search</button>
      </form>
      <Card title={q ? `${venues.length} venues` : "Most-played venues"}>
        {venues.length === 0 ? <Empty>No venues match.</Empty> : (
          <ul className="grid gap-x-8 sm:grid-cols-2 lg:grid-cols-3">
            {venues.map((v) => (
              <li key={v.id} className="border-b border-border">
                <Link href={`/venues/${v.id}`} className="flex items-baseline justify-between gap-3 py-2.5 text-sm hover:text-accent">
                  <span><span className="font-medium">{v.name}</span>{v.city && <span className="text-muted"> · {v.city}</span>}</span>
                  <span className="num shrink-0 text-xs text-muted">{fmt(v.matches)}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
