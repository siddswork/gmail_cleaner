"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import type { SyncStatus } from "@/lib/types";

export function useSyncStatus(account: string | null) {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const esRef = useRef<EventSource | null>(null);

  const openSSE = useCallback((acc: string) => {
    esRef.current?.close();
    const es = new EventSource(api.sync.progressUrl(acc));
    esRef.current = es;

    es.onmessage = (e) => {
      const data = JSON.parse(e.data);
      setStatus((prev) =>
        prev
          ? {
              ...prev,
              total_synced: data.total_synced,
              is_complete: data.is_complete,
              is_syncing: data.is_syncing,
              messages_total: data.messages_total ?? prev.messages_total,
              sync_started_ts: data.sync_started_ts ?? prev.sync_started_ts,
              synced_this_run: data.synced_this_run ?? prev.synced_this_run,
            }
          : null,
      );
    };
    es.addEventListener("complete", () => {
      api.sync.status(acc).then(setStatus).catch(() => {});
      es.close();
      esRef.current = null;
    });
    es.addEventListener("stopped", () => {
      es.close();
      esRef.current = null;
    });
    es.onerror = () => {
      es.close();
      esRef.current = null;
    };
  }, []);

  // On mount / account change: fetch status and auto-reconnect SSE if sync is in progress
  useEffect(() => {
    if (!account) return;

    api.sync.status(account).then((s) => {
      setStatus(s);
      // If a sync is already running, reconnect the SSE stream automatically
      if (s.is_syncing && !esRef.current) {
        openSSE(account);
      }
    }).catch(() => {});

    return () => {
      esRef.current?.close();
      esRef.current = null;
    };
  }, [account, openSSE]);

  const startSync = async () => {
    if (!account) return;
    await api.sync.start(account);
    // Refresh status then open SSE
    api.sync.status(account).then(setStatus).catch(() => {});
    openSSE(account);
  };

  const forceFullSync = async () => {
    if (!account) return;
    await api.sync.forceStart(account);
    api.sync.status(account).then(setStatus).catch(() => {});
    openSSE(account);
  };

  const refreshStatus = useCallback(() => {
    if (!account) return;
    api.sync.status(account).then(setStatus).catch(() => {});
  }, [account]);

  return { status, startSync, forceFullSync, refreshStatus };
}
