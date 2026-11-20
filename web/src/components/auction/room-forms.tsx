"use client";

import { ArrowRightIcon, GavelIcon } from "@phosphor-icons/react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { auctionApi, saveSeat } from "@/lib/auction";

const TEAMS = [2, 4, 6, 8, 10];

export function CreateRoom() {
  const router = useRouter();
  const [nickname, setNickname] = useState("");
  const [mode, setMode] = useState<"mega" | "mini">("mega");
  const [teams, setTeams] = useState(10);
  const [friends, setFriends] = useState(0);
  const [speed, setSpeed] = useState<"normal" | "fast">("normal");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const seat = await auctionApi.create({ nickname: nickname.trim() || "Host", teams: mode === "mini" ? 10 : teams, humans: 1 + friends, speed, mode });
      saveSeat(seat);
      router.push(`/auction/${seat.code}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create the room.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={create} className="space-y-5">
      <Field label="Your name">
        <Input value={nickname} onChange={(e) => setNickname(e.target.value)} maxLength={24} placeholder="Host" className="h-10" />
      </Field>
      <Field label="Auction" hint={mode === "mega"
        ? "Every IPL player of the last three seasons, ₹120 cr each, empty squads."
        : "The real IPL 2026 auction: the 10 franchises with their retained squads and real purses, the 77 players sold that day in the real sets. At the end, see what really happened."}>
        <ToggleGroup type="single" value={mode} variant="outline"
          onValueChange={(v) => { if (!v) return; setMode(v as "mega" | "mini"); if (v === "mini") setTeams(10); }}>
          <ToggleGroupItem value="mega" className="px-4 font-mono text-xs uppercase">Mega auction</ToggleGroupItem>
          <ToggleGroupItem value="mini" className="px-4 font-mono text-xs uppercase">IPL 2026 replay</ToggleGroupItem>
        </ToggleGroup>
      </Field>
      {mode === "mega" && (
        <Field label="Franchises" hint="Fewer teams, shorter auction: the pool scales with the room.">
          <ToggleGroup type="single" value={String(teams)} variant="outline"
            onValueChange={(v) => { if (!v) return; const n = Number(v); setTeams(n); setFriends((f) => Math.min(f, n - 1)); }}>
            {TEAMS.map((n) => <ToggleGroupItem key={n} value={String(n)} className="w-12 font-mono">{n}</ToggleGroupItem>)}
          </ToggleGroup>
        </Field>
      )}
      <Field label="Friends joining" hint={friends === 0 ? `Just you against ${teams - 1} bots.` : `${friends} friend${friends > 1 ? "s" : ""} join with the room code; ${teams - 1 - friends} bot${teams - 1 - friends === 1 ? "" : "s"} fill the rest.`}>
        <div className="flex items-center gap-2">
          <Button type="button" variant="outline" size="icon" onClick={() => setFriends((f) => Math.max(0, f - 1))} aria-label="Fewer friends">−</Button>
          <span className="w-8 text-center font-display text-2xl font-bold tnum">{friends}</span>
          <Button type="button" variant="outline" size="icon" onClick={() => setFriends((f) => Math.min(teams - 1, f + 1))} aria-label="More friends">+</Button>
        </div>
      </Field>
      <Field label="Clock" hint={speed === "normal" ? "15 s to open a player, 10 s after each bid." : "8 s to open, 5 s after each bid."}>
        <ToggleGroup type="single" value={speed} variant="outline" onValueChange={(v) => v && setSpeed(v as "normal" | "fast")}>
          <ToggleGroupItem value="normal" className="px-4 font-mono text-xs uppercase">Normal</ToggleGroupItem>
          <ToggleGroupItem value="fast" className="px-4 font-mono text-xs uppercase">Fast</ToggleGroupItem>
        </ToggleGroup>
      </Field>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Button type="submit" size="lg" disabled={busy} className="h-11 font-mono uppercase">
        <GavelIcon weight="fill" />{busy ? "Setting up the room…" : "Create room"}
      </Button>
    </form>
  );
}

export function JoinRoom() {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [nickname, setNickname] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function join(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const seat = await auctionApi.join(code.trim().toUpperCase(), nickname.trim() || "Player");
      saveSeat(seat);
      router.push(`/auction/${seat.code}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't join.");
      setBusy(false);
    }
  }

  return (
    <form onSubmit={join} className="space-y-5">
      <Field label="Room code">
        <Input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())} maxLength={6} placeholder="ABCDEF"
          className="h-12 font-mono text-2xl tracking-[0.3em] uppercase" autoComplete="off" />
      </Field>
      <Field label="Your name">
        <Input value={nickname} onChange={(e) => setNickname(e.target.value)} maxLength={24} placeholder="Player" className="h-10" />
      </Field>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Button type="submit" variant="outline" size="lg" disabled={busy || code.trim().length !== 6} className="h-11 font-mono uppercase">
        Join room<ArrowRightIcon />
      </Button>
    </form>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="label">{label}</div>
      {children}
      {hint && <p className="font-mono text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}
