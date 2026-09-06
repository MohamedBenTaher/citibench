import type { Metadata } from "next";
import type { ReactNode } from "react";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Citebench",
  description: "Citation-grounded retrieval bench for a frozen public corpus.",
};

const tabs = [
  { href: "/corpus", label: "Corpus" },
  { href: "/playground", label: "Playground" },
  { href: "/traces", label: "Traces" },
  { href: "/evals", label: "Evals" },
] as const;

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header>
          <nav>
            <Link className="brand" href="/">
              Citebench
            </Link>
            {tabs.map((tab) => (
              <Link key={tab.href} href={tab.href}>
                {tab.label}
              </Link>
            ))}
          </nav>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
