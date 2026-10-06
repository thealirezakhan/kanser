"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Shell } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { api, getToken } from "@/lib/api";

interface RunSummary {
  run_id: string;
  status: string;
  case_id: string | null;
  diagnosis: string | null;
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

export default function AlertsPage() {
  const router = useRouter();
  const [alerts, setAlerts] = useState<Alerts | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api<Alerts>("/api/alerts")
      .then(setAlerts)
      .catch((err) => {
        if (err instanceof Error && "status" in err && err.status === 401) {
          router.push("/login");
        } else {
          setError(err instanceof Error ? err.message : "Failed to load alerts");
        }
      });
  }, [router]);

  const failed = alerts?.failed_runs ?? [];
  const highRisk = alerts?.high_risk_cases ?? [];

  return (
    <Shell crumbs={[{ label: "Attention & Alerts" }]}>
      <div className="flex flex-col gap-6 p-6">
        <section>
          <h1 className="font-headline flex items-center gap-2 text-2xl font-bold text-on-surface">
            <span className="material-symbols-outlined text-error">warning</span>
            Attention & Alerts
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            Failed runs and high-risk patients that need eyes on them.
          </p>
        </section>

        {error && (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 font-mono text-xs text-rose-700">
            {error}
          </p>
        )}

        {!alerts ? (
          <p className="text-sm text-outline">Loading alerts…</p>
        ) : (
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
                  <span className="material-symbols-outlined text-[18px] text-rose-600">
                    error
                  </span>
                  Failed runs ({failed.length})
                </h2>
              </div>
              {failed.length === 0 ? (
                <p className="rounded-lg border border-dashed border-emerald-200 bg-emerald-50/50 p-5 text-center text-sm text-emerald-700">
                  All runs completed cleanly.
                </p>
              ) : (
                <div className="flex flex-col divide-y divide-outline-variant">
                  {failed.map((r) => (
                    <div
                      key={r.run_id}
                      className="flex items-center justify-between gap-3 py-3"
                    >
                      <div className="flex min-w-0 flex-col">
                        <span className="truncate font-mono text-xs font-bold text-on-surface">
                          {r.run_id}
                        </span>
                        <span className="font-mono text-[11px] text-outline">
                          {new Date(r.updated_at * 1000).toLocaleString()}
                        </span>
                      </div>
                      <Link href={`/runs/${encodeURIComponent(r.run_id)}`}>
                        <Button variant="outline">Inspect</Button>
                      </Link>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
                  <span className="material-symbols-outlined text-[18px] text-error">
                    priority_high
                  </span>
                  High-risk cases ({highRisk.length})
                </h2>
              </div>
              {highRisk.length === 0 ? (
                <p className="rounded-lg border border-dashed border-outline-variant p-5 text-center text-sm text-outline">
                  No high-risk cases on file.
                </p>
              ) : (
                <div className="flex flex-col divide-y divide-outline-variant">
                  {highRisk.map((c) => (
                    <div
                      key={c.case_id}
                      className="flex items-center justify-between gap-3 py-3"
                    >
                      <div className="flex min-w-0 flex-col">
                        <span className="font-mono text-sm font-bold text-on-surface">
                          {c.patient_ref}
                        </span>
                        <span className="text-xs text-outline">
                          {c.risk_grade} risk · priority {c.priority}
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
          </div>
        )}
      </div>
    </Shell>
  );
}
