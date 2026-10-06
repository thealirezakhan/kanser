# KANser — Laya / System 1 Architecture Audit

Companion to `docs/CLINICAL_REALITY_AUDIT.md`.
Rule followed: **only verified laya 0.3.20 capabilities are described** (read from `backend/.venv/Lib/site-packages/laya/`); anything else is marked `UNKNOWN — NEEDS VERIFICATION`.

---

## 1. Verified laya 0.3.20 capability inventory

Source: installed package `laya/__init__.py` (`__version__ = "0.3.20"`), `router.py`, `common.py`, `presets.py`, `structured.py`, `integrations/langchain.py`.

| Capability | Verified API | Evidence |
|---|---|---|
| Fast non-autoregressive decision engine with calibrated probabilities | module docstring, `Router.predict(state, questions)` | `laya/__init__.py:1`, `router.py:503` |
| 3 checkpoints, script/language-routed (english ModernBERT-large 512 tok / multilingual mmBERT 1024 tok / typed-decisions) | `DEFAULT_MODELS`, `router.py` docstring | `router.py:13-20` |
| Question types: `choice`, `score`, `noul` (normalized unit interval label) | `QTYPES = {"choice": 0, "score": 1, "noul": 2}` | `common.py:12` |
| Batch route without loading models; batch predict grouped by checkpoint | `route_batch`, `predict_batch` | `router.py:606,648` |
| Confidence functions + calibration metrics (ECE) | `answer_confidence`, `confidence_from_probs`, `ece_score` | `common.py:260,273,289` |
| Preset question sets | `triage_questions`, `email_questions`, `guard_questions`, `moderation_questions`, `router_questions` | `presets.py:5-154` |
| **Guardrail preset** (LLM input safety) | `guard_questions()` → `jailbreak`, `prompt_injection`, `sensitive_data`, `harm_severity`, `topic` | `presets.py:82-112` |
| Structured decisions from Pydantic / JSON schema | `decide`, `questions_from_pydantic`, `answer_to_pydantic`, `DecisionResult` | `structured.py` |
| LangChain integrations | `LayaRouter`, `LayaGuardrail`, `LayaTriage`, `LayaEvaluator` | `integrations/langchain.py:162,258,389,466` |
| Language detection (pure Python, no torch) | `analyse`, `detect_script`, `is_english` | `laya/lang.py` exports |
| Torch-backed names lazy-loaded | `_LAZY_ATTRS` mechanism | `laya/__init__.py` |
| ONNX agent exists | `onnx_agent.py`, `LayaRouter` in `_LAZY_ATTRS` | module list |
| HuggingFace checkpoint bundle | `convaiinnovations/laya` (+ `/multilingual`, `/typed-decisions` subfolders) | `router.py:BUNDLE_REPO` |
| **NOT verified from code** | clinical/medical checkpoints, oncology benchmarks, cancer-specific calibration, GPU throughput figures | **UNKNOWN — NEEDS VERIFICATION** |
| **NOT present** | "Jev" / Jevons logic anywhere in repo | grep `jev` backend → **0 hits** |

---

## 2. How KANser uses Laya today

`backend/app/system1.py`:

| Element | Code | Status |
|---|---|---|
| `HeuristicRouter` | modality-presence rules + keyword risk regex (`system1.py:60-75`) | **IMPLEMENTED — active default** |
| `LayaRouter` | 4 questions: 3 × `noul` (radiology/pathology/genomics "required?") + 1 × `choice` risk grade (`system1.py:81-103`); calls `Router().predict(state, _QUESTIONS)` (`system1.py:116-144`) | **IMPLEMENTED but OFF** |
| Presence hard-override | Laya's `noul` answer only *selects among* agents the data allows; `_apply_presence` drops any agent whose modality is absent (`system1.py:51-57`, asserted by `test_system1.py:100`) | IMPLEMENTED |
| Provider selection | `SYSTEM1_PROVIDER` env, default `heuristic` (`.env:7`, `.env.example:7`) | **heuristic in dev and container** |
| Availability | `laya = ["laya>=0.3"]` is an **optional extra** (`pyproject.toml:26`), not in Docker image install list | **Laya unavailable in container** |
| Latency budget | `LATENCY_BUDGET_MS = 50.0` with `ponytail:` note: CPU Laya measured 193–464 ms preloaded (`system1.py:18-20`) | budget **unmet on CPU** |
| Fallback | try/except at `get_router` (`system1.py:149-157`) + second fallback in `route_case` (`system1.py:161-184`) | IMPLEMENTED; `routing.confidence` recorded but **consumed by nothing downstream** (grep `routing.*confidence` → only `swarm.py` stores `routing` dict; `_calibrate` never reads it) |
| Tests | `test_system1.py:84-103` uses `FakeLaya` — the real model is **never exercised in tests** | mocked coverage only |

**Net:** Laya is wired as a drop-in router behind one env flag, with honest fallback. Its output (risk grade, priority, confidence) feeds alerts and run priority only.

---

## 3. Where System 1 duties actually live today

| System-1 duty (architecture intent) | Current owner | Status |
|---|---|---|
| Intake triage / risk grade | `system1.py:_risk` regex (`:43-48`) | IMPLEMENTED (keyword) |
| Agent routing | `system1.py` presence rules | IMPLEMENTED |
| Planning (which tools) | `planner.py:27-48` | IMPLEMENTED, tools **not executed** (`swarm.py:583` writes `plan.tools`, no reader) |
| Evidence sufficiency gate | — | **MISSING** (confidence floor `0.01` `swarm.py:97` hides it) |
| Conflict detection | `_conflict` spread ≥ 0.3 (`swarm.py:80-82`) | IMPLEMENTED (confidence-only, not claim-level) |
| Abstention gate | — | **MISSING** |
| Re-run trigger on new evidence | chat context freeze (`chat.py:103-108`) | **MISSING** |
| Final safety gate (output check) | — | **MISSING** (see Safety audit) |
| LLM input guardrails | `GuardedLLM` PII scrub (`swarm.py:59-69`) | IMPLEMENTED (PII only; no injection check — laya `guard_questions` **unused**) |
| Calibration | `_calibrate` (`swarm.py:89-108`) | IMPLEMENTED but ignores Laya calibration fields |

---

## 4. Target architecture (System 1 control plane)

Deterministic-or-Laya gates with **identical fallback schema**, so a missing GPU never changes the contract:

```
upload ──> G1 intake classify (kind, ambiguous → physician ask)
       ──> G2 evidence sufficiency (critical modality present?)
       ──> route (agents, tools)              [system1.py today]
       ──> execute plan.tools                 [currently decorative]
       ──> agents ──> G3 claim extraction + validation
       ──> G4 conflict score (claim-level, not just confidence spread)
       ──> debate? ──> G5 evidence gate (citations ⊆ retrieved)
       ──> G6 abstention gate (diagnosis state machine)
       ──> G7 final safety gate (banned claims, wording, patient match)
       ──> report (provenance-tagged)
```

**Gate contract (all seven):**
```python
@dataclass(frozen=True)
class GateResult:
    name: str
    verdict: str          # "pass" | "fail" | "warn" | "unknown"
    reason: str
    resolvable_by: tuple[str, ...]
    provider: str         # "laya" | "heuristic"
    latency_ms: float
```
Fallback provider returns the same dataclass (`unknown`/`heuristic`) — test asserts schema parity with Laya enabled and disabled.

**Laya placement (verified APIs only):**
- G1/G2/G4/G6: Laya `predict` with `choice`/`score`/`noul` questions over serialized state (`laya.structured.questions_from_pydantic` can generate the schema from a Pydantic gate model).
- G7 (and prompt-injection defense): laya `guard_questions()` preset — `jailbreak`, `prompt_injection`, `sensitive_data` NOUL scores + `harm_severity` — **already installed, currently unused**.
- Heuristic fallback: deterministic rules (presence regex, whitelist, citation set-diff) — same `GateResult`.
- Latency: keep `LATENCY_BUDGET_MS` instrumented; `route_case` already measures (`system1.py:163-175`) — extend per gate, record p50/p95/p99 in run events.

**Non-goals:** no claim of clinical checkpoints (UNKNOWN); no GPU requirement — CPU Laya 193–464 ms (`system1.py:18-20`) means gate budget must be sized per gate, or ONNX path (`laya/onnx_agent.py`, `LayaRouter` lazy attr) evaluated — **verify actual ONNX throughput before committing**.

---

## 5. Acceptance criteria

1. `SYSTEM1_PROVIDER=laya` runs in the container (laya installed or honest 503-fallback with logged reason); test asserts provider value in `/api/system/status`.
2. All 7 gates emit `GateResult`; schema-parity test green with and without laya.
3. `plan.tools` executed (vision runs on `ct` uploads) or field removed; grep in CI.
4. Laya `guard_questions` runs on every prompt; injection fixture blocked (ties GAP-017).
5. `routing.confidence`/Laya calibration consumed by `_calibrate` or removed from output — no dead fields.
6. Per-gate latency recorded in run events; p95 published; budget exceeded → gate degrades to heuristic, never blocks the run.

## 6. Open questions

- Does laya's `noul` calibration transfer to clinical inputs? **UNKNOWN — NEEDS VERIFICATION** (no medical benchmark in package; would need local eval set).
- ONNX latency on CPU host? **UNKNOWN — NEEDS VERIFICATION**.
- Interaction of `typed-decisions` checkpoint with custom gate schemas? Package says never selected unless `auto_task_detection=True` — opt in explicitly only after eval.
