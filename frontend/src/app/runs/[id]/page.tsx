"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/card";
import { api, getToken } from "@/lib/api";
import { type RunEvent } from "@/lib/runEvents";
import { useRunStream } from "@/lib/useRunStream";

interface RunResult {
  consensus?: { diagnosis?: string; confidence?: number };
  explain?: { clinician?: string; patient?: string };
  warnings?: string[];
  evidence?: { id: string; metadata?: Record<string, unknown> }[];
  reports?: Record<string, { hypothesis?: string; confidence?: number }>;
}

export default function RunPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { events, done, status } = useRunStream(id);
  const [result, setResult] = useState<RunResult | null>(null);
  const [view, setView] = useState<"clinician" | "patient">("clinician");

  useEffect(() => {
    if (!getToken()) router.push("/login");
  }, [router]);

  useEffect(() => {
    if (!done) return;
    api<{ status: string; result: RunResult | null }>(`/api/runs/${id}`)
      .then((snap) => setResult(snap.result))
      .catch(() => undefined);
  }, [done, id]);

  const consensus = result?.consensus;

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Run {id.slice(0, 8)}</h1>
        <span
          className={
            done ? "text-sm text-green-700" : "animate-pulse text-sm text-amber-600"
          }
        >
          {status}
        </span>
      </div>

      <Card>
        <h2 className="mb-3 font-medium">Agent timeline</h2>
        <ul className="flex flex-col gap-1">
          {events.map((ev: RunEvent, i: number) => (
            <li key={i} className="flex gap-2 text-sm">
              <code className="shrink-0 text-neutral-500">{ev.type}</code>
              <span className="min-w-0">
                <span>
                  {ev.node}
                  {ev.status ? ` · ${ev.status}` : ""}
                  {"confidence" in ev ? ` · ${String(ev.confidence)}` : ""}
                  {"hits" in ev ? ` · ${String(ev.hits)} hits` : ""}
                  {"round" in ev ? ` · round ${String(ev.round)}` : ""}
                </span>
                {typeof ev.detail === "string" && ev.detail && (
                  <span className="block whitespace-pre-wrap break-words text-xs text-neutral-500">
                    {ev.detail}
                  </span>
                )}
              </span>
            </li>
          ))}
          {events.length === 0 && (
            <li className="text-sm text-neutral-500">Waiting for events…</li>
          )}
        </ul>
      </Card>

      {consensus && (
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="font-medium">Report</h2>
            <div className="flex gap-2 text-sm">
              <button
                className={view === "clinician" ? "font-semibold text-blue-600" : ""}
                onClick={() => setView("clinician")}
              >
                Clinician
              </button>
              <button
                className={view === "patient" ? "font-semibold text-blue-600" : ""}
                onClick={() => setView("patient")}
              >
                Patient
              </button>
            </div>
          </div>
          <p className="text-lg font-medium">{consensus.diagnosis}</p>
          <p className="text-sm text-neutral-500">
            confidence {(consensus.confidence ?? 0).toFixed(2)}
          </p>
          <p className="mt-3 whitespace-pre-wrap text-sm">
            {view === "clinician"
              ? (result?.explain?.clinician ?? "")
              : (result?.explain?.patient ?? "")}
          </p>
          {!!result?.warnings?.length && (
            <>
              <h3 className="mt-4 mb-1 font-medium text-amber-700">Warnings</h3>
              <ul className="list-disc pl-5 text-sm text-amber-800">
                {result.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </>
          )}
          {!!result?.evidence?.length && (
            <>
              <h3 className="mt-4 mb-1 font-medium">Evidence</h3>
              <ul className="list-disc pl-5 text-sm">
                {result.evidence.map((e) => (
                  <li key={e.id}>
                    {e.id}{" "}
                    {typeof e.metadata?.year === "number" ? `(${e.metadata.year})` : ""}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
      )}

      <Link href="/cases" className="text-sm text-blue-600 hover:underline">
        ← Back to cases
      </Link>
    </main>
  );
}
