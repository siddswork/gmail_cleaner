"use client";
import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import { api } from "@/lib/api";
import type { AccountInfo } from "@/lib/types";

interface AccountContextValue {
  accounts: AccountInfo[];
  activeAccount: string | null;
  setActiveAccount: (email: string | null) => void;
  loading: boolean;
  refresh: () => Promise<void>;
  connect: () => Promise<void>;
  remove: (email: string) => Promise<void>;
}

const AccountContext = createContext<AccountContextValue | null>(null);

export function AccountProvider({ children }: { children: ReactNode }) {
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [activeAccount, setActiveAccount] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await api.auth.accounts();
      setAccounts(data.accounts);
      // Auto-select first account if none selected
      setActiveAccount((prev) => {
        if (prev) return prev; // keep existing selection
        return data.accounts[0]?.email ?? null;
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

  const remove = useCallback(async (email: string) => {
    await api.auth.removeAccount(email);
    await refresh();
    setActiveAccount((prev) => {
      if (prev !== email) return prev;
      return accounts.find((a) => a.email !== email)?.email ?? null;
    });
  }, [accounts, refresh]);

  return (
    <AccountContext.Provider value={{ accounts, activeAccount, setActiveAccount, loading, refresh, connect, remove }}>
      {children}
    </AccountContext.Provider>
  );
}

export function useAccountContext() {
  const ctx = useContext(AccountContext);
  if (!ctx) throw new Error("useAccountContext must be used inside AccountProvider");
  return ctx;
}
