export function PageHeader({
  title,
  description,
  eyebrow,
}: {
  title: string;
  description?: string;
  eyebrow?: string;
}) {
  return (
    <div className="space-y-2">
      <div className="space-y-1.5">
        {eyebrow ? (
          <div className="flex items-center gap-2">
            <span
              className="h-3 w-1 border-y-2 border-l-2 border-foreground/70"
              aria-hidden="true"
            />
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted-foreground">
              {eyebrow}
            </p>
            <span
              className="h-3 w-1 border-y-2 border-r-2 border-foreground/70"
              aria-hidden="true"
            />
          </div>
        ) : null}
        <h1 className="font-heading text-balance text-2xl font-medium tracking-tighter">{title}</h1>
      </div>
      {description ? (
        <p className="max-w-3xl text-pretty text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
      ) : null}
    </div>
  );
}
