"use client";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { AssessmentPanel } from "@/components/assessment-panel";
import { CaseTimeline } from "@/components/case-timeline";
import { FindingsPanel } from "@/components/findings-panel";
import { GroupChat } from "@/components/group-chat";
import { Shell } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { api, getToken } from "@/lib/api";

interface Case {
  id: string;
  patient_ref: string;
  modalities: string[];
  clinical_notes: string;
  metadata: Record<string, string>;
  created_at?: string;
}

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState<"diagnose" | null>(null);
  const [assessKey, setAssessKey] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    let cancelled = false;
    api<Case>(`/api/cases/${id}`)
      .then((data) => {
        if (!cancelled) setCaseData(data);
      })
      .catch((err) => {
        if (!cancelled && err instanceof Error && "status" in err && err.status === 401) {
          router.push("/login");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [id, router]);

  async function diagnose() {
    setMessage(null);
    setBusy("diagnose");
    try {
      const { run_id } = await api<{ run_id: string }>(`/api/cases/${id}/diagnose`, {
        method: "POST",
      });
      router.push(`/runs/${run_id}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Diagnose failed");
      setBusy(null);
    }
  }

  async function upload(file: File) {
    setMessage(null);
    const form = new FormData();
    form.append("file", file);
    form.append("case_id", id);
    try {
      const res = await api<{
        filename: string;
        sha256: string;
        kind: string | null;
        standardized: { labs?: { values: Record<string, string> } } | null;
      }>("/api/documents/ingest", {
        method: "POST",
        body: form,
      });
      const parsed = res.standardized
        ? ` · standardized (${Object.keys(res.standardized.labs?.values ?? {}).length} labs)`
        : "";
      setMessage(
        `Uploaded ${res.filename} [${res.kind ?? "raw"}] (sha256 ${res.sha256.slice(0, 12)}…)${parsed}`,
      );
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Upload failed");
    }
  }

  if (!caseData) {
    return (
      <Shell crumbs={[{ label: "Cases", href: "/cases" }, { label: "…" }]}>
        <main className="p-6 text-sm text-outline">Loading case…</main>
      </Shell>
    );
  }

  const finding = caseData.clinical_notes.split("\n")[0]?.slice(0, 90) || "No primary finding";

  return (
    <Shell
      crumbs={[
        { label: "Cases", href: "/cases" },
        { label: caseData.patient_ref },
        { label: "Workspace" },
      ]}
    >
      <div className="flex flex-col gap-6 p-6">
        <section className="flex flex-col gap-3 rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-xs">
          <div className="flex flex-col justify-between gap-4 xl:flex-row xl:items-center">
            <div className="flex flex-col gap-1.5">
              <div className="flex flex-wrap items-center gap-2.5">
                <span className="rounded border border-sky-200 bg-sky-50 px-2 py-0.5 font-mono text-sm font-bold text-primary">
                  {caseData.patient_ref}
                </span>
                <span className="h-1.5 w-1.5 rounded-full bg-outline-variant" />
                <span className="text-sm font-medium text-on-surface-variant">
                  {caseData.modalities.join(" · ") || "no modalities"}
                </span>
                <span className="flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 font-mono text-xs text-emerald-700">
                  <span className="h-1.5 w-1.5 animate-ping rounded-full bg-emerald-500" />
                  Multimodal Case Open
                </span>
              </div>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="font-mono text-xs font-semibold uppercase tracking-wider text-outline">
                  Primary Finding:
                </span>
                <span className="font-headline text-lg font-bold tracking-tight text-on-surface">
                  {finding}
                </span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 self-start xl:self-auto">
              <Button variant="outline" onClick={() => fileRef.current?.click()}>
                Upload study
              </Button>
              <Button onClick={diagnose} disabled={busy !== null}>
                {busy === "diagnose" ? "Starting…" : "Run diagnosis"}
              </Button>
            </div>
          </div>
          {message && (
            <p className="rounded-lg bg-surface-container px-3 py-2 font-mono text-xs text-primary">
              {message}
            </p>
          )}
        </section>

        <div className="grid grid-cols-1 gap-6 2xl:grid-cols-12">
          <div className="flex flex-col gap-6 2xl:col-span-8">
            <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
                <span className="material-symbols-outlined text-[18px] text-primary">
                  clinical_notes
                </span>
                Clinical Notes
              </h2>
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-on-surface-variant">
                {caseData.clinical_notes || "—"}
              </p>
            </section>

            <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
                <span className="material-symbols-outlined text-[18px] text-primary">upload</span>
                Upload study file
              </h2>
              <input
                ref={fileRef}
                type="file"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void upload(f);
                  e.target.value = "";
                }}
                className="hidden"
              />
              <button
                onClick={() => fileRef.current?.click()}
                className="flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed border-outline-variant bg-surface-container-low px-4 py-8 text-sm text-on-surface-variant transition-colors hover:border-primary hover:bg-surface-container"
              >
                <span className="material-symbols-outlined text-[28px] text-primary">
                  cloud_upload
                </span>
                <span className="font-semibold">Click to upload CT report, labs, or notes</span>
                <span className="font-mono text-[11px] text-outline">
                  sha256-verified ingestion
                </span>
              </button>
            </section>

            <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
                <span className="material-symbols-outlined text-[18px] text-primary">history</span>
                Visit timeline
              </h2>
              <CaseTimeline caseId={id} />
            </section>

            <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
                <span className="material-symbols-outlined text-[18px] text-primary">fact_check</span>
                Evidence findings
              </h2>
              <FindingsPanel caseId={id} onVerified={() => setAssessKey((k) => k + 1)} />
            </section>

            <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
              <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
                <span className="material-symbols-outlined text-[18px] text-primary">route</span>
                System 1 assessment
              </h2>
              <AssessmentPanel caseId={id} key={assessKey} />
            </section>
          </div>

          <div className="flex flex-col gap-6 2xl:col-span-4">
            <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
              <h2 className="mb-3 text-sm font-bold uppercase tracking-wider text-outline">
                Case Telemetry
              </h2>
              <div className="flex flex-col gap-2 font-mono text-xs">
                <div className="flex justify-between border-b border-surface-container-high py-1.5">
                  <span className="text-outline">Case ID</span>
                  <span className="font-bold text-on-surface">{caseData.id.slice(0, 12)}…</span>
                </div>
                <div className="flex justify-between border-b border-surface-container-high py-1.5">
                  <span className="text-outline">Modalities</span>
                  <span className="font-bold text-on-surface">{caseData.modalities.length}</span>
                </div>
                <div className="flex justify-between py-1.5">
                  <span className="text-outline">Created</span>
                  <span className="text-on-surface">
                    {caseData.created_at ? new Date(caseData.created_at).toLocaleString() : "—"}
                  </span>
                </div>
              </div>
            </section>

            <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
              <div className="flex items-center gap-2 mb-3">
                <span className="material-symbols-outlined text-[18px] text-primary">hub</span>
                <h2 className="text-sm font-bold uppercase tracking-wider text-on-surface">
                  Next Step
                </h2>
              </div>
              <p className="mb-3 text-xs text-outline">
                Fan out the agent swarm: routing, RAG evidence, debate, consensus, explanation.
              </p>
              <button
                onClick={diagnose}
                disabled={busy !== null}
                className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary-container px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-white shadow-md transition hover:opacity-90 disabled:opacity-50"
              >
                <span className="material-symbols-outlined text-[16px]">neurology</span>
                Run diagnosis
              </button>
            </section>
          </div>
        </div>

        <section>
          <div className="mb-3 flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px] text-primary">forum</span>
            <h2 className="text-sm font-bold uppercase tracking-wider text-on-surface">
              Ask the agent board
            </h2>
            <span className="font-mono text-[11px] text-outline">
              @radiologist · @clinician · @all
            </span>
          </div>
          <div className="h-[560px]">
            <GroupChat caseId={id} />
          </div>
        </section>
      </div>
    </Shell>
  );
}
