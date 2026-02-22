"use client";
import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { api } from "@/lib/api";
import type { AccountInfo } from "@/lib/types";

interface AccountContextValue {
  accounts: AccountInfo[];
  activeAccount: string | null;
  loading: boolean;
  refresh: () => Promise<void>;
  connect: () => Promise<void>;
  logout: () => Promise<void>;
}

const AccountContext = createContext<AccountContextValue | null>(null);

export function AccountProvider({ children }: { children: ReactNode }) {
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [activeAccount, setActiveAccount] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.auth.accounts();
      // Filter __new__ client-side as safety net
      const filtered = data.accounts.filter((a) => a.email !== "__new__");
      setAccounts(filtered);
      // Auto-select first account
      setActiveAccount((prev) => {
        if (prev && filtered.some((a) => a.email === prev)) return prev;
        return filtered[0]?.email ?? null;
      });
    } catch {
      // backend not yet running
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const connect = useCallback(async () => {
    const { auth_url } = await api.auth.connect();
    window.open(auth_url, "_blank");
  }, []);

  const logout = useCallback(async () => {
    if (!activeAccount) return;
    await api.auth.logout(activeAccount);
    // Clear active account immediately — do NOT call refresh() here because
    // refresh() auto-selects the first account, which would undo the logout.
    setActiveAccount(null);
    // Update accounts list for display without triggering auto-select.
    try {
      const data = await api.auth.accounts();
      const filtered = data.accounts.filter((a) => a.email !== "__new__");
      setAccounts(filtered);
    } catch {
      // ignore
    }
  }, [activeAccount]);

  return (
    <AccountContext.Provider value={{ accounts, activeAccount, loading, refresh, connect, logout }}>
      {children}
    </AccountContext.Provider>
  );
}

export function useAccountContext() {
  const ctx = useContext(AccountContext);
  if (!ctx) throw new Error("useAccountContext must be used inside AccountProvider");
  return ctx;
}
