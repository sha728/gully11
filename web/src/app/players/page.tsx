import type { Metadata } from "next";
import Link from "next/link";
import { Nothing, PageHeader } from "@/components/blocks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Pagination, PaginationContent, PaginationItem, PaginationNext, PaginationPrevious,
} from "@/components/ui/pagination";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  api, displayName, fmt, FORMAT_LABEL, FORMATS, ROLE_LABEL, type Format, type Role, type SearchResult,
} from "@/lib/api";

export const metadata: Metadata = { title: "Players" };

type SP = Promise<{ q?: string; format?: string; role?: string; country?: string; sort?: string; page?: string }>;
const PAGE = 25;
const SORTS = { matches: "Matches", runs: "Runs", wickets: "Wickets" } as const;

export default async function PlayersPage({ searchParams }: { searchParams: SP }) {
  const sp = await searchParams;
  const format = FORMATS.includes(sp.format as Format) ? (sp.format as Format) : undefined;
  const role = ["BAT", "BOWL", "AR", "WK"].includes(sp.role ?? "") ? (sp.role as Role) : undefined;
  const sort = format && sp.sort && sp.sort in SORTS ? (sp.sort as keyof typeof SORTS) : "matches";
  const page = Math.max(1, Number(sp.page) || 1);
  const q = sp.q && sp.q.trim().length >= 2 ? sp.q.trim() : undefined;
  const res = await api<SearchResult>("/players", {
    q, format, role, country: sp.country, sort, limit: PAGE, offset: (page - 1) * PAGE,
  });
  const pages = Math.ceil(res.total / PAGE);
  const link = (p: number) => {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries({ q, format, role, country: sp.country, sort: sort === "matches" ? undefined : sort })) {
      if (v) u.set(k, v);
    }
    u.set("page", String(p));
    return `/players?${u}`;
  };

  return (
    <div>
      <PageHeader
        kicker={`${fmt(res.total)} players${format ? ` · ${FORMAT_LABEL[format]}` : ""}`}
        title={q ? <>“{q}”</> : "Players"}
        sub={format ? `Ranked by ${SORTS[sort].toLowerCase()} in ${FORMAT_LABEL[format]}.` : "Everyone with a ball bowled or faced in the records, most matches first."}
      />

      {/* Plain GET form: no JavaScript needed, every filter lives in the URL. */}
      <form action="/players" className="mb-6 grid gap-3 border bg-card p-4 sm:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr_1fr_auto] lg:items-end">
        <label className="grid gap-1.5">
          <span className="label">Name</span>
          <Input name="q" defaultValue={q} placeholder="Any" className="h-10" />
        </label>
        <label className="grid gap-1.5">
          <span className="label">Format</span>
          <Select name="format" defaultValue={format ?? "any"}>
            <SelectTrigger className="h-10 w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any format</SelectItem>
              {FORMATS.map((f) => <SelectItem key={f} value={f}>{FORMAT_LABEL[f]}</SelectItem>)}
            </SelectContent>
          </Select>
        </label>
        <label className="grid gap-1.5">
          <span className="label">Role</span>
          <Select name="role" defaultValue={role ?? "any"}>
            <SelectTrigger className="h-10 w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="any">Any role</SelectItem>
              {(Object.keys(ROLE_LABEL) as Role[]).map((r) => <SelectItem key={r} value={r}>{ROLE_LABEL[r]}</SelectItem>)}
            </SelectContent>
          </Select>
        </label>
        <label className="grid gap-1.5">
          <span className="label">Country</span>
          <Input name="country" defaultValue={sp.country} placeholder="Any" className="h-10" />
        </label>
        <label className="grid gap-1.5">
          <span className="label">Rank by</span>
          <Select name="sort" defaultValue={sort}>
            <SelectTrigger className="h-10 w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              {Object.entries(SORTS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        </label>
        <Button type="submit" className="h-10 px-5">Search</Button>
      </form>

      {res.items.length === 0 ? (
        <Nothing title="No one matches">Try fewer filters, or just a surname.</Nothing>
      ) : (
        <div className="border-y">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-10 label">#</TableHead>
                <TableHead className="label">Player</TableHead>
                <TableHead className="label">Role</TableHead>
                <TableHead className="label">Years</TableHead>
                <TableHead className="label text-right">Mat</TableHead>
                {format && <>
                  <TableHead className="label text-right">Runs</TableHead>
                  <TableHead className="label text-right">Avg</TableHead>
                  <TableHead className="label text-right">SR</TableHead>
                  <TableHead className="label text-right">Wkts</TableHead>
                  <TableHead className="label text-right">Econ</TableHead>
                </>}
              </TableRow>
            </TableHeader>
            <TableBody className="font-mono tnum">
              {res.items.map((p, i) => (
                <TableRow key={p.id}>
                  <TableCell className="text-muted-foreground">{(page - 1) * PAGE + i + 1}</TableCell>
                  <TableCell className="font-sans">
                    <Link href={`/players/${p.id}${format ? `?format=${format}` : ""}`} className="font-semibold hover:text-signal">
                      {displayName(p)}
                    </Link>
                    <span className="ml-2 text-xs text-muted-foreground">{p.country ?? ""}</span>
                  </TableCell>
                  <TableCell><Badge variant="outline" className="font-mono text-[10px] uppercase">{ROLE_LABEL[p.role]}</Badge></TableCell>
                  <TableCell className="text-muted-foreground">{p.era_start}–{p.era_end}</TableCell>
                  <TableCell className="text-right">{fmt(format ? p.format_matches : p.matches)}</TableCell>
                  {format && <>
                    <TableCell className={`text-right ${sort === "runs" ? "font-semibold text-signal" : ""}`}>{fmt(p.runs)}</TableCell>
                    <TableCell className="text-right">{fmt(p.bat_avg, 2)}</TableCell>
                    <TableCell className="text-right">{fmt(p.bat_sr, 1)}</TableCell>
                    <TableCell className={`text-right ${sort === "wickets" ? "font-semibold text-signal" : ""}`}>{fmt(p.wickets)}</TableCell>
                    <TableCell className="text-right">{fmt(p.bowl_econ, 2)}</TableCell>
                  </>}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {pages > 1 && (
        <Pagination className="mt-6">
          <PaginationContent className="w-full justify-between">
            <PaginationItem>
              {page > 1 ? <PaginationPrevious href={link(page - 1)} /> : <span />}
            </PaginationItem>
            <PaginationItem className="label">Page {page} / {fmt(pages)}</PaginationItem>
            <PaginationItem>
              {page < pages ? <PaginationNext href={link(page + 1)} /> : <span />}
            </PaginationItem>
          </PaginationContent>
        </Pagination>
      )}
    </div>
  );
}
