"use client";

export interface ReadinessItem {
  key: string;
  label: string;
  status: "complete" | "pending" | "missing" | "not_applicable";
  reason: string;
}

export interface ReadinessPathway {
  score: number;
  ready: boolean;
  confidence: number;
  items: ReadinessItem[];
}

export interface Recommendation {
  test: string;
  question: string;
  why: string;
  priority: string;
  pathway: string;
  conditional: boolean;
}

export interface Readiness {
  system_status: string;
  pathways: Record<string, ReadinessPathway>;
  recommended_tests: string[];
  recommendations?: Recommendation[];
  uncertainty_flags: { key: string; message: string }[];
}

const PATHWAY_LABELS: Record<string, string> = {
  diagnostic: "Diagnostic assessment",
  staging: "Staging assessment",
  treatment: "Treatment planning",
};

const STATUS_TONE: Record<string, string> = {
  complete: "bg-emerald-500",
  pending: "bg-amber-500",
  missing: "bg-error",
  not_applicable: "bg-outline-variant",
};

const TIER_BANNER: Record<string, [string, string]> = {
  READY_FOR_TREATMENT_PLANNING: ["bg-emerald-50 text-emerald-700", "Ready for treatment planning"],
  READY_FOR_STAGING: ["bg-emerald-50 text-emerald-700", "Ready for staging"],
  READY_FOR_DIAGNOSIS: ["bg-amber-50 text-amber-700", "Ready for diagnosis"],
  NOT_READY: [
    "bg-error-container text-on-error-container",
    "Not ready — evidence still needed",
  ],
};

function PathwayBar({ name, pw }: { name: string; pw: ReadinessPathway }) {
  const label = PATHWAY_LABELS[name] ?? name;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className="font-semibold text-on-surface">{label}</span>
        <span className="flex items-center gap-2 font-mono text-[11px]">
          <span className={pw.ready ? "text-emerald-600" : "text-amber-700"}>
            {pw.ready ? "READY" : "GAPS"}
          </span>
          <span className="font-bold text-on-surface-variant">{pw.score}%</span>
          <span className="text-outline">conf {pw.confidence}</span>
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-surface-container-highest">
        <div
          className={`h-full rounded-full ${pw.ready ? "bg-emerald-500" : "bg-amber-500"}`}
          style={{ width: `${pw.score}%` }}
        />
      </div>
    </div>
  );
}

export function ReadinessPanel({ readiness }: { readiness: Readiness | null }) {
  if (!readiness) {
    return (
      <p className="font-mono text-[11px] text-outline">
        Awaiting required intake (age, sex, reason)…
      </p>
    );
  }
  const [tone, label] = TIER_BANNER[readiness.system_status] ?? [
    "bg-amber-50 text-amber-700",
    "Assessing…",
  ];
  const gaps = readiness.uncertainty_flags ?? [];
  return (
    <div className="flex flex-col gap-3">
      <div className={`rounded-lg px-3 py-2 text-xs font-bold uppercase tracking-wider ${tone}`}>
        {label}
      </div>
      {Object.entries(readiness.pathways).map(([name, pw]) => (
        <PathwayBar key={name} name={name} pw={pw} />
      ))}
      {gaps.length > 0 && (
        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-bold uppercase tracking-wider text-outline">
            Clinical data gaps — incomplete profile
          </span>
          <ul className="flex flex-col gap-0.5 text-xs text-on-surface-variant">
            {gaps.map((f) => (
              <li key={f.key} className="flex items-start gap-1.5">
                <span className="material-symbols-outlined text-[13px] text-amber-600">
                  help
                </span>
                {f.message}
              </li>
            ))}
          </ul>
        </div>
      )}
      {readiness.recommendations && readiness.recommendations.length > 0 ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-[11px] font-bold uppercase tracking-wider text-outline">
            Recommended next investigations
          </span>
          <ul className="flex flex-col gap-1.5 text-xs text-on-surface-variant">
            {readiness.recommendations.map((rec) => (
              <li key={rec.test} className="flex flex-col gap-0.5 rounded-lg bg-surface-container-low p-2">
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
                <span className="text-[11px] text-outline">Q: {rec.question}</span>
                <span className="text-[11px]">Why: {rec.why}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        readiness.recommended_tests.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-[11px] font-bold uppercase tracking-wider text-outline">
              Recommended next tests
            </span>
            <ul className="flex flex-col gap-0.5 text-xs text-on-surface-variant">
              {readiness.recommended_tests.map((t) => (
                <li key={t} className="flex items-start gap-1.5">
                  <span className="material-symbols-outlined text-[13px] text-amber-600">
                    checklist
                  </span>
                  {t}
                </li>
              ))}
            </ul>
          </div>
        )
      )}
      <details className="rounded-lg border border-outline-variant bg-surface-container-low p-2">
        <summary className="cursor-pointer text-[11px] font-bold uppercase tracking-wider text-outline">
          Section detail
        </summary>
        <div className="mt-2 flex flex-col gap-2">
          {Object.entries(readiness.pathways).map(([name, pw]) => (
            <div key={name} className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-on-surface">
                {PATHWAY_LABELS[name] ?? name}
              </span>
              {pw.items.map((i) => (
                <div key={i.key} className="flex items-start gap-2 text-[11px]">
                  <span
                    className={`mt-1 h-2 w-2 shrink-0 rounded-full ${STATUS_TONE[i.status]}`}
                  />
                  <span className="text-on-surface">{i.label}</span>
                  <span className="text-outline">— {i.reason}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}
