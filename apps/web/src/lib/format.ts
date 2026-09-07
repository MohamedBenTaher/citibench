export function formatScore(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return value.toFixed(3);
}

export function formatDiff(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "n/a";
  }
  const abs = Math.abs(value).toFixed(3);
  if (value > 0) {
    return `+${abs}`;
  }
  if (value < 0) {
    return `-${abs}`;
  }
  return "0.000";
}

export function formatUtc(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return `${new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date)} UTC`;
}

export function snippet(text: string, max = 72): string {
  const trimmed = text.trim() || "(empty query)";
  if (trimmed.length <= max) {
    return trimmed;
  }
  return `${trimmed.slice(0, Math.max(0, max - 1))}…`;
}

export function formatLatency(ms: number): string {
  if (!Number.isFinite(ms)) {
    return "—";
  }
  if (Math.abs(ms) >= 10) {
    return `${Math.round(ms)} ms`;
  }
  return `${ms.toFixed(1)} ms`;
}

export function formatUsd(value: number, digits = 4): string {
  if (!Number.isFinite(value)) {
    return "—";
  }
  if (value === 0) {
    return "$0";
  }
  return `$${value.toFixed(digits)}`;
}
