#!/usr/bin/env python3
"""Score diagnosis predictions for the KANser evaluation dataset.

Usage:
    python evaluate.py predictions.json
    python evaluate.py predictions.json --strict            # exit 1 unless everything correct
    python evaluate.py --build-inputs [--as-of N]           # emit agent-visible inputs only

Predictions file: JSON list of objects, e.g.
    [{"patient_id": "P001", "histology": "lung adenocarcinoma",
      "stage": "stage ia", "egfr": "not mutated"}]
Free text is normalized against the label sets in ground_truth/ground_truth.json.

--build-inputs writes build/agent_input/<pid>/ containing case.json plus the
timeline filtered to the cutoff day. That folder is the only thing a diagnosis
agent should ever read; ground_truth/ must never be exposed to it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
GT_PATH = ROOT / "ground_truth" / "ground_truth.json"

HIST_RULES = [
    (r"small\s*-?\s*cell|\bsclc\b", "small_cell_lung_carcinoma"),
    (r"squamous|sqcc|\bscc\b|epidermoid", "lung_squamous_cell_carcinoma"),
    (r"adeno|luad", "lung_adenocarcinoma"),
    (r"granulom|benign|non-?malignant|inflammator", "benign_pulmonary_granuloma"),
]

STAGE_RULES = [
    (r"extensive\s*stage|extensive\s*disease|\besclc\b", "extensive_stage"),
    (r"iiia|\b3a\b", "IIIA"),
    (r"iiib|\b3b\b", "IIIB"),
    (r"iib|\b2b\b", "IIB"),
    (r"iia|\b2a\b", "IIA"),
    (r"\biv\b|\b4\b", "IV"),
    (r"\bib\b|\b1b\b", "IB"),
    (r"\bia\b|\b1a\b", "IA"),
    (r"not\s*applicable|\bn\s*a\b|\bna\b|none", "not_applicable"),
]

EGFR_NEG = r"wild|not\s*mutat|not\s*detected|negative|absent|no\s*egfr|\bwt\b|wildtype|wild-?type"
EGFR_POS = r"mut|positive|altered|present|p\.[a-z0-9]"


def normalize(value, rules, default=None):
    text = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
    for pattern, label in rules:
        if re.search(pattern, text):
            return label
    return default if default is not None else (str(value).strip() or None)


def normalize_histology(value):
    return normalize(value, HIST_RULES, default="unmapped")


def normalize_stage(value):
    return normalize(value, STAGE_RULES, default="unmapped")


def normalize_egfr(value):
    text = re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()
    if not text:
        return None
    if re.search(r"not\s*applicable|\bn\s*a\b|\bna\b", text):
        return "not_applicable"
    if re.search(EGFR_NEG, text):
        return "EGFR_not_mutated"
    if re.search(EGFR_POS, text):
        return "EGFR_mutant"
    return str(value).strip()


def prf(confusion, labels, support):
    """Per-class precision/recall/F1 plus macro and weighted averages."""
    per_class, macro, weighted = {}, [], []
    for label in labels:
        row = confusion.get(label, {})
        tp = row.get(label, 0)
        fp = sum(confusion.get(other, {}).get(label, 0) for other in labels if other != label)
        fn = sum(row.get(other, 0) for other in labels if other != label)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        per_class[label] = (precision, recall, f1, support.get(label, 0))
        macro.append(f1)
        weight = support.get(label, 0)
        if weight:
            weighted.append((f1, weight))
    macro_f1 = sum(macro) / len(macro) if macro else 0.0
    total = sum(w for _, w in weighted)
    weighted_f1 = sum(f * w for f, w in weighted) / total if total else 0.0
    return per_class, macro_f1, weighted_f1


def score_field(gt_patients, preds, key, normalizer, accept_key=None):
    """Return (correct, total, confusion, support, rows)."""
    confusion, support, rows = {}, {}, []
    correct = total = 0
    for pid in sorted(gt_patients):
        expected = gt_patients[pid][key]
        if key == "egfr_status" and expected == "not_applicable":
            continue
        pred_raw = preds.get(pid, {}).get(key)
        got = normalizer(pred_raw) if pred_raw is not None else None
        ok = got in (gt_patients[pid].get(accept_key) or [expected]) if accept_key else got == expected
        counted = expected if ok else got
        confusion.setdefault(expected, {})
        confusion[expected][counted] = confusion[expected].get(counted, 0) + 1
        support[expected] = support.get(expected, 0) + 1
        correct += ok
        total += 1
        rows.append((pid, expected, got, ok))
    return correct, total, confusion, support, rows


def prediction_key_map(pred):
    """Map whatever the submitter called the fields onto GT field names."""
    out = dict(pred)
    aliases = {
        "histology": "histology_class",
        "diagnosis": "histology_class",
        "histology_class": "histology_class",
        "stage": "stage_class",
        "stage_class": "stage_class",
        "egfr": "egfr_status",
        "egfr_status": "egfr_status",
        "biomarker": "egfr_status",
    }
    return {aliases.get(k, k): v for k, v in out.items()}


def print_report(gt, preds, strict):
    patients = gt["patients"]
    normalizers = {
        "histology_class": normalize_histology,
        "stage_class": normalize_stage,
        "egfr_status": normalize_egfr,
    }
    titles = {
        "histology_class": "Histology (diagnosis)",
        "stage_class": "Stage / extent",
        "egfr_status": "EGFR status",
    }
    all_ok = True
    field_rows = {}
    print(f"KANser eval dataset - {len(patients)} patients")
    for key in ("histology_class", "stage_class", "egfr_status"):
        correct, total, confusion, support, rows = score_field(
            patients, preds, key, normalizers[key],
            accept_key="acceptable_stage_classes" if key == "stage_class" else None,
        )
        field_rows[key] = rows
        predicted = {r for _, _, r, _ in rows if r}
        labels = sorted(
            l for l in set(gt["label_sets"][key]) | predicted
            if support.get(l, 0) or l in predicted
        )
        accuracy = correct / total if total else 0.0
        all_ok = all_ok and correct == total
        print(f"\n== {titles[key]} ==")
        print(f"accuracy: {correct}/{total} ({accuracy:.3f})")
        per_class, macro_f1, weighted_f1 = prf(confusion, labels, support)
        print(f"{'class':32} {'P':>6} {'R':>6} {'F1':>6} {'n':>4}")
        for label in labels:
            p, r, f, n = per_class[label]
            print(f"{label:32} {p:6.3f} {r:6.3f} {f:6.3f} {n:4d}")
        print(f"macro F1: {macro_f1:.3f}   weighted F1: {weighted_f1:.3f}")
        if key in ("histology_class", "stage_class"):
            col_labels = labels
            width = max(12, max(len(x) for x in col_labels) + 1)
            print("confusion matrix (rows=expected, cols=predicted):")
            print(" " * 34 + "".join(f"{c[:width - 1]:>{width}}" for c in col_labels))
            for row in labels:
                cells = "".join(f"{confusion.get(row, {}).get(c, 0):>{width}}" for c in col_labels)
                print(f"{row:34}{cells}")
    print("\n== Per patient ==")
    for pid in sorted(patients):
        parts = []
        for key in ("histology_class", "stage_class", "egfr_status"):
            row = next((r for r in field_rows[key] if r[0] == pid), None)
            if row is None:
                parts.append(f"{key.split('_')[0]}=SKIP")
                continue
            _, expected, got, ok = row
            parts.append(f"{key.split('_')[0]}={'OK' if ok else f'FAIL(exp={expected},got={got})'}")
        verdict = "OK" if all(p.endswith("OK") or p.endswith("SKIP") for p in parts) else "FAIL"
        print(f"{pid} {verdict}  " + "  ".join(parts))
    exact = sum(
        1
        for pid in patients
        if all(
            next((r for r in field_rows[k] if r[0] == pid), (None, None, None, True))[3]
            for k in field_rows
        )
    )
    print(f"\nOverall exact (all scored fields correct): {exact}/{len(patients)}")
    if strict and not all_ok:
        sys.exit(1)


def load_predictions(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("predictions", [data])
    preds = {}
    for item in data:
        pid = item.get("patient_id") or item.get("id")
        if not pid:
            raise SystemExit("each prediction needs a patient_id")
        preds[pid] = prediction_key_map(item)
    return preds


def build_inputs(as_of):
    out_dir = ROOT / "build" / "agent_input"
    out_dir.mkdir(parents=True, exist_ok=True)
    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))
    for pid in sorted(gt["patients"]):
        case = json.loads((ROOT / "patients" / pid / "case.json").read_text(encoding="utf-8"))
        timeline = json.loads((ROOT / "patients" / pid / "timeline.json").read_text(encoding="utf-8"))
        cutoff = as_of if as_of is not None else case.get("default_as_of_day")
        case.pop("ground_truth_file", None)
        case.pop("scenario", None)
        events = [e for e in timeline["events"] if e["day_offset"] <= cutoff]
        (out_dir / pid).mkdir(parents=True, exist_ok=True)
        (out_dir / pid / "case.json").write_text(json.dumps(case, indent=2) + "\n", encoding="utf-8")
        filtered = {
            "patient_id": pid,
            "cutoff_day": cutoff,
            "time_axis": timeline["time_axis"],
            "events": events,
        }
        (out_dir / pid / "timeline.json").write_text(json.dumps(filtered, indent=2) + "\n", encoding="utf-8")
    print(f"wrote agent-visible inputs for {len(gt['patients'])} patients to {out_dir}")


def validate(gt):
    problems = []
    for pid, rec in gt["patients"].items():
        for name in ("case.json", "timeline.json"):
            path = ROOT / "patients" / pid / name
            if not path.exists():
                problems.append(f"missing {path.relative_to(ROOT)}")
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if name == "timeline.json":
                offsets = [e["day_offset"] for e in data["events"]]
                if offsets != sorted(offsets):
                    problems.append(f"{pid}: timeline not sorted by day_offset")
                if any("stage" in json.dumps(e).lower() and re.search(r"stage\s+(ia|iiia|iv)", json.dumps(e).lower()) for e in data["events"]):
                    problems.append(f"{pid}: event text contains an AJCC stage label (ground-truth leak)")
        if rec["histology_class"] not in gt["label_sets"]["histology_class"]:
            problems.append(f"{pid}: histology_class outside label set")
        if rec["stage_class"] not in gt["label_sets"]["stage_class"]:
            problems.append(f"{pid}: stage_class outside label set")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("predictions", nargs="?", help="JSON file with agent predictions")
    ap.add_argument("--strict", action="store_true", help="exit 1 unless every scored field is correct")
    ap.add_argument("--build-inputs", action="store_true", help="write build/agent_input/ (no scoring)")
    ap.add_argument("--as-of", type=int, default=None, help="cutoff day used by --build-inputs")
    ap.add_argument("--validate", action="store_true", help="check dataset integrity and exit")
    args = ap.parse_args()

    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))
    problems = validate(gt)
    if problems:
        print("dataset problems:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    if args.validate:
        print("dataset OK")
        return
    if args.build_inputs:
        build_inputs(args.as_of)
        return
    if not args.predictions:
        ap.error("predictions file required unless --build-inputs or --validate")
    print_report(gt, load_predictions(args.predictions), args.strict)


if __name__ == "__main__":
    main()
