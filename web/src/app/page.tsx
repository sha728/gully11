import { ArrowRightIcon, ArrowUpRightIcon } from "@phosphor-icons/react/ssr";
import Link from "next/link";
import { Section } from "@/components/blocks";
import { SearchTrigger } from "@/components/search-palette";
import { api, displayName, fmt, type PlayerSummary, type SearchResult, type VenueSummary } from "@/lib/api";

// A few fixed starting points; ids are Cricsheet register ids.
const QUICK = [
  { href: "/players/ba607b88", label: "Virat Kohli" },
  { href: "/players/462411b3", label: "Jasprit Bumrah" },
  { href: "/players/5f547c8b?format=IPL", label: "Rashid Khan" },
  { href: "/venues/wankhede-stadium", label: "Wankhede" },
  { href: "/venues/lord-s", label: "Lord’s" },
];
const MATCHUPS = [
  { href: "/compare?a=ba607b88&b=30a45b23&format=Test", a: "Kohli", b: "Smith", f: "Tests" },
  { href: "/compare?a=a343262c&b=d027ba9f&format=Test", a: "Root", b: "Williamson", f: "Tests" },
  { href: "/compare?a=462411b3&b=5f547c8b&format=IPL", a: "Bumrah", b: "Rashid", f: "IPL" },
  { href: "/compare?a=ba607b88&b=740742ef&format=IPL", a: "Kohli", b: "Rohit", f: "IPL" },
];

export default async function Home() {
  const [iplRuns, iplWkts, testRuns, testWkts, grounds] = await Promise.all([
    api<SearchResult>("/players", { format: "IPL", sort: "runs", limit: 5 }),
    api<SearchResult>("/players", { format: "IPL", sort: "wickets", limit: 5 }),
    api<SearchResult>("/players", { format: "Test", sort: "runs", limit: 5 }),
    api<SearchResult>("/players", { format: "Test", sort: "wickets", limit: 5 }),
    api<VenueSummary[]>("/venues", { limit: 6 }),
  ]);
  const top = iplRuns.items[0];
  const ticker = [
    ...iplRuns.items.map((p) => `IPL runs · ${displayName(p)} ${fmt(p.runs)}`),
    ...iplWkts.items.map((p) => `IPL wickets · ${displayName(p)} ${fmt(p.wickets)}`),
    ...testRuns.items.map((p) => `Test runs since 2001 · ${displayName(p)} ${fmt(p.runs)}`),
    ...testWkts.items.map((p) => `Test wickets since 2001 · ${displayName(p)} ${fmt(p.wickets)}`),
  ];

  return (
    <div className="space-y-16">
      {/* Hero */}
      <section className="-mt-8 grid gap-10 pt-10 lg:grid-cols-[1.25fr_1fr] lg:items-end">
        <div>
          <div className="label mb-4">Men&apos;s cricket · Tests since 2001 · every IPL ball</div>
          <h1 className="font-display text-[clamp(3.5rem,11vw,8.5rem)] leading-[0.82] font-black tracking-tight uppercase">
            Every ball.<br />
            <span className="text-signal">Look it up.</span>
          </h1>
          <p className="mt-6 max-w-lg text-base text-muted-foreground">
            Careers, seasons, powerplay-to-death splits and ground records, built from
            ten million deliveries. No opinions, just the scorebook.
          </p>
          <div className="mt-8 max-w-xl">
            <SearchTrigger size="lg" />
          </div>
          <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 font-mono text-xs">
            <span className="text-muted-foreground">Try</span>
            {QUICK.map((q) => (
              <Link key={q.href} href={q.href} className="underline decoration-signal/50 underline-offset-4 hover:decoration-signal">
                {q.label}
              </Link>
            ))}
          </div>
        </div>

        {/* Ground scoreboard: always dark, like the one at the ground */}
        <Link href={`/players/${top.id}?format=IPL`}
          className="group relative block overflow-hidden bg-[oklch(0.17_0.01_150)] p-6 text-[oklch(0.93_0.012_85)] ring-1 ring-black/10">
          <div className="flex items-center justify-between font-mono text-[11px] tracking-widest uppercase opacity-70">
            <span>IPL · most runs</span>
            <span className="flex items-center gap-1.5"><span className="size-1.5 animate-pulse rounded-full bg-[oklch(0.67_0.19_27)]" />2008–2026</span>
          </div>
          <div className="mt-6 font-display text-[clamp(4.5rem,10vw,7.5rem)] leading-none font-black text-[oklch(0.67_0.19_27)] tnum">
            {fmt(top.runs)}
          </div>
          <div className="mt-2 font-display text-3xl font-bold uppercase">{displayName(top)}</div>
          <div className="mt-6 grid grid-cols-3 gap-px bg-white/10 font-mono text-xs">
            {[["Mat", fmt(top.format_matches)], ["Avg", fmt(top.bat_avg, 2)], ["SR", fmt(top.bat_sr, 1)]].map(([k, v]) => (
              <div key={k} className="bg-[oklch(0.17_0.01_150)] py-2">
                <div className="opacity-60">{k}</div>
                <div className="mt-0.5 text-lg tnum">{v}</div>
              </div>
            ))}
          </div>
          <div className="mt-5 space-y-1.5 font-mono text-xs">
            {iplRuns.items.slice(1, 5).map((p, i) => (
              <div key={p.id} className="flex items-baseline gap-3 opacity-80">
                <span className="w-4 opacity-50 tnum">{i + 2}</span>
                <span className="flex-1 truncate">{displayName(p)}</span>
                <span className="tnum">{fmt(p.runs)}</span>
              </div>
            ))}
          </div>
          <ArrowUpRightIcon className="absolute top-6 right-6 size-5 opacity-0 transition-opacity group-hover:opacity-70" />
        </Link>
      </section>

      {/* Ticker */}
      <div className="-mx-4 overflow-hidden border-y bg-card py-2.5 sm:-mx-6" aria-label="Leaders">
        <div className="ticker-track flex w-max gap-10 font-mono text-xs whitespace-nowrap">
          {[...ticker, ...ticker].map((t, i) => (
            <span key={i} className="flex items-center gap-10">
              <span>{t}</span><span className="text-signal">●</span>
            </span>
          ))}
        </div>
      </div>

      {/* Leaderboards */}
      <div className="grid gap-12 md:grid-cols-2 xl:grid-cols-4">
        <Leaders n={1} title="IPL wickets" rows={iplWkts.items} value={(p) => fmt(p.wickets)} unit="wkts" format="IPL" more="/players?format=IPL" />
        <Leaders n={2} title="Test runs" rows={testRuns.items} value={(p) => fmt(p.runs)} unit="runs" format="Test" more="/players?format=Test" />
        <Leaders n={3} title="Test wickets" rows={testWkts.items} value={(p) => fmt(p.wickets)} unit="wkts" format="Test" more="/players?format=Test" />
        <Section n={4} title="Busiest grounds">
          <ol className="divide-y border-y">
            {grounds.slice(0, 5).map((v, i) => (
              <li key={v.id}>
                <Link href={`/venues/${v.id}`} className="group flex items-baseline gap-3 py-2.5">
                  <span className="w-5 font-display text-xl font-bold text-muted-foreground tnum">{i + 1}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium group-hover:text-signal">{v.name}</span>
                    <span className="label normal-case tracking-normal">{v.city}</span>
                  </span>
                  <span className="font-mono text-sm tnum">{fmt(v.matches)}</span>
                </Link>
              </li>
            ))}
          </ol>
          <Link href="/venues" className="mt-3 inline-flex items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground">
            All grounds <ArrowRightIcon className="size-3" />
          </Link>
        </Section>
      </div>

      {/* Head-to-head band */}
      <section className="relative -mx-4 overflow-hidden bg-signal px-4 py-10 text-signal-foreground sm:-mx-6 sm:px-6">
        <div className="grid gap-8 lg:grid-cols-[1fr_1.4fr] lg:items-center">
          <div>
            <div className="font-mono text-xs tracking-widest uppercase opacity-80">Head to head</div>
            <h2 className="mt-2 font-display text-6xl leading-[0.85] font-black uppercase sm:text-7xl">Settle it.</h2>
            <p className="mt-3 max-w-sm text-sm opacity-90">
              Any two players, one format, any span of years, ranked against everyone with 500+ balls.
            </p>
          </div>
          <div className="grid gap-px bg-signal-foreground/20 sm:grid-cols-2">
            {MATCHUPS.map((m) => (
              <Link key={m.href} href={m.href} className="group flex items-center justify-between bg-signal px-4 py-4 hover:bg-[color-mix(in_oklch,var(--signal),black_12%)]">
                <span className="font-display text-2xl font-extrabold whitespace-nowrap uppercase xl:text-3xl">
                  {m.a} <span className="opacity-60">v</span> {m.b}
                </span>
                <span className="flex items-center gap-2 font-mono text-[11px] uppercase opacity-80">
                  {m.f}<ArrowRightIcon className="size-3.5 transition-transform group-hover:translate-x-0.5" />
                </span>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function Leaders({ n, title, rows, value, unit, format, more }: {
  n: number; title: string; rows: PlayerSummary[]; value: (p: PlayerSummary) => string;
  unit: string; format: string; more: string;
}) {
  return (
    <Section n={n} title={title}>
      <ol className="divide-y border-y">
        {rows.map((p, i) => (
          <li key={p.id}>
            <Link href={`/players/${p.id}?format=${format}`} className="group flex items-baseline gap-3 py-2.5">
              <span className="w-5 font-display text-xl font-bold text-muted-foreground tnum">{i + 1}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium group-hover:text-signal">{displayName(p)}</span>
                <span className="label normal-case tracking-normal">{p.country ?? "—"}</span>
              </span>
              <span className="font-mono text-sm tnum">{value(p)}<span className="ml-1 text-[10px] text-muted-foreground">{unit}</span></span>
            </Link>
          </li>
        ))}
      </ol>
      <Link href={more} className="mt-3 inline-flex items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground">
        Everyone <ArrowRightIcon className="size-3" />
      </Link>
    </Section>
  );
}
