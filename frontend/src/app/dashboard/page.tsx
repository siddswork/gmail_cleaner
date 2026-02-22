"use client";
import { useState, useEffect } from "react";
import { useAccounts } from "@/hooks/useAccounts";
import { api } from "@/lib/api";
import type { OverallStats, SenderInfo, CategoryInfo, TimelineBucket } from "@/lib/types";
import { MetricCard } from "@/components/MetricCard";
import { DataTable } from "@/components/DataTable";
import { SendersBar } from "@/components/charts/SendersBar";
import { CategoryBar } from "@/components/charts/CategoryBar";
import { TimelineLine } from "@/components/charts/TimelineLine";
import { fmtCount, fmtDate, fmtSize } from "@/lib/format";

export default function DashboardPage() {
  const { activeAccount } = useAccounts();
  const [stats, setStats] = useState<OverallStats | null>(null);
  const [senders, setSenders] = useState<SenderInfo[]>([]);
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [timeline, setTimeline] = useState<TimelineBucket[]>([]);
  const [senderMode, setSenderMode] = useState<"count" | "size">("count");
  const [senderLimit, setSenderLimit] = useState(20);
  const [timelineMode, setTimelineMode] = useState<"count" | "size">("count");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!activeAccount) return;
    setLoading(true);
    Promise.all([
      api.dashboard.stats(activeAccount).then(setStats),
      api.dashboard.topSenders(activeAccount, senderMode, senderLimit).then(setSenders),
      api.dashboard.categories(activeAccount).then(setCategories),
      api.dashboard.timeline(activeAccount).then(setTimeline),
    ]).finally(() => setLoading(false));
  }, [activeAccount, senderMode, senderLimit]);

  if (!activeAccount) {
    return <div className="p-8 text-gray-500">Connect a Gmail account from the Home page first.</div>;
  }

  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-2xl font-bold mb-1">Dashboard</h1>
      <p className="text-xs text-gray-400 mb-6">{activeAccount}</p>

      {loading && <p className="text-sm text-gray-400 mb-4">Loading...</p>}

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <MetricCard label="Total emails" value={fmtCount(stats.total_count)} />
          <MetricCard label="Total size" value={fmtSize(stats.total_size)} />
          <MetricCard label="Unread" value={fmtCount(stats.unread_count)} />
          <MetricCard label="Starred" value={fmtCount(stats.starred_count)} />
          <MetricCard label="Oldest email" value={fmtDate(stats.oldest_ts)} />
          <MetricCard label="Newest email" value={fmtDate(stats.newest_ts)} />
          <MetricCard label="Read" value={fmtCount(stats.read_count)} />
          <MetricCard label="Important" value={fmtCount(stats.important_count)} />
        </div>
      )}

      <section className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Top Senders</h2>
          <div className="flex gap-2">
            <select
              value={senderMode}
              onChange={(e) => setSenderMode(e.target.value as "count" | "size")}
              className="border border-gray-300 rounded px-2 py-1 text-xs"
            >
              <option value="count">By count</option>
              <option value="size">By size</option>
            </select>
            <select
              value={senderLimit}
              onChange={(e) => setSenderLimit(Number(e.target.value))}
              className="border border-gray-300 rounded px-2 py-1 text-xs"
            >
              {[10, 20, 50].map((n) => (
                <option key={n} value={n}>Top {n}</option>
              ))}
            </select>
          </div>
        </div>
        <SendersBar data={senders} mode={senderMode} />
        <div className="mt-4">
          <DataTable
            data={senders}
            columns={[
              { key: "sender_email", header: "Email" },
              { key: "sender_name", header: "Name" },
              { key: "count", header: "Emails", render: (r) => fmtCount(r.count as number) },
              { key: "total_size", header: "Size", render: (r) => fmtSize(r.total_size as number) },
            ]}
          />
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-3">By Category</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <p className="text-xs text-gray-500 mb-2">Email count</p>
            <CategoryBar data={categories} mode="count" />
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-2">Total size</p>
            <CategoryBar data={categories} mode="size" />
          </div>
        </div>
      </section>

      <section className="mb-8">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold">Storage Over Time</h2>
          <select
            value={timelineMode}
            onChange={(e) => setTimelineMode(e.target.value as "count" | "size")}
            className="border border-gray-300 rounded px-2 py-1 text-xs"
          >
            <option value="count">Email count</option>
            <option value="size">Size</option>
          </select>
        </div>
        <TimelineLine data={timeline} mode={timelineMode} />
      </section>
    </div>
  );
}
