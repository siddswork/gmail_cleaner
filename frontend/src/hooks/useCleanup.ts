"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import type { CleanupPreview, CleanupPreviewRequest, CleanupResult } from "@/lib/types";

type CleanupState = "idle" | "previewing" | "confirming" | "executing" | "done";

export function useCleanup(account: string | null) {
  const [state, setState] = useState<CleanupState>("idle");
  const [preview, setPreview] = useState<CleanupPreview | null>(null);
  const [result, setResult] = useState<CleanupResult | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  const doExecute = async (confirmWord?: string) => {
    if (!account || !preview) return;
    setError(null);
    setState("executing");
    try {
      const data = await api.cleanup.execute(account, preview.message_ids, confirmWord);
      setResult(data);
      setState("done");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Execute failed");
      setState("confirming");
    }
  };

  const reset = () => {
    setState("idle");
    setPreview(null);
    setResult(null);
    setError(null);
  };

  return { state, preview, result, error, doPreview, doExecute, reset };
}
