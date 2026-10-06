"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { IntakeWizard } from "@/components/intake-wizard";
import { Shell } from "@/components/shell";
import { api, getToken } from "@/lib/api";

interface Case {
  id: string;
  patient_ref: string;
  modalities: string[];
  created_at: string;
}

function StatTile({
  label,
  icon,
  value,
  unit,
  bar,
  accent,
}: {
  label: string;
  icon: string;
  value: string;
  unit: string;
  bar: number;
  accent: string;
}) {
  return (
    <div className="flex flex-col justify-between rounded-xl border border-outline-variant bg-surface-container-lowest p-4 shadow-sm">
      <div className="flex items-center justify-between text-[11px] font-semibold uppercase tracking-wider text-outline">
        <span>{label}</span>
        <span className={`material-symbols-outlined text-[18px] ${accent}`}>{icon}</span>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="font-headline text-2xl font-bold text-primary">{value}</span>
        <span className="text-xs text-outline">{unit}</span>
      </div>
      <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-surface-container-highest">
        <div className={`h-full rounded-full ${accent.replace("text-", "bg-")}`} style={{ width: `${bar}%` }} />
      </div>
    </div>
  );
}

export default function CasesPage() {
  const router = useRouter();
  const [cases, setCases] = useState<Case[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    let cancelled = false;
    api<Case[]>("/api/cases")
      .then((data) => {
        if (!cancelled) {
          setCases(data);
          setLoaded(true);
        }
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

  const ctCount = cases.filter((c) => c.modalities.includes("ct")).length;

  return (
    <Shell crumbs={[{ label: "Cases" }]}>
      <div className="flex flex-col gap-6 p-6">
        <section className="flex flex-col justify-between gap-4 rounded-xl border border-outline-variant bg-surface-container-lowest p-6 shadow-sm xl:flex-row xl:items-end">
          <div>
            <h1 className="font-headline text-2xl font-bold tracking-tight text-on-surface">
              Cases
            </h1>
            <p className="mt-1 text-sm text-outline">
              Case intake, uploads, and agent workspaces
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => setShowForm((v) => !v)}
              className="flex items-center gap-2 rounded-lg bg-primary-container px-4 py-2 font-mono text-xs font-bold uppercase tracking-wider text-white shadow-sm transition hover:opacity-90"
            >
              <span className="material-symbols-outlined text-[16px]">add_circle</span>
              New Case Intake
            </button>
          </div>
        </section>

        <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <StatTile
            label="Active Cases"
            icon="folder_shared"
            value={String(cases.length)}
            unit="in workspace"
            bar={Math.min(100, cases.length * 20)}
            accent="text-primary"
          />
          <StatTile
            label="CT Studies"
            icon="monitoring"
            value={String(ctCount)}
            unit="with imaging"
            bar={cases.length ? Math.round((ctCount / cases.length) * 100) : 0}
            accent="text-tertiary"
          />
        </section>

        <section className="flex flex-col overflow-hidden rounded-xl border border-outline-variant bg-surface-container-lowest shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline-variant bg-surface-container-low px-6 py-3">
            <div className="flex items-center gap-3">
              <span className="h-2.5 w-2.5 animate-ping rounded-full bg-primary" />
              <div className="flex flex-col">
                <span className="text-sm font-bold uppercase tracking-wider text-on-surface">
                  Case list
                </span>
                <span className="text-xs text-outline">
                  Open a workspace to upload studies and run the agent swarm
                </span>
              </div>
            </div>
            <span className="font-mono text-[11px] text-outline">
              {cases.length} total
            </span>
          </div>

          {loaded && cases.length === 0 && (
            <p className="px-6 py-8 text-sm text-outline">
              No cases yet — use New Case Intake above.
            </p>
          )}
          {!loaded && <p className="px-6 py-8 text-sm text-outline">Loading cases…</p>}

          <div className="flex flex-col divide-y divide-outline-variant">
            {cases.map((c) => (
              <div
                key={c.id}
                className="flex flex-col justify-between gap-3 px-6 py-4 transition-colors hover:bg-surface-container-low xl:flex-row xl:items-center"
              >
                <div className="flex min-w-[280px] items-start gap-4">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-sky-200 bg-surface-container text-primary">
                    <span className="material-symbols-outlined text-[20px]">folder_open</span>
                  </div>
                  <div className="flex flex-col">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="rounded border border-outline-variant bg-white px-2 py-0.5 font-mono font-bold text-primary shadow-xs">
                        {c.id.slice(0, 8)}
                      </span>
                      <span className="font-medium text-on-surface">{c.patient_ref}</span>
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {c.modalities.map((m) => (
                        <span
                          key={m}
                          className="rounded border border-outline-variant bg-surface-container px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase text-on-surface-variant"
                        >
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-4 xl:justify-end">
                  <span className="font-mono text-[11px] text-outline">
                    {new Date(c.created_at).toLocaleString()}
                  </span>
                  <Link
                    href={`/cases/${c.id}`}
                    className="flex items-center gap-1.5 rounded-lg border border-outline-variant bg-white px-3 py-1.5 text-xs font-semibold text-on-surface transition-colors hover:bg-surface-container"
                  >
                    <span className="material-symbols-outlined text-[15px] text-primary">
                      open_in_new
                    </span>
                    Open Workspace
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </section>

        {showForm && <IntakeWizard onCreated={(id) => router.push(`/cases/${id}`)} />}
      </div>
    </Shell>
  );
}
