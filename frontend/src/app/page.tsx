"use client";
import { useState, useEffect, useRef, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useAccountContext } from "@/lib/AccountContext";
import { useSyncStatus } from "@/hooks/useSyncStatus";
import { SyncBanner } from "@/components/SyncBanner";
import { MetricCard } from "@/components/MetricCard";
import { DataTable } from "@/components/DataTable";
import { SendersBar } from "@/components/charts/SendersBar";
import { CategoryBar } from "@/components/charts/CategoryBar";
import { TimelineLine } from "@/components/charts/TimelineLine";
import { api } from "@/lib/api";
import type { OverallStats, SenderInfo, CategoryInfo, TimelineBucket } from "@/lib/types";
import { fmtCount, fmtDate, fmtSize } from "@/lib/format";

// ---------------------------------------------------------------------------
// Login page — shown when no account is connected
// ---------------------------------------------------------------------------

function LoginPage({ connect }: { connect: () => Promise<void> }) {
  return (
    <div className="flex-1 flex items-center justify-center min-h-screen">
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 px-10 py-12 max-w-sm w-full text-center">
        <h1 className="text-2xl font-bold mb-2">Gmail Cleaner</h1>
        <p className="text-gray-500 text-sm mb-8">
          Connect your Gmail account to visualize and reclaim storage.
        </p>
        <button
          onClick={connect}
          className="w-full px-4 py-2 rounded bg-blue-600 text-white font-medium hover:bg-blue-700 transition-colors"
        >
          Connect Account
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dashboard — shown when logged in
// ---------------------------------------------------------------------------

function Dashboard({ account }: { account: string }) {
  const { status, startSync } = useSyncStatus(account);
  const [stats, setStats] = useState<OverallStats | null>(null);
  const [senders, setSenders] = useState<SenderInfo[]>([]);
  const [categories, setCategories] = useState<CategoryInfo[]>([]);
  const [timeline, setTimeline] = useState<TimelineBucket[]>([]);
  const [senderMode, setSenderMode] = useState<"count" | "size">("count");
  const [senderLimit, setSenderLimit] = useState(20);
  const [timelineMode, setTimelineMode] = useState<"count" | "size">("count");
  const [loading, setLoading] = useState(false);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDashboard = () => {
    setLoading(true);
    Promise.all([
      api.dashboard.stats(account).then(setStats),
      api.dashboard.topSenders(account, senderMode, senderLimit).then(setSenders),
      api.dashboard.categories(account).then(setCategories),
      api.dashboard.timeline(account).then(setTimeline),
    ]).finally(() => {
      setLoading(false);
      setLastRefreshed(new Date());
    });
  };

  // Initial fetch and when sort/limit changes
  useEffect(() => {
    fetchDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account, senderMode, senderLimit]);

  // Auto-refresh every 30s while sync is running
  useEffect(() => {
    if (status?.is_syncing) {
      intervalRef.current = setInterval(fetchDashboard, 30_000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.is_syncing]);

  return (
    <div className="p-8 max-w-5xl">
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold mb-1">Dashboard</h1>
          <p className="text-xs text-gray-400">{account}</p>
        </div>
        {lastRefreshed && status?.is_syncing && (
          <p className="text-xs text-gray-400 mt-1">
            Data refreshed at {lastRefreshed.toLocaleTimeString()}
          </p>
        )}
      </div>

      <div className="mb-6">
        <SyncBanner status={status} onStartSync={startSync} />
      </div>

      {loading && <p className="text-sm text-gray-400 mb-4">Loading...</p>}

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <MetricCard label="Total emails" value={fmtCount(stats.total_count)} />
          <MetricCard label="Total size" value={fmtSize(stats.total_size)} />
          <MetricCard label="Unread" value={fmtCount(stats.unread_count)} />
          <MetricCard label="Starred" value={fmtCount(stats.starred_count)} />
          <MetricCard label="Cache size" value={fmtSize(stats.db_size_bytes)} />
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

// ---------------------------------------------------------------------------
// Root page — login or dashboard based on auth state
// ---------------------------------------------------------------------------

function HomeInner() {
  const { activeAccount, loading, connect, refresh } = useAccountContext();
  const searchParams = useSearchParams();

  useEffect(() => {
    if (searchParams.get("auth") === "success") {
      refresh();
      window.history.replaceState({}, "", "/");
    }
  }, [searchParams, refresh]);

  if (loading) {
    return <div className="p-8 text-gray-400 text-sm">Loading...</div>;
  }

  if (!activeAccount) {
    return <LoginPage connect={connect} />;
  }

  return <Dashboard account={activeAccount} />;
}

export default function Home() {
  return (
    <Suspense>
      <HomeInner />
    </Suspense>
  );
}
