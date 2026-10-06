"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Shell } from "@/components/shell";
import { Button } from "@/components/ui/button";
import { api, getToken } from "@/lib/api";

interface Citation {
  id: string;
  text: string;
  score: number;
  rerank_score?: number;
  metadata?: Record<string, unknown>;
}

interface SearchResult {
  query: string;
  verified: Citation[];
  dropped: { id: string | null; reason: string }[];
}

export default function EvidencePage() {
  const router = useRouter();
  const [query, setQuery] = useState("stage I non-small cell lung cancer");
  const [result, setResult] = useState<SearchResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) router.push("/login");
  }, [router]);

  async function search() {
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(
        await api<SearchResult>(
          `/api/evidence/search?q=${encodeURIComponent(query.trim())}`,
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell crumbs={[{ label: "Evidence & Literature" }]}>
      <div className="flex flex-col gap-6 p-6">
        <section>
          <h1 className="font-headline text-2xl font-bold text-on-surface">
            Evidence & Literature
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            Hybrid dense + BM25 retrieval with cross-encoder rerank. Stale (&gt;5yr) and
            biomarker-contradicted papers are rejected before you see them.
          </p>
        </section>

        <section className="flex flex-col gap-3 rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-xs sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-outline">
              search
            </span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void search();
              }}
              placeholder="e.g. osimertinib EGFR mutated NSCLC"
              className="h-11 w-full rounded-lg border border-outline-variant bg-white pl-9 pr-3 text-sm text-on-surface placeholder:text-outline focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
            />
          </div>
          <Button onClick={() => void search()} disabled={busy}>
            <span className="material-symbols-outlined text-[16px]">search</span>
            {busy ? "Searching…" : "Search PubMed index"}
          </Button>
        </section>

        {error && (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 font-mono text-xs text-rose-700">
            {error}
          </p>
        )}

        {result && (
          <div className="flex flex-col gap-4">
            <div className="flex items-center gap-3 font-mono text-xs text-outline">
              <span className="rounded bg-surface-container px-2 py-1">
                {result.verified.length} verified
              </span>
              <span className="rounded bg-surface-container px-2 py-1">
                {result.dropped.length} rejected
              </span>
              <span className="truncate">query: “{result.query}”</span>
            </div>

            {result.verified.length === 0 ? (
              <div className="rounded-xl border border-dashed border-outline-variant p-8 text-center text-sm text-outline">
                No verified citations for this query. Try broader terms.
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                {result.verified.map((c) => (
                  <article
                    key={c.id}
                    className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-xs"
                  >
                    <div className="mb-2 flex flex-wrap items-center gap-2">
                      <span className="rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-mono text-[11px] font-bold text-emerald-700">
                        verified
                      </span>
                      <span className="font-mono text-xs font-bold text-primary">{c.id}</span>
                      {c.metadata?.year !== undefined && (
                        <span className="font-mono text-xs text-outline">
                          {String(c.metadata.year)}
                        </span>
                      )}
                      <span className="ml-auto font-mono text-[11px] text-outline">
                        score {c.score.toFixed(3)}
                        {c.rerank_score !== undefined
                          ? ` · rerank ${c.rerank_score.toFixed(3)}`
                          : ""}
                      </span>
                    </div>
                    <p className="text-sm leading-relaxed text-on-surface-variant">
                      {c.text.length > 600 ? `${c.text.slice(0, 600)}…` : c.text}
                    </p>
                  </article>
                ))}
              </div>
            )}

            {result.dropped.length > 0 && (
              <details className="rounded-xl border border-outline-variant bg-surface-container-low p-4">
                <summary className="cursor-pointer text-xs font-bold uppercase tracking-wider text-outline">
                  {result.dropped.length} rejected citations (stale / contradicted)
                </summary>
                <ul className="mt-2 flex flex-col gap-1 font-mono text-xs text-on-surface-variant">
                  {result.dropped.map((d, i) => (
                    <li key={`${d.id}-${i}`}>
                      {d.id} — <span className="text-rose-600">{d.reason}</span>
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )}
      </div>
    </Shell>
  );
}
