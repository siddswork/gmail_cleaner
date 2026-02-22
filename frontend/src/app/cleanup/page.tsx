"use client";
import { useState, useEffect } from "react";
import { useAccounts } from "@/hooks/useAccounts";
import { useCleanup } from "@/hooks/useCleanup";
import { api } from "@/lib/api";
import type { SenderInfo } from "@/lib/types";
import { FilterPanel } from "@/components/FilterPanel";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { DataTable } from "@/components/DataTable";
import { MetricCard } from "@/components/MetricCard";
import { fmtCount, fmtSize } from "@/lib/format";

const LARGE_BATCH_THRESHOLD = 500;

export default function CleanupPage() {
  const { activeAccount } = useAccounts();
  const { state, preview, result, error, doPreview, doExecute, reset } = useCleanup(activeAccount);
  const [topSenders, setTopSenders] = useState<SenderInfo[]>([]);

  useEffect(() => {
    if (!activeAccount) return;
    api.dashboard.topSenders(activeAccount, "count", 50).then(setTopSenders).catch(() => {});
  }, [activeAccount]);

  if (!activeAccount) {
    return <div className="p-8 text-gray-500">Connect a Gmail account from the Home page first.</div>;
  }

  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-2xl font-bold mb-1">Cleanup</h1>
      <p className="text-xs text-gray-400 mb-6">{activeAccount}</p>
      <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2 mb-6">
        Starred and important emails are always excluded and will never be trashed.
      </p>

      {result && (
        <div className="mb-6 p-4 rounded-lg border border-green-200 bg-green-50">
          <p className="font-semibold text-green-800 mb-1">Done</p>
          <p className="text-sm text-green-700">
            Trashed {fmtCount(result.trashed)} emails — reclaimed {fmtSize(result.size_reclaimed)}.
            {result.blocked > 0 && ` ${result.blocked} skipped (starred/important).`}
            {result.errors > 0 && ` ${result.errors} skipped (API error).`}
          </p>
          <button onClick={reset} className="mt-2 text-xs text-green-600 underline">Start over</button>
        </div>
      )}

      {error && (
        <div className="mb-6 p-3 rounded border border-red-200 bg-red-50 text-sm text-red-700">{error}</div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="md:col-span-1">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-600 mb-3">Filters</h2>
          <FilterPanel
            senders={topSenders}
            onPreview={doPreview}
            loading={state === "previewing" || state === "executing"}
          />
        </div>

        <div className="md:col-span-2">
          {(state === "confirming" || state === "executing") && preview && (
            <>
              <div className="grid grid-cols-2 gap-4 mb-6">
                <MetricCard label="Emails to trash" value={fmtCount(preview.count)} />
                <MetricCard label="Space to reclaim" value={fmtSize(preview.total_size)} />
              </div>

              {state === "confirming" && (
                <ConfirmDialog
                  count={preview.count}
                  totalSize={preview.total_size}
                  isLargeBatch={preview.count > LARGE_BATCH_THRESHOLD}
                  onConfirm={(word) => doExecute(word)}
                  onCancel={reset}
                />
              )}

              {state === "executing" && (
                <div className="rounded bg-blue-50 border border-blue-200 px-4 py-3 text-sm flex items-center gap-3">
                  <span className="inline-block w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
                  <span>Syncing, checking labels, and trashing {fmtCount(preview.count)} emails...</span>
                </div>
              )}
            </>
          )}

          {state === "idle" && topSenders.length > 0 && (
            <div>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-gray-600 mb-3">Top Senders</h2>
              <DataTable
                data={topSenders}
                columns={[
                  { key: "sender_email", header: "Email" },
                  { key: "count", header: "Emails", render: (r) => fmtCount(r.count as number) },
                  { key: "total_size", header: "Size", render: (r) => fmtSize(r.total_size as number) },
                ]}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
