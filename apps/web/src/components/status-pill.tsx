import type { ReactNode } from "react";
import { CheckCircle2Icon, CircleAlertIcon, CircleHelpIcon, OctagonXIcon } from "lucide-react";
import { cn } from "@/lib/utils";

export type StatusTone = "success" | "warning" | "danger" | "info" | "neutral";

const TONE_CLASS: Record<StatusTone, string> = {
  success: "border-success/40 bg-success/10 text-success",
  warning: "border-warning/40 bg-warning/10 text-warning",
  danger: "border-destructive/40 bg-destructive/10 text-destructive",
  info: "border-info/40 bg-info/10 text-info",
  neutral: "border-border bg-muted text-muted-foreground",
};

const TONE_ICON: Record<StatusTone, typeof CheckCircle2Icon | null> = {
  success: CheckCircle2Icon,
  warning: CircleHelpIcon,
  danger: OctagonXIcon,
  info: CircleAlertIcon,
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
      {withIcon && Icon ? <Icon className="size-3" aria-hidden="true" /> : null}
      {children}
    </span>
  );
}
