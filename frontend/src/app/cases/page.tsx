"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { api, getToken } from "@/lib/api";

interface Case {
  id: string;
  patient_ref: string;
  modalities: string[];
  created_at: string;
}

const MODALITIES = ["ct", "cxr", "pathology", "genomics", "labs", "notes"];

export default function CasesPage() {
  const router = useRouter();
  const [cases, setCases] = useState<Case[]>([]);
  const [patientRef, setPatientRef] = useState("");
  const [notes, setNotes] = useState("");
  const [mods, setMods] = useState<string[]>(["ct", "notes"]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    let cancelled = false;
    api<Case[]>("/api/cases")
      .then((data) => {
        if (!cancelled) setCases(data);
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

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const created = await api<{ id: string }>("/api/cases", {
        method: "POST",
        body: JSON.stringify({
          patient_ref: patientRef,
          modalities: mods,
          clinical_notes: notes,
        }),
      });
      router.push(`/cases/${created.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
    }
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 p-6">
      <h1 className="text-xl font-semibold">Cases</h1>

      <Card>
        <h2 className="mb-3 font-medium">New case</h2>
        <form onSubmit={create} className="flex flex-col gap-3">
          <input
            className="rounded-md border border-neutral-300 px-3 py-2 text-sm"
            placeholder="Patient reference (no real identifiers)"
            value={patientRef}
            onChange={(e) => setPatientRef(e.target.value)}
            required
          />
          <textarea
            className="rounded-md border border-neutral-300 px-3 py-2 text-sm"
            placeholder="Clinical notes"
            rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
          />
          <div className="flex flex-wrap gap-3">
            {MODALITIES.map((m) => (
              <label key={m} className="flex items-center gap-1 text-sm">
                <input
                  type="checkbox"
                  checked={mods.includes(m)}
                  onChange={(e) =>
                    setMods((prev) =>
                      e.target.checked ? [...prev, m] : prev.filter((x) => x !== m),
                    )
                  }
                />
                {m}
              </label>
            ))}
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit">Create case</Button>
        </form>
      </Card>

      <Card>
        <h2 className="mb-3 font-medium">Existing ({cases.length})</h2>
        {cases.length === 0 ? (
          <p className="text-sm text-neutral-500">No cases yet.</p>
        ) : (
          <ul className="flex flex-col divide-y">
            {cases.map((c) => (
              <li key={c.id} className="py-2">
                <Link href={`/cases/${c.id}`} className="text-blue-600 hover:underline">
                  {c.patient_ref}
                </Link>{" "}
                <span className="text-xs text-neutral-500">
                  {c.modalities.join(", ")} · {new Date(c.created_at).toLocaleString()}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </main>
  );
}
