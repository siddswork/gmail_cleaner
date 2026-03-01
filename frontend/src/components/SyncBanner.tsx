"use client";
import { useState } from "react";
import type { SyncStatus } from "@/lib/types";
import { fmtCount, fmtDate } from "@/lib/format";

interface Props {
  status: SyncStatus | null;
  onStartSync: () => void;
  onForceSync: () => void;
}

function fmtEta(seconds: number): string {
  if (seconds < 60) return "< 1 min remaining";
  const mins = Math.round(seconds / 60);
  if (mins < 60) return `~${mins} min remaining`;
  const hrs = Math.floor(mins / 60);
  const remMins = mins % 60;
  return remMins > 0 ? `~${hrs}h ${remMins}min remaining` : `~${hrs}h remaining`;
}

export function SyncBanner({ status, onStartSync, onForceSync }: Props) {
  const [showConfirm, setShowConfirm] = useState(false);

  if (!status) return null;

  if (status.is_syncing) {
    const hasTotal = status.messages_total != null && status.messages_total > 0;
    const pct = hasTotal ? Math.min(100, Math.round((status.total_synced / status.messages_total!) * 100)) : null;

    let eta: string | null = null;
    if (hasTotal && status.sync_started_ts != null && status.synced_this_run > 0) {
      const elapsed = Date.now() / 1000 - status.sync_started_ts;
      const rate = status.synced_this_run / elapsed;  // emails/sec fetched in this run only
      const remaining = (status.messages_total! - status.total_synced) / rate;
      if (remaining > 0 && isFinite(remaining)) {
        eta = fmtEta(remaining);
      }
    }

    return (
      <div className="rounded bg-blue-50 border border-blue-200 px-4 py-3 text-sm">
        <div className="flex items-center gap-3 mb-2">
          <span className="inline-block w-3 h-3 rounded-full bg-blue-500 animate-pulse shrink-0" />
          <span>
            {hasTotal
              ? `Syncing… ${fmtCount(status.total_synced)} / ${fmtCount(status.messages_total!)} emails (${pct}%)`
              : `Syncing… ${fmtCount(status.total_synced)} emails cached so far.`}
          </span>
          {eta && <span className="ml-auto text-xs text-blue-500">{eta}</span>}
        </div>
        {pct != null && (
          <div className="w-full bg-blue-200 rounded-full h-1.5">
            <div
              className="bg-blue-500 h-1.5 rounded-full transition-all duration-500"
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
      </div>
    );
  }

  if (status.needs_full_sync) {
    return (
      <div className="rounded bg-amber-50 border border-amber-200 px-4 py-3 text-sm flex items-center justify-between">
        <span>No sync yet. Initial sync takes 90–120 minutes for a large mailbox.</span>
        <button
          onClick={onStartSync}
          className="ml-4 px-3 py-1 rounded bg-amber-500 text-white text-xs font-medium hover:bg-amber-600"
        >
          Start sync
        </button>
      </div>
    );
  }

  if (status.is_complete) {
    return (
      <div className="rounded bg-green-50 border border-green-200 px-4 py-3 text-sm">
        <div className="flex items-center justify-between">
          <span>
            {fmtCount(status.total_synced)} emails cached. Last sync:{" "}
            {fmtDate(status.last_full_sync_ts)}.
          </span>
          <div className="flex items-center gap-2 ml-4">
            <button
              onClick={onStartSync}
              className="px-3 py-1 rounded bg-green-600 text-white text-xs font-medium hover:bg-green-700"
            >
              Sync now
            </button>
            <button
              onClick={() => setShowConfirm(true)}
              className="px-3 py-1 rounded border border-red-400 text-red-600 text-xs font-medium hover:bg-red-50"
            >
              Force full re-sync
            </button>
          </div>
        </div>
        {showConfirm && (
          <div className="mt-3 p-3 rounded bg-red-50 border border-red-200 text-xs">
            <p className="mb-2 text-red-700 font-medium">
              This will clear your local cache and re-sync all emails from Gmail. This takes 90–120 minutes. Continue?
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => { setShowConfirm(false); onForceSync(); }}
                className="px-3 py-1 rounded bg-red-600 text-white font-medium hover:bg-red-700"
              >
                Yes, re-sync everything
              </button>
              <button
                onClick={() => setShowConfirm(false)}
                className="px-3 py-1 rounded border border-gray-300 text-gray-600 hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    );
  }

  return null;
}
