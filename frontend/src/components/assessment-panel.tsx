"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Readiness } from "./intake-readiness";

interface DiagnosticState {
  state: string;
  label: string;
  explanation: string;
}

interface Tnm {
  staging_system: string;
  t: string | null;
  n: string | null;
  m: string | null;
  stage_group: string;
  determinable: boolean;
  warnings: string[];
}

interface Contradiction {
  type: string;
  key: string;
  values: { value: string; source_doc: string; verification: string }[];
}

interface Assessment {
  pathway: string;
  readiness: Readiness;
  routing: {
    activated: string[];
    dropped: string[];
    risk_grade: string;
    priority: number;
    provider: string;
    confidence?: number;
    needs_human_review?: boolean;
    tumor_board?: boolean;
  };
  agents_skipped: Record<string, string>;
  must_not_infer: string[];
  diagnostic_state: DiagnosticState;
  tnm: Tnm;
  contradictions: Contradiction[];
}

const UNKNOWN_STATES = new Set([
  "no_evidence",
  "uncertain",
  "primary_uncertain",
  "non_diagnostic",
  "tissue_pending",
]);

function GateRow({ name, ready }: { name: string; ready: boolean }) {
  return (
    <div className="flex items-center justify-between border-b border-surface-container-high py-1.5">
      <span className="text-outline">{name}</span>
      <span className={`font-bold ${ready ? "text-emerald-600" : "text-amber-700"}`}>
        {ready ? "READY" : "GAPS"}
      </span>
    </div>
  );
}

export function AssessmentPanel({ caseId }: { caseId: string }) {
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api<Assessment>(`/api/cases/${caseId}/assessment`)
      .then((data) => {
        if (!cancelled) setAssessment(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Assessment failed");
      });
    return () => {
      cancelled = true;
    };
  }, [caseId]);

  if (error) {
    return (
      <p className="rounded-lg bg-error-container px-3 py-2 text-xs text-on-error-container">
        {error}
      </p>
    );
  }
  if (!assessment) {
    return <p className="font-mono text-[11px] text-outline">System 1 assessing case…</p>;
  }

  const { routing, readiness, must_not_infer, agents_skipped, pathway } = assessment;
  const { diagnostic_state: state, tnm, contradictions } = assessment;
  const unknown = UNKNOWN_STATES.has(state.state);

  return (
    <div className="flex flex-col gap-3">
      <div
        className={`rounded-lg border px-3 py-2.5 ${
          contradictions.length > 0
            ? "border-red-300 bg-red-50"
            : unknown
              ? "border-amber-300 bg-amber-50"
              : "border-emerald-200 bg-emerald-50"
        }`}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-bold text-on-surface">{state.label}</span>
          <span className="font-mono text-[10px] font-bold uppercase text-outline">
            {state.state}
          </span>
        </div>
        <p className="mt-1 text-xs text-on-surface-variant">{state.explanation}</p>
        <p className="mt-1.5 font-mono text-[11px] text-on-surface">
          {tnm.determinable ? (
            <span className="font-bold text-emerald-700">
              {tnm.stage_group} ({tnm.t} {tnm.n} {tnm.m})
            </span>
          ) : (
            <span className="font-bold text-amber-700">Stage indeterminate — insufficient evidence</span>
          )}
        </p>
        {tnm.warnings.map((w) => (
          <p key={w} className="mt-0.5 text-[11px] text-outline">
            note: {w}
          </p>
        ))}
      </div>

      {contradictions.length > 0 && (
        <div className="flex flex-col gap-1.5 rounded-lg border border-red-200 bg-red-50 p-2.5 text-xs">
          <span className="text-[11px] font-bold uppercase tracking-wider text-red-700">
            Conflicting evidence — clinician resolution required
          </span>
          {contradictions.map((c) => (
            <div key={`${c.type}-${c.key}`} className="flex flex-col gap-0.5">
              <span className="font-mono text-[11px] font-bold text-red-700">
                {c.type.replaceAll("_", " ")}: {c.key}
              </span>
              <ul className="flex flex-col gap-0.5 text-on-surface-variant">
                {c.values.map((v, i) => (
                  <li key={i} className="font-mono text-[11px]">
                    &quot;{v.value}&quot; — {v.source_doc || "documented"} [{v.verification}]
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="rounded bg-primary-container px-2 py-0.5 font-mono font-bold uppercase text-white">
          pathway: {pathway}
        </span>
        <span className="rounded bg-surface-container-highest px-2 py-0.5 font-mono uppercase text-on-surface-variant">
          risk: {routing.risk_grade}
        </span>
        <span className="text-outline">via {routing.provider}</span>
        {routing.needs_human_review && (
          <span className="rounded border border-amber-300 bg-amber-50 px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase text-amber-700">
            HITL review
          </span>
        )}
        {routing.tumor_board && (
          <span className="rounded border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase text-indigo-700">
            tumor board
          </span>
        )}
        {routing.confidence !== undefined && (
          <span className="font-mono text-[11px] text-outline">
            conf {routing.confidence}
          </span>
        )}
      </div>

      <div className="flex flex-col">
        <span className="mb-1 text-[11px] font-bold uppercase tracking-wider text-outline">
          Readiness gates
        </span>
        <span className="mb-1 font-mono text-[11px] text-on-surface-variant">
          {readiness.system_status.replaceAll("_", " ").toLowerCase()}
        </span>
        {Object.entries(readiness.pathways).map(([name, pw]) => (
          <GateRow key={name} name={name} ready={pw.ready} />
        ))}
      </div>

      {readiness.uncertainty_flags.length > 0 && (
        <div className="flex flex-col gap-1 text-xs">
          <span className="text-[11px] font-bold uppercase tracking-wider text-outline">
            Clinical data gaps — incomplete profile
          </span>
          <ul className="flex flex-col gap-0.5">
            {readiness.uncertainty_flags.map((f) => (
              <li key={f.key} className="flex items-start gap-1.5 text-on-surface-variant">
                <span className="material-symbols-outlined text-[13px] text-amber-600">
                  help
                </span>
                {f.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-1 text-xs">
        <span className="text-[11px] font-bold uppercase tracking-wider text-outline">
          Agent routing
        </span>
        <div className="flex flex-wrap gap-1.5">
          {routing.activated.map((a) => (
            <span
              key={a}
              className="rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 font-mono text-[10px] font-bold text-emerald-700"
            >
              {a}
            </span>
          ))}
          {routing.dropped.map((a) => (
            <span
              key={a}
              title={agents_skipped[a]}
              className="rounded border border-outline-variant bg-surface-container px-1.5 py-0.5 font-mono text-[10px] font-bold text-outline"
            >
              {a} (skipped)
            </span>
          ))}
        </div>
        {routing.dropped.length > 0 && (
          <ul className="mt-1 flex flex-col gap-0.5 text-[11px] text-outline">
            {Object.entries(agents_skipped).map(([a, why]) => (
              <li key={a}>
                {a}: {why}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="flex flex-col gap-1 text-xs">
        <span className="text-[11px] font-bold uppercase tracking-wider text-outline">
          What the system will not infer
        </span>
        {must_not_infer.length === 0 ? (
          <span className="text-emerald-600">No inference limits — evidence complete.</span>
        ) : (
          <ul className="flex flex-col gap-1">
            {must_not_infer.map((w) => (
              <li key={w} className="flex items-start gap-1.5 text-on-surface-variant">
                <span className="material-symbols-outlined text-[13px] text-amber-600">
                  lock
                </span>
                {w}
              </li>
            ))}
          </ul>
        )}
      </div>

      {readiness.recommendations && readiness.recommendations.length > 0 ? (
        <div className="flex flex-col gap-1.5 text-xs">
          <span className="text-[11px] font-bold uppercase tracking-wider text-outline">
            Recommended next investigations
          </span>
          <ul className="flex flex-col gap-1.5">
            {readiness.recommendations.map((rec) => (
              <li key={rec.test} className="rounded-lg bg-surface-container-low p-2">
                <span className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-on-surface">
                    <span className="font-mono text-[10px] uppercase text-outline">
                      {rec.pathway} ·{" "}
                    </span>
                    {rec.test}
                  </span>
                  <span className="rounded bg-surface-container-highest px-1.5 py-0.5 font-mono text-[10px] uppercase text-outline">
                    {rec.priority}
                  </span>
                </span>
                <span className="block text-[11px] text-outline">Q: {rec.question}</span>
                <span className="block text-[11px] text-on-surface-variant">Why: {rec.why}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        readiness.recommended_tests.length > 0 && (
          <div className="flex flex-col gap-1 text-xs">
            <span className="text-[11px] font-bold uppercase tracking-wider text-outline">
              Recommended next tests
            </span>
            <ul className="flex flex-col gap-0.5 text-on-surface-variant">
              {readiness.recommended_tests.map((t) => (
                <li key={t}>• {t}</li>
              ))}
            </ul>
          </div>
        )
      )}
    </div>
  );
}
