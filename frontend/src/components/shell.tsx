"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { api, clearToken, getToken } from "@/lib/api";

export interface Crumb {
  label: string;
  href?: string;
}

interface NavItem {
  label: string;
  icon: string;
  href: string;
  tag: string;
  live?: boolean;
  alert?: boolean;
}

const NAV: NavItem[] = [
  { label: "Command Center", icon: "grid_view", href: "/", tag: "dash" },
  { label: "Cases", icon: "folder_shared", href: "/cases", tag: "queue" },
  { label: "Live Agent Swarm", icon: "hub", href: "/swarm", tag: "", live: true },
  { label: "Tumor Board", icon: "groups_3", href: "/tumor-board", tag: "chat" },
  { label: "Evidence & Literature", icon: "menu_book", href: "/evidence", tag: "PubMed" },
  { label: "Longitudinal Intel", icon: "monitoring", href: "/longitudinal", tag: "3-yr" },
  { label: "Attention & Alerts", icon: "warning", href: "/alerts", tag: "", alert: true },
  { label: "Administration", icon: "settings", href: "/admin", tag: "sys" },
];

function Logo() {
  return (
    <div className="flex items-center gap-2">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-container shadow-sm">
        <span className="material-symbols-outlined text-[20px] text-white">bubble_chart</span>
      </div>
      <div className="flex flex-col">
        <span className="font-headline text-[15px] font-bold uppercase tracking-wider text-on-surface">
          KANser
        </span>
        <span className="text-[10px] font-semibold uppercase tracking-widest text-outline">
          Clinical AI
        </span>
      </div>
    </div>
  );
}

function decodeUser(token: string | null): string {
  if (!token) return "";
  try {
    const payload = JSON.parse(atob(token.split(".")[1] ?? ""));
    return typeof payload.sub === "string" ? payload.sub : "";
  } catch {
    return "";
  }
}

function Sidebar({
  activeHref,
  alertCount,
  version,
  user,
}: {
  activeHref: string;
  alertCount: number;
  version: string;
  user: string;
}) {
  return (
    <aside className="fixed left-0 top-0 z-50 flex h-full w-72 flex-col justify-between border-r border-outline-variant bg-surface-container-lowest shadow-sm">
      <div className="flex flex-col">
        <div className="flex h-16 items-center justify-between border-b border-outline-variant bg-surface-container-lowest px-4">
          <Logo />
          {version && (
            <span className="rounded border border-sky-200 bg-sky-50 px-2 py-0.5 font-mono text-[11px] font-semibold text-primary">
              v{version}
            </span>
          )}
        </div>
        <div className="px-3 py-3">
          <div className="px-2 py-1 text-[11px] font-bold uppercase tracking-wider text-outline">
            Multimodal Navigation
          </div>
          <nav className="mt-1 flex flex-col gap-1">
            {NAV.map((item) => {
              const active = activeHref === item.href;
              const classes = active
                ? "bg-surface-container text-primary font-semibold border-l-4 border-primary"
                : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface border-l-4 border-transparent";
              const badge =
                item.alert && alertCount > 0 ? (
                  <span className="rounded-full border border-rose-200 bg-error-container px-1.5 py-0.5 font-mono text-[11px] font-bold text-on-error-container">
                    {alertCount}
                  </span>
                ) : item.live ? (
                  <span className="h-2 w-2 animate-pulse rounded-full bg-primary" />
                ) : (
                  <span className="font-mono text-[11px] text-outline">{item.tag}</span>
                );
              return (
                <Link
                  key={item.label}
                  href={item.href}
                  className={`flex items-center justify-between rounded-lg px-3 py-2.5 transition-all ${classes}`}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className={`material-symbols-outlined text-[19px] ${
                        active ? "text-primary" : "text-outline"
                      }`}
                    >
                      {item.icon}
                    </span>
                    <span className="text-sm">{item.label}</span>
                  </div>
                  {badge}
                </Link>
              );
            })}
          </nav>
        </div>
      </div>
      <div className="flex flex-col gap-2 border-t border-outline-variant bg-surface-container-low p-3">
        <div className="flex items-center justify-between rounded-lg border border-outline-variant bg-white p-2 shadow-sm">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-full border border-primary/40 bg-surface-container font-bold text-primary">
              {(user || "?").slice(0, 2).toUpperCase()}
            </div>
            <div className="flex min-w-0 flex-col">
              <span className="truncate text-sm font-semibold text-on-surface">
                {user || "Not signed in"}
              </span>
              <span className="truncate text-[11px] text-outline">Signed-in user</span>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}

function Header({ crumbs, alertCount, user }: { crumbs: Crumb[]; alertCount: number; user: string }) {
  const router = useRouter();
  return (
    <header className="fixed left-72 right-0 top-0 z-40 flex h-16 items-center justify-between border-b border-outline-variant bg-white/95 px-6 shadow-sm backdrop-blur-md">
      <div className="flex items-center gap-3 text-on-surface-variant">
        <span className="material-symbols-outlined text-[20px] text-primary">account_tree</span>
        <div className="flex items-center gap-1 text-xs">
          <span className="text-outline">KANser</span>
          {crumbs.map((c) => (
            <span key={c.label} className="flex items-center gap-1">
              <span className="text-outline-variant">/</span>
              {c.href ? (
                <Link href={c.href} className="text-outline hover:text-on-surface">
                  {c.label}
                </Link>
              ) : (
                <span className="font-semibold text-on-surface">{c.label}</span>
              )}
            </span>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Link
          href="/alerts"
          aria-label="Alerts"
          className="relative rounded-lg border border-outline-variant bg-surface-container-low p-2 text-on-surface-variant transition-colors hover:bg-surface-container"
        >
          <span className="material-symbols-outlined text-[20px]">notifications</span>
          {alertCount > 0 && (
            <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-error font-mono text-[10px] font-bold text-white">
              {alertCount}
            </span>
          )}
        </Link>
        <div className="flex items-center gap-2 pl-1">
          <div className="flex h-8 w-8 items-center justify-center rounded-full border border-primary/40 bg-surface-container text-xs font-bold text-primary">
            {(user || "?").slice(0, 2).toUpperCase()}
          </div>
          <div className="hidden flex-col 2xl:flex">
            <span className="text-sm font-semibold leading-tight text-on-surface">
              {user || "Not signed in"}
            </span>
          </div>
          <button
            onClick={() => {
              clearToken();
              router.push("/login");
            }}
            aria-label="Sign out"
            className="rounded-lg border border-outline-variant bg-surface-container-low px-2 py-1.5 font-mono text-[11px] uppercase text-on-surface-variant transition-colors hover:bg-surface-container"
          >
            Sign out
          </button>
        </div>
      </div>
    </header>
  );
}

export function Shell({ crumbs, children }: { crumbs: Crumb[]; children: ReactNode }) {
  const pathname = usePathname();
  const [alertCount, setAlertCount] = useState(0);
  const [version, setVersion] = useState("");
  const user = decodeUser(getToken());
  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    api<{ failed_runs: unknown[]; high_risk_cases: unknown[] }>("/api/alerts")
      .then((a) => {
        if (!cancelled) setAlertCount(a.failed_runs.length + a.high_risk_cases.length);
      })
      .catch(() => undefined);
    api<{ version: string }>("/api/system/status")
      .then((s) => {
        if (!cancelled && s.version) setVersion(s.version);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [pathname]);
  const activeHref = pathname.startsWith("/runs") || pathname === "/swarm"
    ? "/swarm"
    : pathname === "/" || pathname.startsWith("/cases")
      ? (pathname === "/" ? "/" : "/cases")
      : pathname;
  return (
    <div>
      <Sidebar activeHref={activeHref} alertCount={alertCount} version={version} user={user} />
      <div className="pl-72">
        <Header crumbs={crumbs} alertCount={alertCount} user={user} />
        <main className="min-h-screen bg-background pt-16">{children}</main>
      </div>
    </div>
  );
}
