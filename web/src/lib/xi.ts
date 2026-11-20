// XI Builder: types and calls for /api/v1/xi. Spins, series and saved challenges
// are user-specific, so nothing here is cached.

import { API_URL, NotFound, type Role } from "@/lib/api";

export const XI_FORMATS = ["Test", "ODI", "T20I", "IPL"] as const;
export type XIFormat = (typeof XI_FORMATS)[number];

export const XI_COPY: Record<XIFormat, { title: string; blurb: string; unit: string }> = {
  Test: { title: "Test", blurb: "Five Tests against the Greats: Bradman, Sobers, Warne and co.", unit: "nation" },
  ODI: { title: "ODI", blurb: "Fifty overs a side against Tendulkar, Viv Richards and Muralitharan.", unit: "nation" },
  T20I: { title: "T20I", blurb: "Twenty overs a side against the T20I Greats.", unit: "nation" },
  IPL: { title: "IPL", blurb: "Draft franchise by franchise, four overseas at most, against the IPL Greats.", unit: "franchise" },
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
  /** Their real captaincy record in this format (or the closest one), if any. */
  captaincy?: CaptainRecord | null;
}

/** A captaincy record and the tactical rating (0..1) it gives in the simulator. */
export interface CaptainRecord { format: string; matches: number; won: number; lost: number; win_pct: number | null; rating: number }

export interface CaptainInfo { id: string | null; name: string | null; rating: number; record: CaptainRecord | null }

export interface Position {
  slot: number;
  label: string;
  short: string;
}

/** A candidate as the draft sees it: the slots it could take right now (best
 * first), or why it can't be picked. */
export interface DraftCandidate extends Candidate {
  options: number[];
  why: string | null;
}

export interface RevealedSpin {
  spin: number;
  era: string;
  side: string;
  candidates: DraftCandidate[];
  pick: { id: string; slot: number } | null;
}

export interface LineupSlot extends Position {
  spin: number | null;
  player: Candidate | null;
  /** Slots this player may move to (swapping with whoever is there). */
  targets: number[];
}

export interface DraftView {
  id: string;
  format: XIFormat;
  seed: number;
  daily: string | null;
  rival: string | null;
  challenge: string | null;
  positions: Position[];
  reel: { eras: string[]; sides: string[] };
  revealed: number;
  total: number;
  spins: RevealedSpin[];
  lineup: LineupSlot[];
  can_spin: boolean;
  waiting: boolean;
  /** Your chosen captain (a pick), and who leads if you don't choose. */
  captain: string | null;
  captain_auto: string | null;
  status: { picked: number; openers: number; keeper_top6: boolean; overseas: number | null; ready: boolean };
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
  created_at?: string;
  captain?: string | null;
  captains?: { mine: CaptainInfo; them: CaptainInfo } | null;
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
  wicket_kind?: string;
  fielder?: string | null;
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
  toss?: { winner: string; decision: "bat" | "bowl"; captain: string | null; called_right: boolean } | null;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(API_URL + path, {
      ...init,
      cache: "no-store",
      headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    // The browser only says "Failed to fetch": the API is down or unreachable.
    throw new Error("Can't reach the game server. Check that the API is running and try again.");
  }
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

const post = (body?: unknown) => ({ method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const draftPath = (id: string) => `/xi/drafts/${encodeURIComponent(id)}`;

export const xiApi = {
  newDraft: (format: XIFormat, opts: { seed?: number; daily?: boolean; vs?: string }) =>
    call<DraftView>("/xi/drafts", post({ format, ...opts })),
  draft: (id: string) => call<DraftView>(draftPath(id)),
  spin: (id: string) => call<DraftView>(`${draftPath(id)}/spin`, post()),
  pick: (id: string, spin: number, player: string, slot?: number) =>
    call<DraftView>(`${draftPath(id)}/pick`, post({ spin, player, slot })),
  unpick: (id: string, spin: number) => call<DraftView>(`${draftPath(id)}/pick/${spin}`, { method: "DELETE" }),
  move: (id: string, from: number, to: number) => call<DraftView>(`${draftPath(id)}/move`, post({ from, to })),
  captain: (id: string, player: string | null) => call<DraftView>(`${draftPath(id)}/captain`, post({ player })),
  play: (id: string) => call<{ slug: string; rival: string | null }>(`${draftPath(id)}/play`, post()),
  challenge: (slug: string) => call<Challenge>(`/xi/challenge/${encodeURIComponent(slug)}`),
  match: (slug: string, n: number) => call<FullMatch>(`/xi/challenge/${encodeURIComponent(slug)}/match/${n}`),
};

export const isOverseas = (c: Pick<Candidate, "country">) => !!c.country && c.country !== "India";
export const KEEPER_SLOT = 6;

/** "Captained 68 Tests, won 59%" */
export function captainText(r: CaptainRecord): string {
  const unit = r.format === "IPL" ? "IPL matches" : `${r.format}s`;
  return `Captained ${r.matches} ${unit}${r.win_pct != null ? `, won ${Math.round(r.win_pct)}%` : ""}`;
}
