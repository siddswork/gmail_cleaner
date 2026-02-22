"use client";
import type { AccountInfo } from "@/lib/types";

interface Props {
  accounts: AccountInfo[];
  activeAccount: string | null;
  onSwitch: (email: string) => void;
  onConnect: () => void;
  onRemove: (email: string) => void;
}

export function AccountSwitcher({ accounts, activeAccount, onSwitch, onConnect, onRemove }: Props) {
  return (
    <div className="flex flex-col gap-2">
      {accounts.map((a) => (
        <div
          key={a.email}
          className={`flex items-center justify-between px-3 py-2 rounded border text-sm ${
            a.email === activeAccount
              ? "border-blue-500 bg-blue-50"
              : "border-gray-200 bg-white"
          }`}
        >
          <button
            className="flex-1 text-left truncate"
            onClick={() => onSwitch(a.email)}
          >
            {a.email}
          </button>
          <button
            onClick={() => onRemove(a.email)}
            className="ml-2 text-xs text-red-500 hover:text-red-700"
          >
            Remove
          </button>
        </div>
      ))}
      <button
        onClick={onConnect}
        className="px-3 py-2 rounded border border-dashed border-gray-400 text-sm text-gray-600 hover:border-blue-400 hover:text-blue-600 transition-colors"
      >
        + Connect account
      </button>
      {accounts.length === 0 && (
        <p className="text-xs text-gray-500 mt-1">
          Click above, then open the auth URL in your browser to connect a Gmail account.
        </p>
      )}
    </div>
  );
}
