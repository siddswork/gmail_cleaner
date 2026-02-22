"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAccountContext } from "@/lib/AccountContext";
import { useSyncStatus } from "@/hooks/useSyncStatus";
import { fmtCount } from "@/lib/format";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/cleanup", label: "Cleanup" },
  { href: "/unsubscribe", label: "Unsubscribe" },
  { href: "/insights", label: "Insights" },
];

export function Sidebar() {
  const pathname = usePathname();
  const { activeAccount, logout } = useAccountContext();
  const { status } = useSyncStatus(activeAccount);

  return (
    <aside className="w-52 min-h-screen bg-gray-900 text-gray-100 flex flex-col py-6 px-4 shrink-0">
      <div className="mb-8">
        <h1 className="text-lg font-bold tracking-tight">Gmail Cleaner</h1>
        {activeAccount && (
          <p className="text-xs text-gray-400 mt-1 truncate" title={activeAccount}>
            {activeAccount}
          </p>
        )}
      </div>

      {activeAccount && (
        <nav className="flex flex-col gap-1">
          {NAV.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className={`px-3 py-2 rounded text-sm transition-colors ${
                pathname === href
                  ? "bg-blue-600 text-white font-medium"
                  : "text-gray-300 hover:bg-gray-700 hover:text-white"
              }`}
            >
              {label}
            </Link>
          ))}
          <button
            onClick={logout}
            className="w-full text-left px-3 py-2 rounded text-sm text-gray-400 hover:bg-gray-700 hover:text-white transition-colors"
          >
            Log out
          </button>
        </nav>
      )}

      {/* Sync status indicator */}
      {status?.is_syncing && (
        <div className="mt-auto pt-4 border-t border-gray-700">
          <div className="flex items-center gap-2 text-xs text-blue-300">
            <span className="inline-block w-2 h-2 rounded-full bg-blue-400 animate-pulse shrink-0" />
            <span>Syncing… {fmtCount(status.total_synced)} cached</span>
          </div>
        </div>
      )}
      {status?.is_complete && !status.is_syncing && (
        <div className="mt-auto pt-4 border-t border-gray-700">
          <p className="text-xs text-green-400">{fmtCount(status.total_synced)} emails synced</p>
        </div>
      )}
    </aside>
  );
}
