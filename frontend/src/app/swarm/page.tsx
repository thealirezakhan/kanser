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
  confidence: number | null;
  event_count: number;
  updated_at: number;
}

const STATUS_STYLE: Record<string, string> = {
  completed: "border-emerald-200 bg-emerald-50 text-emerald-700",
  failed: "border-rose-200 bg-rose-50 text-rose-700",
};

export default function SwarmPage() {
  const router = useRouter();
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    let cancelled = false;
    const load = () => {
      api<{ runs: RunSummary[] }>("/api/runs")
        .then((data) => {
          if (cancelled) return;
          setRuns(data.runs);
          setLoaded(true);
          setError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          if (err instanceof Error && "status" in err && err.status === 401) {
            router.push("/login");
          } else {
            setError(err instanceof Error ? err.message : "Failed to load runs");
          }
        });
    };
    load();
    const t = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [router]);

  return (
    <Shell crumbs={[{ label: "Live Agent Swarm" }]}>
      <div className="flex flex-col gap-6 p-6">
        <section className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-headline flex items-center gap-2 text-2xl font-bold text-on-surface">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-primary" />
              Live Agent Swarm
            </h1>
            <p className="mt-1 text-sm text-on-surface-variant">
              Every diagnosis run, streamed status, meaningful run IDs derived from patient
              and case data. Refreshes every 5s.
            </p>
          </div>
          <Link href="/cases">
            <Button variant="outline">
              <span className="material-symbols-outlined text-[16px]">add</span>
              New case
            </Button>
          </Link>
        </section>

        {error && (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 font-mono text-xs text-rose-700">
            {error}
          </p>
        )}

        {!loaded ? (
          <p className="text-sm text-outline">Loading runs…</p>
        ) : runs.length === 0 ? (
          <div className="rounded-xl border border-dashed border-outline-variant bg-surface-container-lowest p-10 text-center">
            <span className="material-symbols-outlined text-[36px] text-outline">hub</span>
            <p className="mt-2 text-sm font-semibold text-on-surface-variant">
              No runs yet. Open a case and run diagnosis.
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {runs.map((r) => (
              <Link
                key={r.run_id}
                href={`/runs/${encodeURIComponent(r.run_id)}`}
                className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-outline-variant bg-surface-container-lowest px-5 py-4 shadow-xs transition-colors hover:border-primary"
              >
                <div className="flex min-w-0 flex-col gap-1">
                  <span className="font-mono text-sm font-bold text-on-surface">
                    {r.run_id}
                  </span>
                  <span className="truncate text-xs text-on-surface-variant">
                    {r.diagnosis ?? "awaiting consensus"}
                    {r.confidence !== null
                      ? ` · confidence ${(r.confidence * 100).toFixed(0)}%`
                      : ""}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="font-mono text-[11px] text-outline">
                    {r.event_count} events
                  </span>
                  <span className="font-mono text-[11px] text-outline">
                    {new Date(r.updated_at * 1000).toLocaleTimeString()}
                  </span>
                  <span
                    className={`rounded-full border px-2.5 py-0.5 font-mono text-[11px] font-bold uppercase ${
                      STATUS_STYLE[r.status] ??
                      "border-amber-200 bg-amber-50 text-amber-700"
                    }`}
                  >
                    {r.status}
                  </span>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </Shell>
  );
}
