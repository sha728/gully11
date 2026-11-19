import Link from "next/link";
import SearchBox from "@/components/SearchBox";
import { api, displayName, fmt, type SearchResult, type VenueSummary } from "@/lib/api";

export default async function Home() {
  const [ipl, tests, venues] = await Promise.all([
    api<SearchResult>("/players", { format: "IPL", limit: 6 }),
    api<SearchResult>("/players", { format: "Test", limit: 6 }),
    api<VenueSummary[]>("/venues", { limit: 6 }),
  ]);

  return (
    <div className="space-y-12">
      <section className="py-6">
        <h1 className="max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">
          Every modern player, every format, ball by ball.
        </h1>
        <p className="mt-3 max-w-xl text-muted">
          Career and season stats, powerplay-to-death splits, head-to-head comparisons and
          venue records for Tests, ODIs, T20Is and the IPL.
        </p>
        <div className="mt-6 max-w-xl">
          <SearchBox size="lg" autoFocus placeholder="Try “Kohli”, “Rashid” or “Wankhede”" />
        </div>
      </section>

      <div className="grid gap-8 md:grid-cols-3">
        <Shortlist title="Most-capped in the IPL" href="/players?format=IPL"
          rows={ipl.items.map((p) => ({ href: `/players/${p.id}`, label: displayName(p),
            value: `${fmt(p.runs)} runs · ${fmt(p.wickets)} wkts` }))} />
        <Shortlist title="Most Tests (since 2001)" href="/players?format=Test"
          rows={tests.items.map((p) => ({ href: `/players/${p.id}`, label: displayName(p),
            value: `${fmt(p.format_matches)} Tests` }))} />
        <Shortlist title="Busiest venues" href="/venues"
          rows={venues.map((v) => ({ href: `/venues/${v.id}`, label: v.name,
            value: `${fmt(v.matches)} matches` }))} />
      </div>

      <section className="rounded-xl border border-border bg-surface p-6">
        <h2 className="font-semibold">Settle an argument</h2>
        <p className="mt-1 text-sm text-muted">
          Put any two players side by side in one format, with percentile ranks against everyone
          who has faced or bowled 500+ balls.
        </p>
        <Link href="/compare" className="mt-4 inline-block rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-text">
          Compare players
        </Link>
      </section>
    </div>
  );
}

function Shortlist({ title, href, rows }: {
  title: string; href: string; rows: { href: string; label: string; value: string }[];
}) {
  return (
    <section>
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold">{title}</h2>
        <Link href={href} className="text-xs text-accent">See all</Link>
      </div>
      <ul className="divide-y divide-border rounded-xl border border-border bg-surface">
        {rows.map((r) => (
          <li key={r.href}>
            <Link href={r.href} className="flex items-baseline justify-between gap-3 px-4 py-2.5 text-sm hover:bg-surface-2">
              <span className="font-medium">{r.label}</span>
              <span className="num text-xs text-muted">{r.value}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
