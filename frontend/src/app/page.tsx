"use client";
import { useEffect, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { AccountSwitcher } from "@/components/AccountSwitcher";
import { SyncBanner } from "@/components/SyncBanner";
import { useAccounts } from "@/hooks/useAccounts";
import { useSyncStatus } from "@/hooks/useSyncStatus";

function HomeInner() {
  const { accounts, activeAccount, setActiveAccount, loading, refresh, connect, remove } = useAccounts();
  const { status, startSync } = useSyncStatus(activeAccount);
  const searchParams = useSearchParams();

  useEffect(() => {
    if (searchParams.get("auth") === "success") {
      refresh();
      window.history.replaceState({}, "", "/");
    }
  }, [searchParams, refresh]);

  return (
    <div className="p-8 max-w-2xl">
      <h1 className="text-2xl font-bold mb-2">Gmail Cleaner</h1>
      <p className="text-gray-500 text-sm mb-8">
        Visualize and clean up storage on your Gmail account.
      </p>

      <section className="mb-8">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">Accounts</h2>
        {loading ? (
          <p className="text-sm text-gray-400">Loading...</p>
        ) : (
          <AccountSwitcher
            accounts={accounts}
            activeAccount={activeAccount}
            onSwitch={setActiveAccount}
            onConnect={connect}
            onRemove={remove}
          />
        )}
      </section>

      {activeAccount && (
        <section>
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-3">Sync Status</h2>
          <SyncBanner status={status} onStartSync={startSync} />
          {status?.is_complete && (
            <p className="text-xs text-gray-500 mt-3">
              Navigate to Dashboard, Cleanup, Unsubscribe, or Insights using the sidebar.
            </p>
          )}
        </section>
      )}
    </div>
  );
}

export default function Home() {
  return (
    <Suspense>
      <HomeInner />
    </Suspense>
  );
}
