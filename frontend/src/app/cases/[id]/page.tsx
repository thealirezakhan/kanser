"use client";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, getToken } from "@/lib/api";

interface Case {
  id: string;
  patient_ref: string;
  modalities: string[];
  clinical_notes: string;
  metadata: Record<string, string>;
}

export default function CaseDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [routing, setRouting] = useState<unknown>(null);
  const [message, setMessage] = useState<string | null>(null);
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
    try {
      const { run_id } = await api<{ run_id: string }>(`/api/cases/${id}/diagnose`, {
        method: "POST",
      });
      router.push(`/runs/${run_id}`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Diagnose failed");
    }
  }

  async function previewRouting() {
    setMessage(null);
    try {
      setRouting(await api(`/api/cases/${id}/routing`, { method: "POST" }));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Routing failed");
    }
  }

  async function upload(file: File) {
    setMessage(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await api<{ filename: string; sha256: string }>(
        "/api/documents/ingest",
        { method: "POST", body: form },
      );
      setMessage(`Uploaded ${res.filename} (sha256 ${res.sha256.slice(0, 12)}…)`);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Upload failed");
    }
  }

  if (!caseData) return <main className="p-6 text-neutral-500">Loading…</main>;

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Case {caseData.patient_ref}</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={previewRouting}>
            Preview routing
          </Button>
          <Button onClick={diagnose}>Diagnose</Button>
        </div>
      </div>

      {message && <p className="text-sm text-blue-700">{message}</p>}

      <Card>
        <h2 className="mb-2 font-medium">Modalities</h2>
        <p className="text-sm">{caseData.modalities.join(", ") || "none"}</p>
        <h2 className="mt-4 mb-2 font-medium">Clinical notes</h2>
        <p className="whitespace-pre-wrap text-sm">
          {caseData.clinical_notes || "—"}
        </p>
        <h2 className="mt-4 mb-2 font-medium">Upload study file</h2>
        <input
          ref={fileRef}
          type="file"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
          }}
          className="text-sm"
        />
      </Card>

      {routing !== null && (
        <Card>
          <h2 className="mb-2 font-medium">Routing preview</h2>
          <pre className="overflow-x-auto rounded bg-neutral-50 p-3 text-xs">
            {JSON.stringify(routing, null, 2)}
          </pre>
        </Card>
      )}
    </main>
  );
}
