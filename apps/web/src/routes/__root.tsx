import type { ReactNode } from "react";
import {
  HeadContent,
  Link,
  Outlet,
  Scripts,
  createRootRoute,
  useRouterState,
} from "@tanstack/react-router";
import {
  ActivityIcon,
  DatabaseIcon,
  GaugeIcon,
  InfoIcon,
  LayoutDashboardIcon,
  ListTreeIcon,
  SparklesIcon,
  type LucideIcon,
} from "lucide-react";
import { CitebenchMark } from "@/components/citebench-mark";
import { RouteError } from "@/components/status";
import { ThemeToggle } from "@/components/theme-toggle";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider, useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import "../styles.css";

const THEME_BOOTSTRAP = `(function(){try{var t=localStorage.getItem('citebench-theme');var r=document.documentElement;if(t==='light'){r.classList.remove('dark')}else{r.classList.add('dark')}r.style.colorScheme=t==='light'?'light':'dark';}catch(e){}})();`;

type NavItem = { to: string; label: string; icon: LucideIcon; exact?: boolean };

const PRIMARY_NAV: NavItem[] = [
  { to: "/", label: "Index", icon: LayoutDashboardIcon, exact: true },
  { to: "/playground", label: "Ask", icon: SparklesIcon },
  { to: "/evals", label: "Evals", icon: GaugeIcon },
  { to: "/traces", label: "Traces", icon: ListTreeIcon },
  { to: "/corpus", label: "Corpus", icon: DatabaseIcon },
];

const SECONDARY_NAV: NavItem[] = [
  { to: "/metrics", label: "Metrics", icon: ActivityIcon },
  { to: "/about", label: "About", icon: InfoIcon },
];

function isActive(pathname: string, item: NavItem): boolean {
  if (item.exact) {
    return pathname === item.to;
  }
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
}

function NavLinkItem({
  item,
  pathname,
  compact,
}: {
  item: NavItem;
  pathname: string;
  compact?: boolean;
}) {
  const active = isActive(pathname, item);
  const Icon = item.icon;
  return (
    <Link
      to={item.to}
      preload="intent"
      aria-current={active ? "page" : undefined}
      className={cn(
        "group flex items-center gap-2.5 rounded-md text-sm transition-colors duration-150 ease-standard",
        compact ? "shrink-0 px-2.5 py-1.5" : "px-2.5 py-2",
        active
          ? "bg-sidebar-accent font-medium text-sidebar-foreground"
          : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
      )}
    >
      <Icon
        className={cn("size-4 shrink-0", active ? "text-primary" : "text-muted-foreground")}
        aria-hidden="true"
      />
      <span>{item.label}</span>
    </Link>
  );
}

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      { title: "Citebench" },
      {
        name: "description",
        content:
          "Citation-grounded retrieval bench: frozen corpus, hybrid retrieve, abstain by policy.",
      },
    ],
    links: [{ rel: "icon", href: "/favicon.svg", type: "image/svg+xml" }],
  }),
  component: RootComponent,
  errorComponent: RouteError,
});

function RootComponent() {
  return (
    <RootDocument>
      <Outlet />
    </RootDocument>
  );
}

function ThemedToaster() {
  const { theme } = useTheme();
  return <Toaster theme={theme} />;
}

function RootDocument({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const isNavigating = useRouterState({ select: (state) => state.isLoading });

  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <HeadContent />
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body>
        <ThemeProvider>
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:rounded-md focus:border focus:border-border focus:bg-card focus:px-3 focus:py-2 focus:text-sm"
          >
            Skip to content
          </a>

          <div className="lg:grid lg:grid-cols-[15rem_minmax(0,1fr)]">
            <aside className="sticky top-0 hidden h-dvh flex-col border-r border-sidebar-border bg-sidebar lg:flex">
              <Link
                to="/"
                preload="intent"
                className="flex items-center gap-2.5 px-4 py-4"
              >
                <CitebenchMark className="size-6" />
                <span className="font-heading text-sm font-semibold tracking-tight text-sidebar-foreground">
                  Citebench
                </span>
                <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
                  bench
                </span>
              </Link>
              <nav className="flex flex-1 flex-col gap-0.5 px-2 py-2" aria-label="Primary">
                {PRIMARY_NAV.map((item) => (
                  <NavLinkItem key={item.to} item={item} pathname={pathname} />
                ))}
                <div className="my-2 border-t border-sidebar-border" />
                {SECONDARY_NAV.map((item) => (
                  <NavLinkItem key={item.to} item={item} pathname={pathname} />
                ))}
              </nav>
              <div className="flex items-center justify-between gap-2 border-t border-sidebar-border px-3 py-2.5">
                <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
                  {isNavigating ? "working…" : "circuit ready"}
                </span>
                <ThemeToggle />
              </div>
            </aside>

            <div className="flex min-w-0 flex-col">
              <header className="sticky top-0 z-10 flex items-center gap-2 border-b border-border bg-background/85 px-3 py-2 backdrop-blur lg:hidden">
                <Link to="/" preload="intent" className="flex items-center gap-2">
                  <CitebenchMark className="size-5" />
                  <span className="font-heading text-sm font-semibold tracking-tight">
                    Citebench
                  </span>
                </Link>
                <nav
                  className="ml-auto flex items-center gap-0.5 overflow-x-auto"
                  aria-label="Primary"
                >
                  {PRIMARY_NAV.map((item) => (
                    <NavLinkItem
                      key={item.to}
                      item={item}
                      pathname={pathname}
                      compact
                    />
                  ))}
                </nav>
                <ThemeToggle />
              </header>

              <main
                id="main"
                tabIndex={-1}
                className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 py-8 outline-none sm:px-6 lg:py-10"
              >
                {children}
              </main>
            </div>
          </div>
          <ThemedToaster />
          <Scripts />
        </ThemeProvider>
      </body>
    </html>
  );
}
