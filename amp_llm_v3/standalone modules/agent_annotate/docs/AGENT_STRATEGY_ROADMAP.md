# Agent Strategy Roadmap

**Status:** active — this is the governing document for all future agent changes.
**Created:** 2026-04-23 (post v42.6.9 recovery).
**Supersedes:** the "Phase 6 cut-over" plan in `ATOMIC_EVIDENCE_DECOMPOSITION.md`.

Read this before proposing any agent change. If it's not in here, it needs a plan update first.

---

## 1. Current state (last refreshed 2026-04-28)

- **Authoritative pipelines:** legacy for every field.
- **Shadow pipelines:** `classification_atomic`, `failure_reason_atomic`, `outcome_atomic` all run and write `<field>_atomic` for audit — never in the critical path.
- **Commit:** `fdd6859b` on main (v42.7.17 — Rule 7 softening). Full v42.7.5–v42.7.17 shipped:
  - v42.7.5–v42.7.11: code-sync, NIH RePORTER (19th agent), vaccine override, FDA/SEC wiring, query extension, intervention type preservation, drug-name surfacing
  - v42.7.12: FDA label indications + CT.gov registered-pubs gate (Job #92 over-call fix)
  - v42.7.13: explicit "Registered Trial Publications: 0" line + Rule 7 hallucination fix
  - v42.7.14: Failed override gated on terminal registry status
  - v42.7.15: _NEGATIVE_KW tightening (remove bare "failed" / "negative")
  - v42.7.16: sequence canonicalizer strips terminal -OH / -NH2 chemistry suffix
  - v42.7.17: Rule 7 over-correction fix — accept pub-title-pattern as alternative trial-specificity (drug name + phase/first-in-human/clinical-trial descriptor in title; generic field reviews excluded). Triggered by Job #96 held-out-B revealing v42.7.13's strict FALLBACK was too literal.

- **Held-out slices:** A (30, retired post-#95), B (25, retired post-#96 — surfaced over-correction), C (25, active, Job #97 in flight).
- **Job validation history (recent):**
  - Job #92 (held-out-A, v42.7.11): outcome 60.0%, classification 100%, sequence 50%
  - Job #95 (held-out-A re-run, v42.7.13): outcome 60.0% (same accuracy, 4 over-calls fixed but 4 noise-floor losses)
  - Job #96 (held-out-B, v42.7.16): outcome 36% — revealed v42.7.13 over-correction
  - Job #97 (held-out-C, v42.7.17): in flight, target outcome ≥55%
- **Research agents:** 19 total — 15 pre-v42 + bioRxiv (v42 Phase 6) + SEC EDGAR + FDA Drugs (v42.7.0) + NIH RePORTER (v42.7.6).
- **Validation baselines (47-NCT clean slice, GT/registry-aligned):**
  - **Job #83 (v42.6.15)** — peptide 81.1%, classification 90.7%, delivery 91.7%, outcome 61.7%, RfF 83.3%, sequence 75.0%.
  - **Job #88 (v42.7.3)** — same five fields essentially flat with **RfF +7.6pp** (90.9%) and **outcome -2.1pp** (59.6%). Pub expansion 281 → 809 cites (4.7x).
  - **Job #89 (v42.7.4, current)** — peptide 81.1%, classification 90.7%, **delivery 94.4% (+2.8)**, **outcome 61.7% (recovered)**, **RfF 91.7% (+8.3)**, sequence 75.0%. Pubs 838.
  - 0–2 warnings per run (down from 59 pre-v42.6.13).
- **Active iteration line:** v42.6.10 → .11 → .12 → .13 → .14 → .15 → .16 → .17 → .18 → .19 → v42.7.0 → .1 → .2 → .3 → .4. Each commit is one or two narrow fixes with smoke validation; full re-baselines reserved for cycle close-out (Jobs #83, #88, #89 are the v42.7 re-baseline trio).
- **Test suite:** 167+ unit tests across 23+ files (`scripts/test_v42_*.py`) + 15 trip-wires (`scripts/test_v42_trip_wires.py`) + live-API integration (`scripts/test_*_live.py`). Run `bash scripts/run_full_regression.sh` for the 3-tier sweep (source / trip-wires / live).

---

## 2. What the v42 atomic experiment actually taught us

### 2.1 Verdict by field

| Field | Legacy peak | Atomic Phase 5 shadow | v42.6 re-validation | Verdict |
|---|---|---|---|---|
| Classification | 91–92% | **93% / 86% AMP recall** | 90.5% (poisoned by pregate) | **Atomic wins** when isolated. Re-validate on ≥500 NCTs before any cut-over. |
| Peptide | 91–96% | not built | 62–78% (destroyed by pregate) | Legacy is at ceiling. Do **not** build an atomic peptide agent. |
| Outcome | 58–65% | 40–62% | 17% (field collapsed) | Atomic **loses**. Outcome needs synthesis. Keep shadow, never promote. |
| Failure_reason | 85–95% | 67% scoreable | 0% (gate bug — only fires on `outcome=="Failed"`) | One-line gate bug; recoverable. Re-validate in shadow. |
| Delivery_mode | 80–87% | not built | 50.6% | Legacy is already mostly deterministic. Don't atomic it. |
| Sequence | ~50% | not built | 0% (formatting drift) | Legacy's structured-DB lookup is the right model. |

### 2.2 Six lessons that go on the wall

These are the rules for the next 12 months of work. Violating one is a red flag on the change, not a permission to override.

1. **Decomposition must be exhaustive.** Narrow Y/N/Unclear questions beat open-ended multi-class calls — but only if the N questions collectively cover **every signal** that could flip the label. If your aggregator has a catch-all default ("R8 else → Unknown"), the default will eat every case the atomic questions missed. In outcome, we missed safety-only-implies-efficacy, buried regulatory-approval signals, and combination-arm outcomes. That's why R8 swallowed 23 cases on 94 NCTs.

2. **Aggregator defaults determine outcome more than rules do.** R6 "default → Other" in classification ate Curodont/P11-4 AMPs. R8 "default → Unknown" in outcome ate tons. Before merging a new aggregator, **list every label the default catches and justify it on realistic evidence**, not just the happy path.

3. **The pattern that works is "deterministic preempt + LLM gap-fill + optional atomic audit."** Every field that wins (peptide with known-sequences, classification with DBAASP hits, sequence with structured DB lookup) uses this pattern. Every field that loses when forced into pure-atomic or pure-LLM is missing a layer of this.

4. **Efficiency is caching, concurrency, and model-grouping. Not skipping.** `skip_legacy_when_atomic`, `deterministic_peptide_pregate`, `skip_amp_research_for_non_peptides` cost accuracy to buy throughput. `per_drug_research_cache` (when wired), `parallel_research`, model-grouped verification give throughput at zero accuracy cost. **Default to caching; treat skipping as last resort.**

5. **Shadow ≥500 NCTs before any cut-over.** 94 NCTs showed `classification_atomic` at 93% vs legacy 80%. We cut over. The v42.6 re-run didn't replicate it — the 93% was partly noise, partly poisoned by pregate. Rule: shadow through **at least 500 NCTs across three batches** before promoting any atomic to authoritative.

6. **Never bundle accuracy changes with efficiency changes.** Phase 6 cut-over + v42.6 efficiency pack landed in the same week. When #75c/#76 regressed we couldn't tell which change caused which delta. It took two weeks to untangle. **Rule: one axis of change per validation job. Accuracy changes always land alone.**

---

## 3. Forward principles (the design rules)

### 3.1 The layered pattern

Every annotation field should be structured as **three layers**:

```
Layer 0 — Deterministic preempt
  (structured DB hit, registry status, known-sequence match)
  If match → return with high confidence, skip everything else.

Layer 1 — LLM integration
  One call on curated evidence. Must return a value AND a confidence.
  This is the ambiguous-middle workhorse.

Layer 2 — Atomic shadow (optional, diagnostic)
  Parallel narrow Y/N questions + deterministic aggregator.
  Writes <field>_atomic. Never in critical path unless promoted per §4.
```

Layer 0 gives you speed + accuracy on unambiguous cases.
Layer 1 handles the messy middle with integrative judgment.
Layer 2 is a free continuous audit — when it disagrees with Layer 1, it's diagnostic signal.

### 3.2 Prohibitions (things that recent experience proves are bad ideas)

- No drug-name cheat sheets. No `_KNOWN_AMP_DRUGS` lookup tables. Chemistry/biology classifications (INN suffixes, UniProt structural data, sequence length) are fine; brand-name enumeration is not.
- No catch-all default rules in aggregators without field-specific justification listing what the default will catch.
- No efficiency flag that trades accuracy for speed — unless (a) the accuracy loss is measured on ≥200 NCTs and (b) the user approves the tradeoff in writing.
- No pipeline cut-over on <500 NCTs of shadow data.
- No bundling: one axis of change per validation job.

---

## 4. The iteration loop (how any future change gets promoted)

This is **the** workflow. Every proposed agent change goes through it. Skipping steps is the #1 source of regressions.

```
Step 1 — Design doc
  One page. Problem statement, proposed change, success metric,
  what would cause rollback. Reviewed before code.

Step 2 — Unit tests
  Synthetic inputs → expected outputs. ≥10 cases covering
  happy path + known edge cases + default-rule trigger cases.

Step 3 — Smoke run (10 NCTs, ≤30 min)
  Catches crashes, config errors, JSON parse failures,
  obviously-broken prompts. Not a validation — just "does it run."

Step 4 — Shadow validation (100 NCTs, 1 batch)
  Change runs under shadow flag only. Legacy stays authoritative.
  Compare <field>_atomic vs legacy on same data.
  Gate: shadow must be within 5pp of legacy OR clearly better on
  a specific failure mode we're targeting. Otherwise stop.

Step 5 — Extended shadow (500 NCTs, ≥3 batches)
  Rerun across diverse stratification (AMPs, non-AMP peptides,
  small molecules, biologics). Each batch compared independently.
  Gate: consistent ≥5pp improvement across all three batches,
  OR no regression on any field and clearly better on target.

Step 6 — Hybrid validation (100 NCTs, cut-over flag ON)
  Promote to authoritative. Nothing else changes in the same run.
  Compare full pipeline output vs pre-change baseline.
  Gate: field-level metrics within 2pp of shadow prediction.
  Any surprise = rollback and investigate why.

Step 7 — Full regression (300+ NCTs)
  Final check on a fresh stratified set. All fields measured.
  Gate: no field drops below its current baseline by more than 2pp.

Step 8 — Ship
  Merge to main. Update AGENT_STRATEGY_ROADMAP.md §1 with
  new commit hash + validation job IDs.
```

**Rollback is cheap.** Every step's validation job ID is logged. If anything regresses after ship, we have the previous known-good commit + validation bundle to return to.

---

## 5. Field-by-field forward plan

### 5.1 Classification (AMP vs Other)

**Status:** legacy authoritative, atomic in shadow.
**Plan:** atomic **may** be better than legacy, but the Phase 5 signal was ambiguous. Re-validate cleanly before any move.

**Next jobs:**
- Job #79 — 500-NCT shadow run, no pregate, no efficiency flags. Stratified: 150 AMPs + 200 non-AMP peptides + 150 others.
  - **Gate:** atomic within 5pp of legacy on overall agreement, AND AMP recall ≥ legacy AMP recall.
  - Pass → Job #80. Fail → leave atomic in shadow, move on.
- Job #80 — 100-NCT hybrid: `prefer_atomic_classification: true`, everything else off. Fresh NCTs.
  - **Gate:** overall agreement within 2pp of Job #79 atomic measurement. AMP recall not worse.
  - Pass → merge flag on. Fail → rollback.

**Target:** lift classification 92% → 94%+ AMP recall 80% → 90%.

### 5.2 Peptide

**Status:** legacy authoritative. **Do not build an atomic peptide agent.**
**Reason:** legacy 91–96% is at the inter-annotator ceiling. Time/cost to atomize is not justified.

**Only change allowed:** expand `_KNOWN_SEQUENCES` when a new well-characterized peptide appears in the data (chemistry, not drug-name cheat-sheeting). Updates require a 100-NCT re-run to confirm no regression on existing cases.

### 5.3 Outcome

**Status:** legacy authoritative. Atomic in shadow as permanent diagnostic signal.
**Plan:** **Never promote.** Outcome requires integrative synthesis over fuzzy signals; narrow Y/N questions cannot deliver that.

**Use of atomic shadow:**
- Flag cases where atomic and legacy disagree with high confidence on both sides. These are worth human review — usually one of the two agents is wrong.
- Track atomic accuracy over time. If a future architectural change (e.g. better Tier 1b assessor model) lifts atomic past 70%, revisit.

**Only legacy-side improvements allowed:**
- Better publication-priority override (v41b's regression is the current ceiling; revisit after more shadow data shows where legacy over/under-calls).
- Better Tier 0 deterministic status mapping (e.g. withdrawn + no results → Terminated, not Unknown).

### 5.4 Failure_reason

**Status:** legacy authoritative. Atomic has a one-line gate bug (`outcome == "Failed"` should be `outcome in ("Failed", "Terminated", "Withdrawn")`).
**Plan:**
- **Fix the gate** (Task: see §7).
- Re-run atomic in shadow on 100 NCTs. If it reaches 85%+ scoreable agreement, push through the iteration loop toward cut-over.
- If not, leave shadow as diagnostic.

### 5.5 Delivery_mode

**Status:** legacy authoritative. No atomic built. Do not build one.
**Current known issue:** multi-intervention route-list handling — e.g. "injection/infusion, oral" collapses to "N/A". This is legacy-side and should be fixed inside the legacy path, not via atomic.

### 5.6 Sequence

**Status:** legacy authoritative. Already structured (DB lookup + `_KNOWN_SEQUENCES`). No atomic.
**Known issue:** formatting drift (multi-sequence `|`-separated output vs GT single canonical). Fix inside the legacy formatter.

---

## 6. Efficiency — the cache strategy

### 6.1 The standing rule

**Efficiency through caching, concurrency, and model-grouping. Never through skipping.**

### 6.2 Concrete wins available now

| Win | Estimated speedup | Accuracy cost | Status |
|---|---|---|---|
| `DrugResearchCache` wired into chembl/dbaasp/apd/iuphar/rcsb_pdb/pdbe/ebi_proteins | 30–50% on batches with repeated drugs | 0% | **In progress** (Task #86) |
| `parallel_research: true` | already on | 0% | done |
| `parallel_annotation: true` | already on | 0% | done |
| Model-grouped verification (v11+eff) | already on | 0% | done |
| `outcome_atomic_max_voting_pubs: 20` | bounds tail-latency on 45-pub trials | 0% | done |
| HTTP response cache for idempotent GETs (second-order) | 5–15% | 0% | deferred — do only if drug_cache isn't enough |

### 6.3 Concrete efficiency loss recovery

Compared to the (broken) v42.6.8 run at 134 s/trial:
- Pure legacy with no caching: ~320 s/trial. **2.4x slower** than broken-but-fast.
- Pure legacy + drug_cache: expected ~220–250 s/trial. **~30% faster** than pure legacy.

We lose most of the v42.6.8 speedup but we get back to **better accuracy than #71 at ~70% of #77's speed**, which is a clean win.

---

## 7. Near-term concrete plan

(Section last refreshed 2026-04-26. Jobs #78–#89 already executed —
see `LEARNING_RUN_PLAN.md` for the full registry.)

The v42.7 cycle just closed with Jobs #88 + #89 on the 47-NCT clean slice.
Net deltas vs Job #83 baseline: peptide flat, classification flat, delivery
+2.8pp, outcome flat (recovered after #88's -2.1pp dip), RfF +8.3pp. All
116+ unit tests pass.

### Currently in flight
*(none — v42.7 cycle closed; planning next cycle)*

### v42.7 cycle close-out (what shipped)
| Sub-version | Commit | What it did | Validated by |
|---|---|---|---|
| v42.7.0 | 2cd0378a | SEC EDGAR + FDA Drugs research agents (17 agents total) | live tests + Job #87s |
| v42.7.1 | f1c57e08 | 5-tier `evidence_grade` + diagnostics aggregate | Job #87t |
| v42.7.2 | ed380774 | `commit_accuracy_report.py` + pub classifier expansion (5 agents in deterministic outcome override) | Job #88 |
| v42.7.3 | 5e548125 | Per-field `_DB_KEYWORDS_BY_FIELD` dispatch (fixes commit-accuracy inversion) | Job #88 |
| v42.7.4 | 0c0a7471 | Two-tier source weighting (`_PUB_AGENTS_HIGH_QUALITY` for keyword scan) | Job #89 |

### Recurring discipline (not jobs — process)
1. Every code change ships with a unit test in `scripts/test_v42_*_*.py`.
2. Smoke validation on a targeted slice (5–20 NCTs that exercise the
   change) before any full re-baseline.
3. Full re-baseline only when ≥3 narrow fixes have accumulated, OR when a
   change touches the global pipeline.
4. Jobs that fail their gate are rolled back via revert commit, not by
   pushing a "fix the fix" patch on top.
5. NCT slices for outcome accuracy must be GT/registry-aligned (excluded
   GT=active when CT.gov says COMPLETED/UNKNOWN). See §9 entry.
6. Smoke runs assert running-service commit hash equals on-disk HEAD
   before reporting pass (memory-vs-disk pitfall — see §9 2026-04-25 entry).

### Future targets (not committed; ranked by ROI, post-v42.7)
1. **PMC OpenAccess full-text.** Currently reads abstracts; PMC OAI has
   full article XML. 2-3x trial-specific evidence per pub. Adds compute
   for parsing — measure cost-per-NCT before committing.
2. **Calibrated-decline layer phase 3** — extend INCONCLUSIVE first-class
   labelling to outcome (Phase 2 was scaffolding only). Once SEC EDGAR
   + FDA Drugs commit-accuracy is measured, we'll know the threshold.
3. **classification_atomic shadow re-validation** — 500 NCTs to test
   whether Phase 5's 93% beat-legacy was real or noise. Now realistic
   given the 19-agent pipeline is stable.
4. **Phase 1 outcome reasoning push.** Job #83's confusion matrix shows
   Positive-class recall 46% (the under-call, biggest single bucket).
   Targeted prompt + dossier work on positives. Independent of new APIs.
5. **Reduce 5-NCT smoke ceremony.** v42.7.x cycle had 4–5 smokes; some
   were redundant. Define a clearer "trip-wire test" — a 1-NCT
   regression test pinned to specific past bugs (NCT04527575 EpiVacCorona,
   NCT01689051 GLP-1, NCT03196219 DBAASP) — to replace exploratory smokes.
6. **v42.7.5 + v42.7.6 main-merge cadence.** Both items currently sit on
   dev pending smoke validation. Smoke #91 (10-NCT, code-sync gate +
   NIH RePORTER hit count) merges both atomically once active job ≠ 0
   becomes a non-issue (post-Job-#90).

### What's no longer on the list (closed in v42.7.0–v42.7.6)
- ~~SEC EDGAR research agent~~ — shipped v42.7.0.
- ~~FDA Drugs@FDA research agent~~ — shipped v42.7.0.
- ~~Pub classifier expansion (broaden `_GENERAL_SIGNALS`)~~ — shipped v42.7.2 (then refined in v42.7.4 to two-tier).
- ~~drug_cache validation run~~ — Jobs #87s + #87t confirmed cache stats wired and populated; hit_rate is currently low (7–15%) on drug-diverse slices but works as designed.
- ~~Memory-vs-disk pitfall — structural fix~~ — shipped v42.7.5 (BOOT_COMMIT_* + `/api/diagnostics/code_sync` + `scripts/check_code_sync.sh`).
- ~~Held-out 30-NCT outcome test set~~ — shipped as `scripts/holdout_outcome_slice_v42_7_5.json` (30 NCTs: 7 terminated + 14 positive-heavy + 9 unknown). Use for next code-cycle validation.
- ~~NIH RePORTER research agent~~ — shipped v42.7.6 as the 19th agent. Discovery: documented `clinical_trial_ids` criterion silently no-ops; only `advanced_text_search` actually filters.

### Free data sources surveyed (2026-04-25)

Already wired: ClinicalTrials.gov, PubMed/PMC abstracts, UniProt, DRAMP,
APD, DBAASP, ChEMBL, IUPHAR, RCSB PDB, EBI Proteins, PDBe, WHO ICTRP,
DuckDuckGo, bioRxiv/medRxiv, OpenAlex, Semantic Scholar, CrossRef.

To add (priority order matches §7 ranking above):
- **SEC EDGAR** — `efts.sec.gov/LATEST/search-index` — 10-K/10-Q/8-K
- **FDA Drugs@FDA** — `api.fda.gov/drug/drugsfda.json`
- **NIH RePORTER** — `api.reporter.nih.gov/v2/projects/search`
- **PMC OpenAccess full-text** — `eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc`
- **Europe PMC full-spectrum** — extend existing client to query `SRC:MED`, `SRC:CTX`, `SRC:PMC`, not just `SRC:PPR`
- **CORE** — `core.ac.uk/services/api` — open-access aggregator, free key 10K/month
- **Wikidata SPARQL** — pre-curated drug discontinuation dates
- **Crossref Event Data** — `api.eventdata.crossref.org` — social/blog mentions

Excluded (not free or not useful enough): pharma-news scrapers
(FiercePharma, Endpoints — paid/ToS issues), conference-abstract
aggregators beyond what PMC already covers.

**Excluded by user direction (2026-04-25):** active-learning loop. No
human-in-the-loop will correct agent indecision. The pipeline must
self-resolve: every NCT gets a final committed value AND a confidence
grade; downstream filters by confidence (see §11). No retraining loop
from human corrections.

---

## 11. Calibrated-decline layer (planned, not committed)

User goal: "truth in reality, not hallucinations or math problem
solutions." Every committed answer must be grounded in citable
evidence; otherwise the agent emits a confidence flag downstream can
filter on. No human in the loop — Inconclusive is a **final state**,
not a hand-off.

### Evidence grades (5-tier)

Every annotation carries a `confidence_grade` field in addition to
`value` + `confidence` (numeric). Grades, in descending strength:

1. **DB_CONFIRMED** — authoritative database entry.
   - DRAMP/DBAASP/APD hit (classification, sequence)
   - FDA approval letter (outcome=Positive)
   - SEC 8-K disclosing trial discontinuation (outcome=Failed/Terminated, RfF=*)
   - p<0.05 verbatim in trial-specific publication (outcome=Positive)
   - UniProt mature chain length 2-100 aa (peptide=True)
2. **REGISTRY_DETERMINISTIC** — CT.gov status mapping.
   - status=TERMINATED + whyStopped match → Terminated/Failed
   - status=ACTIVE_NOT_RECRUITING + not stale → Active, not recruiting
   - status=COMPLETED + hasResults=True → Positive
3. **PUB_TRIAL_SPECIFIC** — multiple (≥2) trial-specific pubs agree.
   - 2+ pubs say "primary endpoint met" or equivalent strong-efficacy
   - 2+ pubs report a specific failure (not just safety mention)
4. **LLM_INFERRED** — LLM judgment over evidence.
   - The current default. Pass 1+2+verifier consensus, no DB anchor.
5. **INCONCLUSIVE** — no grounded signal.
   - Output for cases where the agent has no business committing.

### Per-field commit thresholds

Different fields have different evidence requirements before they may
commit (otherwise → INCONCLUSIVE):

| Field | Minimum to commit |
|---|---|
| Peptide | LLM_INFERRED OK (already near-ceiling) |
| Classification (Other) | LLM_INFERRED OK |
| Classification (AMP) | DB_CONFIRMED preferred, PUB_TRIAL_SPECIFIC OK |
| Delivery_mode | REGISTRY_DETERMINISTIC OK |
| Outcome (Positive) | **DB_CONFIRMED or PUB_TRIAL_SPECIFIC required** |
| Outcome (Failed) | DB_CONFIRMED or REGISTRY_DETERMINISTIC required |
| Outcome (Terminated/Withdrawn/Active/Recruiting) | REGISTRY_DETERMINISTIC required |
| Outcome (Unknown) | reserved for "trial state genuinely unknown after evidence review" |
| RfF | DB_CONFIRMED (whyStopped parse, SEC filing) or PUB_TRIAL_SPECIFIC |
| Sequence | DB_CONFIRMED OK (UniProt/DRAMP/DBAASP/APD/known-sequence) |

### Why this matches "truth in reality"

1. Every committed answer cites specific evidence (DRAMP entry,
   SEC filing URL, pub PMID, registry status). No hand-wavy LLM
   "Positive because pubs looked good".
2. Hallucinations are blocked at the commit gate — if no DB / pub /
   registry signal backs the LLM's answer, the agent declines to
   commit.
3. Confidence becomes empirical (count of grounded signals agreeing),
   not LLM self-reported.
4. The audit trail is reviewable per-trial — every output has a
   citable provenance chain.

### Use of INCONCLUSIVE downstream

- **Training-data filtering**: a downstream consumer building a
  high-precision dataset filters to commits ≥ DB_CONFIRMED.
- **Coverage trade-off**: a high-recall consumer keeps LLM_INFERRED
  too, accepting more noise.
- **Confidence-weighted prediction**: downstream weights predictions
  by their evidence grade.

### Scoring impact

Concordance scoring should report TWO numbers:
- **Coverage**: % of trials where agent committed (i.e. NOT Inconclusive)
- **Commit accuracy**: of committed cases, % matching GT

An agent that commits on 60% of trials at 95% accuracy is more useful
than one that commits on 100% at 70% accuracy — in any use case where
wrong labels cost more than missing labels (which is most of them).

### Roll-out phases (when committed)

- Phase 1: add `confidence_grade` field to FieldAnnotation. All current
  output keeps existing values, gets graded.
- Phase 2: implement INCONCLUSIVE for outcome only (highest gain). Run
  shadow validation: how does coverage × commit-accuracy compare to
  current raw accuracy?
- Phase 3: extend to RfF, then sequence (DB_CONFIRMED is most natural
  there).
- Phase 4: extend to other fields if Phases 1-3 deliver expected lift.

Not committed yet — pending the SEC EDGAR / FDA Drugs / NIH RePORTER
work to give the calibrated-decline layer enough DB_CONFIRMED signals
to commit on.

---

## 8. Operational discipline

### 8.1 Commit hygiene

- One logical change per commit. Never bundle "fix X + efficiency Y".
- Every commit that changes an annotator, aggregator, or research client has a corresponding unit test and smoke-run plan in the commit message.
- Before merging to main: state the validation job ID that justified the merge.

### 8.2 Documentation

Three always-current docs:
- `AGENT_STRATEGY_ROADMAP.md` (this file) — rules and forward plan.
- `LEARNING_RUN_PLAN.md` — job registry with outcomes.
- `ATOMIC_EVIDENCE_DECOMPOSITION.md` — design reference for the atomic shadow pipelines (preserved for history + future re-evaluation).

Nothing else. Additional docs fork the source of truth.

### 8.3 Never-do-again list (the wall of shame)

Things that cost us real time and must not repeat:

- Cutting over `prefer_atomic_classification` + `prefer_atomic_failure_reason` at the same time as rolling out `deterministic_peptide_pregate` + `skip_legacy_when_atomic` + `skip_amp_research_for_non_peptides`. Five flag changes in one release, no way to isolate.
- Treating 94-NCT shadow results as ship-ready.
- Iterating on `deterministic_peptide_pregate` for 4 versions (v42.6.5 → .6 → .7 → .8) when the approach itself was unsound. We should have killed the feature at v42.6.6.
- Running the autoupdater with a 3-second curl timeout against an active-jobs endpoint that could block > 3s under load. Cost us Job #75 mid-run.
- Having a pregate match `"NS"` (normal saline) and `"Curodont"` (brand name) as peptide sequences — no minimum-length guard, no word-boundary check.

---

## 9. Decision log (append-only)

Record what was decided and why. Future-you needs to read this.

| Date | Decision | Reason | Reversal trigger |
|---|---|---|---|
| 2026-04-23 | Flip all atomic cut-over + efficiency-pack flags OFF. Keep shadow. | Jobs #76/#77 showed systemic regression vs v40; flipping flags restores without code revert. | Job #78 fails to restore baseline → code-level investigation. |
| 2026-04-23 | Freeze `deterministic_peptide_pregate`. Will not re-enable. | 4 iterations failed; approach is unsound (spurious matches, ChEMBL FNs on obvious peptides). | Never — remove the code entirely once all references are purged. |
| 2026-04-23 | Wire `DrugResearchCache` into research clients one at a time. | Pure efficiency win, zero accuracy cost. Already-written infrastructure unused. | Any validation shows field-level change → rollback that client's wiring. |
| 2026-04-23 | Outcome atomic will never be promoted. Runs shadow permanently as diagnostic. | Synthesis-heavy field; narrow Y/N questions structurally cannot deliver the integrative judgment required. | An architectural change that gives atomic a meta-integration step AND shadow beats legacy by ≥5pp on 500 NCTs. |
| 2026-04-23 | Narrow peptide=False cascade to sequence + classification only. | Job #78 revealed the v15/v18 broad cascade was zeroing delivery/outcome/failure_reason for non-peptide trials, when GT annotators give those fields specific values (non-peptide trials still have delivery modes and outcomes). Cost: ~27pp delivery, ~30pp outcome. | A validation run shows delivery regresses vs Job #78 (impossible since #78 was already cascade-zeroed). |
| 2026-04-23 | Restore ANR Active guard for past-completion + no-publications case. | v41b removed the days_since<=180 guard to let publication-priority override fire, but swung too far: ANR with past completion + zero pubs defaulted to Unknown from the LLM. New condition (ANR + not stale + 0 trial-specific pubs + no hasResults) restores deterministic Active without blocking pub-override. | Validation shows false Active calls on trials with real published Positive results — tighten the guard further. |
| 2026-04-23 | Do not run exploratory prod jobs. Every prod job must test a specific hypothesis after code fixes + unit tests on dev. | Job #78 cost 4.2h of prod time and produced garbage because I flipped flags without fully understanding the cascade. Bad results have no value except audit signal. | N/A — this is permanent discipline. |
| 2026-04-24 | Tighten `_dossier_publication_override` to require ≥2 trial-specific pubs + strong efficacy keyword (primary endpoint met / p<0.05 / approval / phase advancement). | Job #79 analysis showed 9 of 11 Positive over-calls were caused by the v41 override firing on loose efficacy keywords present in review-article titles. Review articles often contain "clinical benefit", "efficacy", "antitumor activity" without a primary-endpoint statement, and these were being read as Positive signal. | Legitimate Positive trials (primary endpoint met, ≥2 pubs) begin returning Unknown — then widen the efficacy list. |
| 2026-04-24 | Always re-score analysis scripts against `app.services.concordance_service._normalise` before claiming an agent regression. | My ad-hoc Job #78/#79 analysis used raw-string comparison and missed the production alias map (`active` ↔ `Active, not recruiting`, `N/A` as blank). This inflated the apparent delivery regression from "disaster" (53%) to a small dip (88.9% → 84.2%), and made me pursue a cascade fix that was less impactful than claimed. | N/A — this is permanent analysis discipline. |
| 2026-04-24 | v42.6.12: CT.gov ACTIVE_NOT_RECRUITING is the default outcome label for stale ANR trials, NOT "Unknown". Post-LLM safety net maps Unknown → canonical registry status for ANR/Recruiting/NotYetRecruiting/EnrollingByInvitation. | Job #80 showed v42.6.11's tightened Positive-over-call prompt over-corrected: 11 of 13 GT=active trials flipped to "Unknown" instead of "Active, not recruiting". GT annotators use the CT.gov status label regardless of staleness; staleness alone is not grounds for "Unknown". The strong-efficacy override remains and promotes real positives. | A validation run shows legitimate Positive trials misclassified as Active (strong-efficacy gate too narrow) — loosen strong-efficacy or add explicit hasResults+completed-status override. |
| 2026-04-24 | v42.6.13: preserve retry-failure annotations with a model='agent-crashed' sentinel + CRASH warning + stderr traceback, instead of the original and retry both silently dropping. | Job #80 had 9 "missing" delivery_mode annotations with no visible cause — the asyncio.gather exception handler and the retry exception handler both swallowed errors. With v42.6.13, Job #81 surfaced the exact bug: `UnboundLocalError: not_specified_override` on the Pass 2 = Other path of delivery_mode.annotate(). 10 trials recovered with full error visibility. Diagnostic preservation is a permanent investment, not a one-off fix. | Never. |
| 2026-04-24 | v42.6.14: bare "approved" and "granted approval" removed from `_STRONG_EFFICACY`; require regulatory-qualified phrases (FDA/EMA/regulatory/marketing authorization/received approval). | NCT04527575 (COVID vaccine EpiVacCorona) flipped Unknown→Positive on a review snippet "EpiVacCorona was approved for emergency use in Russia". The word "approved" in a pub title is too weak a signal — it catches drug-class descriptions and emergency-use designations, not trial-specific primary-endpoint wins. | A validation shows a legitimate FDA-approved drug gets missed (rare; the qualified phrases still catch them). |
| 2026-04-24 | Outcome accuracy on this 50-NCT set has a hard ceiling ~50-60% driven by GT/registry divergence (10 of 20 GT="active" trials have CT.gov status COMPLETED or UNKNOWN). Not all remaining outcome gaps are agent bugs. | Confusion-matrix inspection on #81: 4 of 10 GT=active→pred=Unknown have status=COMPLETED (CT.gov says done, human says active); 6 have status=UNKNOWN (CT.gov itself doesn't know). No pipeline fix can reconcile this — humans are using out-of-band info. | Expand ground-truth audit — either flag these trials as GT-ambiguous or accept the outcome ceiling on this set and evaluate on a different NCT slice. |
| 2026-04-24 | Validation scope must match change scope. Two-line fixes get smoke runs (5-15 NCTs targeting the trials that exercise the change), not full 50-NCT re-baselines. Re-baseline only when (a) a coherent group of fixes has accumulated, or (b) a change touches the global pipeline. | Job #82 was submitted as a full 50-NCT validation for v42.6.14 (delivery null-init + 'approved' keyword narrowing) — both already proven by unit tests. User correctly flagged it as wasteful. Cancelled and re-run as 11-NCT targeted smoke (Job #82s) with sharp pass criteria (0 CRASH warnings, NCT04527575 ≠ Positive, 10/10 delivery annotations real). All gates passed in ~1h vs 6h. | N/A — permanent discipline. |
| 2026-04-25 | The "25% outcome ceiling" on the original 50-NCT set was ~75% measurement artifact, not agent failure. On a GT/registry-aligned slice (Job #83, 47 NCTs), outcome is 61.7% — close to v34 historical 65%. Future outcome validation MUST use slices where GT and CT.gov status are aligned; mixing in GT=active+CT.gov=COMPLETED trials makes any number meaningless. | Job #83 confusion matrix: Terminated 12/12 (100%), Unknown 12/13 (92%), Positive 6/13 (46%), Failed 2/9 (22%). The agent is genuinely competent on terminated/unknown; remaining gap is Positive under-call (strong-efficacy gate too strict for non-canonical wording) and Failed scatter (whyStopped not flowing through). | Future GT audit shows the divergent 'active' annotations were correct after all (e.g. via direct sponsor inquiry) — would re-frame those as agent miss. Unlikely. |
| 2026-04-25 | Pipeline emits `reason_for_failure` (full name) as the FieldAnnotation field_name; old analysis scripts that searched for `failure_reason` (short) silently returned empty for every RfF query. ALWAYS try both variants when scoring RfF outside the production concordance_service. | Job #85 first looked like 0/20 on RfF (catastrophe); actually 8/20 = 40% once the field-name lookup checked both spellings. Real category breakdown: Business 62.5%, Recruitment 75%, Ineffective 0% (gated upstream by Unknown outcome), Toxic 0/1, Covid 0/1. | N/A — the production concordance_service uses the correct name. Discipline applies to ad-hoc analysis scripts only. |
| 2026-04-25 | When the autoupdater skips an annotate restart (because of an active job), code-on-disk diverges from code-in-memory. Smoke validations must verify the running service's commit reflects the change — not just the on-disk commit. Push a no-op trigger commit if needed to force restart on the next active-jobs=0 cycle. | The v42.6.17 + v42.6.18 smokes (f44a87f1477c, 57bd65a8d271, 925f4dfc3b54 first run) both ran on stale memory because Job #85 ran continuously through the merges; the no-op-commit trigger (00660388) forced the autoupdater to redeploy and the re-run smoke (3d8862f2dcd6) finally validated cleanly. | N/A — permanent operational discipline. |
| 2026-04-25 | When fixing a substring/disambiguation issue in a helper, grep the whole file for OTHER places that iterate the same data structure directly. The first v42.6.18 commit fixed `resolve_known_sequence()` but missed a parallel loop at sequence.py:595 that uses the same `_KNOWN_SEQUENCES` dict; only the second commit (v42.6.18 part 2) caught it. | Smoke 86s passed Gates 1+2 but failed Gate 3 (GLP-1 still resolved to glucagon) because the second iteration site bypassed the helper. Now both call sites use longest-first iteration. | N/A — permanent code-review discipline. |
| 2026-04-26 | Active-learning loop is OUT of the calibrated-decline design. INCONCLUSIVE is a final state for downstream filtering, NOT a hand-off to humans. Downstream consumers filter by evidence_grade and accept lower coverage in exchange for higher commit-accuracy. | User direction: "no human will come in an correct any indecision by the llms." The pipeline must self-resolve every NCT to a final committed value plus an evidence grade; the grade IS the indecision signal. | User reverses on human-in-the-loop. Unlikely. |
| 2026-04-26 | Two-tier publication source weighting is the right pattern: broad set for LLM-visible context, peer-reviewed-only set for deterministic keyword overrides. Preprints and aggregators (biorxiv, semantic_scholar, crossref) add useful breadth in the LLM dossier but introduce noise when their titles are scanned for strong-efficacy keywords. | Job #88's pub-classifier expansion to all 5 agents lost -2.1pp outcome (4 new under-calls, 3 new gains) while gaining +7.6pp RfF. Job #89's restriction of the keyword-scan branch to `_PUB_AGENTS_HIGH_QUALITY = (literature, openalex)` recovered outcome to baseline while keeping the +8.3pp RfF gain. Two-tier source weighting is now a documented design pattern for any future expansion of dossier sources. | A future expansion adds a sixth pub agent that is BOTH peer-reviewed AND noisy on keyword scan — would need a third tier or per-keyword tier. Not currently anticipated. |
| 2026-04-28 | Prompt FALLBACK clauses with "default to Unknown" wording must NEVER be the strongest part of a rule — the LLM follows them too literally. Job #96 on held-out-B revealed v42.7.13's "If 'Registered Trial Publications: 0' appears, default to Unknown" caused 12 GT=positive trials to be under-called even when pub titles like "Randomized phase I/II clinical trial of [drug]" were unambiguously the trial report. Outcome dropped 60% → 36% on a positive-heavy slice. Fix at v42.7.17: replace strict FALLBACK with an EQUIVALENT alternative path (pub title contains drug name + phase/first-in-human/clinical-trial descriptor; generic field reviews still excluded). The LLM gets explicit permission, not just a denial-default. | Future prompt-rule design: prefer "Mark X when ALL of (i)-(iv) hold; otherwise consider Y" over "Mark X only if Z; default Unknown otherwise." The asymmetric "default Unknown" form discounts the LLM's own judgment on the evidence it actually sees. | If a future rule rewrite reintroduces a strict FALLBACK and accuracy drops on the held-out, soften it back. |
| 2026-04-27 | Standard tune-set / held-out separation: each held-out NCT slice is used **at most twice** before retirement. Held-out-A (30 NCTs, `holdout_outcome_slice_v42_7_5.json`) was used as Job #92 (v42.7.11) and Job #95 (v42.7.13) — it is now retired. Held-out-B (`holdout_outcome_slice_b_v42_7_14.json`, 25 NCTs, seed 5252) is the slice for v42.7.14+ validation. | The original held-out was built to validate v42.7.7-11. Job #92 surfaced 12 errors that we then categorized (4 over-calls, 3 hard under-calls, GT category boundaries, etc.) — that categorization is "training" against the slice. Re-running held-out-A after applying gates derived from those categorizations is overfitting in the strict ML sense; the LLM noise floor (~8.5% per-trial) is bigger than the marginal effect of v42.7.14/15 on this slice anyway. Per-cycle fresh held-out is the discipline. | Active. The picker is parameterized — generate held-out-C/D/etc. for future cycles by changing the seed and extending the exclusion list. |
| 2026-04-27 | The orchestrator must preserve intervention `type` when building the metadata dict passed to research agents. SEC EDGAR / FDA Drugs / NIH RePORTER all filter by `type in ("DRUG", "BIOLOGICAL")`; if `type` is absent, the dict is silently dropped. Fix at orchestrator.py:1183. | v42.7.0 (2026-04-25) introduced the new agents but only built `{"name": name}` dicts. Discovered while validating v42.7.7+8 on dev smoke `e46797571504`: NCT00002228 (Enfuvirtide DRUG) and NCT03199872 (RV001V BIOLOGICAL) both reported "No interventions to search" from all 3 new agents despite having clear interventions. Every prod job since v42.7.0 (jobs #87s/87t/88/89/90) ran with these 3 agents silently no-op-ing on drug-name search — they returned only NCT-based hits at best. Trip-wire added to lock the fix. | A future research agent has different filter rules — just add a new path in `_extract_intervention_names`. The orchestrator's broader contract (preserve type) is now a hard rule. |
| 2026-04-27 | Vaccine/immunotherapy Phase I trials have immunogenicity AS the primary endpoint, not clinical efficacy. The outcome agent's prompt and override now treat ≥2 trial-specific publications reporting immunogenicity (induces immune response / antibody titers / T-cell response / seroconversion) as "primary endpoint met" — but only when the trial is detected as a vaccine/immunotherapy trial (intervention name OR brief title match). | Job #83 confusion matrix: Positive recall 6/13 = 46%; ~5 of the 7 under-calls are vaccine/immunotherapy trials (NCT03199872 RhoC vaccine, NCT03272269 peptide immunotherapy, NCT03645148 pancreatic vaccine, NCT03380871 lung cancer vaccine, NCT00002228 HIV/T-20). Loosening the gate for non-vaccine trials would recreate the v41 over-call regression that v42.6.11 fixed; gating tightly on `is_vaccine_trial` keeps non-vaccine behaviour unchanged. | Held-out validation shows the gate firing on non-vaccine trials (would mean the heuristic is mis-detecting trial type) — would tighten the detector. |
| 2026-04-26 | Per-field `_DB_KEYWORDS_BY_FIELD` is mandatory for any future evidence-grading work. UniProt/ChEMBL/RCSB confirm peptide-ness but say nothing about AMP-vs-Other; treating their hits as `db_confirmed` for classification overrates an LLM call dressed up in DB clothing. | Job #88's commit_accuracy_report showed db_confirmed at 71% accuracy on classification while llm registered 100% — inverted ranking. Fixed by per-field dispatch: classification db_confirmed only when DRAMP/DBAASP/APD hits. Outcome db_confirmed only when SEC EDGAR/FDA Drugs hits. | Future evidence sources (NIH RePORTER, PMC) need to declare which fields they confirm — same dispatch pattern. |
