"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { Readiness } from "./intake-readiness";
import { ReadinessPanel } from "./intake-readiness";
import {
  ChipGroup,
  COMORBIDITIES,
  ENCOUNTERS,
  EXPOSURES,
  Field,
  IMAGING_STUDIES,
  Select,
  StepTitle,
  SYMPTOMS,
  inputCls,
  type StudyState,
  type SymptomState,
} from "./intake-fields";

interface BiomarkerRow {
  gene: string;
  result: string;
  method: string;
}

interface Draft {
  patientRef: string;
  reason: string;
  notes: string;
  age: string;
  sex: string;
  encounter: string;
  smoking: string;
  packYears: string;
  symptoms: Record<string, SymptomState>;
  exposures: string[];
  imaging: Record<string, StudyState>;
  priorImaging: string;
  tissueStatus: string;
  tissueRoute: string;
  histology: string;
  mediastinal: string;
  molecularStatus: string;
  biomarkers: BiomarkerRow[];
  ecog: string;
  fev1: string;
  dlco: string;
  comorbidities: string[];
  priorCancer: boolean;
}

const INITIAL: Draft = {
  patientRef: "",
  reason: "",
  notes: "",
  age: "",
  sex: "",
  encounter: "new_suspected",
  smoking: "unknown",
  packYears: "",
  symptoms: {},
  exposures: [],
  imaging: {},
  priorImaging: "unknown",
  tissueStatus: "unknown",
  tissueRoute: "",
  histology: "",
  mediastinal: "unknown",
  molecularStatus: "unknown",
  biomarkers: [],
  ecog: "",
  fev1: "",
  dlco: "",
  comorbidities: [],
  priorCancer: false,
};

const STEPS = ["Clinical context", "Imaging", "Pathology", "Molecular", "Clinical / labs"];

const TISSUE_STATUSES: [string, string][] = [
  ["unknown", "Not yet assessed"],
  ["no_tissue", "No tissue obtained"],
  ["biopsy_planned", "Biopsy planned"],
  ["biopsy_pending", "Biopsy pending"],
  ["biopsy_performed", "Biopsy performed"],
  ["cytology_only", "Cytology only"],
  ["histology_available", "Histology available"],
  ["surgical_specimen", "Surgical specimen"],
];

const MOLECULAR_STATUSES: [string, string][] = [
  ["unknown", "Not yet assessed"],
  ["not_ordered", "Not ordered"],
  ["ordered", "Ordered"],
  ["pending", "Pending"],
  ["partial", "Partial"],
  ["complete", "Complete"],
];

const DATA_STATES: [string, string][] = [
  ["unknown", "Unknown / not yet assessed"],
  ["assessed", "Assessed"],
  ["not_performed", "Not performed"],
  ["not_applicable", "Not applicable"],
];

const STUDY_STATES: [string, string][] = [
  ["unknown", "Not assessed"],
  ["performed", "Performed"],
  ["not_performed", "Not performed"],
];

function num(v: string): number | null {
  if (v.trim() === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function buildPayload(d: Draft) {
  const payload: Record<string, unknown> = {
    patient_ref: d.patientRef.trim() || "preview",
    clinical_notes: d.notes,
    modalities: [],
  };
  const age = num(d.age);
  if (age !== null && d.sex && d.reason.trim() !== "") {
    payload.intake = {
      age,
      sex: d.sex,
      reason_for_presentation: d.reason.trim(),
      encounter: d.encounter,
      smoking_status: d.smoking,
      pack_years: num(d.packYears),
      symptoms: Object.entries(d.symptoms)
        .filter(([, s]) => s !== "unknown")
        .map(([name, state]) => ({ name, state })),
      exposures: d.exposures,
      imaging: Object.entries(d.imaging)
        .filter(([, s]) => s === "performed")
        .map(([k]) => k),
      not_performed: Object.entries(d.imaging)
        .filter(([, s]) => s === "not_performed")
        .map(([k]) => k),
      prior_imaging: d.priorImaging,
      tissue_status: d.tissueStatus,
      tissue_route: d.tissueRoute,
      histology: d.histology,
      mediastinal: d.mediastinal,
      molecular_status: d.molecularStatus,
      biomarkers: d.biomarkers.filter((b) => b.gene.trim() !== ""),
      ecog: num(d.ecog),
      fev1_pct: num(d.fev1),
      dlco_pct: num(d.dlco),
      comorbidities: d.comorbidities,
      prior_cancer: d.priorCancer,
    };
  }
  return payload;
}

export function IntakeWizard({ onCreated }: { onCreated: (id: string) => void }) {
  const [draft, setDraft] = useState<Draft>(INITIAL);
  const [step, setStep] = useState(0);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const payload = useMemo(() => buildPayload(draft), [draft]);

  useEffect(() => {
    let cancelled = false;
    const t = setTimeout(() => {
      api<Readiness>("/api/readiness/preview", {
        method: "POST",
        body: JSON.stringify(payload),
      })
        .then((r) => {
          if (!cancelled) setReadiness(r);
        })
        .catch(() => undefined);
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [payload]);

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((prev) => ({ ...prev, [key]: value }));
  }

  function cycle<T extends string>(map: Record<string, T>, key: string, order: T[]) {
    const idx = order.indexOf(map[key] ?? order[0]);
    const next = order[(idx + 1) % order.length];
    return { ...map, [key]: next };
  }

  function toggle(list: string[], value: string) {
    return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
  }

  function validate(): string | null {
    if (draft.patientRef.trim() === "") return "Patient reference is required";
    const age = num(draft.age);
    if (age === null || age < 0 || age > 130) return "Age is required (0–130)";
    if (draft.sex === "") return "Sex is required";
    if (draft.reason.trim() === "") return "Reason for presentation is required";
    return null;
  }

  async function create() {
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const created = await api<{ id: string }>("/api/cases", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      onCreated(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Create failed");
      setBusy(false);
    }
  }

  const last = step === STEPS.length - 1;

  return (
    <section className="flex flex-col gap-4 rounded-xl border border-outline-variant bg-surface-container-lowest p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-surface-container-high pb-3">
        <span className="text-sm font-bold uppercase tracking-wider text-on-surface">
          New lung cancer case
        </span>
        <div className="flex flex-wrap gap-1.5">
          {STEPS.map((label, i) => (
            <button
              key={label}
              type="button"
              onClick={() => setStep(i)}
              className={`rounded-full px-2.5 py-1 text-[11px] font-bold transition-colors ${
                i === step
                  ? "bg-primary-container text-white"
                  : "bg-surface-container-highest text-on-surface-variant"
              }`}
            >
              {i + 1}. {label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        <div className="flex flex-col gap-4 xl:col-span-2">
          {step === 0 && (
            <>
              <StepTitle
                title="Clinical context"
                hint="Minimum to open a case: patient reference, age, sex, reason for presentation. Evidence (imaging, tissue) is added later."
              />
              <Field label="Reason for presentation" required>
                <textarea
                  className={inputCls}
                  rows={2}
                  placeholder="Persistent cough — no imaging yet"
                  value={draft.reason}
                  onChange={(e) => set("reason", e.target.value)}
                />
              </Field>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Field label="Patient reference" required>
                  <input
                    className={inputCls}
                    placeholder="DEMO-001 (no real identifiers)"
                    value={draft.patientRef}
                    onChange={(e) => set("patientRef", e.target.value)}
                  />
                </Field>
                <Field label="Age" required>
                  <input
                    className={inputCls}
                    type="number"
                    min={0}
                    max={130}
                    placeholder="62"
                    value={draft.age}
                    onChange={(e) => set("age", e.target.value)}
                  />
                </Field>
                <Field label="Sex" required>
                  <Select
                    value={draft.sex}
                    onChange={(v) => set("sex", v)}
                    options={[
                      ["", "Select…"],
                      ["male", "Male"],
                      ["female", "Female"],
                      ["other", "Other"],
                      ["unknown", "Unknown"],
                    ]}
                  />
                </Field>
                <Field label="Encounter type">
                  <Select
                    value={draft.encounter}
                    onChange={(v) => set("encounter", v)}
                    options={ENCOUNTERS}
                  />
                </Field>
                <Field label="Smoking status">
                  <Select
                    value={draft.smoking}
                    onChange={(v) => set("smoking", v)}
                    options={[
                      ["unknown", "Unknown"],
                      ["never", "Never"],
                      ["former", "Former"],
                      ["current", "Current"],
                    ]}
                  />
                </Field>
                <Field label="Pack-years">
                  <input
                    className={inputCls}
                    type="number"
                    min={0}
                    placeholder="35"
                    value={draft.packYears}
                    onChange={(e) => set("packYears", e.target.value)}
                  />
                </Field>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-on-surface-variant">
                  Symptoms (click cycles present → absent → unknown)
                </span>
                <div className="flex flex-wrap gap-1.5">
                  {SYMPTOMS.map((s) => {
                    const state = draft.symptoms[s] ?? "unknown";
                    return (
                      <button
                        key={s}
                        type="button"
                        onClick={() =>
                          set("symptoms", cycle(draft.symptoms, s, ["unknown", "present", "absent"]))
                        }
                        className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
                          state === "present"
                            ? "border-error bg-error-container text-on-error-container"
                            : state === "absent"
                              ? "border-emerald-300 bg-emerald-50 text-emerald-700"
                              : "border-outline-variant bg-white text-outline"
                        }`}
                      >
                        {s}
                        {state !== "unknown" && ` · ${state}`}
                      </button>
                    );
                  })}
                </div>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-on-surface-variant">
                  Occupational / environmental exposure
                </span>
                <ChipGroup
                  options={EXPOSURES}
                  selected={draft.exposures}
                  onToggle={(v) => set("exposures", toggle(draft.exposures, v))}
                />
              </div>
            </>
          )}

          {step === 1 && (
            <>
              <StepTitle
                title="Imaging"
                hint="Optional at creation. Record what exists — missing studies stay soft gaps, never blocks."
              />
              <div className="flex flex-col gap-2">
                {IMAGING_STUDIES.map((study) => (
                  <div
                    key={study}
                    className="flex items-center justify-between gap-3 rounded-lg border border-outline-variant bg-white px-3 py-2"
                  >
                    <span className="font-mono text-xs font-bold uppercase text-on-surface">
                      {study.replace("_", " ")}
                    </span>
                    <select
                      className="rounded-lg border border-outline-variant bg-white px-2 py-1 text-xs text-on-surface"
                      value={draft.imaging[study] ?? "unknown"}
                      onChange={(e) =>
                        set("imaging", {
                          ...draft.imaging,
                          [study]: e.target.value as StudyState,
                        })
                      }
                    >
                      {STUDY_STATES.map(([v, l]) => (
                        <option key={v} value={v}>
                          {l}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
              <Field label="Prior / comparison imaging">
                <Select
                  value={draft.priorImaging}
                  onChange={(v) => set("priorImaging", v)}
                  options={DATA_STATES}
                />
              </Field>
              <p className="text-xs text-outline">
                Upload DICOM studies and radiology reports from the case workspace after creation —
                headers and measurements are extracted automatically.
              </p>
            </>
          )}

          {step === 2 && (
            <>
              <StepTitle
                title="Tissue / pathology"
                hint="Tissue status drives diagnostic gates; histology required before tumor type."
              />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label="Tissue status">
                  <Select
                    value={draft.tissueStatus}
                    onChange={(v) => set("tissueStatus", v)}
                    options={TISSUE_STATUSES}
                  />
                </Field>
                <Field label="Acquisition route">
                  <Select
                    value={draft.tissueRoute}
                    onChange={(v) => set("tissueRoute", v)}
                    options={[
                      ["", "Not recorded"],
                      ["ct_guided", "CT-guided needle biopsy"],
                      ["bronchoscopy", "Bronchoscopy"],
                      ["ebus", "EBUS"],
                      ["surgical", "Surgical biopsy"],
                      ["other", "Other"],
                    ]}
                  />
                </Field>
                <Field label="Histology (if available)">
                  <input
                    className={inputCls}
                    placeholder="adenocarcinoma"
                    value={draft.histology}
                    onChange={(e) => set("histology", e.target.value)}
                  />
                </Field>
                <Field label="Mediastinal assessment">
                  <Select
                    value={draft.mediastinal}
                    onChange={(v) => set("mediastinal", v)}
                    options={DATA_STATES}
                  />
                </Field>
              </div>
            </>
          )}

          {step === 3 && (
            <>
              <StepTitle
                title="Molecular"
                hint="Status gates actionable-mutation inference; add biomarker rows as results arrive."
              />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label="Molecular status">
                  <Select
                    value={draft.molecularStatus}
                    onChange={(v) => set("molecularStatus", v)}
                    options={MOLECULAR_STATUSES}
                  />
                </Field>
              </div>
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-on-surface-variant">
                    Biomarkers (EGFR, ALK, PD-L1, …)
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      set("biomarkers", [
                        ...draft.biomarkers,
                        { gene: "", result: "", method: "" },
                      ])
                    }
                    className="rounded-lg border border-outline-variant bg-white px-2 py-1 text-xs font-semibold text-primary"
                  >
                    + Add biomarker
                  </button>
                </div>
                {draft.biomarkers.map((b, i) => (
                  <div key={i} className="grid grid-cols-1 gap-2 sm:grid-cols-4">
                    <input
                      className={inputCls}
                      placeholder="Gene (EGFR)"
                      value={b.gene}
                      onChange={(e) =>
                        set(
                          "biomarkers",
                          draft.biomarkers.map((row, j) =>
                            j === i ? { ...row, gene: e.target.value } : row,
                          ),
                        )
                      }
                    />
                    <input
                      className={inputCls}
                      placeholder="Result (exon 19 del / TPS 80%)"
                      value={b.result}
                      onChange={(e) =>
                        set(
                          "biomarkers",
                          draft.biomarkers.map((row, j) =>
                            j === i ? { ...row, result: e.target.value } : row,
                          ),
                        )
                      }
                    />
                    <input
                      className={inputCls}
                      placeholder="Method (NGS)"
                      value={b.method}
                      onChange={(e) =>
                        set(
                          "biomarkers",
                          draft.biomarkers.map((row, j) =>
                            j === i ? { ...row, method: e.target.value } : row,
                          ),
                        )
                      }
                    />
                    <button
                      type="button"
                      onClick={() =>
                        set(
                          "biomarkers",
                          draft.biomarkers.filter((_, j) => j !== i),
                        )
                      }
                      className="rounded-lg border border-outline-variant bg-white text-xs text-error"
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}

          {step === 4 && (
            <>
              <StepTitle
                title="Clinical / laboratory"
                hint="ECOG and PFT gate treatment-planning readiness."
              />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Field label="ECOG performance status">
                  <Select
                    value={draft.ecog}
                    onChange={(v) => set("ecog", v)}
                    options={[
                      ["", "Not recorded"],
                      ["0", "0 — fully active"],
                      ["1", "1 — restricted"],
                      ["2", "2 — ambulatory"],
                      ["3", "3 — limited self-care"],
                      ["4", "4 — disabled"],
                    ]}
                  />
                </Field>
                <Field label="FEV1 % predicted">
                  <input
                    className={inputCls}
                    type="number"
                    placeholder="72"
                    value={draft.fev1}
                    onChange={(e) => set("fev1", e.target.value)}
                  />
                </Field>
                <Field label="DLCO % predicted">
                  <input
                    className={inputCls}
                    type="number"
                    placeholder="68"
                    value={draft.dlco}
                    onChange={(e) => set("dlco", e.target.value)}
                  />
                </Field>
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-on-surface-variant">Comorbidities</span>
                <ChipGroup
                  options={COMORBIDITIES}
                  selected={draft.comorbidities}
                  onToggle={(v) => set("comorbidities", toggle(draft.comorbidities, v))}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-xs font-semibold text-on-surface-variant">
                  Prior cancer history
                </span>
                <div className="flex gap-1.5">
                  {[
                    [false, "No"],
                    [true, "Yes"],
                  ].map(([v, l]) => (
                    <button
                      key={String(v)}
                      type="button"
                      onClick={() => set("priorCancer", v as boolean)}
                      className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                        draft.priorCancer === v
                          ? "border-primary bg-primary-container font-semibold text-white"
                          : "border-outline-variant bg-white text-on-surface-variant hover:bg-surface-container"
                      }`}
                    >
                      {l}
                    </button>
                  ))}
                </div>
              </div>
              <Field label="Clinical notes">
                <textarea
                  className={inputCls}
                  rows={3}
                  placeholder="Presenting story, imaging impression, open questions…"
                  value={draft.notes}
                  onChange={(e) => set("notes", e.target.value)}
                />
              </Field>
            </>
          )}

          <div className="flex items-center justify-between gap-2 border-t border-surface-container-high pt-3">
            <Button
              type="button"
              variant="outline"
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
            >
              Back
            </Button>
            {last ? (
              <Button type="button" onClick={() => void create()} disabled={busy}>
                {busy ? "Creating…" : "Create case & open workspace"}
              </Button>
            ) : (
              <Button type="button" onClick={() => setStep((s) => s + 1)}>
                Next
              </Button>
            )}
          </div>
          {error && (
            <p className="rounded-lg bg-error-container px-3 py-2 text-sm text-on-error-container">
              {error}
            </p>
          )}
        </div>

        <aside className="rounded-xl border border-outline-variant bg-surface-container-low p-4">
          <span className="mb-3 block text-xs font-bold uppercase tracking-wider text-outline">
            Case readiness
          </span>
          <ReadinessPanel readiness={readiness} />
        </aside>
      </div>
    </section>
  );
}
