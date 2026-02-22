"use client";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { TimelineBucket } from "@/lib/types";
import { fmtSize, fmtCount } from "@/lib/format";

interface Props {
  data: TimelineBucket[];
  mode: "count" | "size";
}

export function TimelineLine({ data, mode }: Props) {
  const chartData = data.map((b) => ({
    period: b.period,
    value: mode === "count" ? b.count : b.total_size,
  }));

  const fmt = mode === "count" ? fmtCount : fmtSize;

  return (
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={chartData} margin={{ left: 8, right: 20 }}>
        <XAxis dataKey="period" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tickFormatter={(v) => fmt(v)} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v) => fmt(Number(v))} />
        <Line type="monotone" dataKey="value" stroke="#3B82F6" dot={false} strokeWidth={2} />
      </LineChart>
    </ResponsiveContainer>
  );
}
