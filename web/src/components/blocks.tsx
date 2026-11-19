import Link from "next/link";
import { Empty, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { FORMAT_LABEL, type Format } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Big condensed page title with a mono kicker and the ball-seam rule underneath. */
export function PageHeader({ kicker, title, sub, actions, className }: {
  kicker?: React.ReactNode; title: React.ReactNode; sub?: React.ReactNode; actions?: React.ReactNode; className?: string;
}) {
  return (
    <div className={cn("mb-8", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
        <div className="min-w-0">
          {kicker && <div className="label mb-2">{kicker}</div>}
          <h1 className="font-display text-5xl leading-[0.9] font-extrabold tracking-tight uppercase sm:text-7xl">
            {title}
          </h1>
          {sub && <div className="mt-3 text-sm text-muted-foreground">{sub}</div>}
        </div>
        {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
      </div>
      <div className="seam mt-5" aria-hidden />
    </div>
  );
}

/** Numbered section: "01  CAREER ———— aside". */
export function Section({ n, title, aside, children, className }: {
  n?: number; title: string; aside?: React.ReactNode; children: React.ReactNode; className?: string;
}) {
  return (
    <section className={cn("min-w-0", className)}>
      <div className="mb-3 flex items-baseline gap-3">
        {n !== undefined && <span className="font-mono text-xs text-signal tnum">{String(n).padStart(2, "0")}</span>}
        <h2 className="font-mono text-xs font-semibold tracking-[0.12em] uppercase">{title}</h2>
        <span className="h-px flex-1 translate-y-[-3px] bg-border" />
        {aside && <span className="label normal-case tracking-normal">{aside}</span>}
      </div>
      {children}
    </section>
  );
}

export interface ScoreItem {
  label: string;
  value: string;
  hint?: string;
  emphasis?: boolean;
}

/** Stretch the last scoreboard cell over any empty slots in its row (2 cols on
 *  phones, 3 on tablets, one row on desktop), so no bare gap shows. */
function fillLast(n: number) {
  const phone = n % 2 === 1 ? "col-span-2" : "";
  const tablet = { 0: "sm:col-span-1", 1: "sm:col-span-3", 2: "sm:col-span-2" }[n % 3 as 0 | 1 | 2];
  return cn(phone, tablet, "lg:col-span-1");
}

/** Scoreboard strip: big condensed numbers between hairlines, no boxes. */
export function Scoreboard({ items, className }: { items: ScoreItem[]; className?: string }) {
  return (
    // 1px gaps over a border-coloured background draw the hairlines at any column count.
    <div className={cn("grid grid-cols-2 gap-px border-y bg-border sm:grid-cols-3 lg:grid-flow-col lg:auto-cols-fr lg:grid-cols-none", className)}>
      {items.map((it, i) => (
        <div key={it.label} className={cn("bg-background px-4 py-4 sm:py-5", i === items.length - 1 && fillLast(items.length))}>
          <div className="label">{it.label}</div>
          <div className={cn("mt-1 font-display text-4xl leading-none font-bold sm:text-5xl", it.emphasis && "text-signal")}>
            {it.value}
          </div>
          {it.hint && <div className="mt-1.5 font-mono text-[11px] text-muted-foreground">{it.hint}</div>}
        </div>
      ))}
    </div>
  );
}

/** Format switcher as real links (every format view has its own URL). */
export function FormatTabs({ formats, active, hrefFor, className }: {
  formats: Format[]; active?: Format; hrefFor: (f: Format) => string; className?: string;
}) {
  return (
    <nav aria-label="Format" className={cn("flex gap-0 overflow-x-auto overflow-y-hidden border-b", className)}>
      {formats.map((f) => (
        <Link key={f} href={hrefFor(f)} scroll={false} aria-current={f === active ? "page" : undefined}
          className={cn(
            "relative shrink-0 px-4 py-2.5 font-mono text-xs tracking-wider uppercase transition-colors",
            f === active ? "text-foreground" : "text-muted-foreground hover:text-foreground",
          )}>
          {FORMAT_LABEL[f]}
          {f === active && <span className="absolute inset-x-0 bottom-0 h-0.5 bg-signal" />}
        </Link>
      ))}
    </nav>
  );
}

export function Nothing({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <Empty className="border border-dashed py-10">
      <EmptyHeader>
        <EmptyTitle className="font-display text-2xl uppercase">{title}</EmptyTitle>
        {children && <EmptyDescription>{children}</EmptyDescription>}
      </EmptyHeader>
    </Empty>
  );
}

/** A thin horizontal share bar (dismissal types, percentiles). */
export function Bar({ value, max = 100, tone = "signal", className }: {
  value: number; max?: number; tone?: "signal" | "a" | "b" | "muted"; className?: string;
}) {
  const pct = Math.max(0, Math.min(100, (100 * value) / (max || 1)));
  const color = { signal: "bg-signal", a: "bg-chart-1", b: "bg-chart-2", muted: "bg-muted-foreground/50" }[tone];
  return (
    <div className={cn("h-1.5 w-full bg-muted", className)}>
      <div className={cn("h-full", color)} style={{ width: `${pct}%` }} />
    </div>
  );
}
