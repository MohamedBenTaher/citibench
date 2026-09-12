import type { ReactNode } from "react";
import {
  HeadContent,
  Link,
  Outlet,
  Scripts,
  createRootRoute,
  useRouterState,
} from "@tanstack/react-router";
import { CitebenchMark } from "@/components/citebench-mark";
import { RouteError } from "@/components/status";
import { ThemeToggle } from "@/components/theme-toggle";
import { buttonVariants } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Toaster } from "@/components/ui/sonner";
import { ThemeProvider, useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";
import "../styles.css";

const THEME_BOOTSTRAP = `(function(){try{var t=localStorage.getItem('citebench-theme');var r=document.documentElement;if(t==='light'){r.classList.remove('dark')}else{r.classList.add('dark')}r.style.colorScheme=t==='light'?'light':'dark';}catch(e){}})();`;

const tabs = [
  { to: "/corpus", label: "Corpus" },
  { to: "/playground", label: "Playground" },
  { to: "/traces", label: "Traces" },
  { to: "/evals", label: "Evals" },
  { to: "/metrics", label: "Metrics" },
  { to: "/about", label: "About" },
] as const;

export const Route = createRootRoute({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      {
        title: "Citebench",
      },
      {
        name: "description",
        content: "Citation-grounded retrieval bench for a frozen public corpus.",
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
  const isNavigating = useRouterState({
    select: (state) => state.isLoading,
  });

  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <HeadContent />
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP }} />
      </head>
      <body>
        <ThemeProvider>
          <header className="sticky top-0 z-10 border-b border-border bg-background">
            <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2 px-4 py-2.5">
              <Link
                to="/"
                className={cn(buttonVariants({ variant: "ghost" }), "gap-2 font-heading text-base")}
                preload="intent"
              >
                <CitebenchMark className="size-6" />
                Citebench
              </Link>
              <Separator orientation="vertical" className="hidden h-5 sm:block" />
              <nav className="flex flex-wrap items-end gap-0.5">
                {tabs.map((tab) => {
                  const isActive = pathname === tab.to;
                  return (
                    <Link
                      key={tab.to}
                      to={tab.to}
                      preload="intent"
                      className={cn(
                        buttonVariants({ variant: "ghost", size: "sm" }),
                        "rounded-none px-2.5 pb-2 pt-1.5",
                        isActive
                          ? "border-b-2 border-foreground font-medium text-foreground"
                          : "text-muted-foreground",
                      )}
                      aria-current={isActive ? "page" : undefined}
                    >
                      {tab.label}
                    </Link>
                  );
                })}
              </nav>
              <div className="ml-auto flex items-center gap-1.5">
                {isNavigating ? (
                  <span className="text-xs text-muted-foreground" aria-live="polite">
                    Loading…
                  </span>
                ) : null}
                <ThemeToggle />
              </div>
            </div>
            {isNavigating ? (
              <div className="h-0.5 origin-left animate-pulse bg-primary" aria-hidden="true" />
            ) : null}
          </header>
          <main className="mx-auto flex max-w-5xl flex-col gap-8 px-4 py-8">{children}</main>
          <ThemedToaster />
          <Scripts />
        </ThemeProvider>
      </body>
    </html>
  );
}
