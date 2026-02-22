"use client";
import { useState } from "react";
import type { CleanupPreviewRequest } from "@/lib/types";

const LABEL_OPTIONS = [
  "INBOX",
  "CATEGORY_PROMOTIONS",
  "CATEGORY_UPDATES",
  "CATEGORY_SOCIAL",
  "CATEGORY_FORUMS",
  "SENT",
];

interface Props {
  senders: { sender_email: string; sender_name: string | null }[];
  onPreview: (req: CleanupPreviewRequest) => void;
  loading: boolean;
}

export function FilterPanel({ senders, onPreview, loading }: Props) {
  const [senderEmail, setSenderEmail] = useState("");
  const [customSender, setCustomSender] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [labels, setLabels] = useState<string[]>([]);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [minSizeKb, setMinSizeKb] = useState(0);

  const activeSender = customSender.trim() || senderEmail;

  const handleSubmit = () => {
    if (!activeSender) return;
    const toTs = (d: string) =>
      d ? Math.floor(new Date(d).getTime() / 1000) : null;
    onPreview({
      sender_email: activeSender,
      start_ts: toTs(startDate),
      end_ts: toTs(endDate),
      labels: labels.length ? labels : undefined,
      unread_only: unreadOnly,
      min_size: minSizeKb * 1024,
    });
  };

  const toggleLabel = (l: string) =>
    setLabels((prev) => (prev.includes(l) ? prev.filter((x) => x !== l) : [...prev, l]));

  return (
    <div className="flex flex-col gap-4">
      <div>
        <label className="block text-xs text-gray-500 mb-1">Sender</label>
        <select
          value={senderEmail}
          onChange={(e) => setSenderEmail(e.target.value)}
          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
        >
          <option value="">— choose a sender —</option>
          {senders.map((s) => (
            <option key={s.sender_email} value={s.sender_email}>
              {s.sender_email}
            </option>
          ))}
        </select>
      </div>

      <div>
        <label className="block text-xs text-gray-500 mb-1">Or type email</label>
        <input
          type="email"
          value={customSender}
          onChange={(e) => setCustomSender(e.target.value)}
          placeholder="sender@example.com"
          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
        />
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="block text-xs text-gray-500 mb-1">From date</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">To date</label>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
          />
        </div>
      </div>

      <div>
        <label className="block text-xs text-gray-500 mb-1">Labels</label>
        <div className="flex flex-wrap gap-1">
          {LABEL_OPTIONS.map((l) => (
            <button
              key={l}
              onClick={() => toggleLabel(l)}
              className={`px-2 py-0.5 rounded text-xs border transition-colors ${
                labels.includes(l)
                  ? "bg-blue-600 text-white border-blue-600"
                  : "border-gray-300 text-gray-600 hover:border-blue-400"
              }`}
            >
              {l.replace("CATEGORY_", "")}
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="checkbox"
          id="unread-only"
          checked={unreadOnly}
          onChange={(e) => setUnreadOnly(e.target.checked)}
          className="rounded"
        />
        <label htmlFor="unread-only" className="text-sm text-gray-700">Unread only</label>
      </div>

      <div>
        <label className="block text-xs text-gray-500 mb-1">Min size (KB)</label>
        <input
          type="number"
          min={0}
          step={10}
          value={minSizeKb}
          onChange={(e) => setMinSizeKb(Number(e.target.value))}
          className="w-full border border-gray-300 rounded px-2 py-1.5 text-sm"
        />
      </div>

      <button
        onClick={handleSubmit}
        disabled={!activeSender || loading}
        className="px-4 py-2 rounded bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-40"
      >
        {loading ? "Loading..." : "Preview"}
      </button>
    </div>
  );
}
