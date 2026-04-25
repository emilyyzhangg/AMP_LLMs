# Agent Strategy Roadmap

**Status:** active — this is the governing document for all future agent changes.
**Created:** 2026-04-23 (post v42.6.9 recovery).
**Supersedes:** the "Phase 6 cut-over" plan in `ATOMIC_EVIDENCE_DECOMPOSITION.md`.

Read this before proposing any agent change. If it's not in here, it needs a plan update first.

---

## 1. Current state

- **Authoritative pipelines:** legacy for every field.
- **Shadow pipelines:** `classification_atomic`, `failure_reason_atomic`, `outcome_atomic` all run and write `<field>_atomic` for audit — never in the critical path.
- **Commit:** `257810da` on main (v42.6.9).
- **Last validation baseline:** Job #78 (in flight) — 50-NCT re-run of the #75c/#76 set with every efficiency/cut-over flag off. Target: restore v40-equivalent accuracy (peptide ≥90%, classification ≥90%, delivery ≥80%, outcome ≥60%, RfF ≥85%).

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

## 7. Near-term concrete plan (next 4 jobs)

### Job #78 — IN FLIGHT
- **Purpose:** confirm flag flip restores v40 baseline.
- **Config:** v42.6.9 (atomic + efficiency flags off), legacy authoritative.
- **Data:** same 50 NCTs as #75c/#76.
- **Gate:** peptide ≥90%, classification ≥90%, delivery ≥80%, outcome ≥60%, RfF ≥85%.
- **Pass:** proceed to Job #79.
- **Fail:** the regression isn't config-gated; full code-level investigation required.

### Job #79 — classification_atomic shadow re-validation (pending)
- **Purpose:** test Lesson 5 — is Phase 5's 93% atomic real or noise?
- **Config:** v42.6.9. Atomic shadow ON (default). No cut-over flag.
- **Data:** 500 NCTs, stratified: 150 AMPs + 200 non-AMP peptides + 150 others.
- **Measurement:** `classification_atomic` vs legacy `classification` on same 500 trials. AMP recall, precision, overall agreement.
- **Gate for promotion (Job #80):** atomic ≥ legacy on AMP recall AND overall agreement within 5pp.

### Job #80 — classification_atomic cut-over (pending Job #79)
- **Purpose:** confirm hybrid-mode behavior matches shadow prediction.
- **Config:** v42.6.9 + `prefer_atomic_classification: true`. No other change.
- **Data:** 100 fresh NCTs.
- **Gate:** classification field within 2pp of Job #79 atomic score.

### Job #81 — drug_cache speedup validation (concurrent with #79)
- **Purpose:** confirm drug_cache is pure speedup.
- **Config:** v42.6.9 + drug_cache wired into research clients.
- **Data:** 50 NCTs with high drug repetition (e.g. 50 semaglutide trials from training CSV).
- **Gate:** identical field values to legacy reference run AND ≥25% wall-clock reduction.

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
