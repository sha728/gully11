// The season after an auction: setup (XIs), the played season, and how far this
// viewer has got through it (kept in this browser, so the table fills in as you go).

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
}

export interface CapRow { id: string; name: string; team: string; runs?: number; balls?: number; wickets?: number }

export interface Season {
  teams: { id: string; name: string }[];
  matches: MatchSummary[];
  table: TableRow[];
  champion: { id: string; name: string };
  runner_up: { id: string; name: string };
  caps: { orange: CapRow[]; purple: CapRow[] };
  lineups: Record<string, { xi: string[]; impact: string | null; picked: boolean }>;
  format: string;
}

export interface SeasonView {
  code: string;
  mode: string;
  you: string | null;
  host: boolean;
  played: boolean;
  teams?: SetupTeam[];
  season?: Season;
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
  play: (code: string, token: string | null) =>
    call<{ season: Season }>(`${base(code)}/play`, { method: "POST", body: JSON.stringify({ token }) }),
  match: (code: string, n: number) => call<FullMatch>(`${base(code)}/match/${n}`),
};

// How many matches this viewer has seen.
const progressKey = (code: string) => `gully11:season:${code.toUpperCase()}`;
export function loadProgress(code: string): number {
  try { return Number(localStorage.getItem(progressKey(code)) ?? 0) || 0; } catch { return 0; }
}
export function saveProgress(code: string, n: number) {
  try { localStorage.setItem(progressKey(code), String(Math.max(n, loadProgress(code)))); } catch { /* storage blocked */ }
}

export interface TableRow {
  team: string; played: number; won: number; lost: number; tied: number; points: number; nrr: number;
}

function balls(overs: string) {
  const [o, b] = overs.split(".");
  return Number(o) * 6 + Number(b ?? 0);
}

/** The points table after the league matches given (same rules as the server:
 * 2 for a win, 1 for a tie; net run rate with an all-out side charged 20 overs). */
export function pointsTable(matches: MatchSummary[], teams: string[]): TableRow[] {
  const rows = Object.fromEntries(teams.map((t) => [t, { team: t, played: 0, won: 0, lost: 0, tied: 0, points: 0, fr: 0, fb: 0, ar: 0, ab: 0 }]));
  for (const m of matches) {
    if (m.stage !== "League") continue;
    m.scores.forEach((s, i) => {
      const bat = rows[s.team], bowl = rows[m.scores[1 - i].team];
      const b = s.wickets >= 10 ? 120 : balls(s.overs);
      bat.fr += s.runs; bat.fb += b; bowl.ar += s.runs; bowl.ab += b;
    });
    for (const t of m.teams) {
      const r = rows[t];
      r.played++;
      if (m.winner == null) { r.tied++; r.points++; }
      else if (m.winner === t) { r.won++; r.points += 2; }
      else r.lost++;
    }
  }
  return Object.values(rows)
    .map((r) => ({ team: r.team, played: r.played, won: r.won, lost: r.lost, tied: r.tied, points: r.points,
      nrr: Math.round(((r.fb ? 6 * r.fr / r.fb : 0) - (r.ab ? 6 * r.ar / r.ab : 0)) * 1000) / 1000 }))
    .sort((a, b) => b.points - a.points || b.nrr - a.nrr || a.team.localeCompare(b.team));
}
