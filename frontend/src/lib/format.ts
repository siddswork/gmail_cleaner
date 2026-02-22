// Formatting utilities

export function fmtSize(bytes: number): string {
  if (bytes >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(1)} GB`;
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  if (bytes >= 1_024) return `${(bytes / 1_024).toFixed(1)} KB`;
  return `${bytes} B`;
}

export function fmtDate(ts: number | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function fmtCount(n: number): string {
  return n.toLocaleString();
}

export function fmtPct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

export function cleanCategory(cat: string): string {
  return cat.replace("CATEGORY_", "").replace(/_/g, " ");
}
