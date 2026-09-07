export function CornerBrackets() {
  return (
    <>
      <span
        className="pointer-events-none absolute left-2 top-2 h-3 w-3 border-l-2 border-t-2 border-foreground"
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute right-2 top-2 h-3 w-3 border-r-2 border-t-2 border-foreground"
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute bottom-2 left-2 h-3 w-3 border-b-2 border-l-2 border-foreground"
        aria-hidden="true"
      />
      <span
        className="pointer-events-none absolute bottom-2 right-2 h-3 w-3 border-b-2 border-r-2 border-foreground"
        aria-hidden="true"
      />
    </>
  );
}
