// Fetch wrapper for the FastAPI backend

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail || res.statusText);
  }
  return res.json();
}

// Auth
export const api = {
  auth: {
    accounts: () => request<{ accounts: import("./types").AccountInfo[] }>("/api/auth/accounts"),
    connect: () => request<{ auth_url: string; state: string }>("/api/auth/connect", { method: "POST" }),
    removeAccount: (email: string) =>
      request<{ message: string }>(`/api/auth/accounts/${encodeURIComponent(email)}`, { method: "DELETE" }),
    logout: (email: string) =>
      request<{ message: string }>(`/api/auth/accounts/${encodeURIComponent(email)}/logout`, { method: "POST" }),
  },

  sync: {
    status: (account: string) =>
      request<import("./types").SyncStatus>(`/api/sync/status?account=${encodeURIComponent(account)}`),
    start: (account: string) =>
      request<{ message: string; already_running: boolean }>(`/api/sync/start?account=${encodeURIComponent(account)}`, { method: "POST" }),
    progressUrl: (account: string) =>
      `${API}/api/sync/progress?account=${encodeURIComponent(account)}`,
  },

  dashboard: {
    stats: (account: string) =>
      request<import("./types").OverallStats>(`/api/dashboard/stats?account=${encodeURIComponent(account)}`),
    topSenders: (account: string, sort: "count" | "size" = "count", limit = 20) =>
      request<import("./types").SenderInfo[]>(`/api/dashboard/top-senders?account=${encodeURIComponent(account)}&sort=${sort}&limit=${limit}`),
    categories: (account: string) =>
      request<import("./types").CategoryInfo[]>(`/api/dashboard/categories?account=${encodeURIComponent(account)}`),
    timeline: (account: string, granularity: "month" | "year" = "month") =>
      request<import("./types").TimelineBucket[]>(`/api/dashboard/timeline?account=${encodeURIComponent(account)}&granularity=${granularity}`),
  },

  cleanup: {
    preview: (account: string, body: import("./types").CleanupPreviewRequest) =>
      request<import("./types").CleanupPreview>(`/api/cleanup/preview?account=${encodeURIComponent(account)}`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    execute: (account: string, message_ids: string[], confirm_word?: string) =>
      request<import("./types").CleanupJob>(`/api/cleanup/execute?account=${encodeURIComponent(account)}`, {
        method: "POST",
        body: JSON.stringify({ message_ids, confirm_word }),
      }),
    jobStatus: (account: string) =>
      request<import("./types").CleanupJob>(`/api/cleanup/job-status?account=${encodeURIComponent(account)}`),
    stop: (account: string) =>
      request<{ message: string }>(`/api/cleanup/stop?account=${encodeURIComponent(account)}`, { method: "POST" }),
    progressUrl: (account: string) =>
      `${API}/api/cleanup/progress?account=${encodeURIComponent(account)}`,
    smartSweep: (account: string) =>
      request<import("./types").SmartSweepSender[]>(`/api/cleanup/smart-sweep?account=${encodeURIComponent(account)}`),
    smartSweepPreview: (account: string, sender_emails: string[]) =>
      request<import("./types").CleanupPreview>(`/api/cleanup/smart-sweep/preview?account=${encodeURIComponent(account)}`, {
        method: "POST",
        body: JSON.stringify({ sender_emails }),
      }),
  },

  unsubscribe: {
    dead: (account: string, days = 30) =>
      request<import("./types").DeadSubscription[]>(`/api/unsubscribe/dead?account=${encodeURIComponent(account)}&days=${days}`),
    post: (unsubscribe_url: string, unsubscribe_post?: string) =>
      request<{ success: boolean }>("/api/unsubscribe/post", {
        method: "POST",
        body: JSON.stringify({ unsubscribe_url, unsubscribe_post }),
      }),
  },

  insights: {
    readRate: (account: string, limit = 50) =>
      request<import("./types").ReadRateSender[]>(`/api/insights/read-rate?account=${encodeURIComponent(account)}&limit=${limit}`),
    unreadByLabel: (account: string) =>
      request<import("./types").UnreadByLabel[]>(`/api/insights/unread-by-label?account=${encodeURIComponent(account)}`),
    oldestUnread: (account: string, limit = 20) =>
      request<import("./types").OldestUnreadSender[]>(`/api/insights/oldest-unread?account=${encodeURIComponent(account)}&limit=${limit}`),
  },
};
