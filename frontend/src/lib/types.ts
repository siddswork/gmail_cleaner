// TypeScript interfaces matching the FastAPI Pydantic schemas

export interface AccountInfo {
  email: string;
  has_token: boolean;
}

export interface SyncStatus {
  total_synced: number;
  is_complete: boolean;
  page_token: string | null;
  last_full_sync_ts: number | null;
  needs_full_sync: boolean;
  is_syncing: boolean;
  messages_total: number | null;
  sync_started_ts: number | null;
}

export interface OverallStats {
  total_count: number;
  total_size: number;
  read_count: number;
  unread_count: number;
  starred_count: number;
  important_count: number;
  oldest_ts: number | null;
  newest_ts: number | null;
  db_size_bytes: number;
}

export interface SenderInfo {
  sender_email: string;
  sender_name: string | null;
  count: number;
  total_size: number;
}

export interface CategoryInfo {
  category: string;
  count: number;
  total_size: number;
}

export interface TimelineBucket {
  period: string;
  count: number;
  total_size: number;
}

export interface CleanupPreviewRequest {
  sender_email?: string | null;
  start_ts?: number | null;
  end_ts?: number | null;
  labels?: string[];
  unread_only?: boolean;
  min_size?: number;
}

export interface CleanupPreview {
  count: number;
  total_size: number;
  message_ids: string[];
}

export interface CleanupResult {
  trashed: number;
  size_reclaimed: number;
  blocked: number;
  errors: number;
}

export interface CleanupJob {
  status: "idle" | "running" | "done" | "stopped" | "error";
  total: number;
  processed: number;
  trashed: number;
  size_reclaimed: number;
  errors: number;
}

export interface SmartSweepSender {
  sender_email: string;
  count: number;
  total_size: number;
  read_rate: number;
}

export interface DeadSubscription {
  sender_email: string;
  sender_name: string | null;
  count: number;
  total_size: number;
  latest_ts: number;
  unsubscribe_url: string;
}

export interface ReadRateSender {
  sender_email: string;
  sender_name: string | null;
  total_count: number;
  read_count: number;
  read_rate: number;
}

export interface UnreadByLabel {
  category: string;
  unread_count: number;
  total_size: number;
}

export interface OldestUnreadSender {
  sender_email: string;
  sender_name: string | null;
  unread_count: number;
  total_size: number;
  latest_unread_ts: number;
}
