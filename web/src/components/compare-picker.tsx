"use client";

import { CaretUpDownIcon, XIcon } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { playerMeta, useLookup } from "@/components/search-palette";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { displayName, FORMAT_LABEL, FORMATS, type Format } from "@/lib/api";
import { cn } from "@/lib/utils";

type P = { id: string; name: string } | null;

function PlayerSlot({ label, tone, value, onChange }: {
  label: string; tone: "a" | "b"; value: P; onChange: (p: P) => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const { players, loading } = useLookup(q, false);
  return (
    <div className="min-w-0 flex-1">
      <div className="label mb-1.5 flex items-center gap-2">
        <span className={cn("size-2", tone === "a" ? "bg-chart-1" : "bg-chart-2")} />{label}
      </div>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button variant="outline" role="combobox" aria-expanded={open}
            className="h-11 w-full justify-between px-3 text-left text-sm font-normal">
            {value ? <span className="font-display text-xl font-bold uppercase">{value.name}</span>
              : <span className="text-muted-foreground">Pick a player…</span>}
            <CaretUpDownIcon className="opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-(--radix-popover-trigger-width) min-w-72 p-0" align="start">
          <Command shouldFilter={false}>
            <CommandInput value={q} onValueChange={setQ} placeholder="Type a name…" />
            <CommandList>
              {q.trim().length >= 2 && (
                <CommandEmpty>{loading ? "Looking…" : "No one by that name."}</CommandEmpty>
              )}
              {players.length > 0 && (
                <CommandGroup>
                  {players.map((p) => (
                    <CommandItem key={p.id} value={p.id} onSelect={() => {
                      onChange({ id: p.id, name: displayName(p) });
                      setOpen(false);
                      setQ("");
                    }}>
                      <div className="min-w-0">
                        <div className="font-medium">{displayName(p)}</div>
                        <div className="truncate text-[11px] text-muted-foreground">{playerMeta(p)}</div>
                      </div>
                    </CommandItem>
                  ))}
                </CommandGroup>
              )}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>
      {value && (
        <button type="button" onClick={() => onChange(null)}
          className="mt-1 inline-flex items-center gap-1 font-mono text-[11px] text-muted-foreground hover:text-foreground">
          <XIcon className="size-3" />clear
        </button>
      )}
    </div>
  );
}

export function ComparePicker({ a, b, format, from, to }: {
  a: P; b: P; format: Format; from?: number; to?: number;
}) {
  const router = useRouter();
  const [y0, setY0] = useState(from ? String(from) : "");
  const [y1, setY1] = useState(to ? String(to) : "");

  function push(next: { a?: P; b?: P; f?: Format; y0?: string; y1?: string }) {
    const A = next.a !== undefined ? next.a : a;
    const B = next.b !== undefined ? next.b : b;
    const u = new URLSearchParams({ format: next.f ?? format });
    if (A) u.set("a", A.id);
    if (B) u.set("b", B.id);
    const f0 = next.y0 ?? y0;
    const f1 = next.y1 ?? y1;
    if (/^\d{4}$/.test(f0)) u.set("from", f0);
    if (/^\d{4}$/.test(f1)) u.set("to", f1);
    router.push(`/compare?${u}`, { scroll: false });
  }

  return (
    <div className="grid gap-5 border bg-card p-4 sm:p-5 lg:grid-cols-[1fr_auto_1fr_auto] lg:items-start">
      <PlayerSlot label="Player A" tone="a" value={a} onChange={(p) => push({ a: p })} />
      <div className="hidden self-center pt-5 font-display text-3xl font-extrabold text-muted-foreground lg:block">VS</div>
      <PlayerSlot label="Player B" tone="b" value={b} onChange={(p) => push({ b: p })} />
      <div className="flex flex-wrap items-end gap-3 lg:border-l lg:pl-5">
        <div>
          <div className="label mb-1.5">Format</div>
          <Select value={format} onValueChange={(v) => push({ f: v as Format })}>
            <SelectTrigger className="h-11 w-32"><SelectValue /></SelectTrigger>
            <SelectContent>
              {FORMATS.map((f) => <SelectItem key={f} value={f}>{FORMAT_LABEL[f]}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); push({}); }}>
          <label>
            <div className="label mb-1.5">From</div>
            <Input value={y0} onChange={(e) => setY0(e.target.value)} inputMode="numeric" placeholder="Year"
              className="h-11 w-20 font-mono" />
          </label>
          <label>
            <div className="label mb-1.5">To</div>
            <Input value={y1} onChange={(e) => setY1(e.target.value)} inputMode="numeric" placeholder="Year"
              className="h-11 w-20 font-mono" />
          </label>
          <Button type="submit" variant="secondary" className="h-11">Apply</Button>
        </form>
      </div>
    </div>
  );
}
