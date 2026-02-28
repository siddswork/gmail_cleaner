"use client";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useAccounts } from "@/hooks/useAccounts";
import { useCleanup } from "@/hooks/useCleanup";
import { useSyncStatus } from "@/hooks/useSyncStatus";
import { api } from "@/lib/api";
import type { SenderInfo, SmartSweepSender } from "@/lib/types";
import { FilterPanel } from "@/components/FilterPanel";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { CleanupProgressBar } from "@/components/CleanupProgressBar";
import { MetricCard } from "@/components/MetricCard";
import { fmtCount, fmtSize, fmtPct } from "@/lib/format";

const LARGE_BATCH_THRESHOLD = 500;
const TABS = ["Bulk Senders", "Smart Sweep", "Advanced"] as const;
type Tab = (typeof TABS)[number];

type SortKey = "sender" | "count" | "size";
type SweepSortKey = SortKey | "read_rate";
type SortDir = "asc" | "desc";

function sortArrow(active: boolean, dir: SortDir) {
  if (!active) return null;
  return <span className="ml-0.5">{dir === "asc" ? "\u25B2" : "\u25BC"}</span>;
}

export default function CleanupPage() {
  const { activeAccount } = useAccounts();
  const { state, preview, job, error, doPreview, doSmartSweepPreview, doExecute, doStop, reset } =
    useCleanup(activeAccount);
  const { status: syncStatus } = useSyncStatus(activeAccount);
  const router = useRouter();

  const isSyncing = syncStatus?.is_syncing ?? false;

  const [activeTab, setActiveTab] = useState<Tab>("Bulk Senders");

  // Bulk Senders tab
  const [topSenders, setTopSenders] = useState<SenderInfo[]>([]);
  const [selectedSenders, setSelectedSenders] = useState<Set<string>>(new Set());

  // Smart Sweep tab
  const [sweepSenders, setSweepSenders] = useState<SmartSweepSender[]>([]);
  const [sweepLoading, setSweepLoading] = useState(false);
  const [selectedSweepEmails, setSelectedSweepEmails] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!activeAccount) {
      router.replace("/");
      return;
    }
    api.dashboard.topSenders(activeAccount, "count", 50).then(setTopSenders).catch(() => {});
  }, [activeAccount, router]);

  // Load smart sweep senders when that tab is opened
  useEffect(() => {
    if (activeTab !== "Smart Sweep" || !activeAccount) return;
    setSweepLoading(true);
    api.cleanup
      .smartSweep(activeAccount)
      .then(setSweepSenders)
      .catch(() => {})
      .finally(() => setSweepLoading(false));
  }, [activeTab, activeAccount]);

  if (!activeAccount) return null;

  const isRunning = state === "running";

  const toggleSender = (email: string) => {
    setSelectedSenders((prev) => {
      const next = new Set(prev);
      if (next.has(email)) next.delete(email);
      else next.add(email);
      return next;
    });
  };

  const toggleSweepEmail = (email: string) => {
    setSelectedSweepEmails((prev) => {
      const next = new Set(prev);
      if (next.has(email)) next.delete(email);
      else next.add(email);
      return next;
    });
  };

  const refreshData = () => {
    api.dashboard.topSenders(activeAccount, "count", 50).then(setTopSenders).catch(() => {});
    if (activeTab === "Smart Sweep") {
      setSweepLoading(true);
      api.cleanup.smartSweep(activeAccount).then(setSweepSenders).catch(() => {}).finally(() => setSweepLoading(false));
    }
  };

  const handleReset = () => {
    reset();
    setSelectedSenders(new Set());
    setSelectedSweepEmails(new Set());
    refreshData();
  };

  return (
    <div className="p-8 max-w-6xl">
      <h1 className="text-2xl font-bold mb-1">Cleanup</h1>
      <p className="text-xs text-gray-400 mb-4">{activeAccount}</p>

      <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 mb-6">
        Starred and important emails are always excluded and will never be trashed.
      </p>

      {isSyncing && (
        <p className="text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded px-3 py-2 mb-6">
          Sync is in progress — cleanup is disabled until sync completes.
        </p>
      )}

      {/* Tab bar */}
      <div className="flex border-b border-gray-200 mb-8">
        {TABS.map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            disabled={isRunning}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors disabled:opacity-40 ${
              activeTab === tab
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-600 hover:text-gray-900"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        {/* Left: tab-specific content */}
        <div>
          {activeTab === "Bulk Senders" && (
            <BulkSendersTab
              senders={topSenders}
              selected={selectedSenders}
              onToggle={toggleSender}
              onSelectAll={() =>
                setSelectedSenders(new Set(topSenders.map((s) => s.sender_email)))
              }
              onClearAll={() => setSelectedSenders(new Set())}
              onPreview={() => doSmartSweepPreview(Array.from(selectedSenders))}
              loading={state === "previewing"}
              disabled={isRunning || isSyncing}
            />
          )}

          {activeTab === "Smart Sweep" && (
            <SmartSweepTab
              senders={sweepSenders}
              loading={sweepLoading}
              selected={selectedSweepEmails}
              onToggle={toggleSweepEmail}
              onSelectAll={() =>
                setSelectedSweepEmails(new Set(sweepSenders.map((s) => s.sender_email)))
              }
              onClearAll={() => setSelectedSweepEmails(new Set())}
              onPreview={() => doSmartSweepPreview(Array.from(selectedSweepEmails))}
              previewLoading={state === "previewing"}
              disabled={isRunning || isSyncing}
            />
          )}

          {activeTab === "Advanced" && (
            <FilterPanel
              senders={topSenders}
              onPreview={doPreview}
              loading={state === "previewing" || isRunning || isSyncing}
            />
          )}
        </div>

        {/* Right: shared workflow panel */}
        <div>
          {error && (
            <div className="mb-4 p-3 rounded border border-red-200 bg-red-50 text-sm text-red-700">
              {error}
            </div>
          )}

          {state === "previewing" && (
            <div className="flex items-center gap-2 text-sm text-gray-500 pt-4">
              <span className="inline-block w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
              Loading preview...
            </div>
          )}

          {(state === "confirming" || state === "running" || state === "done" || state === "error") && preview && (
            <>
              <div className="grid grid-cols-2 gap-4 mb-6">
                {(state === "running" || state === "done" || state === "error") && job ? (
                  <>
                    <MetricCard label="Emails to trash" value={fmtCount(job.total)} />
                    <MetricCard label="Space reclaimed" value={fmtSize(job.size_reclaimed)} />
                  </>
                ) : (
                  <>
                    <MetricCard label="Emails to trash" value={fmtCount(preview.count)} />
                    <MetricCard label="Space to reclaim" value={fmtSize(preview.total_size)} />
                  </>
                )}
              </div>

              {state === "confirming" && (
                <ConfirmDialog
                  count={preview.count}
                  totalSize={preview.total_size}
                  isLargeBatch={preview.count > LARGE_BATCH_THRESHOLD}
                  onConfirm={(word) => doExecute(word)}
                  onCancel={handleReset}
                />
              )}

              {state === "running" && job && (
                <CleanupProgressBar job={job} onStop={doStop} />
              )}

              {state === "done" && job && (
                <div className="p-4 rounded-lg border border-green-200 bg-green-50">
                  <p className="font-semibold text-green-800 mb-1">
                    {job.status === "stopped" ? "Stopped" : "Done"}
                  </p>
                  <p className="text-sm text-green-700">
                    Trashed {fmtCount(job.trashed)} emails — reclaimed {fmtSize(job.size_reclaimed)}.
                    {job.errors > 0 && ` ${job.errors} errors.`}
                  </p>
                  <button onClick={handleReset} className="mt-2 text-xs text-green-600 underline">
                    Start over
                  </button>
                </div>
              )}

              {state === "error" && (
                <div className="p-4 rounded-lg border border-red-200 bg-red-50">
                  <p className="font-semibold text-red-800 mb-1">Cleanup failed</p>
                  <p className="text-sm text-red-700">
                    {job ? `Trashed ${fmtCount(job.trashed)} emails before the error.` : "An error occurred."}
                  </p>
                  <button onClick={handleReset} className="mt-2 text-xs text-red-600 underline">
                    Start over
                  </button>
                </div>
              )}
            </>
          )}

          {state === "idle" && (
            <p className="text-sm text-gray-400 pt-4">
              Select a sender or configure filters to preview emails for deletion.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Bulk Senders tab (multi-select with search/sort)
// ---------------------------------------------------------------------------

interface BulkSendersTabProps {
  senders: SenderInfo[];
  selected: Set<string>;
  onToggle: (email: string) => void;
  onSelectAll: () => void;
  onClearAll: () => void;
  onPreview: () => void;
  loading: boolean;
  disabled: boolean;
}

function BulkSendersTab({
  senders,
  selected,
  onToggle,
  onSelectAll,
  onClearAll,
  onPreview,
  loading,
  disabled,
}: BulkSendersTabProps) {
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SortKey>("count");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const handleSort = (key: SortKey) => {
    if (sortBy === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortBy(key); setSortDir("desc"); }
  };

  const filtered = useMemo(() => {
    let list = senders;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((s) => s.sender_email.toLowerCase().includes(q));
    }
    return [...list].sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      if (sortBy === "sender") return dir * a.sender_email.localeCompare(b.sender_email);
      if (sortBy === "count") return dir * (a.count - b.count);
      return dir * (a.total_size - b.total_size);
    });
  }, [senders, search, sortBy, sortDir]);

  const selectedStats = senders
    .filter((s) => selected.has(s.sender_email))
    .reduce((acc, s) => ({ count: acc.count + s.count, size: acc.size + s.total_size }), { count: 0, size: 0 });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500">
          {senders.length} senders loaded.
          {selected.size > 0 && ` ${selected.size} selected — ~${fmtCount(selectedStats.count)} emails, ~${fmtSize(selectedStats.size)}`}
        </p>
        <div className="flex gap-2">
          <button
            onClick={onSelectAll}
            disabled={disabled}
            className="text-xs text-blue-600 hover:underline disabled:opacity-40"
          >
            Select all
          </button>
          <span className="text-gray-300">|</span>
          <button
            onClick={onClearAll}
            disabled={disabled}
            className="text-xs text-gray-500 hover:underline disabled:opacity-40"
          >
            Clear
          </button>
        </div>
      </div>

      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search senders..."
        className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
      />

      <div className="overflow-x-auto max-h-96 overflow-y-auto border border-gray-200 rounded">
        {senders.length === 0 ? (
          <p className="text-sm text-gray-400 text-center py-6">No senders — run a sync first.</p>
        ) : (
          <table className="min-w-full text-sm">
            <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-3 py-2 w-8" />
                <th
                  onClick={() => handleSort("sender")}
                  className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer select-none"
                >
                  Sender{sortArrow(sortBy === "sender", sortDir)}
                </th>
                <th
                  onClick={() => handleSort("count")}
                  className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer select-none"
                >
                  Emails{sortArrow(sortBy === "count", sortDir)}
                </th>
                <th
                  onClick={() => handleSort("size")}
                  className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer select-none"
                >
                  Size{sortArrow(sortBy === "size", sortDir)}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((s) => (
                <tr
                  key={s.sender_email}
                  onClick={() => !disabled && onToggle(s.sender_email)}
                  className={`cursor-pointer transition-colors ${
                    selected.has(s.sender_email)
                      ? "bg-blue-50"
                      : "hover:bg-gray-50"
                  } ${disabled ? "cursor-default" : ""}`}
                >
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selected.has(s.sender_email)}
                      onChange={() => onToggle(s.sender_email)}
                      disabled={disabled}
                      onClick={(e) => e.stopPropagation()}
                      className="rounded"
                    />
                  </td>
                  <td className="px-3 py-2 text-gray-700 truncate max-w-xs">{s.sender_email}</td>
                  <td className="px-3 py-2 text-gray-500 text-right">{fmtCount(s.count)}</td>
                  <td className="px-3 py-2 text-gray-500 text-right">{fmtSize(s.total_size)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <button
        onClick={onPreview}
        disabled={selected.size === 0 || loading || disabled}
        className="px-4 py-2 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-40 self-start"
      >
        {loading ? "Loading..." : `Preview selected (${selected.size})`}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Smart Sweep tab (multi-select with search/sort)
// ---------------------------------------------------------------------------

interface SmartSweepTabProps {
  senders: SmartSweepSender[];
  loading: boolean;
  selected: Set<string>;
  onToggle: (email: string) => void;
  onSelectAll: () => void;
  onClearAll: () => void;
  onPreview: () => void;
  previewLoading: boolean;
  disabled: boolean;
}

function SmartSweepTab({
  senders,
  loading,
  selected,
  onToggle,
  onSelectAll,
  onClearAll,
  onPreview,
  previewLoading,
  disabled,
}: SmartSweepTabProps) {
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState<SweepSortKey>("count");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const handleSort = (key: SweepSortKey) => {
    if (sortBy === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortBy(key); setSortDir("desc"); }
  };

  const filtered = useMemo(() => {
    let list: SmartSweepSender[] = senders;
    if (search) {
      const q = search.toLowerCase();
      list = list.filter((s) => s.sender_email.toLowerCase().includes(q));
    }
    return [...list].sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      if (sortBy === "sender") return dir * a.sender_email.localeCompare(b.sender_email);
      if (sortBy === "count") return dir * (a.count - b.count);
      if (sortBy === "read_rate") return dir * (a.read_rate - b.read_rate);
      return dir * (a.total_size - b.total_size);
    });
  }, [senders, search, sortBy, sortDir]);

  const selectedStats = senders
    .filter((s) => selected.has(s.sender_email))
    .reduce((acc, s) => ({ count: acc.count + s.count, size: acc.size + s.total_size }), { count: 0, size: 0 });

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-500 py-4">
        <span className="inline-block w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
        Analyzing senders...
      </div>
    );
  }

  if (senders.length === 0) {
    return (
      <p className="text-sm text-gray-500 py-4">
        No qualifying senders found. Smart Sweep looks for senders with 5+ promotional emails
        in the last 90 days with a read rate below 30%.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
        Counts and sizes below are for the <strong>last 90 days</strong> only — used to identify
        senders you mostly ignore. Deletion will trash <strong>all</strong> emails from selected
        senders (not just the last 90 days).
      </p>
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500">
          {senders.length} high-volume, low-read-rate senders found.
          {selected.size > 0 && ` ${selected.size} selected — ~${fmtCount(selectedStats.count)} emails, ~${fmtSize(selectedStats.size)} (90-day view)`}
        </p>
        <div className="flex gap-2">
          <button
            onClick={onSelectAll}
            disabled={disabled}
            className="text-xs text-blue-600 hover:underline disabled:opacity-40"
          >
            Select all
          </button>
          <span className="text-gray-300">|</span>
          <button
            onClick={onClearAll}
            disabled={disabled}
            className="text-xs text-gray-500 hover:underline disabled:opacity-40"
          >
            Clear
          </button>
        </div>
      </div>

      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search senders..."
        className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
      />

      <div className="overflow-x-auto max-h-80 overflow-y-auto border border-gray-200 rounded">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-gray-50 border-b border-gray-200">
            <tr>
              <th className="px-3 py-2 w-8" />
              <th
                onClick={() => handleSort("sender")}
                className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer select-none"
              >
                Sender{sortArrow(sortBy === "sender", sortDir)}
              </th>
              <th
                onClick={() => handleSort("count")}
                className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer select-none"
              >
                Emails (90d){sortArrow(sortBy === "count", sortDir)}
              </th>
              <th
                onClick={() => handleSort("size")}
                className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer select-none"
              >
                Size (90d){sortArrow(sortBy === "size", sortDir)}
              </th>
              <th
                onClick={() => handleSort("read_rate")}
                className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wide cursor-pointer select-none"
              >
                Read%{sortArrow(sortBy === "read_rate", sortDir)}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.map((s) => (
              <tr
                key={s.sender_email}
                onClick={() => !disabled && onToggle(s.sender_email)}
                className={`cursor-pointer transition-colors ${
                  selected.has(s.sender_email) ? "bg-blue-50" : "hover:bg-gray-50"
                } ${disabled ? "cursor-default" : ""}`}
              >
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={selected.has(s.sender_email)}
                    onChange={() => onToggle(s.sender_email)}
                    disabled={disabled}
                    onClick={(e) => e.stopPropagation()}
                    className="rounded"
                  />
                </td>
                <td className="px-3 py-2 text-gray-700 truncate max-w-xs">{s.sender_email}</td>
                <td className="px-3 py-2 text-gray-500 text-right">{fmtCount(s.count)}</td>
                <td className="px-3 py-2 text-gray-500 text-right">{fmtSize(s.total_size)}</td>
                <td className="px-3 py-2 text-gray-500 text-right">{fmtPct(s.read_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <button
        onClick={onPreview}
        disabled={selected.size === 0 || previewLoading || disabled}
        className="px-4 py-2 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-40 self-start"
      >
        {previewLoading ? "Loading..." : `Preview selected (${selected.size})`}
      </button>
    </div>
  );
}
