"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAccounts } from "@/hooks/useAccounts";
import { api } from "@/lib/api";
import type { ReadRateSender, UnreadByLabel, OldestUnreadSender } from "@/lib/types";
import { ReadRateBar } from "@/components/charts/ReadRateBar";
import { CategoryBar } from "@/components/charts/CategoryBar";
import { DataTable } from "@/components/DataTable";
import { fmtCount, fmtDate, fmtPct, fmtSize, cleanCategory } from "@/lib/format";

export default function InsightsPage() {
  const { activeAccount } = useAccounts();
  const [readRate, setReadRate] = useState<ReadRateSender[]>([]);
  const [unreadByLabel, setUnreadByLabel] = useState<UnreadByLabel[]>([]);
  const [oldest, setOldest] = useState<OldestUnreadSender[]>([]);
  const [rrLimit, setRrLimit] = useState(50);
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (!activeAccount) {
      router.replace("/");
      return;
    }
    setLoading(true);
    Promise.all([
      api.insights.readRate(activeAccount, rrLimit).then(setReadRate),
      api.insights.unreadByLabel(activeAccount).then(setUnreadByLabel),
      api.insights.oldestUnread(activeAccount, 20).then(setOldest),
    ]).finally(() => setLoading(false));
  }, [activeAccount, rrLimit, router]);

  if (!activeAccount) {
    return null;
  }

  // Convert UnreadByLabel to CategoryInfo shape for CategoryBar
  const asCategories = unreadByLabel.map((u) => ({
    category: u.category,
    count: u.unread_count,
    total_size: u.total_size,
  }));

  return (
    <div className="p-8 max-w-5xl">
      <h1 className="text-2xl font-bold mb-1">Insights</h1>
      <p className="text-xs text-gray-400 mb-6">{activeAccount}</p>

      {loading && <p className="text-sm text-gray-400 mb-4">Loading...</p>}

      {/* Section 1: Read Rate */}
      <section className="mb-10">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold">Read Rate by Sender</h2>
            <p className="text-xs text-gray-500">How often do you read emails from each sender? Ordered by volume.</p>
          </div>
          <select
            value={rrLimit}
            onChange={(e) => setRrLimit(Number(e.target.value))}
            className="border border-gray-300 rounded px-2 py-1 text-xs"
          >
            {[10, 20, 50, 100].map((n) => (
              <option key={n} value={n}>Top {n}</option>
            ))}
          </select>
        </div>
        <ReadRateBar data={readRate} />
        <div className="mt-4">
          <DataTable
            data={readRate}
            columns={[
              { key: "sender_email", header: "Email" },
              { key: "sender_name", header: "Name" },
              { key: "total_count", header: "Total", render: (r) => fmtCount(r.total_count as number) },
              { key: "read_count", header: "Read", render: (r) => fmtCount(r.read_count as number) },
              {
                key: "unread_count",
                header: "Unread",
                render: (r) => fmtCount((r.total_count as number) - (r.read_count as number)),
              },
              { key: "read_rate", header: "Read %", render: (r) => fmtPct(r.read_rate as number) },
            ]}
          />
        </div>
      </section>

      {/* Section 2: Unread by category */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold mb-1">Unread Emails by Category</h2>
        <p className="text-xs text-gray-500 mb-3">How many unread emails are in each Gmail category?</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-4">
          <div>
            <p className="text-xs text-gray-500 mb-2">Unread count</p>
            <CategoryBar data={asCategories} mode="count" />
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-2">Unread size</p>
            <CategoryBar data={asCategories} mode="size" />
          </div>
        </div>
        <DataTable
          data={unreadByLabel}
          columns={[
            { key: "category", header: "Category", render: (r) => cleanCategory(r.category as string) },
            { key: "unread_count", header: "Unread", render: (r) => fmtCount(r.unread_count as number) },
            { key: "total_size", header: "Size", render: (r) => fmtSize(r.total_size as number) },
          ]}
        />
      </section>

      {/* Section 3: Oldest unread */}
      <section className="mb-10">
        <h2 className="text-lg font-semibold mb-1">Oldest Unread Senders</h2>
        <p className="text-xs text-gray-500 mb-3">
          Senders whose most recent unread email is the oldest — you haven&apos;t touched their emails in the longest time.
        </p>
        <DataTable
          data={oldest}
          columns={[
            { key: "sender_email", header: "Email" },
            { key: "sender_name", header: "Name" },
            { key: "unread_count", header: "Unread", render: (r) => fmtCount(r.unread_count as number) },
            { key: "total_size", header: "Size", render: (r) => fmtSize(r.total_size as number) },
            { key: "latest_unread_ts", header: "Last Unread", render: (r) => fmtDate(r.latest_unread_ts as number) },
          ]}
          emptyMessage="No unread emails found."
        />
      </section>
    </div>
  );
}
