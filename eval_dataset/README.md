# KANser Evaluation Dataset

Longitudinal, multimodal lung-cancer case set for evaluating the KANser diagnosis
agent against predefined ground truth. Seven patients, five real (GDC + TCIA)
and two synthetic (clearly labeled).

## Roster

| id | origin | source case | scenario | histology class | stage class |
|------|-----------|------------------|----------------------------------------------|-------------------------------|-------------|
| P001 | real | TCGA-J2-A4AE | early-stage adenocarcinoma, no recurrence to last FU | lung_adenocarcinoma | IA |
| P002 | real | TCGA-34-8454 | locally advanced squamous carcinoma, tumor-free FU | lung_squamous_cell_carcinoma | IIIA |
| P003 | real | TCGA-38-6178 | EGFR-mutated adenocarcinoma, disease present at FU | lung_adenocarcinoma | IIIA |
| P004 | real | TCGA-50-6591 | metastatic adenocarcinoma, rapid decline, death d119 | lung_adenocarcinoma | IV |
| P005 | real | TCGA-50-5049 | early-stage adenocarcinoma, late recurrence at d2146 | lung_adenocarcinoma | IA (see note) |
| P006 | synthetic | none | extensive-stage small cell carcinoma, response then progression | small_cell_lung_carcinoma | extensive_stage |
| P007 | synthetic | none | incidental nodule, benign granuloma on biopsy | benign_pulmonary_granuloma | not_applicable |

Trajectories deliberately do not march I to IV: P001 never recurs, P002 stays
tumor-free after locally advanced disease, P004 dies within four months,
P005 recurs only after six years.

## Real vs synthetic

Every event in every `patients/<id>/timeline.json` carries `data_origin`:

- `real` - value copied from a source API response (follow-up responses,
  staging descriptors, demographics, molecular calls, TCIA series metadata).
- `real_derived` - narrative text assembled only from real structured fields
  (e.g. pathology sentence built from `primary_diagnosis` + `morphology`).
- `synthetic` - constructed for evaluation, never attributable to a real
  patient (symptom narratives, radiology report text, all treatment events,
  all of P006 and P007).

| field | P001-P005 (real) | P006-P007 (synthetic) |
|---|---|---|
| demographics, vital status, follow-up responses | real | synthetic |
| histology / ICD-O-3 / T,N,M descriptors | real | synthetic |
| molecular variants (EGFR, TP53, ...) | real (open GDC MAF) | not tested / n/a |
| imaging metadata (modality, series) | real (TCIA) | synthetic |
| radiology report text, symptoms, labs | synthetic | synthetic |
| treatment records | synthetic (TCGA has none) | synthetic |
| absolute calendar dates | absent (TCGA date-obfuscated; day offsets used) | synthetic |

## Sources and provenance

Raw API responses are stored verbatim under `sources/` - these are the
provenance record for every `real` value above.

- Clinical/demographic/follow-up: NCI Genomic Data Commons (GDC) Cases API
  `POST https://api.gdc.cancer.gov/cases` with `expand=demographic,diagnoses,follow_ups,exposures,treatments`
  - one file per case: `sources/gdc/<barcode>.json`
  - fetched 2026-10-07
- Molecular: GDC open-access `Masked Somatic Mutation` MAF files
  (`data_category=Simple Nucleotide Variation`, `access=open`), downloaded from
  `https://api.gdc.cancer.gov/data/<file_id>`; file UUIDs are recorded in each
  timeline's molecular event `source` field and in ground truth. Files are
  gzip-compressed MAFs; variant calls were extracted verbatim.
- Imaging metadata: TCIA NBIA API
  `GET https://services.cancerimagingarchive.net/nbia-api/services/v1/getSeries?Collection=<C>&PatientID=<P>&format=json`
  - `sources/tcia/<barcode>_series.json` (series modality/description only; no
    pixel data is distributed with this dataset)
  - fetched 2026-10-07
- Candidate selection: TCIA patient lists from NBIA `getPatient`
  intersected with GDC cases filtered by `diagnoses.ajcc_pathologic_stage`, so
  every real patient has both GDC clinical data and TCIA imaging metadata.

Unavailable sources (documented, not silently replaced): MIMIC-IV/-Note
requires PhysioNet credentialing; the IDC API returns HTTP 410; GDC holds no
SCLC project; no TCIA collection is SCLC-specific. SCLC (P006) and the benign
case (P007) are therefore synthetic.

## Licensing and citation

- GDC/TCGA open-access data: free to use under TCGA data-usage policy. Do not
  attempt to re-identify participants. Cite: TCGA Research Network,
  https://www.cancergenome.nih.gov; NCI Genomic Data Commons,
  https://gdc.cancer.gov.
- TCIA metadata: The Cancer Imaging Archive - collections TCGA-LUAD and
  TCGA-LUSC. Most TCIA collections are CC BY 4.0 unless a collection page says
  otherwise; check the per-collection license and citation requirements at
  https://www.cancerimagingarchive.net before redistributing anything from
  `sources/tcia/`.
- Synthetic cases P006/P007: constructed for this evaluation, no license
  constraints, but never present them as real patient data.

## Ground truth: hidden from the agent

`ground_truth/ground_truth.json` is immutable reference data. It contains
histology class, stage class, EGFR status, scenario, outcomes and provenance.

Protocol:

1. Run `python evaluate.py --build-inputs` - writes `build/agent_input/<pid>/`
   containing only `case.json` + the timeline filtered to the cutoff day.
2. Point the diagnosis agent at `build/agent_input/` (or `patients/`) only.
   Never expose `ground_truth/` or `patients/*/timeline.json` beyond the
   cutoff when running a horizon-limited evaluation.
3. Collect the agent's predictions as JSON, then score with
   `python evaluate.py <predictions.json>`.

`evaluate.py --validate` re-checks dataset integrity, including that no event
text contains an AJCC stage label (the one ground-truth leak vector in
`patients/`).

## Chronological protocol

- Events are ordered by `day_offset` (0 = index diagnosis). Real patients have
  no absolute dates: TCGA open data is date-obfuscated, so day offsets are the
  honest representation. Synthetic cases carry explicit synthetic dates.
- `case.json.default_as_of_day` is the default cutoff. `--build-inputs --as-of N`
  filters every patient to day N, so a horizon-limited run (e.g. "diagnose from
  the first 90 days") never shows the agent later events.

## What is scored

Predictions file: JSON list of `patient_id`, `histology`, `stage`, `egfr`
(free text is normalized against the label sets).

- histology: accuracy, per-class precision/recall/F1, macro and weighted F1,
  confusion matrix
- stage: same metrics (P005 accepts IA or IB, see note below)
- EGFR: accuracy/P/R/F1 over the five cases where EGFR status is meaningful
- per-patient OK/FAIL lines and an overall exact-match count
- `--strict` exits non-zero unless everything is correct

Outcome, trajectory and treatment response are recorded in ground truth for
human review but are not scored.

## Known limitations (read before citing results)

- P005 source conflict: GDC records `ajcc_pathologic_stage = Stage IA` while the
  descriptors read T2 N0 M0 (AJCC would map that to IB). Both appear in the
  record; scoring accepts IA or IB, and `stage_detail` explains why.
- EGFR "mutant" means an EGFR coding variant exists in the open MAF. Only
  P003's `p.E746_A750del` is a classic activating exon-19 deletion; P004's
  `p.K754_I759del`/`p.L833V` are reported as-is without a pathogenicity claim.
  "not_mutated" means no EGFR variant was called in that file.
- Treatment events for real patients are synthetic: TCGA case records have
  empty `treatments` blocks.
- Imaging is metadata only (no pixels, no report text) - the agent cannot read
  images from this dataset.
- Sex is read from GDC `sex_at_birth` (not the empty `sex` field).
- Two synthetic patients only. Five real patients is the practical maximum
  without proprietary data: GDC has no SCLC, MIMIC needs credentials, and IDC
  is retired (HTTP 410).

## Layout

```
eval_dataset/
├── README.md
├── evaluate.py                  # validator, input builder, scorer
├── predictions.example.json     # reference run (scores 7/7)
├── ground_truth/
│   └── ground_truth.json        # IMMUTABLE, never shown to the agent
├── patients/
│   └── P00X/
│       ├── case.json            # agent-safe metadata (no answers)
│       └── timeline.json        # chronological events with data_origin
└── sources/
    ├── gdc/<barcode>.json       # raw GDC API responses
    └── tcia/<barcode>_series.json
```

## Commands

```bash
cd eval_dataset
python evaluate.py --validate            # dataset integrity
python evaluate.py --build-inputs        # agent-visible inputs -> build/agent_input/
python evaluate.py --build-inputs --as-of 90   # horizon-limited inputs
python evaluate.py predictions.example.json    # reference scoring run
python evaluate.py my_predictions.json --strict
```
