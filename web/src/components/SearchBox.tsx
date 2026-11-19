"use client";

import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { API_URL, displayName, ROLE_LABEL, type PlayerSummary, type VenueSummary } from "@/lib/api";

type Hit =
  | { kind: "player"; id: string; label: string; sub: string }
  | { kind: "venue"; id: string; label: string; sub: string };

/** Typeahead over players and venues. Enter with nothing selected opens full results. */
export default function SearchBox({
  autoFocus = false,
  size = "md",
  placeholder = "Search players or venues",
  onPick,
}: {
  autoFocus?: boolean;
  size?: "md" | "lg";
  placeholder?: string;
  /** If set, picking a player calls this instead of navigating (used by Compare). */
  onPick?: (p: { id: string; name: string }) => void;
}) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const listId = useId();
  const seq = useRef(0);

  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setHits([]);
      return;
    }
    const mine = ++seq.current;
    const t = setTimeout(async () => {
      try {
        const [players, venues] = await Promise.all([
          fetch(`${API_URL}/players?q=${encodeURIComponent(term)}&limit=7`).then((r) => r.json()),
          onPick
            ? Promise.resolve([])
            : fetch(`${API_URL}/venues?q=${encodeURIComponent(term)}&limit=3`).then((r) => r.json()),
        ]);
        if (mine !== seq.current) return; // a newer keystroke won
        const ph: Hit[] = (players.items as PlayerSummary[]).map((p) => ({
          kind: "player",
          id: p.id,
          label: displayName(p),
          sub: [p.full_name && p.full_name !== p.name ? p.name : null, p.country, ROLE_LABEL[p.role], p.era_start && `${p.era_start}–${p.era_end}`]
            .filter(Boolean)
            .join(" · "),
        }));
        const vh: Hit[] = (venues as VenueSummary[]).map((v) => ({
          kind: "venue",
          id: v.id,
          label: v.name,
          sub: [v.city, `${v.matches} matches`].filter(Boolean).join(" · "),
        }));
        setHits([...ph, ...vh]);
        setActive(-1);
        setOpen(true);
      } catch {
        setHits([]);
      }
    }, 150);
    return () => clearTimeout(t);
  }, [q, onPick]);

  function go(h: Hit) {
    setOpen(false);
    if (h.kind === "player" && onPick) {
      onPick({ id: h.id, name: h.label });
      setQ("");
      return;
    }
    router.push(h.kind === "player" ? `/players/${h.id}` : `/venues/${h.id}`);
  }

  function onKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.min(a + 1, hits.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, -1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (active >= 0 && hits[active]) go(hits[active]);
      else if (hits.length && onPick) go(hits[0]);
      else if (q.trim().length >= 2 && !onPick) {
        setOpen(false);
        router.push(`/players?q=${encodeURIComponent(q.trim())}`);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  const big = size === "lg";
  return (
    <div className="relative w-full">
      <input
        type="search"
        value={q}
        autoFocus={autoFocus}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={onKey}
        onFocus={() => hits.length && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        placeholder={placeholder}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        className={`w-full rounded-lg border border-border bg-surface text-text placeholder:text-muted
          outline-none focus:border-accent focus:ring-2 focus:ring-accent-soft
          ${big ? "px-4 py-3 text-lg" : "px-3 py-2 text-sm"}`}
      />
      {open && hits.length > 0 && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-30 mt-1 w-full overflow-hidden rounded-lg border border-border bg-surface shadow-lg"
        >
          {hits.map((h, i) => (
            <li
              key={h.kind + h.id}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                go(h);
              }}
              onMouseEnter={() => setActive(i)}
              className={`flex cursor-pointer items-baseline justify-between gap-3 px-3 py-2 text-sm
                ${i === active ? "bg-accent-soft" : ""}`}
            >
              <span className="font-medium">{h.label}</span>
              <span className="truncate text-xs text-muted">
                {h.kind === "venue" ? "Venue · " : ""}
                {h.sub}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
