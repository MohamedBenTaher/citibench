import { cn } from "@/lib/utils";

export function CitebenchMark({
  className,
  title = "Citebench",
}: {
  className?: string;
  title?: string;
}) {
  return (
    <svg
      viewBox="0 0 32 32"
      role="img"
      aria-label={title}
      className={cn("size-6 shrink-0", className)}
    >
      <title>{title}</title>
      <rect width="32" height="32" rx="8" className="fill-foreground" />
      <path
        d="M10 8.5h-2.2v15H10"
        className="fill-none stroke-background"
        strokeWidth="2.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M22 8.5h2.2v15H22"
        className="fill-none stroke-background"
        strokeWidth="2.1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M12.4 12.2h7.2M12.4 16h5.4M12.4 19.8h4"
        className="stroke-background"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
    </svg>
  );
}
