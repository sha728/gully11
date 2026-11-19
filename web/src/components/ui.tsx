import Link from "next/link";
import { FORMAT_LABEL, type Format } from "@/lib/api";

export function Card({ title, aside, children, className = "" }: {
  title?: string; aside?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <section className={`rounded-xl border border-border bg-surface ${className}`}>
      {title && (
        <div className="flex items-baseline justify-between gap-3 border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold">{title}</h2>
          {aside && <div className="text-xs text-muted">{aside}</div>}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className="num mt-0.5 text-2xl font-semibold tracking-tight">{value}</div>
      {hint && <div className="mt-0.5 text-xs text-muted">{hint}</div>}
    </div>
  );
}

export function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-border bg-surface-2 px-2.5 py-0.5 text-xs text-muted">
      {children}
    </span>
  );
}

/** Format switcher as plain links, so every tab is a crawlable URL. */
export function FormatTabs({ formats, active, hrefFor }: {
  formats: Format[]; active?: Format; hrefFor: (f: Format) => string;
}) {
  return (
    <nav className="flex flex-wrap gap-1 rounded-lg border border-border bg-surface p-1" aria-label="Format">
      {formats.map((f) => (
        <Link
          key={f}
          href={hrefFor(f)}
          scroll={false}
          aria-current={f === active ? "page" : undefined}
          className={`rounded-md px-3 py-1.5 text-sm ${f === active
            ? "bg-accent font-medium text-accent-text" : "text-muted hover:bg-surface-2 hover:text-text"}`}
        >
          {FORMAT_LABEL[f]}
        </Link>
      ))}
    </nav>
  );
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="py-6 text-center text-sm text-muted">{children}</p>;
}
