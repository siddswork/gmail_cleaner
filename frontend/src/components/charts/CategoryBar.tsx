"use client";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import type { CategoryInfo } from "@/lib/types";
import { cleanCategory, fmtSize, fmtCount } from "@/lib/format";

interface Props {
  data: CategoryInfo[];
  mode: "count" | "size";
}

export function CategoryBar({ data, mode }: Props) {
  const chartData = data.map((c) => ({
    name: cleanCategory(c.category),
    value: mode === "count" ? c.count : c.total_size,
  }));

  const fmt = mode === "count" ? fmtCount : fmtSize;

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData} margin={{ left: 8, right: 20, bottom: 8 }}>
        <XAxis dataKey="name" tick={{ fontSize: 11 }} />
        <YAxis tickFormatter={(v) => fmt(v)} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v) => fmt(Number(v))} />
        <Bar dataKey="value" fill="#8B5CF6" radius={[3, 3, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
