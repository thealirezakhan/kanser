"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Shell } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { api, getToken } from "@/lib/api";

interface Case {
  id: string;
  patient_ref: string;
  modalities: string[];
}

interface Visit {
  id: string;
  visit_date: string;
  size_mm: number | null;
  notes: string;
}

interface Progression {
  trend: string;
  delta_mm: number | null;
  doubling_time_days: number | null;
  growth_mm_per_day: number | null;
  series: { date: string; size_mm: number }[];
}

interface VisitData {
  visits: Visit[];
  progression: Progression;
}

const TREND_STYLE: Record<string, string> = {
  growing: "border-rose-200 bg-rose-50 text-rose-700",
  shrinking: "border-emerald-200 bg-emerald-50 text-emerald-700",
  stable: "border-sky-200 bg-sky-50 text-sky-700",
};

export default function LongitudinalPage() {
  const router = useRouter();
  const [cases, setCases] = useState<Case[]>([]);
  const [caseId, setCaseId] = useState<string>("");
  const [data, setData] = useState<VisitData | null>(null);
  const [date, setDate] = useState("");
  const [size, setSize] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api<Case[]>("/api/cases")
      .then((all) => {
        setCases(all);
        if (all[0]) setCaseId(all[0].id);
      })
      .catch((err) => {
        if (err instanceof Error && "status" in err && err.status === 401) {
          router.push("/login");
        }
      });
  }, [router]);

  useEffect(() => {
    if (!caseId) return;
    api<VisitData>(`/api/cases/${caseId}/visits`)
      .then(setData)
      .catch(() => setData({ visits: [], progression: {
        trend: "unknown", delta_mm: null, doubling_time_days: null,
        growth_mm_per_day: null, series: [],
      } }));
  }, [caseId]);

  async function addVisit() {
    if (!date || !caseId) return;
    setBusy(true);
    setError(null);
    try {
      await api(`/api/cases/${caseId}/visits`, {
        method: "POST",
        body: JSON.stringify({
          visit_date: date,
          size_mm: size ? Number(size) : null,
          notes,
        }),
      });
      setDate("");
      setSize("");
      setNotes("");
      setData(await api<VisitData>(`/api/cases/${caseId}/visits`));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add visit");
    } finally {
      setBusy(false);
    }
  }

  const prog = data?.progression;
  const maxSize = Math.max(1, ...(prog?.series.map((s) => s.size_mm) ?? [1]));

  return (
    <Shell crumbs={[{ label: "Longitudinal Intel" }]}>
      <div className="flex flex-col gap-6 p-6">
        <section className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="font-headline text-2xl font-bold text-on-surface">
              Longitudinal Intel
            </h1>
            <p className="mt-1 text-sm text-on-surface-variant">
              Track lesion size across visits — trend, growth rate, doubling time.
            </p>
          </div>
          <select
            value={caseId}
            onChange={(e) => setCaseId(e.target.value)}
            className="h-10 rounded-lg border border-outline-variant bg-white px-3 text-sm text-on-surface focus:border-primary focus:outline-none"
          >
            {cases.length === 0 && <option value="">No cases</option>}
            {cases.map((c) => (
              <option key={c.id} value={c.id}>
                {c.patient_ref} ({c.modalities.join(", ") || "—"})
              </option>
            ))}
          </select>
        </section>

        {error && (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 font-mono text-xs text-rose-700">
            {error}
          </p>
        )}

        {prog && (
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
              <span className="text-xs font-bold uppercase tracking-wider text-outline">
                Trend
              </span>
              <div className="mt-1.5">
                <span
                  className={`inline-block rounded-full border px-3 py-1 font-mono text-sm font-bold uppercase ${TREND_STYLE[prog.trend] ?? "border-outline-variant bg-surface-container text-on-surface-variant"}`}
                >
                  {prog.trend}
                </span>
              </div>
            </div>
            <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
              <span className="text-xs font-bold uppercase tracking-wider text-outline">
                Size delta
              </span>
              <p className="font-headline mt-1 text-2xl font-bold text-on-surface">
                {prog.delta_mm !== null ? `${prog.delta_mm > 0 ? "+" : ""}${prog.delta_mm} mm` : "—"}
              </p>
            </div>
            <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
              <span className="text-xs font-bold uppercase tracking-wider text-outline">
                Growth rate
              </span>
              <p className="font-headline mt-1 text-2xl font-bold text-on-surface">
                {prog.growth_mm_per_day !== null ? `${prog.growth_mm_per_day} mm/d` : "—"}
              </p>
            </div>
            <div className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4">
              <span className="text-xs font-bold uppercase tracking-wider text-outline">
                Doubling time
              </span>
              <p className="font-headline mt-1 text-2xl font-bold text-on-surface">
                {prog.doubling_time_days !== null ? `${prog.doubling_time_days} d` : "—"}
              </p>
            </div>
          </section>
        )}

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm xl:col-span-7">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
              <span className="material-symbols-outlined text-[18px] text-primary">
                monitoring
              </span>
              Growth series
            </h2>
            {!prog || prog.series.length === 0 ? (
              <p className="rounded-lg border border-dashed border-outline-variant p-6 text-center text-sm text-outline">
                No measured visits yet. Add one on the right.
              </p>
            ) : (
              <div className="flex flex-col gap-3">
                {prog.series.map((s) => (
                  <div key={s.date} className="flex items-center gap-3">
                    <span className="w-24 shrink-0 font-mono text-xs text-outline">
                      {s.date}
                    </span>
                    <div className="h-5 flex-1 overflow-hidden rounded bg-surface-container">
                      <div
                        className="h-full rounded bg-primary-container"
                        style={{ width: `${(s.size_mm / maxSize) * 100}%` }}
                      />
                    </div>
                    <span className="w-16 shrink-0 text-right font-mono text-xs font-bold text-on-surface">
                      {s.size_mm} mm
                    </span>
                  </div>
                ))}
              </div>
            )}
          </section>

          <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm xl:col-span-5">
            <h2 className="mb-4 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
              <span className="material-symbols-outlined text-[18px] text-primary">event</span>
              Add visit
            </h2>
            <div className="flex flex-col gap-3">
              <label className="flex flex-col gap-1 text-xs font-bold text-outline">
                Visit date
                <input
                  type="date"
                  value={date}
                  onChange={(e) => setDate(e.target.value)}
                  className="h-10 rounded-lg border border-outline-variant bg-white px-3 text-sm text-on-surface focus:border-primary focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs font-bold text-outline">
                Size (mm)
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  value={size}
                  onChange={(e) => setSize(e.target.value)}
                  placeholder="e.g. 14.5"
                  className="h-10 rounded-lg border border-outline-variant bg-white px-3 text-sm text-on-surface placeholder:text-outline focus:border-primary focus:outline-none"
                />
              </label>
              <label className="flex flex-col gap-1 text-xs font-bold text-outline">
                Notes
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={3}
                  placeholder="follow-up CT, treatment response…"
                  className="rounded-lg border border-outline-variant bg-white px-3 py-2 text-sm text-on-surface placeholder:text-outline focus:border-primary focus:outline-none"
                />
              </label>
              <Button onClick={() => void addVisit()} disabled={busy || !date || !caseId}>
                {busy ? "Saving…" : "Record visit"}
              </Button>
            </div>

            {data && data.visits.length > 0 && (
              <div className="mt-5 border-t border-outline-variant pt-4">
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-outline">
                  Visit log ({data.visits.length})
                </h3>
                <div className="flex max-h-48 flex-col gap-1.5 overflow-y-auto">
                  {[...data.visits].reverse().map((v) => (
                    <div
                      key={v.id}
                      className="flex items-baseline justify-between gap-2 rounded bg-surface-container-low px-2.5 py-1.5 font-mono text-xs"
                    >
                      <span className="text-on-surface">{v.visit_date}</span>
                      <span className="text-on-surface-variant">
                        {v.size_mm !== null ? `${v.size_mm} mm` : "—"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>
      </div>
    </Shell>
  );
}
