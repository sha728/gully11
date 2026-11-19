"use client";

import { useState } from "react";
import {
  CartesianGrid, Line, LineChart, PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, XAxis, YAxis,
} from "recharts";
import {
  ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent, type ChartConfig,
} from "@/components/ui/chart";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

export interface SeasonPoint {
  season: string;
  runs: number;
  bat_avg: number | null;
  bat_sr: number | null;
  wickets: number;
  bowl_econ: number | null;
}

const seasonConfig = {
  bat_avg: { label: "Average", color: "var(--chart-1)" },
  bat_sr: { label: "Strike rate", color: "var(--chart-2)" },
  wickets: { label: "Wickets", color: "var(--chart-1)" },
  bowl_econ: { label: "Economy", color: "var(--chart-2)" },
} satisfies ChartConfig;

/** Season-by-season form on two axes: average + strike rate, or wickets + economy. */
export function SeasonChart({ data, showBowling, initial = "bat" }: {
  data: SeasonPoint[]; showBowling: boolean; initial?: "bat" | "bowl";
}) {
  const [side, setSide] = useState<"bat" | "bowl">(showBowling ? initial : "bat");
  const [left, right] = side === "bat" ? (["bat_avg", "bat_sr"] as const) : (["wickets", "bowl_econ"] as const);
  return (
    <div>
      {showBowling && (
        <ToggleGroup type="single" value={side} onValueChange={(v) => v && setSide(v as "bat" | "bowl")}
          variant="outline" size="sm" className="mb-4">
          <ToggleGroupItem value="bat" className="font-mono text-[11px] uppercase">Batting</ToggleGroupItem>
          <ToggleGroupItem value="bowl" className="font-mono text-[11px] uppercase">Bowling</ToggleGroupItem>
        </ToggleGroup>
      )}
      <ChartContainer config={seasonConfig} className="aspect-auto h-72 w-full">
        <LineChart accessibilityLayer data={data} margin={{ top: 8, right: 4, bottom: 0, left: 4 }}>
          <CartesianGrid vertical={false} strokeDasharray="2 4" />
          <XAxis dataKey="season" tickLine={false} axisLine={false} tickMargin={8} minTickGap={16}
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10 }} />
          <YAxis yAxisId="l" tickLine={false} axisLine={false} width={36}
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10 }} />
          <YAxis yAxisId="r" orientation="right" tickLine={false} axisLine={false} width={36}
            tick={{ fontFamily: "var(--font-mono)", fontSize: 10 }} />
          <ChartTooltip cursor={{ strokeDasharray: "3 3" }} content={<ChartTooltipContent indicator="line" />} />
          <ChartLegend content={<ChartLegendContent />} />
          <Line isAnimationActive={false} yAxisId="l" dataKey={left} type="monotone" stroke={`var(--color-${left})`} strokeWidth={2.25}
            dot={{ r: 2.5, strokeWidth: 0, fill: `var(--color-${left})` }} activeDot={{ r: 4 }} connectNulls />
          <Line isAnimationActive={false} yAxisId="r" dataKey={right} type="monotone" stroke={`var(--color-${right})`} strokeWidth={2.25}
            strokeDasharray="5 3" dot={false} activeDot={{ r: 4 }} connectNulls />
        </LineChart>
      </ChartContainer>
    </div>
  );
}

export interface RadarRow {
  label: string;
  a: number | null;
  b: number | null;
}

/** Percentile radar for two players (0–100, higher is better on every axis). */
export function CompareRadar({ data, nameA, nameB }: { data: RadarRow[]; nameA: string; nameB: string }) {
  const config = {
    a: { label: nameA, color: "var(--chart-1)" },
    b: { label: nameB, color: "var(--chart-2)" },
  } satisfies ChartConfig;
  return (
    <ChartContainer config={config} className="mx-auto aspect-square max-h-[360px] w-full">
      <RadarChart data={data} outerRadius="66%" margin={{ top: 8, right: 24, bottom: 8, left: 24 }}>
        <ChartTooltip cursor={false} content={<ChartTooltipContent indicator="line"
          formatter={(v, name) => (
            <div className="flex w-full justify-between gap-4">
              <span className="text-muted-foreground">{config[name as "a" | "b"]?.label}</span>
              <span className="font-mono tnum">{v == null ? "–" : `${Math.round(Number(v))}th pct`}</span>
            </div>
          )} />} />
        <PolarGrid gridType="polygon" strokeDasharray="2 4" />
        <PolarAngleAxis dataKey="label" tick={{ fontFamily: "var(--font-mono)", fontSize: 10 }} />
        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
        <Radar isAnimationActive={false} dataKey="a" stroke="var(--color-a)" strokeWidth={2} fill="var(--color-a)" fillOpacity={0.22} />
        <Radar isAnimationActive={false} dataKey="b" stroke="var(--color-b)" strokeWidth={2} fill="var(--color-b)" fillOpacity={0.16} />
        <ChartLegend content={<ChartLegendContent />} />
      </RadarChart>
    </ChartContainer>
  );
}
