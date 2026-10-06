"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Shell } from "@/components/shell";
import { api, getToken } from "@/lib/api";

interface SystemStatus {
  status: string;
  version: string;
  llm: string;
  auth: string;
  uptime_seconds: number;
  rate_limit: Record<string, string>;
}

const ENDPOINTS: [string, string, string][] = [
  ["GET", "/api/health", "Health check"],
  ["POST", "/api/auth/login", "JWT login (admin)"],
  ["GET", "/api/system/status", "Provider, auth, uptime"],
  ["GET", "/api/alerts", "Failed runs + high-risk cases"],
  ["GET", "/api/runs", "Diagnosis run list (persisted)"],
  ["GET", "/api/runs/{id}", "Run snapshot (DB-hydrated)"],
  ["POST", "/api/cases", "Create case (201 + Location)"],
  ["POST", "/api/cases/{id}/diagnose", "Start swarm (202, rate 5/min)"],
  ["POST", "/api/cases/{id}/chat", "Board group chat (REST)"],
  ["WS", "/ws/cases/{id}/chat", "Board group chat (streaming)"],
  ["WS", "/ws/runs/{id}", "Live run event stream"],
  ["POST", "/api/cases/{id}/visits", "Longitudinal visit (201)"],
  ["GET", "/api/cases/{id}/visits", "Visits + progression"],
  ["GET", "/api/evidence/search?q=", "Verified RAG citations"],
  ["POST", "/api/documents/ingest", "sha256 ingest + standardize"],
  ["POST", "/api/vision/analyze", "DICOM/image analysis"],
];

function uptimeLabel(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m ${seconds % 60}s`;
}

export default function AdminPage() {
  const router = useRouter();
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api<SystemStatus>("/api/system/status")
      .then(setStatus)
      .catch((err) => {
        if (err instanceof Error && "status" in err && err.status === 401) {
          router.push("/login");
        } else {
          setError(err instanceof Error ? err.message : "Failed to load status");
        }
      });
  }, [router]);

  return (
    <Shell crumbs={[{ label: "Administration" }]}>
      <div className="flex flex-col gap-6 p-6">
        <section>
          <h1 className="font-headline text-2xl font-bold text-on-surface">
            Administration
          </h1>
          <p className="mt-1 text-sm text-on-surface-variant">
            System posture, providers, rate limits, and the live API surface.
          </p>
        </section>

        {error && (
          <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 font-mono text-xs text-rose-700">
            {error}
          </p>
        )}

        {status ? (
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {[
              ["dns", "API", `${status.status} · v${status.version}`],
              ["neurology", "LLM provider", status.llm],
              ["lock", "Auth", status.auth],
              ["schedule", "Uptime", uptimeLabel(status.uptime_seconds)],
            ].map(([icon, label, value]) => (
              <div
                key={label}
                className="flex items-center gap-3 rounded-xl border border-outline-variant bg-surface-container-lowest p-4 shadow-xs"
              >
                <span className="material-symbols-outlined text-[22px] text-primary">
                  {icon}
                </span>
                <div className="flex min-w-0 flex-col">
                  <span className="text-xs font-bold uppercase tracking-wider text-outline">
                    {label}
                  </span>
                  <span className="truncate font-mono text-sm font-bold text-on-surface">
                    {value}
                  </span>
                </div>
              </div>
            ))}
          </section>
        ) : (
          !error && <p className="text-sm text-outline">Loading status…</p>
        )}

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-12">
          <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm xl:col-span-5">
            <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
              <span className="material-symbols-outlined text-[18px] text-primary">
                speed
              </span>
              Rate limits
            </h2>
            <div className="flex flex-col divide-y divide-outline-variant font-mono text-xs">
              {Object.entries(status?.rate_limit ?? {}).map(([k, v]) => (
                <div key={k} className="flex justify-between py-2">
                  <span className="text-outline">{k}</span>
                  <span className="font-bold text-on-surface">{v}</span>
                </div>
              ))}
            </div>

            <h2 className="mb-3 mt-6 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
              <span className="material-symbols-outlined text-[18px] text-primary">
                verified_user
              </span>
              Security posture
            </h2>
            <ul className="flex flex-col gap-2 font-mono text-xs text-on-surface-variant">
              {[
                "PHI scrubbed before every LLM call (Presidio)",
                "sha256 integrity on every ingest",
                "JWT bearer auth on /api/* + WS upgrade",
                "CORS restricted via CORS_ORIGINS",
              ].map((item) => (
                <li key={item} className="flex items-start gap-2">
                  <span className="material-symbols-outlined text-[14px] text-emerald-600">
                    check_circle
                  </span>
                  {item}
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm xl:col-span-7">
            <h2 className="mb-3 flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-on-surface">
              <span className="material-symbols-outlined text-[18px] text-primary">
                api
              </span>
              API surface
            </h2>
            <div className="flex flex-col divide-y divide-outline-variant">
              {ENDPOINTS.map(([method, path, desc]) => (
                <div key={`${method}${path}`} className="flex items-center gap-3 py-2">
                  <span
                    className={`w-12 shrink-0 rounded px-1.5 py-0.5 text-center font-mono text-[10px] font-bold ${
                      method === "GET"
                        ? "bg-sky-50 text-sky-700"
                        : method === "WS"
                          ? "bg-violet-50 text-violet-700"
                          : "bg-emerald-50 text-emerald-700"
                    }`}
                  >
                    {method}
                  </span>
                  <span className="w-64 shrink-0 truncate font-mono text-xs text-on-surface">
                    {path}
                  </span>
                  <span className="truncate text-xs text-outline">{desc}</span>
                </div>
              ))}
            </div>
          </section>
        </div>
      </div>
    </Shell>
  );
}
