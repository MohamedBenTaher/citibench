import type { ReactNode } from "react";
import { HugeiconsIcon } from "@hugeicons/react";
import {
  AlertCircleIcon,
  CancelCircleIcon,
  CheckmarkCircle02Icon,
  CircleQuestionMarkIcon,
} from "@hugeicons/core-free-icons";
import { cn } from "@/lib/utils";

export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";

const TONE_CLASS: Record<StatusTone, string> = {
  success: "border-success/40 bg-success/10 text-success",
  warning: "border-warning/40 bg-warning/10 text-warning",
  danger: "border-destructive/40 bg-destructive/10 text-destructive",
  info: "border-info/40 bg-info/10 text-info",
  neutral: "border-border bg-muted text-muted-foreground",
};

const TONE_ICON: Record<StatusTone, typeof CheckmarkCircle02Icon | null> = {
  success: CheckmarkCircle02Icon,
  warning: CircleQuestionMarkIcon,
  danger: CancelCircleIcon,
  info: AlertCircleIcon,
  neutral: null,
};

export function StatusPill({
  tone,
  children,
  withIcon = true,
  className,
}: {
  tone: StatusTone;
  children: ReactNode;
  withIcon?: boolean;
  className?: string;
}) {
  const Icon = TONE_ICON[tone];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
        TONE_CLASS[tone],
        className,
      )}
    >
      {withIcon && Icon ? <HugeiconsIcon icon={Icon} size={12} aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
