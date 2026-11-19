// Auction rooms: REST to create/join, one WebSocket per room for live state.
// The server owns the clock; the browser only draws a countdown from ends_at.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_URL, type Role } from "@/lib/api";

export interface PoolPlayer {
  id: string;
  name: string;
  short_name: string;
  role: Role;
  country: string | null;
  overseas: boolean;
  capped: boolean;
  spinner: boolean;
  last_team: string | null;
  last_ipl: string | null;
  ipl_matches: number | null;
  category: string;
  fair: number;
  base: number;
  rank: number;
  form: { matches: number; runs: number; bat_avg: number | null; bat_sr: number | null; wickets: number; econ: number | null };
}

export interface FranchiseView {
  id: string;
  name: string;
  bot: boolean;
  owner: string | null;
  personality: string | null;
  purse: number;
  squad: { id: string; price: number }[];
  size: number;
  overseas: number;
  roles: Record<Role, number>;
}

export interface LogEntry {
  player: string;
  name: string;
  result: "sold" | "unsold";
  franchise?: string;
  price?: number;
  fair?: number;
  base?: number;
  bids?: number;
}

export interface RoomState {
  type: "state";
  server_now: number;
  code: string;
  mode: string;
  phase: "lobby" | "live" | "ended";
  speed: "normal" | "fast";
  version: number;
  accelerated: boolean;
  presented: number;
  total: number;
  round: { n: number; of: number };
  result?: Summary;
  rules: { purse_lakh: number; squad_min: number; squad_max: number; overseas_max: number; increments: [number | null, number][] };
  franchises: FranchiseView[];
  lot: null | {
    player: PoolPlayer;
    set: string;
    set_label: string;
    price: number | null;
    leader: string | null;
    ends_at: number;
    next: number;
    bids: { franchise: string; amount: number; at: number }[];
    passed: string[];
  };
  upcoming: PoolPlayer[];
  log: LogEntry[];
  players: Record<string, PoolPlayer>;
  you?: string | null;
  host?: boolean;
}

export interface Summary {
  franchises: { id: string; name: string; bot: boolean; owner: string | null; spent: number; purse: number;
    squad: { id: string; price: number; player: PoolPlayer }[] }[];
  sold: number;
  unsold: number;
  best_value: LogEntry[];
}

/** 30 → "₹30 L", 250 → "₹2.5 cr" (money is held in lakh). */
export function money(lakh: number | null | undefined): string {
  if (lakh == null) return "–";
  return lakh >= 100 ? `₹${(lakh / 100).toLocaleString("en-IN", { maximumFractionDigits: 2 })} cr` : `₹${lakh} L`;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, { ...init, cache: "no-store", headers: { "content-type": "application/json" } });
  } catch {
    throw new Error("Can't reach the game server. Check that the API is running and try again.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${res.status})`);
  return body as T;
}

export interface Seat { code: string; token: string; franchise: string }

export const auctionApi = {
  create: (b: { nickname: string; teams: number; humans: number; speed: "normal" | "fast" }) =>
    call<Seat>("/rooms", { method: "POST", body: JSON.stringify(b) }),
  join: (code: string, nickname: string) =>
    call<Seat>(`/rooms/${encodeURIComponent(code)}/join`, { method: "POST", body: JSON.stringify({ nickname }) }),
  get: (code: string) => call<RoomState & { live: boolean; result?: Summary }>(`/rooms/${encodeURIComponent(code)}`),
};

// Your seat in a room is remembered in this browser only.
const seatKey = (code: string) => `gully11:auction:${code.toUpperCase()}`;
export function saveSeat(seat: Seat) {
  try { localStorage.setItem(seatKey(seat.code), JSON.stringify(seat)); } catch { /* storage blocked */ }
}
export function loadSeat(code: string): Seat | null {
  try { const raw = localStorage.getItem(seatKey(code)); return raw ? (JSON.parse(raw) as Seat) : null; } catch { return null; }
}

/** Live room over a WebSocket, reconnecting with backoff. ``offset`` turns the
 * server's clock into this browser's (now + offset = server now). */
export function useRoom(code: string, token: string | null, enabled: boolean) {
  const [state, setState] = useState<RoomState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [gone, setGone] = useState(false);
  const ws = useRef<WebSocket | null>(null);
  const offset = useRef(0);
  const meta = useRef<{ you: string | null; host: boolean }>({ you: null, host: false });

  useEffect(() => {
    if (!enabled) return;
    let stop = false;
    let tries = 0;
    let timer: ReturnType<typeof setTimeout>;
    const url = `${API_URL.replace(/^http/, "ws")}/ws/rooms/${encodeURIComponent(code)}${token ? `?token=${encodeURIComponent(token)}` : ""}`;

    function open() {
      const sock = new WebSocket(url);
      ws.current = sock;
      sock.onopen = () => { tries = 0; setConnected(true); };
      sock.onmessage = (ev) => {
        const m = JSON.parse(ev.data);
        if (m.type === "state") {
          offset.current = m.server_now - Date.now() / 1000;
          if ("you" in m) meta.current = { you: m.you ?? null, host: !!m.host };
          setState({ ...m, ...meta.current });
        } else if (m.type === "error") {
          setError(m.message);
        }
      };
      sock.onclose = (ev) => {
        setConnected(false);
        if (ev.code === 4404) { setGone(true); return; }
        if (!stop) timer = setTimeout(open, Math.min(8000, 500 * 2 ** tries++));
      };
    }
    open();
    return () => { stop = true; clearTimeout(timer); ws.current?.close(); };
  }, [code, token, enabled]);

  const send = useCallback((msg: object) => {
    setError(null);
    if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(msg));
    else setError("Reconnecting to the room…");
  }, []);

  const serverNow = useCallback(() => Date.now() / 1000 + offset.current, []);
  return { state, error, setError, connected, gone, send, serverNow };
}

export const ROLE_ORDER: Role[] = ["BAT", "WK", "AR", "BOWL"];
export const ROLE_SHORT: Record<Role, string> = { BAT: "BAT", WK: "WK", AR: "AR", BOWL: "BOWL" };
