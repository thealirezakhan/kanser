"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Shell } from "@/components/shell";
import { api, getToken } from "@/lib/api";
import { type RunEvent } from "@/lib/runEvents";
import { useRunStream } from "@/lib/useRunStream";

interface AbstainInfo {
  state?: string;
  reason?: string;
  known?: string[];
  unknown?: string[];
  resolvable_by?: string[];
}

interface RunResult {
  consensus?: {
    diagnosis?: string;
    confidence?: number;
    abstain?: AbstainInfo | null;
    diagnosis_state?: string;
  };
  explain?: { clinician?: string; patient?: string };
  warnings?: string[];
  evidence?: { id: string; metadata?: Record<string, unknown> }[];
  reports?: Record<string, { hypothesis?: string; confidence?: number }>;
}

const STATE_LABELS: Record<string, string> = {
  insufficient_evidence: "Insufficient Evidence",
  finding: "Finding",
  suspicion: "Suspicious — Unconfirmed",
  working_diagnosis: "Working Diagnosis",
  confirmed: "Confirmed",
  staged: "Staged",
  treatment_context: "Treatment Context",
};

const abstainList = (v?: string[]): string => (v ?? []).join("; ");

const STATUS_STYLE: Record<string, string> = {
  completed: "bg-emerald-50 border-emerald-200 text-emerald-700",
  failed: "bg-error-container border-rose-200 text-on-error-container",
  expired: "bg-error-container border-rose-200 text-on-error-container",
  running: "bg-sky-50 border-sky-200 text-primary",
};

function EventCard({ ev }: { ev: RunEvent }) {
  const confidence = "confidence" in ev ? Number(ev.confidence) : undefined;
  return (
    <div className="rounded-lg border border-outline-variant bg-surface-container-low p-3 shadow-sm">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase text-primary">
          <span className="h-1.5 w-1.5 rounded-full bg-primary" />
          {ev.node}
        </span>
        <span className="flex items-center gap-2 font-mono text-[10px] text-outline">
          {"round" in ev && <span>ROUND {String(ev.round)}</span>}
          {confidence !== undefined && (
            <span className="rounded bg-surface-container-highest px-1.5 py-0.5 font-bold text-primary">
              {confidence.toFixed(2)}
            </span>
          )}
          {ev.status && <span className="uppercase">{ev.status}</span>}
        </span>
      </div>
      {typeof ev.detail === "string" && ev.detail && (
        <p className="mt-1.5 whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-on-surface-variant">
          {ev.detail}
        </p>
      )}
    </div>
  );
}

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  // key remount: reducer/seq state must never survive an id change (GAP-003)
  return <RunDetail key={id} id={id} />;
}

function RunDetail({ id }: { id: string }) {
  const router = useRouter();
  const { events, done, status } = useRunStream(id);
  const [result, setResult] = useState<RunResult | null>(null);
  const [view, setView] = useState<"clinician" | "patient">("clinician");
  const [who, setWho] = useState<{ caseId: string; patientRef?: string } | null>(null);

  useEffect(() => {
    if (!getToken()) router.push("/login");
  }, [router]);

  useEffect(() => {
    let stop = false;
    api<{ case_id?: string | null }>(`/api/runs/${id}`)
      .then((snap) => {
        if (stop || !snap.case_id) return null;
        setWho({ caseId: snap.case_id });
        return api<{ patient_ref: string }>(`/api/cases/${snap.case_id}`);
      })
      .then((c) => {
        if (!stop && c) setWho((w) => (w ? { ...w, patientRef: c.patient_ref } : w));
      })
      .catch(() => undefined);
    return () => {
      stop = true;
    };
  }, [id]);

  useEffect(() => {
    if (!done) return;
    api<{ status: string; result: RunResult | null }>(`/api/runs/${id}`)
      .then((snap) => setResult(snap.result))
      .catch(() => undefined);
  }, [done, id]);

  const steps = events.filter((e) => e.type === "agent_step");
  const others = events.filter((e) => e.type !== "agent_step" && e.type !== "run_completed");
  const consensus = result?.consensus;
  const statusClass = STATUS_STYLE[status] ?? STATUS_STYLE.running;

  return (
    <Shell
      crumbs={[
        { label: "Cases", href: "/cases" },
        { label: who?.patientRef ?? `Run ${id.slice(0, 8)}` },
      ]}
    >
      <div className="flex flex-col gap-6 p-6">
        <section className="flex flex-col gap-3 rounded-xl border border-outline-variant bg-surface-container-lowest p-4 shadow-sm xl:flex-row xl:items-center xl:justify-between">
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
              <span className="rounded bg-primary px-2 py-0.5 font-bold uppercase tracking-wider text-white">
                Session Active
              </span>
              <span className="text-outline">/</span>
              <span className="font-bold text-on-surface">
                {who?.patientRef ?? "Loading patient…"}
              </span>
              {who && (
                <>
                  <span className="text-outline">/</span>
                  <span className="text-outline">case {who.caseId.slice(0, 8)}</span>
                </>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span
                className={`h-2.5 w-2.5 rounded-full ${
                  done ? "bg-tertiary-container" : "animate-ping bg-primary"
                }`}
              />
              <span className="font-headline text-base font-bold text-on-surface">
                Live Agent Swarm
              </span>
              <span className="font-mono text-xs text-outline-variant">|</span>
              <span className="font-mono text-xs uppercase text-primary">{status}</span>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full border px-3 py-1 font-mono text-[11px] font-bold uppercase ${statusClass}`}
            >
              {status}
            </span>
            <Link
              href="/cases"
              className="flex items-center gap-1.5 rounded-lg border border-outline-variant bg-white px-3 py-1.5 text-xs font-semibold text-on-surface transition-colors hover:bg-surface-container-low"
            >
              <span className="material-symbols-outlined text-[15px] text-outline">arrow_back</span>
              Back to cases
            </Link>
          </div>
        </section>

        {status === "expired" && (
          <section className="rounded-xl border border-rose-200 bg-error-container p-4 text-sm text-on-error-container">
            Run expired — the API restarted and in-memory runs were cleared. Re-run diagnosis from
            the case workspace.
          </section>
        )}

        <div className="grid grid-cols-1 gap-6 2xl:grid-cols-12">
          <div className="flex flex-col gap-6 2xl:col-span-8">
            <section className="rounded-xl border border-outline-variant bg-surface-container-lowest shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-outline-variant bg-surface-container-low px-5 py-3">
                <div className="flex items-center gap-3">
                  <span
                    className={`h-2.5 w-2.5 rounded-full ${
                      done ? "bg-tertiary-container" : "animate-ping bg-primary"
                    }`}
                  />
                  <div className="flex flex-col">
                    <span className="text-sm font-bold uppercase tracking-wider text-on-surface">
                      Agent Event Stream
                    </span>
                    <span className="text-xs text-outline">
                      LangGraph DAG — fan-out, debate, consensus, self-critique
                    </span>
                  </div>
                </div>
                <span className="rounded bg-surface-container px-2 py-0.5 font-mono text-[11px] font-bold text-on-surface-variant">
                  {events.length} EVENTS
                </span>
              </div>
              <div className="flex flex-col gap-2 p-4">
                {steps.map((ev, i) => (
                  <EventCard key={i} ev={ev} />
                ))}
                {others.map((ev, i) => (
                  <div
                    key={`o${i}`}
                    className="flex items-center gap-2 rounded-lg px-3 py-1.5 font-mono text-[11px] text-outline"
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-outline-variant" />
                    <span className="uppercase">{ev.type}</span>
                    {ev.status && <span className="text-on-surface-variant">{ev.status}</span>}
                  </div>
                ))}
                {events.length === 0 && (
                  <p className="py-6 text-center text-sm text-outline">
                    Waiting for swarm events…
                  </p>
                )}
              </div>
            </section>

            {others.length > 0 && (
              <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-4 shadow-sm">
                <span className="text-[11px] font-bold uppercase tracking-wider text-outline">
                  Run Lifecycle
                </span>
                <div className="mt-2 flex flex-wrap gap-2">
                  {others.map((ev, i) => (
                    <span
                      key={i}
                      className="rounded border border-outline-variant bg-surface-container px-2 py-1 font-mono text-[11px] uppercase text-on-surface-variant"
                    >
                      {ev.type}
                    </span>
                  ))}
                </div>
              </section>
            )}
          </div>

          <div className="flex flex-col gap-6 2xl:col-span-4">
            <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
              <div className="mb-4 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="material-symbols-outlined text-[20px] text-primary">
                    manage_search
                  </span>
                  <span className="font-headline text-sm font-bold uppercase tracking-wider text-on-surface">
                    Reasoning Inspector
                  </span>
                </div>
                <span className="rounded bg-surface-container-high px-2 py-0.5 font-mono text-[11px] font-bold text-primary">
                  {status.toUpperCase()}
                </span>
              </div>

              {consensus ? (
                <div className="flex flex-col gap-4">
                  {consensus.abstain ? (
                    <div className="rounded-lg border border-error/40 bg-error-container/30 p-3">
                      <div className="flex items-center gap-1.5">
                        <span className="material-symbols-outlined text-[16px] text-error">
                          report
                        </span>
                        <span className="text-xs font-semibold text-error">
                          Abstained — Insufficient Evidence
                        </span>
                      </div>
                      <p className="mt-1.5 text-sm font-bold text-on-surface">
                        {consensus.abstain.reason}
                      </p>
                      <div className="mt-2 flex flex-col gap-1 text-xs text-on-surface-variant">
                        <div>
                          <span className="font-semibold">Known:</span>{" "}
                          {consensus.abstain.known ? abstainList(consensus.abstain.known) : ""}
                        </div>
                        <div>
                          <span className="font-semibold">Unknown:</span>{" "}
                          {consensus.abstain.unknown ? abstainList(consensus.abstain.unknown) : ""}
                        </div>
                        <div>
                          <span className="font-semibold">Resolvable by:</span>{" "}
                          {consensus.abstain.resolvable_by ? abstainList(consensus.abstain.resolvable_by) : ""}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="rounded-lg border border-outline-variant bg-surface-container p-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-semibold text-primary">
                          {STATE_LABELS[consensus.diagnosis_state ?? ""] ?? "Assessment"}
                        </span>
                        <span className="font-mono text-xs font-bold text-primary">
                          {((consensus.confidence ?? 0) * 100).toFixed(1)}%
                          <span className="font-normal text-outline"> model self-report, uncalibrated</span>
                        </span>
                      </div>
                      <p className="mt-1.5 text-sm font-bold text-on-surface">{consensus.diagnosis}</p>
                      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-surface-container-highest">
                        <div
                          className="h-full rounded-full bg-primary-container"
                          style={{ width: `${Math.round((consensus.confidence ?? 0) * 100)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  <div>
                    <div className="mb-2 flex items-center gap-1 rounded-lg bg-surface-container-low p-1">
                      <button
                        onClick={() => setView("clinician")}
                        className={`flex-1 rounded px-2 py-1 font-mono text-[11px] font-bold uppercase transition-all ${
                          view === "clinician"
                            ? "bg-white text-primary shadow-xs border border-outline-variant"
                            : "text-outline hover:text-on-surface"
                        }`}
                      >
                        Clinician
                      </button>
                      <button
                        onClick={() => setView("patient")}
                        className={`flex-1 rounded px-2 py-1 font-mono text-[11px] font-bold uppercase transition-all ${
                          view === "patient"
                            ? "bg-white text-primary shadow-xs border border-outline-variant"
                            : "text-outline hover:text-on-surface"
                        }`}
                      >
                        Patient
                      </button>
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-on-surface-variant">
                      {view === "clinician"
                        ? (result?.explain?.clinician ?? "")
                        : (result?.explain?.patient ?? "")}
                    </p>
                  </div>

                  {!!result?.warnings?.length && (
                    <div>
                      <div className="mb-1.5 flex items-center justify-between">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-outline">
                          Information Deficits
                        </span>
                        <span className="font-mono text-[11px] font-bold text-error">
                          {result.warnings.length} FLAGS
                        </span>
                      </div>
                      <ul className="flex flex-col gap-1.5">
                        {result.warnings.map((w, i) => (
                          <li
                            key={i}
                            className="flex items-start gap-1.5 rounded bg-surface-container p-2 font-mono text-[11px] text-on-surface-variant"
                          >
                            <span className="material-symbols-outlined text-[14px] text-error">
                              cancel
                            </span>
                            <span>{w}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {!!result?.evidence?.length && (
                    <div>
                      <span className="text-[11px] font-bold uppercase tracking-wider text-outline">
                        Grounding Citations ({result.evidence.length})
                      </span>
                      <ul className="mt-1.5 flex flex-col gap-1">
                        {result.evidence.map((e) => (
                          <li
                            key={e.id}
                            className="flex items-center justify-between rounded border border-outline-variant bg-surface-container-lowest px-2 py-1.5 font-mono text-[11px]"
                          >
                            <span className="truncate text-on-surface-variant">{e.id}</span>
                            {typeof e.metadata?.year === "number" && (
                              <span className="ml-2 shrink-0 font-bold text-primary">
                                {e.metadata.year}
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2 py-8 text-center">
                  <span className="material-symbols-outlined animate-spin text-[28px] text-primary">
                    progress_activity
                  </span>
                  <p className="text-sm font-semibold text-on-surface">
                    {status === "expired" ? "Run no longer available" : "Waiting for consensus…"}
                  </p>
                  <p className="font-mono text-[11px] text-outline">
                    {status === "expired"
                      ? "in-memory run store cleared"
                      : `${events.length} events streamed`}
                  </p>
                </div>
              )}
            </section>
          </div>
        </div>
      </div>
    </Shell>
  );
}
