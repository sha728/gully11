// The season after an auction: XIs (set before or between matches) and the
// season so far, which the host moves on one match (or more) at a time.

import { API_URL, type Role } from "@/lib/api";
import type { FullMatch } from "@/lib/xi";

export interface SeasonPlayer {
  id: string;
  name: string;
  role: Role;
  overseas: boolean;
  fair: number;
  price: number;
  retained: boolean;
  opener: boolean;
}

export interface SetupTeam {
  id: string;
  name: string;
  bot: boolean;
  owner: string | null;
  players: SeasonPlayer[];
  xi: string[];
  impact: string | null;
  picked: boolean;
}

export interface MatchSummary {
  match: number;
  stage: "League" | "Qualifier 1" | "Eliminator" | "Qualifier 2" | "Final";
  teams: [string, string];
  winner: string | null;
  margin: string;
  result: "win" | "tie";
  scores: { team: string; runs: number; wickets: number; overs: string }[];
  top_scorer: { name: string; runs: number; balls: number };
  best_bowler: { name: string; wickets: number; runs: number };
  lineups: Record<string, { xi: string[]; impact: string | null; picked: boolean }>;
}

export interface CapRow { id: string; name: string; team: string; runs?: number; balls?: number; wickets?: number }

export interface TableRow {
  team: string; played: number; won: number; lost: number; tied: number; points: number; nrr: number;
}

/** The season so far (the server's state: grows as the host moves it on). */
export interface Season {
  teams: { id: string; name: string }[];
  matches: MatchSummary[];
  table: TableRow[];
  champion: { id: string; name: string } | null;
  runner_up: { id: string; name: string } | null;
  caps: { orange: CapRow[]; purple: CapRow[] };
  format: string;
}

export interface Fixture { stage: MatchSummary["stage"]; home: string; away: string; match: number }

export interface SeasonView {
  code: string;
  mode: string;
  you: string | null;
  host: boolean;
  started: boolean;
  finished: boolean;
  total: number | null;
  next: Fixture | null;
  teams: SetupTeam[];
  season: Season | null;
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

const base = (code: string) => `/rooms/${encodeURIComponent(code)}/season`;

export const seasonApi = {
  get: (code: string, token: string | null) => call<SeasonView>(`${base(code)}${token ? `?token=${encodeURIComponent(token)}` : ""}`),
  lineup: (code: string, token: string, xi: string[], impact: string | null) =>
    call<{ ok: boolean }>(`${base(code)}/lineup`, { method: "PUT", body: JSON.stringify({ token, xi, impact }) }),
  start: (code: string, token: string | null) =>
    call<SeasonView>(`${base(code)}/start`, { method: "POST", body: JSON.stringify({ token }) }),
  advance: (code: string, token: string | null, how: "next" | "mine" | "end") =>
    call<SeasonView>(`${base(code)}/advance`, { method: "POST", body: JSON.stringify({ token, how }) }),
  match: (code: string, n: number) => call<FullMatch>(`${base(code)}/match/${n}`),
};

// Matches of yours this browser has watched, so a fresh result of yours offers
// "watch it live" rather than just appearing in the list.
const watchedKey = (code: string) => `gully11:season-watched:${code.toUpperCase()}`;
export function watched(code: string): number[] {
  try { return JSON.parse(localStorage.getItem(watchedKey(code)) ?? "[]"); } catch { return []; }
}
export function markWatched(code: string, n: number) {
  try { localStorage.setItem(watchedKey(code), JSON.stringify([...new Set([...watched(code), n])])); } catch { /* storage blocked */ }
}
