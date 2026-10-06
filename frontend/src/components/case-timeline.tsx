"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { inputCls } from "./intake-fields";

interface Visit {
  id: string;
  visit_date: string;
  visit_type: string;
  reason: string;
  doctor: string;
  size_mm: number | null;
  notes: string;
}

interface TimelineData {
  visits: Visit[];
  progression: { trend: string; delta_mm: number | null };
}

const VISIT_TYPES: [string, string][] = [
  ["follow_up", "Follow-up"],
  ["imaging_review", "Imaging review"],
  ["biopsy_review", "Biopsy review"],
  ["staging_review", "Staging review"],
  ["molecular_review", "Molecular review"],
  ["treatment_planning", "Treatment planning"],
  ["post_treatment", "Post-treatment"],
  ["surveillance", "Surveillance"],
  ["other", "Other"],
];

export function CaseTimeline({ caseId }: { caseId: string }) {
  const [data, setData] = useState<TimelineData | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    visit_date: new Date().toISOString().slice(0, 10),
    visit_type: "follow_up",
    reason: "",
    doctor: "",
    size_mm: "",
    notes: "",
  });
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api<TimelineData>(`/api/cases/${caseId}/visits`)
      .then(setData)
      .catch(() => undefined);
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load]);

  async function addVisit() {
    setError(null);
    try {
      await api(`/api/cases/${caseId}/visits`, {
        method: "POST",
        body: JSON.stringify({
          visit_date: form.visit_date,
          visit_type: form.visit_type,
          reason: form.reason,
          doctor: form.doctor,
          size_mm: form.size_mm === "" ? null : Number(form.size_mm),
          notes: form.notes,
        }),
      });
      setOpen(false);
      setForm((f) => ({ ...f, reason: "", doctor: "", size_mm: "", notes: "" }));
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Add visit failed");
    }
  }

  if (!data) return <p className="font-mono text-[11px] text-outline">Loading timeline…</p>;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] text-on-surface-variant">
          {data.visits.length} visits · {data.progression.trend} trend
          {data.progression.delta_mm !== null &&
            ` (${data.progression.delta_mm > 0 ? "+" : ""}${data.progression.delta_mm} mm)`}
        </span>
        <Button variant="outline" onClick={() => setOpen((o) => !o)}>
          {open ? "Cancel" : "+ Add visit"}
        </Button>
      </div>

      {open && (
        <div className="flex flex-col gap-2 rounded-lg border border-outline-variant bg-surface-container-low p-3">
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <input
              type="date"
              className={inputCls}
              value={form.visit_date}
              onChange={(e) => setForm({ ...form, visit_date: e.target.value })}
            />
            <select
              className={inputCls}
              value={form.visit_type}
              onChange={(e) => setForm({ ...form, visit_type: e.target.value })}
            >
              {VISIT_TYPES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
            <input
              className={inputCls}
              placeholder="Reason for visit"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
            />
            <input
              className={inputCls}
              placeholder="Doctor"
              value={form.doctor}
              onChange={(e) => setForm({ ...form, doctor: e.target.value })}
            />
            <input
              className={inputCls}
              type="number"
              placeholder="Lesion size (mm)"
              value={form.size_mm}
              onChange={(e) => setForm({ ...form, size_mm: e.target.value })}
            />
            <input
              className={inputCls}
              placeholder="Notes"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </div>
          <Button onClick={() => void addVisit()}>Save visit</Button>
          {error && <p className="text-xs text-error">{error}</p>}
        </div>
      )}

      <ol className="flex flex-col gap-2">
        {data.visits.map((v) => (
          <li key={v.id} className="flex gap-3 border-l-2 border-primary-container pl-3">
            <span className="font-mono text-[11px] text-outline">{v.visit_date}</span>
            <span className="flex flex-col gap-0.5">
              <span className="text-xs font-bold uppercase text-on-surface">
                {v.visit_type.replaceAll("_", " ")}
              </span>
              <span className="text-xs text-on-surface-variant">
                {v.reason || v.notes || "—"}
                {v.size_mm !== null && (
                  <span className="font-mono text-outline"> · {v.size_mm} mm</span>
                )}
              </span>
              {v.doctor && <span className="font-mono text-[11px] text-outline">{v.doctor}</span>}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
