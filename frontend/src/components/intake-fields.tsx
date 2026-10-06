"use client";

export const SYMPTOMS = [
  "cough",
  "hemoptysis",
  "dyspnea",
  "chest pain",
  "weight loss",
  "fever",
  "fatigue",
  "hoarseness",
  "recurrent pneumonia",
  "neurologic symptoms",
];

export const IMAGING_STUDIES = ["ct_chest", "pet_ct"];

export const ENCOUNTERS: [string, string][] = [
  ["new_suspected", "New suspected lung cancer"],
  ["newly_diagnosed", "Newly diagnosed"],
  ["staging", "Staging"],
  ["treatment_planning", "Treatment planning"],
  ["treatment_response", "Treatment response"],
  ["recurrence", "Recurrence"],
  ["surveillance", "Surveillance"],
  ["second_opinion", "Second opinion"],
];

export const COMORBIDITIES = [
  "COPD",
  "asthma",
  "ILD",
  "cardiovascular disease",
  "CKD",
  "diabetes",
  "liver disease",
  "autoimmune disease",
  "previous cancer",
];

export const EXPOSURES = ["asbestos", "silica", "radon", "diesel exhaust"];

export type SymptomState = "unknown" | "present" | "absent";
export type StudyState = "unknown" | "performed" | "not_performed";

export function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs font-semibold text-on-surface-variant">
      {label}
      {required && <span className="text-error">*</span>}
      {children}
    </label>
  );
}

export const inputCls =
  "rounded-lg border border-outline-variant bg-white px-3 py-2 text-sm text-on-surface " +
  "placeholder:text-outline focus:border-primary focus:outline-none focus:ring-2 " +
  "focus:ring-primary/20";

export function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
}) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)} className={inputCls}>
      {options.map(([v, l]) => (
        <option key={v} value={v}>
          {l}
        </option>
      ))}
    </select>
  );
}

export function ChipGroup({
  options,
  selected,
  onToggle,
}: {
  options: string[];
  selected: string[];
  onToggle: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = selected.includes(o);
        return (
          <button
            key={o}
            type="button"
            onClick={() => onToggle(o)}
            className={`rounded-full border px-2.5 py-1 text-xs transition-colors ${
              on
                ? "border-primary bg-primary-container font-semibold text-white"
                : "border-outline-variant bg-white text-on-surface-variant hover:bg-surface-container"
            }`}
          >
            {o}
          </button>
        );
      })}
    </div>
  );
}

export function StepTitle({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-surface-container-high pb-2">
      <span className="text-sm font-bold uppercase tracking-wider text-on-surface">{title}</span>
      <span className="text-xs text-outline">{hint}</span>
    </div>
  );
}
