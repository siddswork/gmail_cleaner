"use client";
import { fmtCount, fmtDate, fmtSize } from "@/lib/format";
import type { DeadSubscription } from "@/lib/types";

interface Props {
  sub: DeadSubscription;
  actioned: boolean;
  onPostUnsub: (sub: DeadSubscription) => void;
  onSkip: (email: string) => void;
}

export function SenderCard({ sub, actioned, onPostUnsub, onSkip }: Props) {
  return (
    <div
      className={`rounded-lg border p-4 flex flex-col gap-2 ${
        actioned ? "border-green-200 bg-green-50 opacity-60" : "border-gray-200 bg-white"
      }`}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="font-medium text-sm text-gray-900">{sub.sender_name || sub.sender_email}</p>
          <p className="text-xs text-gray-500">{sub.sender_email}</p>
        </div>
        {actioned && (
          <span className="text-xs text-green-600 font-medium">Actioned</span>
        )}
      </div>

      <div className="flex gap-4 text-xs text-gray-600">
        <span>{fmtCount(sub.count)} emails</span>
        <span>{fmtSize(sub.total_size)}</span>
        <span>Last: {fmtDate(sub.latest_ts)}</span>
      </div>

      {!actioned && (
        <div className="flex gap-2 mt-1">
          <button
            onClick={() => onPostUnsub(sub)}
            className="px-3 py-1 rounded text-xs bg-red-600 text-white hover:bg-red-700 font-medium"
          >
            Unsubscribe (POST)
          </button>
          <a
            href={sub.unsubscribe_url}
            target="_blank"
            rel="noopener noreferrer"
            className="px-3 py-1 rounded text-xs border border-gray-300 text-gray-600 hover:bg-gray-50"
          >
            Open URL
          </a>
          <button
            onClick={() => onSkip(sub.sender_email)}
            className="px-3 py-1 rounded text-xs text-gray-500 hover:text-gray-700"
          >
            Skip
          </button>
        </div>
      )}
    </div>
  );
}
