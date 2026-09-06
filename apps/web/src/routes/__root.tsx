import type { ReactNode } from "react";
import {
  HeadContent,
  Link,
  Outlet,
  Scripts,
  createRootRoute,
  useRouterState,
} from "@tanstack/react-router";
import { RouteError } from "../components/status";
import "../styles.css";

const tabs = [
  { to: "/corpus", label: "Corpus" },
  { to: "/playground", label: "Playground" },
  { to: "/traces", label: "Traces" },
  { to: "/evals", label: "Evals" },
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

function RootDocument({ children }: Readonly<{ children: ReactNode }>) {
  const isNavigating = useRouterState({
    select: (state) => state.isLoading,
  });

  return (
    <html lang="en">
      <head>
        <HeadContent />
      </head>
      <body>
        <header>
          <nav>
            <Link className="brand" to="/">
              Citebench
            </Link>
            {tabs.map((tab) => (
              <Link
                key={tab.to}
                to={tab.to}
                activeProps={{ className: "active" }}
                preload="intent"
              >
                {tab.label}
              </Link>
            ))}
            {isNavigating ? (
              <span className="nav-status" aria-live="polite">
                Loading…
              </span>
            ) : null}
          </nav>
          {isNavigating ? <div className="progress" aria-hidden="true" /> : null}
        </header>
        <main>{children}</main>
        <Scripts />
      </body>
    </html>
  );
}
