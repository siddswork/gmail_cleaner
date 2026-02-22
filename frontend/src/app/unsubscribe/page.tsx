"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAccounts } from "@/hooks/useAccounts";
import { api } from "@/lib/api";
import type { DeadSubscription } from "@/lib/types";
import { SenderCard } from "@/components/SenderCard";

export default function UnsubscribePage() {
  const { activeAccount } = useAccounts();
  const [subs, setSubs] = useState<DeadSubscription[]>([]);
  const [days, setDays] = useState(30);
  const [actioned, setActioned] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const router = useRouter();

  useEffect(() => {
    if (!activeAccount) {
      router.replace("/");
      return;
    }
    setLoading(true);
    api.unsubscribe.dead(activeAccount, days)
      .then(setSubs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [activeAccount, days, router]);

  if (!activeAccount) {
    return null;
  }

  const handlePost = async (sub: DeadSubscription) => {
    const res = await api.unsubscribe.post(sub.unsubscribe_url, undefined);
    setActioned((prev) => new Set([...prev, sub.sender_email]));
    setMsg(res.success ? `Unsubscribed from ${sub.sender_email}` : `POST failed for ${sub.sender_email} — try the URL link`);
  };

  const handleSkip = (email: string) => {
    setActioned((prev) => new Set([...prev, email]));
  };

  const pending = subs.filter((s) => !actioned.has(s.sender_email));
  const done = subs.filter((s) => actioned.has(s.sender_email));

  return (
    <div className="p-8 max-w-3xl">
      <h1 className="text-2xl font-bold mb-1">Unsubscribe</h1>
      <p className="text-xs text-gray-400 mb-6">{activeAccount}</p>

      <div className="flex items-center gap-4 mb-6">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Inactivity threshold (days)</label>
          <input
            type="range"
            min={7}
            max={365}
            step={7}
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="w-48"
          />
          <span className="ml-2 text-sm">{days} days</span>
        </div>
        <button
          onClick={() => setActioned(new Set())}
          className="text-xs text-gray-500 underline hover:text-gray-700"
        >
          Reset actioned list
        </button>
      </div>

      {msg && (
        <div className="mb-4 rounded border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-800">{msg}</div>
      )}

      <div className="flex gap-4 text-sm text-gray-500 mb-4">
        <span>Total: {subs.length}</span>
        <span>Pending: {pending.length}</span>
        <span>Actioned: {actioned.size}</span>
      </div>

      {loading && <p className="text-sm text-gray-400">Loading...</p>}

      <div className="flex flex-col gap-3">
        {pending.map((sub) => (
          <SenderCard
            key={sub.sender_email}
            sub={sub}
            actioned={false}
            onPostUnsub={handlePost}
            onSkip={handleSkip}
          />
        ))}
        {done.map((sub) => (
          <SenderCard
            key={sub.sender_email}
            sub={sub}
            actioned={true}
            onPostUnsub={handlePost}
            onSkip={handleSkip}
          />
        ))}
        {!loading && subs.length === 0 && (
          <p className="text-sm text-gray-500">No dead subscriptions found for the selected threshold.</p>
        )}
      </div>
    </div>
  );
}
