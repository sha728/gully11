"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar,
  RadarChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

/** Read design tokens from CSS so charts follow light/dark mode. */
function useTokens() {
  const read = () => {
    if (typeof window === "undefined") return null;
    const s = getComputedStyle(document.documentElement);
    const v = (n: string) => s.getPropertyValue(n).trim();
    return { a: v("--a-series"), b: v("--b-series"), muted: v("--muted"), border: v("--border"),
             surface: v("--surface"), text: v("--text") };
  };
  const [t, setT] = useState<ReturnType<typeof read>>(null);
  useEffect(() => {
    setT(read());
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const on = () => setT(read());
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return t;
}

export interface SeasonPoint {
  season: string;
  runs: number;
  bat_avg: number | null;
  bat_sr: number | null;
  wickets: number;
  bowl_econ: number | null;
}

/** Season-by-season form: batting average + strike rate, or wickets + economy. */
export function SeasonChart({ data, showBowling }: { data: SeasonPoint[]; showBowling: boolean }) {
  const t = useTokens();
  const [side, setSide] = useState<"bat" | "bowl">("bat");
  if (!t) return <div className="h-64" />;
  const bat = side === "bat";
  const left = bat ? "bat_avg" : "wickets";
  const right = bat ? "bat_sr" : "bowl_econ";
  const labels: Record<string, string> = {
    bat_avg: "Average", bat_sr: "Strike rate", wickets: "Wickets", bowl_econ: "Economy",
  };
  return (
    <div>
      {showBowling && (
        <div className="mb-3 flex gap-1 text-xs">
          {(["bat", "bowl"] as const).map((s) => (
            <button key={s} onClick={() => setSide(s)}
              className={`rounded-md px-2.5 py-1 ${side === s ? "bg-accent-soft font-medium text-text" : "text-muted hover:text-text"}`}>
              {s === "bat" ? "Batting" : "Bowling"}
            </button>
          ))}
        </div>
      )}
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 5, bottom: 0, left: -15 }}>
            <CartesianGrid stroke={t.border} strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="season" tick={{ fill: t.muted, fontSize: 11 }} stroke={t.border} />
            <YAxis yAxisId="l" tick={{ fill: t.muted, fontSize: 11 }} stroke={t.border} />
            <YAxis yAxisId="r" orientation="right" tick={{ fill: t.muted, fontSize: 11 }} stroke={t.border} />
            <Tooltip
              contentStyle={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 8, fontSize: 12 }}
              labelStyle={{ color: t.text }}
              formatter={(v: number, k: string) => [v == null ? "–" : Number(v).toFixed(k === "wickets" ? 0 : 2), labels[k]]}
            />
            <Legend formatter={(k: string) => <span style={{ color: t.muted, fontSize: 12 }}>{labels[k]}</span>} />
            <Line yAxisId="l" type="monotone" dataKey={left} stroke={t.a} strokeWidth={2} dot={{ r: 3 }} connectNulls />
            <Line yAxisId="r" type="monotone" dataKey={right} stroke={t.b} strokeWidth={2} dot={{ r: 3 }} connectNulls />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export interface RadarRow {
  label: string;
  a: number | null;
  b: number | null;
}

/** Percentile radar for two players (0-100, higher = better on every axis). */
export function CompareRadar({ data, nameA, nameB }: { data: RadarRow[]; nameA: string; nameB: string }) {
  const t = useTokens();
  if (!t) return <div className="h-80" />;
  return (
    <div className="h-80">
      <ResponsiveContainer width="100%" height="100%">
        <RadarChart data={data} outerRadius="62%" margin={{ top: 10, right: 30, bottom: 10, left: 30 }}>
          <PolarGrid stroke={t.border} />
          <PolarAngleAxis dataKey="label" tick={{ fill: t.muted, fontSize: 11 }} />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Radar name={nameA} dataKey="a" stroke={t.a} fill={t.a} fillOpacity={0.25} />
          <Radar name={nameB} dataKey="b" stroke={t.b} fill={t.b} fillOpacity={0.2} />
          <Legend formatter={(n: string) => <span style={{ color: t.text, fontSize: 12 }}>{n}</span>} />
          <Tooltip
            contentStyle={{ background: t.surface, border: `1px solid ${t.border}`, borderRadius: 8, fontSize: 12 }}
            formatter={(v: number) => [v == null ? "–" : `${Math.round(v)}th percentile`]}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}
