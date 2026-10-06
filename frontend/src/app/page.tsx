"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Shell } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { api, getToken } from "@/lib/api";

interface Case {
  id: string;
  patient_ref: string;
  modalities: string[];
  created_at?: string;
}

interface RunSummary {
  run_id: string;
  status: string;
  case_id: string | null;
  diagnosis: string | null;
  confidence: number | null;
  updated_at: number;
}

interface Alerts {
  failed_runs: RunSummary[];
  high_risk_cases: {
    case_id: string;
    patient_ref: string;
    priority: number;
    risk_grade: string;
  }[];
  total_cases: number;
}

interface SystemStatus {
  status: string;
  version: string;
  llm: string;
  auth: string;
  uptime_seconds: number;
}

function StatTile({
  icon,
  label,
  value,
  accent,
}: {
  icon: string;
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-outline-variant bg-surface-container-lowest p-4 shadow-xs">
      <div
        className={`flex h-11 w-11 items-center justify-center rounded-lg ${accent ? "bg-error-container" : "bg-primary-container"}`}
      >
        <span
          className={`material-symbols-outlined text-[22px] ${accent ? "text-on-error-container" : "text-white"}`}
        >
          {icon}
        </span>
      </div>
      <div className="flex min-w-0 flex-col">
        <span className="font-headline text-2xl font-bold leading-none text-on-surface">
          {value}
        </span>
        <span className="truncate text-xs font-semibold uppercase tracking-wider text-outline">
          {label}
        </span>
      </div>
    </div>
  );
}

export default function CommandCenterPage() {
  const router = useRouter();
  const [cases, setCases] = useState<Case[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [alerts, setAlerts] = useState<Alerts | null>(null);
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loaded, setLoaded] = useState(false);

  const [when, setWhen] = useState<{ date: string; greeting: string } | null>(null);

  useEffect(() => {
    // clock/locale differ between prerender and browser -> render after mount
    const t = setTimeout(() => {
      const n = new Date();
      setWhen({
        date: n.toLocaleDateString(undefined, {
          weekday: "long",
          year: "numeric",
          month: "long",
          day: "numeric",
        }),
        greeting:
          n.getHours() < 12
            ? "Good morning"
            : n.getHours() < 18
              ? "Good afternoon"
              : "Good evening",
      });
    }, 0);
    return () => clearTimeout(t);
  }, []);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    let cancelled = false;
    Promise.all([
      api<Case[]>("/api/cases"),
      api<{ runs: RunSummary[] }>("/api/runs"),
      api<Alerts>("/api/alerts"),
      api<SystemStatus>("/api/system/status"),
    ])
      .then(([c, r, a, s]) => {
        if (cancelled) return;
        setCases(c);
        setRuns(r.runs);
        setAlerts(a);
        setStatus(s);
        setLoaded(true);
      })
      .catch((err) => {
        if (!cancelled && err instanceof Error && "status" in err && err.status === 401) {
          router.push("/login");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  const highRisk = alerts?.high_risk_cases ?? [];
  const recentRuns = runs.slice(0, 6);

  return (
    <Shell crumbs={[{ label: "Command Center" }]}>
      <div className="flex flex-col gap-6 p-6">
        <section className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div>
            <p className="font-mono text-xs font-semibold uppercase tracking-widest text-primary">
              {when?.date ?? ""}
            </p>
            <h1 className="font-headline mt-1 text-3xl font-bold tracking-tight text-on-surface">
              {when?.greeting ?? "Welcome"}, Dr. Mitchell
            </h1>
            <p className="mt-1 text-sm text-on-surface-variant">
              Multimodal lung cancer board — cases, alerts, and agent activity at a glance.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {status && (
              <span className="flex items-center gap-2 rounded-lg border border-outline-variant bg-surface-container-low px-3 py-2 font-mono text-[11px] text-on-surface-variant">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                API {status.version} · LLM {status.llm} · auth {status.auth}
              </span>
            )}
            <Link href="/cases">
              <Button>
                <span className="material-symbols-outlined text-[16px]">add</span>
                New case
              </Button>
            </Link>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile icon="folder_shared" label="Cases in system" value={loaded ? String(cases.length) : "—"} />
          <StatTile icon="neurology" label="Diagnosis runs" value={loaded ? String(runs.length) : "—"} />
          <StatTile
            icon="priority_high"
            label="High-risk cases"
            value={alerts ? String(highRisk.length) : "—"}
            accent={highRisk.length > 0}
          />
          <StatTile
            icon="error"
            label="Failed runs"
            value={alerts ? String(alerts.failed_runs.length) : "—"}
            accent={(alerts?.failed_runs.length ?? 0) > 0}
          />
        </section>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm xl:col-span-7">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
                <span className="material-symbols-outlined text-[18px] text-error">
                  priority_high
                </span>
                Priority queue
              </h2>
              <Link href="/alerts" className="font-mono text-xs text-primary hover:underline">
                all alerts →
              </Link>
            </div>
            {!alerts || highRisk.length === 0 ? (
              <p className="rounded-lg border border-dashed border-outline-variant p-6 text-center text-sm text-outline">
                {alerts ? "No high-risk cases. Queue clear." : "Loading…"}
              </p>
            ) : (
              <div className="flex flex-col divide-y divide-outline-variant">
                {highRisk.slice(0, 5).map((c) => (
                  <div key={c.case_id} className="flex items-center justify-between gap-3 py-3">
                    <div className="flex min-w-0 flex-col">
                      <span className="font-mono text-sm font-bold text-on-surface">
                        {c.patient_ref}
                      </span>
                      <span className="text-xs text-outline">
                        risk {c.risk_grade} · priority {c.priority}
                      </span>
                    </div>
                    <div className="flex shrink-0 gap-2">
                      <Link href={`/cases/${c.case_id}`}>
                        <Button variant="outline">Workspace</Button>
                      </Link>
                      <Link href={`/tumor-board?case=${c.case_id}`}>
                        <Button variant="outline">Ask agents</Button>
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm xl:col-span-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
                <span className="material-symbols-outlined text-[18px] text-primary">hub</span>
                Agent board
              </h2>
              <Link href="/tumor-board" className="font-mono text-xs text-primary hover:underline">
                open board →
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[
                ["scan", "Dr. Reed", "Radiology"],
                ["biotech", "Dr. Path", "Pathology"],
                ["genetics", "Dr. Helix", "Genomics"],
                ["stethoscope", "Dr. Care", "Clinical"],
              ].map(([icon, name, spec]) => (
                <div
                  key={name}
                  className="flex items-center gap-2.5 rounded-lg border border-outline-variant bg-surface-container-low p-2.5"
                >
                  <span className="material-symbols-outlined text-[20px] text-primary">
                    {icon}
                  </span>
                  <div className="flex min-w-0 flex-col">
                    <span className="truncate text-xs font-bold text-on-surface">{name}</span>
                    <span className="truncate text-[10px] text-outline">{spec}</span>
                  </div>
                </div>
              ))}
            </div>
            <p className="mt-3 font-mono text-[11px] text-outline">
              Board chat: mention @all for full reports
            </p>
          </section>

          <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm xl:col-span-7">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
                <span className="material-symbols-outlined text-[18px] text-primary">
                  history
                </span>
                Recent diagnosis runs
              </h2>
              <Link href="/swarm" className="font-mono text-xs text-primary hover:underline">
                live swarm →
              </Link>
            </div>
            {!loaded ? (
              <p className="text-sm text-outline">Loading…</p>
            ) : recentRuns.length === 0 ? (
              <p className="rounded-lg border border-dashed border-outline-variant p-6 text-center text-sm text-outline">
                No runs yet — open a case and run diagnosis.
              </p>
            ) : (
              <div className="flex flex-col divide-y divide-outline-variant">
                {recentRuns.map((r) => (
                  <Link
                    key={r.run_id}
                    href={`/runs/${encodeURIComponent(r.run_id)}`}
                    className="flex items-center justify-between gap-3 py-2.5 transition-colors hover:bg-surface-container-low"
                  >
                    <div className="flex min-w-0 flex-col">
                      <span className="truncate font-mono text-xs font-bold text-on-surface">
                        {r.run_id}
                      </span>
                      <span className="truncate text-xs text-outline">
                        {r.diagnosis ?? "—"}
                        {r.confidence !== null ? ` · ${(r.confidence * 100).toFixed(0)}%` : ""}
                      </span>
                    </div>
                    <span
                      className={`shrink-0 rounded-full border px-2 py-0.5 font-mono text-[10px] font-bold uppercase ${
                        r.status === "completed"
                          ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                          : r.status === "failed"
                            ? "border-rose-200 bg-rose-50 text-rose-700"
                            : "border-amber-200 bg-amber-50 text-amber-700"
                      }`}
                    >
                      {r.status}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm xl:col-span-5">
            <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
              <span className="material-symbols-outlined text-[18px] text-primary">bolt</span>
              Quick actions
            </h2>
            <div className="flex flex-col gap-2">
              {[
                ["menu_book", "Evidence literature search", "/evidence"],
                ["monitoring", "Longitudinal progression", "/longitudinal"],
                ["hub", "Live agent swarm", "/swarm"],
                ["settings", "System administration", "/admin"],
              ].map(([icon, label, href]) => (
                <Link
                  key={href}
                  href={href}
                  className="flex items-center gap-3 rounded-lg border border-outline-variant bg-surface-container-low px-3 py-2.5 text-sm font-medium text-on-surface-variant transition-colors hover:border-primary hover:text-primary"
                >
                  <span className="material-symbols-outlined text-[18px]">{icon}</span>
                  {label}
                </Link>
              ))}
            </div>
          </section>
        </div>
      </div>
    </Shell>
  );
}
