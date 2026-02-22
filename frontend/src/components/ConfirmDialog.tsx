"use client";
import { useState } from "react";
import { fmtSize, fmtCount } from "@/lib/format";

interface Props {
  count: number;
  totalSize: number;
  onConfirm: (confirmWord?: string) => void;
  onCancel: () => void;
  isLargeBatch: boolean;
}

export function ConfirmDialog({ count, totalSize, onConfirm, onCancel, isLargeBatch }: Props) {
  const [typed, setTyped] = useState("");

  const canConfirm = !isLargeBatch || typed === "DELETE";

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-5 flex flex-col gap-4">
      <div>
        <p className="font-semibold text-amber-900 mb-1">Confirm deletion</p>
        <p className="text-sm text-amber-800">
          You are about to move <strong>{fmtCount(count)}</strong> emails (
          {fmtSize(totalSize)}) to Trash. This can be undone from Gmail Trash within 30 days.
        </p>
      </div>

      {isLargeBatch && (
        <div>
          <p className="text-xs text-amber-700 mb-1">
            Large batch — type <strong>DELETE</strong> to confirm:
          </p>
          <input
            type="text"
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            className="border border-amber-300 rounded px-2 py-1 text-sm w-40"
            placeholder="DELETE"
          />
        </div>
      )}

      <div className="flex gap-2">
        <button
          onClick={() => onConfirm(isLargeBatch ? typed : undefined)}
          disabled={!canConfirm}
          className="px-4 py-2 rounded bg-red-600 text-white text-sm font-medium hover:bg-red-700 disabled:opacity-40"
        >
          Move to Trash
        </button>
        <button
          onClick={onCancel}
          className="px-4 py-2 rounded border border-gray-300 text-sm hover:bg-gray-50"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
