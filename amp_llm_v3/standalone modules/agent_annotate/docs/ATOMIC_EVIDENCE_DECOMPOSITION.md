# Atomic Evidence Decomposition — Design Plan

Status: Draft — Phase 0 active
Author: Agent-annotate redesign effort, v41b → v42
Created: 2026-04-17

## 0. Core Philosophy

The problem with v38–v41b outcome agent is not calibration — it is epistemology. A single LLM call asked "given everything, what's the outcome?" produces answers that depend on which signal happened to dominate attention on that generation. Prompt tweaks re-weight dominance → answers flip → overall agreement oscillates between FP-dominant (v40: positive→unknown x7) and FN-dominant (v41: unknown→positive x7) without stabilizing.

The atomic approach inverts this. Instead of one global judgment, we ask many narrow, evidence-scoped questions — each answerable from a single piece of evidence — and combine them with **deterministic, published aggregation rules**.

### Four design principles

1. **Scope every LLM call to a single piece of evidence** (one publication, one source, one protocol arm). The LLM cannot be distracted by unrelated data because it only sees what is relevant.
2. **Ask Yes / No / Unclear, not multi-class.** Binary questions on focused input have ~90%+ reliability; 7-class open-ended decisions are ~55%.
3. **Aggregation is deterministic code, not an LLM call.** The rules from atomic answers → final label are written in Python, versioned, reviewable.
4. **"Unclear" is a first-class answer.** The system must accept uncertainty at the atomic level rather than force the LLM to guess.

### Non-goals (scientific integrity)

- Not maximizing agreement with R1 by tuning to specific NCTs
- No hardcoded expected answers, no drug-name cheat sheets
- No LLM prompts that list "common positive trials" or similar crib notes
- Disagreements with R1 must be diagnosed as either (a) a better atomic question was needed, (b) the research pipeline missed evidence R1 had, or (c) R1 is defensible but differently defensible — not as "let's make the LLM say Positive more"

---

## 1. Outcome Agent — Atomic Per-Publication Assessment

### 1.1 Architecture

```
Trial (NCT)
  │
  ├─▶ Tier 0: Deterministic pre-check
  │     • RECRUITING / NOT_YET / ENROLLING_BY_INVITATION → "Recruiting"
  │     • WITHDRAWN                                      → "Withdrawn"
  │     • COMPLETED + hasResults + p-value≤0.05 on primary endpoint → "Positive"
  │
  ├─▶ Tier 1: Per-publication atomic assessor
  │     For each publication found:
  │       ├─ Trial-Specificity Classifier (deterministic)
  │       │   3 sub-questions (NCT-in-body, CT.gov-references-list,
  │       │   title-signal) → trial_specific | general | ambiguous
  │       │
  │       └─ If trial_specific (or ambiguous): Result-Reporter LLM call
  │            • 5 atomic Y/N/Unclear questions on this pub only
  │            • Returns: {pub_id, verdict: POSITIVE|FAILED|INDETERMINATE,
  │                        answers, evidence_quote}
  │
  ├─▶ Tier 2: Registry Signal Extractor (deterministic)
  │     • status, completion_date, days_since_completion, stale_flag
  │     • drug_max_phase (ChEMBL)
  │     • has_later_phase_trials_for_same_drug
  │
  └─▶ Tier 3: Deterministic Aggregator (rules applied in order)
        TIER0 Deterministic pre-label short-circuit
        R1.   Any POSITIVE pub + 0 FAILED pubs           → Positive
        R2.   Any FAILED pub + 0 POSITIVE pubs           → Failed - completed trial
        R3.   Both POSITIVE and FAILED present           → most-recent-pub verdict
        R4.   REMOVED (Phase 5 post-hoc). Was: "drug advanced"
              → Positive. Drug-level signals do not imply
              this specific trial's outcome.
        R5.   REMOVED (Phase 5 post-hoc). Was: "Phase I
              + any pub" → Positive. Phase I completion
              with non-trial-specific pubs is not evidence
              of THIS trial's success (46% precision on 13
              scoreable firings in Phase 5 validation).
        R6.   Status ACTIVE_NOT_RECRUITING + not stale   → Active, not recruiting
        R7.   Status TERMINATED + no POSITIVE pub        → Terminated
        R8.   Otherwise                                  → Unknown
```

**No LLM call makes the final outcome decision.** The LLM only answers atomic questions about individual publications. The final label comes from R1–R8.

### 1.2 Trial-Specificity Classifier (Tier 1a, no LLM)

Replaces v41's 30-keyword list / v41b's default-to-trial-specific with structural checks:

```python
def classify_pub(pub, nct_id, research_data) -> str:
    # Q1: Does the publication body/abstract contain the NCT ID literal?
    q1 = nct_id.lower() in (pub.full_text or pub.abstract or "").lower()

    # Q2: Is this pub listed in CT.gov's references section for THIS trial?
    q2 = pub.pmid in research_data.ctgov_references

    # Q3: Title contains trial-design signal AND drug name?
    q3 = has_trial_design_phrase(pub.title) and drug_mentioned(pub.title, research_data.drug)

    if q1 or q2:                return "trial_specific"
    if q3:                      return "trial_specific"
    if pub.publication_type == "review": return "general"
    return "ambiguous"
```

Q1 and Q2 are deterministic structural checks — no keyword list, no prompt tuning can flip them.

### 1.3 Result-Reporter LLM Call (Tier 1b)

One focused call per trial-specific (or ambiguous) publication. Prompt:

```
You are reading a single publication to answer atomic questions about
a clinical trial. Answer each question based ONLY on what this
publication's text says. Do not infer beyond what is written.

Trial identifier: {NCT}
Drug: {drug_name}

Publication:
---
{title}

{abstract_or_snippet}  # 1000 chars max
---

Q1. Does this publication report RESULTS from the trial above?
Q2. Was the trial's PRIMARY endpoint met?
    (YES / NO / PARTIALLY / NOT_REPORTED / NA if Q1=NO)
Q3. Does the publication describe clinical EFFICACY outcomes (tumor
    response, symptom reduction, survival, endpoint achievement)?
    Safety-only reports without efficacy → NO.
Q4. Does the publication report trial FAILED or drug demonstrated
    futility / lack of efficacy?
Q5. Does the publication mention this drug advanced to a LATER-PHASE
    trial or received regulatory approval?

Return JSON:
{
  "q1_reports_results": "YES|NO|UNCLEAR",
  "q2_primary_met":     "YES|NO|PARTIALLY|NOT_REPORTED|NA",
  "q3_efficacy":        "YES|NO|UNCLEAR|NA",
  "q4_failure":         "YES|NO|UNCLEAR|NA",
  "q5_advanced":        "YES|NO|UNCLEAR",
  "evidence_quote":     "<one verbatim quote supporting Q2 or Q4, ≤30 words>"
}
```

**Verdict function (deterministic):**
```python
def pub_verdict(a) -> str:
    if a.q4 == "YES":                                 return "FAILED"
    if a.q2 in ("YES", "PARTIALLY"):                  return "POSITIVE"
    if a.q3 == "YES":                                 return "POSITIVE"
    if a.q5 == "YES":                                 return "POSITIVE"
    if a.q1 == "YES" and a.q2 == "NO":                return "FAILED"
    return "INDETERMINATE"
```

The `evidence_quote` forces the LLM to ground Q2/Q4 in literal text — hallucinations become visible in the audit trail.

### 1.4 Registry Signal Extractor (Tier 2)

Pure data extraction, no LLM. Refactor from existing `_build_evidence_dossier` to expose:
- `status`, `completion_date`, `days_since_completion`, `stale_flag`
- `drug_max_phase` (from ChEMBL)
- `has_later_phase_trials_for_same_drug` (query subsequent trials by drug name)

### 1.5 Aggregator Output Contract

Every verdict traces to a named rule + atomic inputs:

```
NCT03314987 → Positive (rule R1: 2 POSITIVE pubs, 0 FAILED)
   pubs: PMID:32145678 → POSITIVE (q2=YES: "primary endpoint was met")
         PMID:34567890 → POSITIVE (q3=YES: "significant clinical benefit")

NCT01653249 → Positive (rule R4: COMPLETED, no trial-specific pubs,
                        ChEMBL shows drug advanced to Phase III)
```

---

## 2. Applicability to Other Agents

### 2.1 Classification (AMP vs Other) — SHIPPED (v42 Phase 5, B2)

Implemented as `agents/annotation/classification_atomic.py`. Runs in shadow by default; `prefer_atomic_classification` flag promotes it to authoritative.

**Tier 0** — deterministic registry hit from peptide_identity, dbaasp, and apd research agents. A citation from any of these databases whose `source_name` (or parent `agent_name`) is `dramp`, `apd`, `dbaasp`, or `uniprot` (with "antimicrobial" in snippet) → AMP with conf 0.95. This caught 6/8 AMPs on the 94-NCT validation set.

**Tier 1b** — single LLM call (qwen3:14b) on the clinical_protocol text (title + summary + conditions + intervention descriptions + primary outcomes), capped at 2400 chars. Three Y/N questions:
- Q1: Does the trial's intervention include a defined peptide sequence?
- Q2: Is the stated mechanism antimicrobial (kills or inhibits a pathogen)?
- Q3: Is the primary indication or endpoint an infectious disease / microbial outcome?

**Aggregator** — six ordered rules, first match wins (all binary AMP/Other, no Unknown):
- R1 registry hit → AMP (0.95)
- R2 3/3 YES → AMP (0.90)
- R3 ≥2 YES, 0 NO → AMP (0.80)
- R4 3/3 NO → Other (0.90)
- R5 ≥2 NO, 0 YES → Other (0.80)
- R6 default → Other (0.55)

No drug-name cheat sheets. No `_KNOWN_AMP_DRUGS` lookups. LLM answers reading-comprehension questions about a single protocol; Python picks the category.

### 2.1 (original — archived for history)

Currently has a two-pass LLM with regex-based Pass1→Pass2 handoff. Fragile.

**Atomic questions (per source citation):**
- Q1: Does it claim the drug has antimicrobial activity?
- Q2: Does it describe direct pathogen-killing mechanism (membrane disruption, pore formation)?
- Q3: Does it identify the drug as host-defense peptide / defensin / bacteriocin?
- Q4: Does it describe primary mechanism as immunomodulation ONLY (without direct antimicrobial)?

**Aggregator:**
- DRAMP / DBAASP / APD DB hit → AMP (DBs authoritative, no LLM)
- Any citation Q1=YES or Q2=YES or Q3=YES → AMP
- Majority Q4=YES and no Q1/Q2/Q3=YES → Other
- Else → Other

Kills Pass1 free-text extraction fragility.

### 2.2 Failure_reason — SHIPPED (v42 Phase 5, B3)

Implemented as `agents/annotation/failure_reason_atomic.py`. Gated on `outcome_atomic ∈ {Terminated, Failed - completed trial}` — non-failed trials short-circuit to empty, mirroring the legacy agent's behavior. Runs in shadow by default; `prefer_atomic_failure_reason` flag promotes it to authoritative.

**Tier 0** — `whyStopped` registry text keyword parse. Priority-ordered keyword groups (COVID > Safety > Recruitment > Efficacy > Business) match generic English phrases (`"covid"`, `"pandemic"`, `"adverse event"`, `"hepatotoxicity"`, `"enrollment"`, `"slow accrual"`, `"lack of efficacy"`, `"futility"`, `"sponsor decision"`, `"strategic"`, `"portfolio"`, etc.) — not drug names.

**Tier 1b** — single LLM call (qwen3:14b) on evidence assembled from (1) whyStopped, (2) web_context snippets (press releases, SEC filings — added Phase 5 post-hoc), (3) literature snippets. Five Y/N/UNCLEAR questions:
- Q1: Does the evidence explicitly cite safety / adverse events as a reason?
- Q2: Failure to meet efficacy / futility?
- Q3: COVID / pandemic impact?
- Q4: Enrollment / accrual difficulties?
- Q5: Sponsor / business / funding / strategic decision?

**Priority aggregator** — safety > efficacy > COVID > recruitment > business; whyStopped Tier 0 preempts atomic answers:
- R1 Tier 0 hit → that category (0.90)
- R2 Q1 YES → Toxic/Unsafe (0.85)
- R3 Q2 YES → Ineffective for purpose (0.85)
- R4 Q3 YES → Due to covid (0.85)
- R5 Q4 YES → Recruitment issues (0.80)
- R6 Q5 YES → Business Reason (0.70)
- R7 default → empty (0.40)

Removes the legacy circular dependency with outcome (the legacy agent's "if outcome=Positive, skip" is replaced by a clean outcome_atomic gate).

### 2.3 Delivery_mode — MEDIUM FIT, DEFER

Already largely deterministic (protocol-route keywords + openFDA + drug-class defaults). Minor wins available per-arm, but not urgent. Revisit after outcome ships.

### 2.4 Peptide — LOW FIT, DO NOT CHANGE

Two-pass LLM + known-drug tables + consistency override already near atomic. 91.5% agreement on v41b is near R1-R2 human ceiling of 86%. Leave as-is.

### 2.5 Sequence — VERY LOW FIT, DO NOT CHANGE

Structured-data-only with known-sequence lookup. Already atomic in spirit — sources scored, highest-confidence match wins.

---

## 3. Implementation Roadmap

All work on `dev` branch. Atomic commit+push after every change to avoid autoupdater wipe.

### Phases 0–5 — COMPLETE (2026-04-17 → 2026-04-21)

- **Phase 0** — design doc committed, plan approved
- **Phase 1** — scaffolding: `outcome_registry_signals.py`, `outcome_pub_classifier.py`, `outcome_atomic.py`; Tier 0 deterministic pre-check; Tier 1a structural classifier (no keyword lists); 10/10 synthetic unit tests + 47-NCT zero-error replay
- **Phase 2** — `outcome_pub_assessor.py`: per-pub LLM call, 5 atomic Y/N/UNCLEAR questions + forced evidence_quote, strict JSON parser with INDETERMINATE fallback, per-(NCT, PMID, text-hash, model) disk cache
- **Phase 3** — `outcome_aggregator.py`: TIER0 + R1–R8 ordered match, AggregatorResult with rule name + description + trace; 18/18 synthetic unit tests
- **Phase 4** — shadow-mode wiring: `OutcomeAtomicAgent` registered in `ANNOTATION_AGENTS`, gated by `outcome_atomic_shadow` config flag, `skip_verification=True` so verifier pool is preserved
- **Phase 4.5** — tooling: `scripts/atomic_preview.py` replay runner (resume-safe, incremental `_summary.json`), `atomic_vs_r1.py` R1 comparison, `atomic_triage.py` four-category auto-triage
- **Phase 4.6** — stability fixes (A1–A4): `outcome_atomic_max_voting_pubs` cap (default 20), Tier 1a drug-name-absence downgrade (pubs with zero drug mentions → `general`), `--no-resume` flag, model-scoped cache keys
- **Phase 5** — 94-NCT prod shadow run + family extension: `classification_atomic` (B2), `reason_for_failure_atomic` (B3), `reconciler_thinking` flag (B4), `--atomic-model` bake-off flag (B1). Unit tests: 22/22 for B2+B3 aggregators + whyStopped parser

### Phase 5 post-hoc fixes (2026-04-21)

All shipped as deterministic code changes with no prompt tuning. Each responded to a specific Phase 5 disagreement pattern.

1. **Tier 0 classification — DBAASP recognition.** `extract_registry_hits` now surfaces DBAASP citations (and falls back to parent `agent_name` when `source_name` is absent). Lifted AMP recall 25% → 75% on the 94-NCT set.
2. **ChEMBL drug_max_phase extractor.** Was reading non-existent `raw_data["molecules"]`; actual shape is per-drug keys `chembl_<drug>_molecules` with string values `"3.0"`/`"-1.0"`. Walk all `*_molecules` keys, take max non-negative `int(float(...))`.
3. **R5 removed.** Former rule "Phase I completion + any pub → Positive" agreed with R1 on 6/13 scoreable cases (46%). Phase I completion with only non-trial-specific pubs is typically Unknown to R1, not a tacit positive.
4. **R4 removed** (post fix #2). With drug_max_phase working, R4 fired 23 times; 6 correct, 7 wrong vs R1=unknown, 10 unscoreable. Drug advancement is evidence about the drug, not this specific trial.
5. **failure_reason web_context Tier 2.** `_assemble_evidence` now includes web_context snippets ahead of literature. Business-reason terminations are rarely quotable from peer-reviewed pubs. Lifted failure_reason scoreable agreement 50% → 67%.

### Phase 6 — Partial cut-over (in progress)

The atomic architecture is validated (0 Cat 3 across 94 NCTs, 1 Cat 2). Classification and failure_reason have shown strong-enough agreement to promote to authoritative:

- `orchestrator.prefer_atomic_classification` (default OFF) — when true, the atomic value populates `classification` and legacy becomes `classification_legacy` (shadow).
- `orchestrator.prefer_atomic_failure_reason` (default OFF) — same for reason_for_failure.
- `outcome_atomic` stays shadow. Overall agreement (62% scoreable) is lower than legacy dossier, and the remaining 23 Cat 1 evidence gaps are structural (research pipeline), not the atomic agent's fault. Cut-over after Phase 6 research-agent expansion.

### Phase 6 — Research pipeline expansion (free APIs only)

The 23 Cat 1 evidence gaps from Phase 5 are cases where R1 relied on a publication our literature pipeline never surfaced. To close them, new research agents are added (free APIs only, per project constraint):

- **bioRxiv / medRxiv preprints** — `agents/research/biorxiv_client.py`. Many R1-cited sources are preprints that only later went to peer review; peer-review-only searches miss them.
- (future) Europe PMC full-text mirror and SEC EDGAR for business-reason context.

### Phase 7 — Outcome cut-over (deferred)

Once outcome_atomic scoreable agreement reaches parity with legacy dossier (currently 58.1% legacy vs 62% atomic — already ahead), promote outcome_atomic to authoritative and delete the dossier path. Blocked on Phase 6 research-agent validation.

---

## 4. Testing Philosophy (non-negotiable)

Every atomic answer must be auditable. Annotation JSON includes per-publication verdicts with `evidence_quote` fields.

**Every disagreement with R1 must be categorized:**

1. **Evidence gap** — R1 had info our research pipeline didn't retrieve. Fix: research pipeline, not agent.
2. **Question gap** — There's a signal R1 considered that no atomic question asks. Fix: add a question (carefully, hard budget of 5 per agent).
3. **Aggregator gap** — Atomic answers right, R1–R8 didn't fire correct rule. Fix: aggregator.
4. **R1 judgment call** — Evidence reasonably supports multiple answers; atomic chose differently but defensibly. Do NOT fix — document.

**Category 4 is allowed to persist.** We are not trying to agreement-max. We are trying to be right in a way that's defensible.

### Metrics

- Overall % agreement with R1 — legacy metric, informational only
- **Defensibility score**: % of disagreements classified Category 4 (target ≥50%)
- **Audit completeness**: % of verdicts with full atomic answer + evidence_quote chain (target 100%)
- **Stability**: same NCT + same research data → same verdict (target 100%; violations = LLM noise)

---

## 5. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Malformed JSON from LLM | Strict parser; INDETERMINATE on parse fail; bucket for analysis |
| Cost (~3–5 pubs/trial × 47 trials = 150–250 LLM calls) | Small prompts (~200 tok), cache on (NCT, PMID). ~10 min / 47-NCT job |
| Pubs without abstract | Use title only; mark ambiguous; verdict weighted lower |
| Trials with 0 pubs | Tier 1 empty → aggregator falls to R4–R8 registry rules |
| First-run disagrees with R1 more than dossier | Expected. Spend Phase 6 on question iteration, not prompt tuning. |
| Scope creep (adding sub-agents per sub-question) | Hard budget: 5 atomic questions per agent. Want a 6th? First remove one |

---

## 6. File Layout (when complete)

```
agents/annotation/
  outcome_atomic.py              # new top-level agent (replaces outcome.py eventually)
  outcome_pub_assessor.py        # Tier 1b: per-publication LLM
  outcome_registry_signals.py    # Tier 2: deterministic registry extraction
  outcome_aggregator.py          # Tier 3: R1–R8 rules
  outcome_pub_classifier.py      # Tier 1a: trial-specific classifier
  outcome.py                     # old, retained during shadow mode, deleted at cut-over
```

Shared module for atomic patterns (future):
```
agents/atomic/
  __init__.py
  assessor_base.py               # shared JSON parsing, caching, retry logic
  verdict_types.py               # POSITIVE / FAILED / INDETERMINATE etc.
```

---

## 7. Commit Discipline

- All work on `dev` branch
- Every change is committed AND pushed in the same operation (to avoid autoupdater wipe — it polls every 30s)
- Explicit file paths only (never `git add -A`)
- Run `CONTINUATION_PLAN.md` + `LEARNING_RUN_PLAN.md` update after every job run
- No merge to main until atomic cut-over is complete AND validated
