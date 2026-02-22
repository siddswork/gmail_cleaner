"use client";
import type { SyncStatus } from "@/lib/types";
import { fmtCount, fmtDate } from "@/lib/format";

interface Props {
  status: SyncStatus | null;
  onStartSync: () => void;
}

export function SyncBanner({ status, onStartSync }: Props) {
  if (!status) return null;

  if (status.is_syncing) {
    return (
      <div className="rounded bg-blue-50 border border-blue-200 px-4 py-3 text-sm flex items-center gap-3">
        <span className="inline-block w-3 h-3 rounded-full bg-blue-500 animate-pulse" />
        <span>
          Syncing... {fmtCount(status.total_synced)} emails cached so far.
        </span>
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
      <div className="rounded bg-green-50 border border-green-200 px-4 py-3 text-sm flex items-center justify-between">
        <span>
          {fmtCount(status.total_synced)} emails cached. Last sync:{" "}
          {fmtDate(status.last_full_sync_ts)}.
        </span>
        <button
          onClick={onStartSync}
          className="ml-4 px-3 py-1 rounded bg-green-600 text-white text-xs font-medium hover:bg-green-700"
        >
          Sync now
        </button>
      </div>
    );
  }

  return null;
}
