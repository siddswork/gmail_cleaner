"use client";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";
import type { ReadRateSender } from "@/lib/types";

interface Props {
  data: ReadRateSender[];
}

export function ReadRateBar({ data }: Props) {
  const chartData = data.slice(0, 30).map((s) => ({
    name: s.sender_email.split("@")[0],
    email: s.sender_email,
    rate: Math.round(s.read_rate * 100),
  }));

  return (
    <ResponsiveContainer width="100%" height={Math.max(300, chartData.length * 22)}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 50 }}>
        <XAxis type="number" domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="name" tick={{ fontSize: 10 }} width={100} />
        <Tooltip
          formatter={(v, _, p) => [`${Number(v)}%`, p.payload.email]}
          labelFormatter={() => ""}
        />
        <Bar dataKey="rate" radius={[0, 3, 3, 0]}>
          {chartData.map((d, i) => (
            <Cell
              key={i}
              fill={d.rate >= 50 ? `rgba(34, ${Math.round(180 * d.rate / 100)}, 80, 0.8)` : `rgba(${Math.round(255 * (1 - d.rate / 100))}, 80, 80, 0.8)`}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
