export function PageHeader({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="space-y-2">
      <div className="space-y-1.5">
        <h1 className="font-heading text-balance text-2xl font-medium tracking-tighter">
          {title}
        </h1>
        <div
          className="h-0.5 w-10 bg-foreground"
          aria-hidden="true"
          title=""
        />
      </div>
      {description ? (
        <p className="max-w-3xl text-pretty text-sm leading-relaxed text-muted-foreground">
          {description}
        </p>
      ) : null}
    </div>
  );
}
