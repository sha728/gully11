// The season after an auction: XIs (set before or between matches) and the
// season so far, which the host moves on one match (or more) at a time.

import { API_URL, type Role } from "@/lib/api";
import type { Award, BowlOption, CaptainRecord, FullMatch } from "@/lib/xi";

export interface SeasonPlayer {
  id: string;
  name: string;
  role: Role;
  overseas: boolean;
  fair: number;
  price: number;
  retained: boolean;
  opener: boolean;
  captaincy: CaptainRecord | null;
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
  captain: string | null;
  choose: boolean;            // its person picks the bowler every over
  impact_out: string | null;  // who the Impact Player replaces (null: the engine picks)
  subs: string[];             // named substitutes (up to five); ``impact`` is the one chosen, null: engine picks
  impact_when: ImpactWhen;
}

/** When the Impact sub comes on: the engine decides, the first ball, or the innings break. */
export type ImpactWhen = "auto" | "start" | "break";

export interface MatchSummary {
  match: number;
  stage: "League" | "Qualifier 1" | "Eliminator" | "Qualifier 2" | "Final";
  teams: [string, string];
  winner: string | null;
  margin: string;
  result: "win" | "tie" | "super over";
  scores: { team: string; runs: number; wickets: number; overs: string }[];
  top_scorer: { name: string; runs: number; balls: number };
  best_bowler: { name: string; wickets: number; runs: number };
  player_of_match?: Award | null;
  lineups: Record<string, { xi: string[]; impact: string | null; picked: boolean; captain?: string | null }>;
}

export interface CapRow {
  id: string; name: string; team: string;
  runs?: number; balls?: number; sr?: number | null;     // Orange Cap: runs, balls faced, strike rate
  wickets?: number; econ?: number | null;                // Purple Cap: wickets, economy
  score?: number; awards?: number; matches?: number;     // Player of the season: impact, player-of-match awards
}

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
  caps: { orange: CapRow[]; purple: CapRow[]; mvp?: CapRow[] };
  format: string;
  /** A match waiting for a captain to choose who bowls the next over. */
  live?: SeasonWait | null;
}

export interface SeasonWait {
  match: number;
  home: string;
  away: string;
  stage: MatchSummary["stage"];
  key: string;            // "<innings>:<over>" (bowling) or "bat:<innings>:<wickets>"
  kind: "bowl" | "bat";   // choosing a bowler, or a batting break (start of innings / a wicket)
  over: number;           // 1-based
  wickets: number;
  waiting: string;        // franchise id whose decision it is
}

/** What a captained side may do with its Impact Player right now. */
export interface ImpactOffer {
  subs: { id: string; name: string; role: Role; kind: "pace" | "spin" | null }[];
  replace: { id: string; name: string; role: Role }[];
}

/** The waiting match so far; ``options`` only for the franchise whose over it is. */
export interface SeasonLive extends SeasonWait {
  match_json: FullMatch;
  yours: boolean;
  options?: BowlOption[];
  suggested?: string;
  innings?: number;
  impact?: ImpactOffer | null;
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
  lineup: (code: string, token: string, xi: string[], impact: string | null, captain: string | null,
           impactOut: string | null = null, impactWhen: ImpactWhen = "auto", subs: string[] = []) =>
    call<{ ok: boolean }>(`${base(code)}/lineup`, {
      method: "PUT",
      body: JSON.stringify({ token, xi, impact, captain, impact_out: impactOut, impact_when: impactWhen, subs }),
    }),
  start: (code: string, token: string | null) =>
    call<SeasonView>(`${base(code)}/start`, { method: "POST", body: JSON.stringify({ token }) }),
  advance: (code: string, token: string | null, how: "next" | "mine" | "end") =>
    call<SeasonView>(`${base(code)}/advance`, { method: "POST", body: JSON.stringify({ token, how }) }),
  match: (code: string, n: number) => call<FullMatch>(`${base(code)}/match/${n}`),
  choose: (code: string, token: string, on: boolean) =>
    call<SeasonView>(`${base(code)}/choose`, { method: "PUT", body: JSON.stringify({ token, on }) }),
  live: (code: string, token: string | null) =>
    call<SeasonLive>(`${base(code)}/live${token ? `?token=${encodeURIComponent(token)}` : ""}`),
  bowl: (code: string, token: string, key: string, bowler: string | null, impactIn?: string, impactOut?: string) =>
    call<SeasonView>(`${base(code)}/live/bowl`, {
      method: "POST",
      body: JSON.stringify({ token, key, bowler, impact_in: impactIn ?? null, impact_out: impactOut ?? null }),
    }),
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
