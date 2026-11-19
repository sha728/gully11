// XI Builder: types and calls for /api/v1/xi. Spins, series and saved challenges
// are user-specific, so nothing here is cached.

import { API_URL, NotFound, type Role } from "@/lib/api";

export const XI_FORMATS = ["Test", "ODI", "T20I", "IPL"] as const;
export type XIFormat = (typeof XI_FORMATS)[number];

export const XI_COPY: Record<XIFormat, { title: string; blurb: string; unit: string }> = {
  Test: { title: "Test", blurb: "Five Tests against the all-time XI: Bradman, Sobers, Warne and co.", unit: "nation" },
  ODI: { title: "ODI", blurb: "Fifty overs a side against Tendulkar, Viv Richards and Muralitharan.", unit: "nation" },
  T20I: { title: "T20I", blurb: "Twenty overs against the T20I World XI.", unit: "nation" },
  IPL: { title: "IPL", blurb: "Draft franchise by franchise, four overseas at most, against the IPL All-Stars.", unit: "franchise" },
};

export interface Candidate {
  id: string;
  person: string;
  name: string;
  kind: "modern" | "legend";
  role: Role;
  country: string | null;
  matches: number;
  runs: number | null;
  bat_avg: number | null;
  bat_sr: number | null;
  wickets: number | null;
  bowl_econ: number | null;
  years: string;
  value: number;
  /** Opened in at least 40% of their innings in this format. */
  opener: boolean;
  spinner: boolean;
  /** Batting positions (1-11) this player may take. */
  slots: number[];
}

export interface Position {
  slot: number;
  label: string;
  short: string;
}

export interface Spin {
  spin: number;
  era: string;
  side: string;
  candidates: Candidate[];
}

export interface SpinSet {
  format: XIFormat;
  seed: number;
  date?: string;
  positions: Position[];
  spins: Spin[];
}

export interface MatchSummary {
  match: number;
  winner: string | null;
  result: "win" | "draw" | "tie";
  margin: string;
  scores: { team: string; runs: number; wickets: number; overs: string; declared: boolean }[];
  top_scorer: { name: string; runs: number; balls: number };
  best_bowler: { name: string; wickets: number; runs: number };
}

export interface SeriesResult {
  won: number;
  lost: number;
  drawn: number;
  tied: number;
  verdict: string;
}

export interface Challenge {
  slug: string;
  format: XIFormat;
  seed: number;
  daily: string | null;
  picks: string[];
  slots?: number[];
  xi: (Candidate & { order: number })[];
  opponent: string;
  result: SeriesResult;
  matches: MatchSummary[];
  spins?: Spin[];
  created_at?: string;
}

export interface BallEvent {
  inns: number;
  ball: string;
  bowler: string;
  batter: string;
  kind: "runs" | "wicket" | "wide" | "noball";
  runs: number;
  bat_runs?: number;
  byes?: number;
  out?: string;
  how?: string;
  score: string;
  text: string;
}

export interface InningsCard {
  batting: string;
  bowling: string;
  runs: number;
  wickets: number;
  overs: string;
  target: number | null;
  declared?: boolean;
  extras: { wides: number; noballs: number; byes: number };
  batting_card: { id: string; name: string; runs: number; balls: number; fours: number; sixes: number; how_out: string | null }[];
  bowling_card: { id: string; name: string; overs: string; maidens: number; runs: number; wickets: number; wides: number; noballs: number }[];
  fall_of_wickets: string[];
}

export interface FullMatch {
  seed: number;
  env: string;
  teams: [string, string];
  innings: InningsCard[];
  winner: string | null;
  margin: string;
  result: "win" | "draw" | "tie";
  commentary: BallEvent[];
  win_prob: [string, number][];
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API_URL + path, {
    ...init,
    cache: "no-store",
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (res.status === 404) throw new NotFound(path);
  if (!res.ok) {
    let detail = `API ${res.status}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const xiApi = {
  spin: (format: XIFormat, seed?: number) =>
    call<SpinSet>("/xi/spin", { method: "POST", body: JSON.stringify({ format, seed }) }),
  daily: (format: XIFormat) => call<SpinSet>(`/xi/daily/${format}`),
  series: (format: XIFormat, seed: number, picks: string[], slots: number[], daily = false) =>
    call<Challenge>("/xi/series", { method: "POST", body: JSON.stringify({ format, seed, picks, slots, daily }) }),
  challenge: (slug: string) => call<Challenge>(`/xi/challenge/${encodeURIComponent(slug)}`),
  match: (slug: string, n: number) => call<FullMatch>(`/xi/challenge/${encodeURIComponent(slug)}/match/${n}`),
};

export const isOverseas = (c: Pick<Candidate, "country">) => !!c.country && c.country !== "India";
export const KEEPER_SLOT = 6;

/** Can ``c`` bat at ``slot``, given who else bats where? Slot 6 is the keeper's
 * unless a keeper already bats in the top five. */
export function fits(c: Candidate, slot: number, bySlot: (Candidate | null)[]): boolean {
  if (!c.slots.includes(slot)) return false;
  if (slot !== KEEPER_SLOT || c.role === "WK") return true;
  return bySlot.some((p, i) => p && p.role === "WK" && i + 1 < KEEPER_SLOT && p.id !== c.id);
}
