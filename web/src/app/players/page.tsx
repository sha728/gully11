import type { Metadata } from "next";
import Link from "next/link";
import { Card, Empty } from "@/components/ui";
import { api, displayName, fmt, FORMAT_LABEL, FORMATS, ROLE_LABEL, type Format, type Role, type SearchResult } from "@/lib/api";

export const metadata: Metadata = { title: "Players" };

type SP = Promise<{ q?: string; format?: string; role?: string; country?: string; page?: string }>;
const PAGE = 25;

export default async function PlayersPage({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const format = FORMATS.includes(sp.format as Format) ? (sp.format as Format) : undefined;
  const role = ["BAT", "BOWL", "AR", "WK"].includes(sp.role ?? "") ? (sp.role as Role) : undefined;
  const page = Math.max(1, Number(sp.page) || 1);
  const q = sp.q && sp.q.trim().length >= 2 ? sp.q.trim() : undefined;
  const res = await api<SearchResult>("/players", {
    q, format, role, country: sp.country, limit: PAGE, offset: (page - 1) * PAGE,
  });
  const pages = Math.ceil(res.total / PAGE);
  const link = (p: number) => {
    const u = new URLSearchParams();
    if (q) u.set("q", q);
    if (format) u.set("format", format);
    if (role) u.set("role", role);
    if (sp.country) u.set("country", sp.country);
    u.set("page", String(p));
    return `/players?${u}`;
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight">
        {q ? <>Players matching “{q}”</> : "Players"}
      </h1>

      {/* Plain GET form: works without JavaScript and keeps every filter in the URL. */}
      <form className="flex flex-wrap items-end gap-3 text-sm" action="/players">
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Name</span>
          <input name="q" defaultValue={q} placeholder="Any" className="w-48 rounded-lg border border-border bg-surface px-3 py-2" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Format</span>
          <select name="format" defaultValue={format ?? ""} className="rounded-lg border border-border bg-surface px-3 py-2">
            <option value="">Any</option>
            {FORMATS.map((f) => <option key={f} value={f}>{FORMAT_LABEL[f]}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Role</span>
          <select name="role" defaultValue={role ?? ""} className="rounded-lg border border-border bg-surface px-3 py-2">
            <option value="">Any</option>
            {(Object.keys(ROLE_LABEL) as Role[]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">Country</span>
          <input name="country" defaultValue={sp.country} placeholder="Any" className="w-36 rounded-lg border border-border bg-surface px-3 py-2" />
        </label>
        <button className="rounded-lg bg-accent px-4 py-2 font-medium text-accent-text">Search</button>
      </form>

      <Card title={`${fmt(res.total)} players`} aside={format ? `${FORMAT_LABEL[format]} figures` : "Matches across all formats"}>
        {res.items.length === 0 ? (
          <Empty>No players match. Try fewer filters or a different spelling.</Empty>
        ) : (
          <div className="-mx-4 overflow-x-auto">
            <table className="stats">
              <thead>
                <tr>
                  <th>Player</th><th>Country</th><th>Role</th><th>Years</th><th>Mat</th>
                  {format && <><th>Runs</th><th>Avg</th><th>SR</th><th>Wkts</th><th>Econ</th></>}
                </tr>
              </thead>
              <tbody>
                {res.items.map((p) => (
                  <tr key={p.id}>
                    <td><Link href={`/players/${p.id}${format ? `?format=${format}` : ""}`} className="font-medium hover:text-accent">{displayName(p)}</Link></td>
                    <td className="text-muted">{p.country ?? "–"}</td>
                    <td className="text-muted">{ROLE_LABEL[p.role]}</td>
                    <td className="text-muted">{p.era_start}–{p.era_end}</td>
                    <td>{fmt(format ? p.format_matches : p.matches)}</td>
                    {format && <>
                      <td>{fmt(p.runs)}</td><td>{fmt(p.bat_avg, 2)}</td><td>{fmt(p.bat_sr, 1)}</td>
                      <td>{fmt(p.wickets)}</td><td>{fmt(p.bowl_econ, 2)}</td>
                    </>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && (
          <div className="mt-4 flex items-center justify-between text-sm">
            {page > 1 ? <Link href={link(page - 1)} className="text-accent">← Previous</Link> : <span />}
            <span className="text-muted">Page {page} of {fmt(pages)}</span>
            {page < pages ? <Link href={link(page + 1)} className="text-accent">Next →</Link> : <span />}
          </div>
        )}
      </Card>
    </div>
  );
}
