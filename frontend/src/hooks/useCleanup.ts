"use client";
import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import type { CleanupPreview, CleanupPreviewRequest, CleanupJob } from "@/lib/types";

export type CleanupState = "idle" | "previewing" | "confirming" | "running" | "done" | "error";

export function useCleanup(account: string | null) {
  const [state, setState] = useState<CleanupState>("idle");
  const [preview, setPreview] = useState<CleanupPreview | null>(null);
  const [job, setJob] = useState<CleanupJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const esRef = useRef<EventSource | null>(null);

  // Close SSE on unmount
  useEffect(() => {
    return () => { esRef.current?.close(); };
  }, []);

  const _openProgressSSE = () => {
    if (!account) return;
    esRef.current?.close();
    const es = new EventSource(api.cleanup.progressUrl(account));
    esRef.current = es;

    es.onmessage = (e) => {
      const data: CleanupJob = JSON.parse(e.data);
      setJob(data);
      if (data.status === "done" || data.status === "stopped" || data.status === "error") {
        es.close();
        esRef.current = null;
        setState(data.status === "error" ? "error" : "done");
      }
    };

    es.onerror = () => {
      es.close();
      esRef.current = null;
    };
  };

  // Preview for Bulk Senders / Advanced tabs (filter-based)
  const doPreview = async (req: CleanupPreviewRequest) => {
    if (!account) return;
    setError(null);
    setState("previewing");
    try {
      const data = await api.cleanup.preview(account, req);
      setPreview(data);
      setState("confirming");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Preview failed");
      setState("idle");
    }
  };

  // Preview for Smart Sweep tab (sender list-based)
  const doSmartSweepPreview = async (senderEmails: string[]) => {
    if (!account) return;
    setError(null);
    setState("previewing");
    try {
      const data = await api.cleanup.smartSweepPreview(account, senderEmails);
      setPreview(data);
      setState("confirming");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Preview failed");
      setState("idle");
    }
  };

  // Execute: POST /execute → 202 → open SSE for live progress
  const doExecute = async (confirmWord?: string) => {
    if (!account || !preview) return;
    setError(null);
    setState("running");
    try {
      const initialJob = await api.cleanup.execute(account, preview.message_ids, confirmWord);
      setJob(initialJob);
      _openProgressSSE();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Execute failed");
      setState("confirming");
    }
  };

  const doStop = async () => {
    if (!account) return;
    await api.cleanup.stop(account).catch(() => {});
  };

  const reset = () => {
    esRef.current?.close();
    esRef.current = null;
    setState("idle");
    setPreview(null);
    setJob(null);
    setError(null);
  };

  return { state, preview, job, error, doPreview, doSmartSweepPreview, doExecute, doStop, reset };
}
