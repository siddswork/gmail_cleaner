"use client";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { SenderInfo } from "@/lib/types";
import { fmtSize, fmtCount } from "@/lib/format";

interface Props {
  data: SenderInfo[];
  mode: "count" | "size";
}

export function SendersBar({ data, mode }: Props) {
  const chartData = data.map((s) => ({
    name: s.sender_email.split("@")[0],
    email: s.sender_email,
    value: mode === "count" ? s.count : s.total_size,
  }));

  const fmt = mode === "count" ? fmtCount : fmtSize;

  const height = Math.max(350, chartData.length * 24);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 40 }}>
        <XAxis type="number" tickFormatter={(v) => fmt(v)} tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 11 }} width={100} />
        <Tooltip
          formatter={(v, _, p) => [fmt(Number(v)), p.payload.email]}
          labelFormatter={() => ""}
        />
        <Bar dataKey="value" fill="#3B82F6" radius={[0, 3, 3, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
