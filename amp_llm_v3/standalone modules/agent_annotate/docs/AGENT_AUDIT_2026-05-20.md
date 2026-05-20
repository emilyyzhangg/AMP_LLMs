# Annotation pipeline audit — 2026-05-20

Extensive review of every annotation agent and the research evidence fed into
it, commissioned to (a) raise the two sub-human-agreement fields (outcome, RfF)
and (b) verify the evidence pipeline actually produces good annotations. Three
parallel read-only audits covered: outcome+RfF, classification/delivery/peptide/
sequence, and research-agent reliability + drug-name propagation.

This document records the findings, the changes shipped today, and the
prioritized backlog. Companion change: a per-trial **LLM audit trail** (see
§Audit trail) now persists the exact input and output of every annotation LLM
call, so future audits read real prompts/outputs instead of inferring them.

---

## Root-cause finding that drove today's change

Slice-M (58 NCTs, v42.8.5b) outcome accuracy was dragged down entirely by the
**positive class: 13/35 = 37%**. Every miss was the agent emitting **`Unknown`**,
never a wrong value — it was *silent*, not wrong.

Tracing all positive-misses:

- 31/32 were registry status **COMPLETED** (not recruiting/active).
- They are overwhelmingly **Phase 1 / first-in-human / PK-safety** studies
  ("Single Ascending Doses", "Pharmacokinetics and Safety"). These trials have
  **no efficacy endpoint to meet**.
- **0/32** had any strong-efficacy phrase ("primary endpoint met", "statistically
  significant") in fetched abstracts; only 3/32 even had safety-success text.
- The human annotators labelled them **positive** because the trial met its
  (safety/feasibility/PK) objective and/or the drug advanced/was approved
  (erenumab→Aimovig, dasiglucagon→Zegalogue, enfuvirtide→Fuzeon).

**Conclusion: a definitional mismatch.** The agent demanded positive-efficacy
*language* before calling success; the correct rule (per product owner) is:

> For all phases, if the objectives are met (safety, feasibility, effectiveness)
> the trial is a success. The language does not have to exist for the agent to
> decide it succeeded — **it just needs to not fail.**

### Change shipped — v42.9 Lever 6: "completed and not failed = success"

`agents/annotation/outcome.py`, post-LLM safety-net chain. When the model leaves
a **COMPLETED** trial at `Unknown` and `hasResults` is not posted, promote to
**Positive** — but only when there is no failure signal:

- not `_has_strong_failure(negative_keywords)` (and by construction the strong-
  failure publication override above already fired for any real failure pub, so a
  remaining `Unknown` means none was detected),
- no negative press release,
- no failed primary endpoint (p ≥ 0.05).

It **fills `Unknown` only** — it never overturns a Failed/Terminated/Positive
call. Drug-advancement data (ChEMBL phase / FDA approval) is *corroborating*, not
required.

Offline replay on slice-M: **+31 wins (all positive-GT), 1 loss (one unknown-GT),
5 neutral** → net +30 correct. The 5 neutral are failed-completed-trial GT whose
failure isn't captured by any signal (already wrong as Unknown; now wrong as
Positive — no accuracy change). Protected by trip-wire
`test_v42_9_completed_not_failed_override`.

---

## Audit trail (companion infrastructure)

Until now only the *parsed* reasoning string survived; the exact prompt the model
saw and its raw reply were thrown away, so "why did it decide X?" was
unanswerable after the fact. New module `app/services/audit_trail.py`:

- Single chokepoint `OllamaAnnotationClient.generate` records every call.
- A `contextvars` context binds each call to its `(nct_id, field, stage)`.
- The orchestrator binds the trial context around `_run_annotation` and the field
  context inside `annotate_field`, then on finalize writes
  `results/annotations/<job_id>/<nct_id>.audit.md` with each field's full input
  (system + prompt + evidence) and raw output.
- Best-effort throughout: auditing can never break annotation. Batched
  cross-trial verifier calls (no trial context) are intentionally not captured to
  keep each document focused and the buffer bounded.

Protected by trip-wire `test_audit_trail_wired`.

---

## Prioritized backlog (audited, not yet shipped)

Ordered by expected accuracy impact per unit risk. Each is a separate validated
change so its effect can be measured cleanly.

### P1 — Resolved drug names never reach ChEMBL/FDA/NIH/SEC/IUPHAR — ✅ SHIPPED 2026-05-20
`_resolve_drug_names` (orchestrator.py:1291) stores Lever-4 canonical names in
`interventions[i]["resolved"]`, but `chembl_client`, `fda_drugs_client`,
`nih_reporter_client`, `sec_edgar_client`, `iuphar_client` all read only the raw
`name` (e.g. they queried "AMG 334", never "erenumab"). `peptide_identity` was
the only consumer that used `resolved`. **Fixed:** new shared helper
`agents/research/resolved_names.py` (`extract_interventions` + `query_names`);
each of the five agents now queries the raw name first and falls back to the
resolved canonical name(s) only when it returns nothing (minimizes extra API
calls). DRUG/BIOLOGICAL type filters and placebo skips preserved. Trip-wire
`test_v42_9_resolved_name_propagation`.

### P1 — ChEMBL `max_phase` lost even for approved drugs — ✅ SHIPPED 2026-05-20
`chembl_client.py` dropped numeric `0` (valid preclinical) via a falsy check, and
the **outcome consumer read a flat `molecules` key that never existed** (ChEMBL
stores `chembl_<name>_molecules`) — so `drug_max_phase` was *always* None.
**Fixed:** `_coerce_phase()` normalizes to int in [0,4] (accepts 0); the outcome
consumer now iterates the real `*_molecules` keys. Relevance-filter loosening
(substring-only) deferred — low marginal value now that the not-failed principle
no longer depends on drug-advancement data.

### P2 — Sequence field (~24%) — DATA-BOUND; partial fix shipped 2026-05-20
**Root-cause re-grounding (slice-M, 25 sequence misses):** 24/25 are RECALL
failures (agent returned N/A), only 1 precision error — so the agent isn't
picking wrong sequences, it finds *nothing*. Critically, **23/24 have the GT
sequence ABSENT from everything the agent fetched** (abstracts only, not full
text; no epitope DB; no antibody DB). The misses break down as:
- **T-cell / tumor-antigen epitopes** (IMDQVPFSV, YLEPGPVTA, YISPWILAV…) — the
  largest group; live in **IEDB**, which the pipeline does not query.
- **Protein fragments** (EPO precursor — verified present in UniProt P01588 but
  not fetched; antibody VH domains like erenumab's).
- **Chemically-modified synthetics** ((Ac)CRGDKGPDC(NH2), DOTA-conjugates,
  non-standard residues) — often not in public structured DBs at all.

So the originally-hypothesized logic fixes (AMP-DB gate, key matching) barely move
slice-M: these sequences aren't in those DBs. The AMP-DB gate was **left as-is on
purpose** — loosening it re-introduces the documented Brevinin-for-cancer-vaccine
false-positive class, and precision is currently near-perfect (24/25). Adding the
specific obscure sequences to `_KNOWN_SEQUENCES` would be cheating.

**Shipped (safe, correct, no-gaming):**
- **Resolved-name DB-key consumption** — P1 made the research agents store
  sequence data under the *resolved* name (`chembl_erenumab_helm`) while the
  sequence agent keyed lookups on the raw trial code; this closes that mismatch
  (`sequence.py`, helper `extract_interventions`). Required to consume P1.
- **LLM sequence fallback widened** from `peptide=='true'` to `peptide!='false'`
  (covers peptide=Unknown; only emits sequences actually found in the text).
Trip-wire `test_v42_9_sequence_resolved_lookup_and_fallback`.

**The real lever (decision pending):** IEDB integration for epitopes — the only
source covering the dominant miss category. Must be done WITHOUT gaming the
set-containment scorer: extract antigen + residue-range/HLA from the protocol and
retrieve the *single* exact epitope (UniProt slice or IEDB lookup), not spray an
antigen's whole epitope set. Antibody-VH-domain and modified-synthetic GT is
likely beyond legitimate automated retrieval.

### P2 — RfF evidence starvation + over-literal whyStopped
`failure_reason.py` feeds the LLM only 4 web + 4 literature citations capped at
2800 chars, and only the `literature`/`web_context` agents (drops openalex,
crossref, biorxiv, structured press releases, SEC). whyStopped keyword matching is
too literal: "interim analysis" → Ineffective (wrong for early-success), bare
"sponsor decision" → Business Reason (masks efficacy/safety failures). Emission
gate defaults aggressively for TERMINATED even on sparse evidence. **Fixes:**
raise caps + priority-sort; broaden agents; remove over-broad keywords + add
negation handling; gate the default on Pass-1 confidence.

### P3 — Classification / delivery / peptide edge cases
Classification: post-LLM AMP override checks "suppress" keywords *after* deciding
(classification.py:513-538); DBAASP-only hits not flagged uncertain to the LLM.
Peptide: insulin is contradictorily in/out of the known list; multi-drug trials
can miss a co-administered peptide. Delivery: multi-route dedup is fragile.

### P3 — Cross-cutting
Drug cache (`drug_cache.py`) caches empty/error results with no TTL → a drug that
fails to resolve once stays empty for the process. No retry for research agents.
Surface trial phase/enrollment/condition to the RfF and outcome prompts (FDA
indication-overlap is currently delegated to implicit LLM reasoning).
