"use client";

import { MagnifyingGlassIcon, MapPinIcon, ScalesIcon, UserIcon } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import {
  Command, CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator,
} from "@/components/ui/command";
import { Kbd, KbdGroup } from "@/components/ui/kbd";
import { API_URL, displayName, ROLE_LABEL, type PlayerSummary, type VenueSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

const Ctx = createContext<{ open: () => void }>({ open: () => {} });
export const useSearchPalette = () => useContext(Ctx);

/** Debounced player + venue lookup against the API; latest keystroke wins. */
export function useLookup(q: string, withVenues = true) {
  const [players, setPlayers] = useState<PlayerSummary[]>([]);
  const [venues, setVenues] = useState<VenueSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  useEffect(() => {
    const term = q.trim();
    if (term.length < 2) {
      setPlayers([]);
      setVenues([]);
      return;
    }
    const mine = ++seq.current;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const [p, v] = await Promise.all([
          fetch(`${API_URL}/players?q=${encodeURIComponent(term)}&limit=8`).then((r) => r.json()),
          withVenues
            ? fetch(`${API_URL}/venues?q=${encodeURIComponent(term)}&limit=4`).then((r) => r.json())
            : Promise.resolve([]),
        ]);
        if (mine !== seq.current) return;
        setPlayers(p.items ?? []);
        setVenues(v ?? []);
      } catch {
        if (mine === seq.current) {
          setPlayers([]);
          setVenues([]);
        }
      } finally {
        if (mine === seq.current) setLoading(false);
      }
    }, 140);
    return () => clearTimeout(t);
  }, [q, withVenues]);
  return { players, venues, loading };
}

export function playerMeta(p: PlayerSummary) {
  return [p.full_name && p.full_name !== p.name ? p.name : null, p.country, ROLE_LABEL[p.role],
    p.era_start ? `${p.era_start}–${p.era_end}` : null].filter(Boolean).join(" · ");
}

export function SearchPaletteProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const { players, venues, loading } = useLookup(q);

  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement)?.closest("input, textarea, [contenteditable]");
      if ((e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  const go = useCallback((href: string) => {
    setOpen(false);
    setQ("");
    router.push(href);
  }, [router]);

  return (
    <Ctx.Provider value={{ open: () => setOpen(true) }}>
      {children}
      <CommandDialog open={open} onOpenChange={setOpen} title="Search Gully11"
        description="Find a player or a ground" className="sm:max-w-xl">
        {/* Results come from the API already ranked, so cmdk's own filter stays off. */}
        <Command shouldFilter={false}>
        <CommandInput value={q} onValueChange={setQ} placeholder="Player or ground — try “Rohit”, “Lord’s”" />
        <CommandList className="max-h-[60vh]">
          {q.trim().length < 2 ? (
            <CommandGroup heading="Jump to">
              <CommandItem value="all-players" onSelect={() => go("/players")}><UserIcon />All players</CommandItem>
              <CommandItem value="compare" onSelect={() => go("/compare")}><ScalesIcon />Compare two players</CommandItem>
              <CommandItem value="venues" onSelect={() => go("/venues")}><MapPinIcon />Grounds</CommandItem>
            </CommandGroup>
          ) : (
            <>
              <CommandEmpty>{loading ? "Looking…" : "Nobody by that name. Try a surname."}</CommandEmpty>
              {players.length > 0 && (
                <CommandGroup heading="Players">
                  {players.map((p) => (
                    <CommandItem key={p.id} value={`p-${p.id}`} onSelect={() => go(`/players/${p.id}`)}>
                      <UserIcon />
                      <span className="font-medium">{displayName(p)}</span>
                      <span className="flex-1 truncate text-right text-muted-foreground">{playerMeta(p)}</span>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
              {venues.length > 0 && (
                <>
                  <CommandSeparator />
                  <CommandGroup heading="Grounds">
                    {venues.map((v) => (
                      <CommandItem key={v.id} value={`v-${v.id}`} onSelect={() => go(`/venues/${v.id}`)}>
                        <MapPinIcon />
                        <span className="font-medium">{v.name}</span>
                        <span className="flex-1 truncate text-right text-muted-foreground">{v.city} · {v.matches} matches</span>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </>
              )}
              {q.trim().length >= 2 && (
                <>
                  <CommandSeparator />
                  <CommandGroup>
                    <CommandItem value="see-all" onSelect={() => go(`/players?q=${encodeURIComponent(q.trim())}`)}>
                      <MagnifyingGlassIcon />See every player matching “{q.trim()}”
                    </CommandItem>
                  </CommandGroup>
                </>
              )}
            </>
          )}
        </CommandList>
        </Command>
      </CommandDialog>
    </Ctx.Provider>
  );
}

/** The fake input that opens the palette (header and home hero). */
export function SearchTrigger({ size = "sm", className }: { size?: "sm" | "lg"; className?: string }) {
  const { open } = useSearchPalette();
  const lg = size === "lg";
  return (
    <button
      type="button"
      onClick={open}
      className={cn(
        "group flex w-full items-center gap-3 border border-input bg-card text-left text-muted-foreground transition-colors hover:border-foreground/40",
        lg ? "h-14 px-4 text-base" : "h-8 px-2.5 text-xs",
        className,
      )}
    >
      <MagnifyingGlassIcon className={lg ? "size-5" : "size-4"} />
      <span className="flex-1 truncate">{lg ? "Search any player or ground since 2001" : "Search players, grounds"}</span>
      <KbdGroup className="hidden sm:flex">
        <Kbd>Ctrl</Kbd><Kbd>K</Kbd>
      </KbdGroup>
    </button>
  );
}
