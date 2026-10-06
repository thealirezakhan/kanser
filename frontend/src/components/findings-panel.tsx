"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { inputCls } from "./intake-fields";

interface Finding {
  id: string;
  key: string;
  value: string;
  source_doc: string;
  source_kind: string;
  origin: "ai" | "clinician";
  confidence: string;
  verification: "pending" | "accepted" | "rejected" | "unknown";
  verified_by: string;
}

const VERIFICATION_TONE: Record<string, string> = {
  pending: "border-amber-300 bg-amber-50 text-amber-700",
  accepted: "border-emerald-300 bg-emerald-50 text-emerald-700",
  rejected: "border-red-300 bg-red-50 text-red-700",
  unknown: "border-outline-variant bg-surface-container text-outline",
};

export function FindingsPanel({
  caseId,
  onVerified,
}: {
  caseId: string;
  onVerified?: () => void;
}) {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [editing, setEditing] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const load = useCallback(() => {
    api<{ findings: Finding[] }>(`/api/cases/${caseId}/findings`)
      .then((d) => setFindings(d.findings))
      .catch(() => undefined);
  }, [caseId]);

  useEffect(() => {
    load();
  }, [load]);

  async function verify(id: string, action: string, value?: string) {
    await api(`/api/findings/${id}/verify`, {
      method: "POST",
      body: JSON.stringify({ action, value }),
    }).catch(() => undefined);
    setEditing(null);
    load();
    onVerified?.();
  }

  if (findings.length === 0) {
    return (
      <p className="font-mono text-[11px] text-outline">
        No extracted evidence yet — upload a report to extract findings with provenance.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-2">
      {findings.map((f) => (
        <li key={f.id} className="rounded-lg border border-outline-variant bg-white p-2.5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-bold text-on-surface">
              <span className="font-mono text-outline">{f.key}</span>
              {editing === f.id ? (
                <span className="ml-2 inline-flex gap-1.5">
                  <input
                    className={`${inputCls} w-32 py-0.5`}
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                  />
                  <button
                    type="button"
                    className="rounded bg-primary-container px-2 py-0.5 text-[11px] font-bold text-white"
                    onClick={() => void verify(f.id, "edit", editValue)}
                  >
                    Save
                  </button>
                </span>
              ) : (
                <span className="ml-2 font-mono">{f.value}</span>
              )}
            </span>
            <span
              className={`rounded-full border px-2 py-0.5 font-mono text-[10px] font-bold uppercase ${VERIFICATION_TONE[f.verification]}`}
            >
              {f.verification}
            </span>
          </div>
          <div className="mt-1 flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-[11px] text-outline">
              {f.source_doc || "manual"} · {f.origin} · conf {f.confidence}
              {f.verified_by && ` · by ${f.verified_by}`}
            </span>
            <span className="flex gap-1.5">
              <button
                type="button"
                className="rounded border border-emerald-300 px-2 py-0.5 text-[11px] font-bold text-emerald-700"
                onClick={() => void verify(f.id, "accept")}
              >
                Accept
              </button>
              <button
                type="button"
                className="rounded border border-outline-variant px-2 py-0.5 text-[11px] font-bold text-on-surface-variant"
                onClick={() => {
                  setEditing(f.id);
                  setEditValue(f.value);
                }}
              >
                Edit
              </button>
              <button
                type="button"
                className="rounded border border-red-300 px-2 py-0.5 text-[11px] font-bold text-red-700"
                onClick={() => void verify(f.id, "reject")}
              >
                Reject
              </button>
              <button
                type="button"
                className="rounded border border-outline-variant px-2 py-0.5 text-[11px] font-bold text-outline"
                onClick={() => void verify(f.id, "unknown")}
              >
                Mark unknown
              </button>
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
