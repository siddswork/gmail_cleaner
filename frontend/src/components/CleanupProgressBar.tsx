"use client";
import { useRef, useEffect } from "react";
import type { CleanupJob } from "@/lib/types";
import { fmtCount, fmtSize } from "@/lib/format";

interface Props {
  job: CleanupJob;
  onStop: () => void;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return "< 1 min";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.round((seconds % 3600) / 60);
  return `${hrs} hr ${mins} min`;
}

export function CleanupProgressBar({ job, onStop }: Props) {
  const pct = job.total > 0 ? Math.round((job.processed / job.total) * 100) : 0;
  const isDone = job.status !== "running";
  const startedAtRef = useRef<number>(Date.now());

  // Reset start time when a new job begins running
  useEffect(() => {
    if (job.status === "running" && job.processed === 0) {
      startedAtRef.current = Date.now();
    }
  }, [job.status, job.processed]);

  let etaText: string | null = null;
  if (!isDone && job.processed > 0 && pct >= 5 && pct < 100) {
    const elapsed = (Date.now() - startedAtRef.current) / 1000;
    const rate = job.processed / elapsed;
    const remaining = (job.total - job.processed) / rate;
    etaText = `~${formatDuration(remaining)} remaining`;
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-sm text-gray-700">
        Trashed {fmtCount(job.trashed)} of {fmtCount(job.total)}{" "}
        <span className="text-gray-400">({pct}%)</span>
        {etaText && <span className="ml-2 text-gray-500">— {etaText}</span>}
        {job.size_reclaimed > 0 && (
          <span className="ml-2 text-gray-500">— {fmtSize(job.size_reclaimed)} reclaimed</span>
        )}
      </p>

      <div className="w-full bg-gray-200 rounded-full h-2">
        <div
          className="bg-blue-600 h-2 rounded-full transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      {!isDone && (
        <button
          onClick={onStop}
          className="self-start px-3 py-1.5 rounded border border-red-300 text-red-600 text-sm hover:bg-red-50"
        >
          Stop
        </button>
      )}

      {job.status === "stopped" && (
        <p className="text-sm text-amber-700">
          Stopped early — {fmtCount(job.trashed)} emails trashed.
        </p>
      )}

      {job.errors > 0 && (
        <p className="text-xs text-red-600">{job.errors} errors encountered.</p>
      )}
    </div>
  );
}
