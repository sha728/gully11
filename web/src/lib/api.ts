// Typed client for the Gully11 API. Used from server components (SSR) and,
// for search/typeahead, from the browser.

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export const FORMATS = ["Test", "ODI", "T20I", "IPL", "T20"] as const;
export type Format = (typeof FORMATS)[number];

export const FORMAT_LABEL: Record<Format, string> = {
  Test: "Test",
  ODI: "ODI",
  T20I: "T20I",
  IPL: "IPL",
  T20: "All T20",
};

export type Role = "BAT" | "BOWL" | "AR" | "WK";
export const ROLE_LABEL: Record<Role, string> = {
  BAT: "Batter",
  BOWL: "Bowler",
  AR: "All-rounder",
  WK: "Wicketkeeper",
};

export interface PlayerSummary {
  id: string;
  name: string;
  full_name: string | null;
  unique_name: string | null;
  country: string | null;
  role: Role;
  capped: boolean;
  era_start: number | null;
  era_end: number | null;
  matches: number;
  format_matches: number | null;
  runs: number | null;
  bat_avg: number | null;
  bat_sr: number | null;
  wickets: number | null;
  bowl_econ: number | null;
}

export interface SearchResult {
  total: number;
  items: PlayerSummary[];
}

export interface FormatStats {
  format: Format;
  season?: string;
  matches: number;
  bat_innings: number;
  runs: number;
  balls_faced: number;
  not_outs: number;
  highest: number | null;
  fifties: number;
  hundreds: number;
  fours: number;
  sixes: number;
  bat_avg: number | null;
  bat_sr: number | null;
  bowl_innings: number;
  balls_bowled: number;
  runs_conceded: number;
  wickets: number;
  best_bowling: string | null;
  five_wkts: number;
  bowl_econ: number | null;
  bowl_avg: number | null;
  bowl_sr: number | null;
  bowl_dot_pct: number | null;
  catches: number;
  stumpings: number;
}

export interface PhaseStats {
  format: Format;
  phase: "PP" | "middle" | "death";
  role: "bat" | "bowl";
  balls: number;
  runs: number;
  wickets: number;
  dot_pct: number | null;
  four_pct: number | null;
  six_pct: number | null;
  dismissal_rate: number | null;
  strike_rate: number | null;
  economy: number | null;
}

export interface VenueSplit {
  format: Format;
  venue_id: string;
  venue_name: string;
  city: string | null;
  bat_innings: number;
  runs: number;
  balls_faced: number;
  highest: number | null;
  bat_avg: number | null;
  bat_sr: number | null;
  balls_bowled: number;
  runs_conceded: number;
  wickets: number;
  bowl_econ: number | null;
}

export interface PlayerProfile {
  player: {
    id: string;
    name: string;
    full_name: string | null;
    unique_name: string | null;
    cricinfo_id: string | null;
    country: string | null;
    role: Role;
    batting_hand: string | null;
    bowling_style: string | null;
    capped: boolean;
    era_start: number | null;
    era_end: number | null;
    matches: number;
  };
  formats: FormatStats[];
  seasons: FormatStats[];
  phases: PhaseStats[];
  dismissals: { format: Format; kind: string; n: number }[];
  venues: VenueSplit[];
}

export interface Metric {
  key: string;
  label: string;
  side: "bat" | "bowl";
  higher_is_better: boolean;
  value: number | null;
  percentile: number | null;
  qualified: boolean;
}

export interface Comparison {
  format: Format;
  from_year: number | null;
  to_year: number | null;
  min_balls_for_percentiles: number;
  min_sample_to_rank: number;
  players: {
    id: string;
    name: string;
    full_name: string | null;
    country: string | null;
    role: Role;
    totals: Record<string, number>;
    metrics: Metric[];
  }[];
}

export interface VenueSummary {
  id: string;
  name: string;
  city: string | null;
  matches: number;
}

export interface VenueFormat {
  format: Format;
  matches: number;
  first_year: number | null;
  last_year: number | null;
  avg_first_innings: number | null;
  avg_first_innings_recent: number | null;
  matches_recent: number | null;
  avg_first_innings_wickets: number | null;
  chasing_win_pct: number | null;
  toss_winner_wins_pct: number | null;
  toss_choose_field_pct: number | null;
  highest_total: number | null;
  lowest_all_out_first_innings: number | null;
}

export interface VenuePage {
  venue: VenueSummary & { first_match: string; last_match: string };
  formats: VenueFormat[];
  top_batters: {
    id: string; name: string; full_name: string | null; country: string | null; format: Format;
    bat_innings: number; runs: number; highest: number | null; bat_avg: number | null; bat_sr: number | null;
  }[];
  top_bowlers: {
    id: string; name: string; full_name: string | null; country: string | null; format: Format;
    balls_bowled: number; wickets: number; runs_conceded: number; bowl_econ: number | null;
  }[];
}

export class NotFound extends Error {}

export async function api<T>(path: string, params: Record<string, string | number | undefined | null> = {}): Promise<T> {
  const url = new URL(API_URL + path);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  // Stats change weekly: cache for an hour in production, never in development.
  const res = await fetch(url, { next: { revalidate: process.env.NODE_ENV === "production" ? 3600 : 0 } });
  if (res.status === 404) throw new NotFound(path);
  if (!res.ok) throw new Error(`API ${res.status} for ${url.pathname}`);
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------- formatting

export function fmt(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "–";
  return v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function overs(balls: number): string {
  return `${Math.floor(balls / 6)}${balls % 6 ? "." + (balls % 6) : ""}`;
}

/** Full name from Wikidata when known, else Cricsheet's initials form. */
export function displayName(p: { name: string; full_name?: string | null }): string {
  return p.full_name || p.name;
}

export function span(a: number | null, b: number | null): string {
  if (!a) return "";
  return a === b || !b ? String(a) : `${a}–${b}`;
}

/** The format a player is best known for: most matches, skipping the all-T20 total. */
export function mainFormat(formats: { format: Format; matches: number }[]): Format | undefined {
  const own = formats.filter((f) => f.format !== "T20");
  const pool = own.length ? own : formats;
  return pool.sort((a, b) => b.matches - a.matches)[0]?.format;
}
