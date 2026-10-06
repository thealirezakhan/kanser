"use client";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { GroupChat } from "@/components/group-chat";
import { Shell } from "@/components/shell";
import { api, getToken } from "@/lib/api";

interface Case {
  id: string;
  patient_ref: string;
  modalities: string[];
  created_at?: string;
}

function BoardInner() {
  const router = useRouter();
  const search = useSearchParams();
  const [cases, setCases] = useState<Case[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    let cancelled = false;
    api<Case[]>("/api/cases")
      .then((all) => {
        if (cancelled) return;
        setCases(all);
        const q = search.get("case");
        setSelected(q && all.some((c) => c.id === q) ? q : (all[0]?.id ?? null));
        setLoaded(true);
      })
      .catch((err) => {
        if (!cancelled && err instanceof Error && "status" in err && err.status === 401) {
          router.push("/login");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [router, search]);

  const active = cases.find((c) => c.id === selected) ?? null;

  return (
    <Shell crumbs={[{ label: "Tumor Board" }]}>
      <div className="flex h-[calc(100vh-4rem)] flex-col gap-4 p-6">
        <section>
          <h1 className="font-headline text-2xl font-bold text-on-surface">
            Tumor Board
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            Multidisciplinary review — pick a case and talk to all agents in one group chat.
            Mention <span className="font-mono text-xs text-primary">@radiologist</span>,{" "}
            <span className="font-mono text-xs text-primary">@clinician</span> or{" "}
            <span className="font-mono text-xs text-primary">@all</span>.
          </p>
        </section>

        <div className="grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-12">
          <aside className="flex min-h-0 flex-col rounded-xl border border-outline-variant bg-surface-container-lowest shadow-sm lg:col-span-4">
            <div className="border-b border-outline-variant px-4 py-3">
              <h2 className="text-sm font-bold uppercase tracking-wider text-on-surface">
                Board cases
              </h2>
            </div>
            <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-2">
              {!loaded ? (
                <p className="p-3 text-sm text-outline">Loading…</p>
              ) : cases.length === 0 ? (
                <div className="p-4 text-center text-sm text-outline">
                  No cases yet.{" "}
                  <Link href="/cases" className="text-primary hover:underline">
                    Create one
                  </Link>
                  .
                </div>
              ) : (
                cases.map((c) => (
                  <button
                    key={c.id}
                    onClick={() => setSelected(c.id)}
                    className={`flex flex-col items-start gap-0.5 rounded-lg border-l-4 px-3 py-2.5 text-left transition-colors ${
                      c.id === selected
                        ? "border-l-primary bg-surface-container text-on-surface"
                        : "border-l-transparent text-on-surface-variant hover:bg-surface-container-low"
                    }`}
                  >
                    <span className="font-mono text-sm font-bold">{c.patient_ref}</span>
                    <span className="truncate text-xs text-outline">
                      {c.modalities.join(" · ") || "no modalities"}
                    </span>
                    <Link
                      href={`/cases/${c.id}`}
                      className="font-mono text-[10px] text-primary hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      open workspace →
                    </Link>
                  </button>
                ))
              )}
            </div>
          </aside>

          <div className="min-h-0 lg:col-span-8">
            {active ? (
              <div className="h-full">
                <GroupChat key={active.id} caseId={active.id} />
              </div>
            ) : (
              <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-outline-variant text-sm text-outline">
                {loaded ? "Select a case to open the board chat." : "Loading…"}
              </div>
            )}
          </div>
        </div>
      </div>
    </Shell>
  );
}

export default function TumorBoardPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-outline">Loading board…</div>}>
      <BoardInner />
    </Suspense>
  );
}
