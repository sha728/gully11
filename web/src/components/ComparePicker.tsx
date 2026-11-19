"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import SearchBox from "@/components/SearchBox";
import { FORMAT_LABEL, FORMATS, type Format } from "@/lib/api";

type P = { id: string; name: string } | null;

export default function ComparePicker({ a, b, format, from, to }: {
  a: P; b: P; format: Format; from?: number; to?: number;
}) {
  const router = useRouter();
  const [pa, setA] = useState<P>(a);
  const [pb, setB] = useState<P>(b);
  const [f, setF] = useState<Format>(format);
  const [y0, setY0] = useState(from ? String(from) : "");
  const [y1, setY1] = useState(to ? String(to) : "");

  function push(next: { a?: P; b?: P; f?: Format; y0?: string; y1?: string }) {
    const A = next.a !== undefined ? next.a : pa;
    const B = next.b !== undefined ? next.b : pb;
    const u = new URLSearchParams({ format: next.f ?? f });
    if (A) u.set("a", A.id);
    if (B) u.set("b", B.id);
    const from_ = next.y0 ?? y0;
    const to_ = next.y1 ?? y1;
    if (/^\d{4}$/.test(from_)) u.set("from", from_);
    if (/^\d{4}$/.test(to_)) u.set("to", to_);
    router.push(`/compare?${u}`);
  }

  const slot = (label: string, p: P, set: (p: P) => void, key: "a" | "b", color: string) => (
    <div className="flex-1 min-w-56">
      <div className="mb-1 flex items-center gap-2 text-xs text-muted">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
        {label}
      </div>
      {p ? (
        <div className="flex items-center justify-between rounded-lg border border-border bg-surface px-3 py-2 text-sm">
          <span className="font-medium">{p.name}</span>
          <button type="button" onClick={() => { set(null); push({ [key]: null }); }}
            className="text-xs text-muted hover:text-text" aria-label={`Remove ${p.name}`}>Change</button>
        </div>
      ) : (
        <SearchBox placeholder="Pick a player" onPick={(x) => { set(x); push({ [key]: x }); }} />
      )}
    </div>
  );

  return (
    <div className="flex flex-wrap items-end gap-4 rounded-xl border border-border bg-surface-2 p-4">
      {slot("Player A", pa, setA, "a", "var(--a-series)")}
      {slot("Player B", pb, setB, "b", "var(--b-series)")}
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-xs text-muted">Format</span>
        <select value={f} onChange={(e) => { const v = e.target.value as Format; setF(v); push({ f: v }); }}
          className="rounded-lg border border-border bg-surface px-3 py-2">
          {FORMATS.map((x) => <option key={x} value={x}>{FORMAT_LABEL[x]}</option>)}
        </select>
      </label>
      <form className="flex items-end gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); push({}); }}>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">From year</span>
          <input value={y0} onChange={(e) => setY0(e.target.value)} inputMode="numeric" placeholder="Any"
            className="w-20 rounded-lg border border-border bg-surface px-3 py-2" />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-xs text-muted">To year</span>
          <input value={y1} onChange={(e) => setY1(e.target.value)} inputMode="numeric" placeholder="Any"
            className="w-20 rounded-lg border border-border bg-surface px-3 py-2" />
        </label>
        <button className="rounded-lg border border-border bg-surface px-3 py-2 hover:border-accent">Apply</button>
      </form>
    </div>
  );
}
