# v42.9 Implementation Plan — Residual-Gap Closure After v42.8

_Authored 2026-05-08. The v42.8 stack (Levers 1-5) is on main and undergoing full-corpus certification (Jobs #105 + #106). This document captures the projected residual gaps once those numbers land, and the executable spec for the v42.9 cycle that targets them. Each lever follows the same pattern as v42.8: scope → API design → integration → tests + trip-wire → held-out validation slice → merge to main._

---

## 0. v42.8 cross-slice analysis (pre-full-corpus)

Slice-G through slice-J probed each v42.8 lever in isolation. Summary of what was learned (full data in CONTINUATION_PLAN slice table + per-NCT audits saved at `results/json/{slice_job_id}.json`):

### Lever-by-lever projection to full-corpus scale

| Lever | Slice signal | Full-corpus prediction |
|---|---|---|
| 1 (RfF emission gate) | slice-G 12/13 = 92% on terminated/withdrawn-class | ~+40pp on true RfF accuracy (closes 38/57 blank-when-GT-had cases where defaults match GT class) |
| 2 (strong-failure override) | slice-G 0/8 — logic correct, no pubs to fire on | depends on Lever 5 surfacing negative PRs; ~0pp standalone |
| 3 (pub-to-trial matcher) | slice-H 0/16 — LLM correctly applies Rule 3 | foundation only; enables Lever 5's matched-pub recognition |
| 4 (drug-code resolver) | slice-I 1/16 (pre-v42.8.4a filter fix) | ~+0.6pp on sequence (only 22/138 misses are code-shaped) |
| **5 (press-release agent)** | **slice-J 5/14 = 36% on NCT05+ pos→unk** ⭐ | **~+2.7pp on outcome (+9 hits on 26 NCT05+ pos→unk full-corpus)** |

### Projected v42.8 full-corpus accuracy

| Field | Pre-v42.8 | Projected v42.8 | Δ |
|---|---|---|---|
| classification | 96.8% | 96-98% | flat |
| peptide | 86.8% | 86-89% | flat |
| delivery | 87.7% | 87-89% | flat |
| outcome | 42.3% | ~45% | +2.7pp |
| sequence | 25.8% | ~26-27% | +0.6pp |
| RfF (true blank-counted) | ~29% | **~70%** | +40pp |
| RfF (score-blind) | 86.2% | 90-93% | +5pp |

**Outcome will still be below human IRA (55.6%) after v42.8.** The residual gap is the targeting class for v42.9.

---

## 0.A. v42.8 actual full-corpus result (2026-05-11)

| Field | Pre-v42.8 | v42.8 actual | vs projection |
|---|---|---|---|
| classification | 96.8% | **96.2%** | flat |
| peptide | 86.8% | **85.5%** | flat |
| delivery | 87.7% | **87.5%** | flat |
| outcome | 42.3% | **41.1%** | **-1.2pp vs +2.7 projected** ❌ |
| sequence | 25.8% | **25.8%** | flat |
| RfF (score-blind) | 86.2% | **90.6%** | +4.4pp |
| RfF (true-recall, new metric) | ~29% | **47.5%** | +18pp (less than projected +40pp) |

### Where projections diverged from reality

**Lever 5 outcome — net regression.** Slice-J showed 5/14 = 36% positive conversion. At full corpus, Lever 5 fired on 100 trials and:
- +3 positive recall hits (positive class 54→57; +2.5pp)
- −7 unknown recall hits (unknown class 65→58; −8.4pp via false flips)
- Net −4 outcome hits

Root cause: slice-J had **zero unknown-GT trials** because it was picked from pos→unk misses. The full corpus exposes the unknown→positive false-flip class — old NCTs (NCT02xxx/NCT03xxx) matching recent Google News results for the same drug but DIFFERENT trial. The v42.8.5 override fired unconditionally on ≥1 positive PR with no recency or multi-source check.

**Mitigation shipped (v42.8.5a, commit `99bb2443`, 2026-05-11):** override now requires ≥2 PRs OR (1 PR + matched/registered trial pub), status COMPLETED or ACTIVE_NOT_RECRUITING, completion within 5 years. Slice-K validation in flight.

**Lever 1 RfF — under-projected ceiling.** I projected +40pp on true-recall to ~70%. Actual: +18pp to 47.5%. Per-class breakdown reveals why:

| GT class | n | hits | blank | accuracy |
|---|---|---|---|---|
| business reason | 25 | 15 | 7 | 60.0% |
| recruitment issues | 15 | 12 | 3 | 80.0% |
| ineffective for purpose | 15 | 1 | 14 | **6.7%** |
| toxic/unsafe | 4 | 1 | 3 | 25.0% |
| due to covid | 2 | 0 | 2 | 0.0% |

The "ineffective for purpose" 1/15 hit-rate is the dominant residual gap. Lever 1's default applies "Ineffective for purpose" only when outcome=Failed-completed-trial. Since the agent's outcome accuracy on Failed-completed-trial is **0/11 = 0%**, the default never fires on these 14 cases — they're scored as Terminated, defaulting to "Business Reason" → miss.

**Cascade dependency:** Lever 1 RfF improvement on this class is GATED on outcome accuracy improvement on Failed-completed-trial. That requires Levers 2 (strong-failure publication override) firing on more cases — which in turn requires Lever 5's NEGATIVE-PR coverage on these trials. The full-corpus audit showed only 8/630 had negative PRs (vs 100 positive PRs); Google News underweights discontinuation announcements.

This is a v42.9 lever target: **Lever 7 (SEC 8-K extension)** specifically addresses failed-completed-trial detection via mandatory regulatory disclosures.

### v42.8.4b improvements shipped this session (2026-05-11)

- **IUPHAR Tier 3 fallback** in `drug_code_resolver.py` (commit `a2000614`): closes AMG 334 → erenumab class. PubChem covers consumer drugs, RxNorm covers FDA-approved + late-stage, IUPHAR covers research-stage biologicals (antibodies, peptides, novel modalities). Slice-I cohort: AMG 334 now resolves; ABY-029/TH1902/DSP-7888/PGV-001 still empty (very early-stage codes not in any public DB).
- **Score script dual-metric RfF reporting** (`scripts/score_full_corpus.py`): the new "Reason for Failure — dual-metric report" section exposes blank-when-GT-had as a miss and breaks down by GT class. Previous score-blind methodology masked Lever 1's actual position.
- **Synonym filter tightening:** colon-prefixed db refs (`RefChem:`, `ChEBI:`), drug-dictionary bracketed suffixes (`[WHO-DD]`, `[INN]`), and salt-form decorations (`GSK3008348 monohydrochloride`) now all drop. 8/8 unit tests + 28/28 trip-wires pass.

---

## 1. Sequencing rules (apply to every v42.9 lever)

1. **Wait for Job #105 + #106 to complete** before starting v42.9 work. Real full-corpus numbers may diverge from projections — calibrate targets against actuals.
2. **One lever per session**; build held-out slice between each.
3. **No drug-name lookups, no NCT shortcuts, no prompt cheat-sheets** (per `feedback_no_cheat_sheets.md`, `feedback_frozen_drug_lists.md`, `feedback_no_verifier_cheatsheet.md`).
4. **Trip-wire test for every code change** in `scripts/test_v42_trip_wires.py`.
5. **Atomic commit + push to main directly** with `GIT_SSH_COMMAND="ssh -i ~/.ssh/id_ed25519 -o IdentitiesOnly=yes" git push origin main` (per the workflow shift recorded in `feedback_dev_prod_workflow.md`).

---

## 2. Lever 6 — Conference Abstract Scrapers (ASCO, ASH, AAD, ESMO, AACR)

**Goal:** capture trial-readout reporting that appears in conference abstracts before (or instead of) peer-reviewed journals OR press releases. Closes the academic-sponsor gap surfaced in slice-J — 9/14 non-flipped NCTs had sponsors like Minia University / Globe Biotech / Peptilogics that don't issue press releases but DO present at conferences.

**Expected lift:** estimated +3-5pp on outcome (closes the academic-sponsor portion of pos→unk misses).

**Effort:** ~2-3 weeks (each conference has its own search interface).

### 2.1 Scope

- New research agent: `agents/research/conference_abstract_client.py`
- Conferences (priority order):
  1. **ASCO Meeting Library** — `https://meetinglibrary.asco.org/`. Free abstract search, no auth. Highest-yield for oncology trials.
  2. **ASH Annual Meeting** — `https://ashpublications.org/blood/issue` (Blood supplements include meeting abstracts). Hematology / immunology.
  3. **AAD Annual Meeting** — `https://www.aad.org/member/meetings-education/am`. Dermatology — relevant for topical AMP trials.
  4. **ESMO** — `https://oncologypro.esmo.org/meeting-resources`. European oncology.
  5. **AACR** — `https://aacrjournals.org/cancerres/issue`. Translational cancer research.

### 2.2 Per-source design

Each source has a different access pattern. Recommended approach: scoped HTTP fetches with HTML parsing, filtered by drug name + sponsor + year window. ASCO + ASH first (highest volume / cleanest interfaces), expand later.

```python
@dataclass
class ConferenceAbstract:
    conference: str  # "ASCO" | "ASH" | "AAD" | "ESMO" | "AACR"
    year: int
    title: str
    abstract_id: str
    url: str
    snippet: str  # first ~1000 chars of abstract body
    classification: str  # "positive" | "negative" | "neutral" via same primary-endpoint headline rules
```

### 2.3 Integration

Wire into the outcome dossier identically to Lever 5's `press_release_evidence`:

```python
"conference_abstract_evidence": [],
"conference_abstract_count": 0,
"has_positive_abstract": False,
"has_negative_abstract": False,
```

Extend the v42.8.5 override to also fire on positive abstracts (gate: status not WITHDRAWN, no contradicting negative signal):

```python
if (dossier.get("has_positive_abstract") or dossier.get("has_positive_pr")) \
        and not (dossier.get("has_negative_abstract") or dossier.get("has_negative_pr")) \
        and status not in ("WITHDRAWN", "") \
        and current_value not in ("Positive", "Failed - completed trial"):
    return "Positive"
```

### 2.4 Validation slice

**Slice-K:** rebuild from the 9 non-flipped NCT05+ NCTs in slice-J + 6 additional pos→unk full-corpus misses with academic/small-biotech sponsors. Submit on prod after v42.9.6 lands. Decision rule: if outcome on the targeted class improves by ≥20% AND no regressions, validated.

### 2.5 Risks

- **Conference HTML changes break scrapers.** Mitigation: each source isolated in its own module; failures degrade gracefully (return empty). Trip-wires assert structural shape, not content.
- **Older trials (NCT01-04) have abstracts in conference archives.** Closes the "older pos→unk" class (53 trials in full-corpus pre-v42.8) that Lever 5 couldn't reach.

---

## 3. Lever 7 — SEC 8-K Trial-Readout Extension

**Goal:** extend the existing `sec_edgar_client.py` to surface 8-K disclosures that specifically announce trial readouts (positive or negative). The current SEC EDGAR agent surfaces sponsor DISCLOSURES of NCT/drug names but doesn't classify whether the disclosure is a positive readout, negative readout, or routine business update. Sponsors are LEGALLY REQUIRED to file 8-Ks for material trial events (discontinuations, primary-endpoint readouts, regulatory decisions).

**Expected lift:** estimated +2pp on outcome (closes part of the failed-completed-trial 0% miss class; also surfaces positive readouts before they reach news wires).

**Effort:** ~1 week (existing agent infrastructure; just adds classification).

### 3.1 Scope

- Modify `agents/research/sec_edgar_client.py` to fetch full 8-K filing text (currently just citation metadata)
- Add headline / "Item 7.01 Regulation FD Disclosure" / "Item 2.02 Results of Operations and Financial Condition" content scan
- Reuse `press_release_client.classify_headline()` for outcome direction
- Output: `sec_8k_readouts: list[dict]` in dossier

### 3.2 Integration

Add field to dossier:

```python
"sec_8k_readouts": [],
"has_positive_8k": False,
"has_negative_8k": False,
```

Promote to override class alongside Lever 5's PR + Lever 6's conference abstract (composite "trial readout" signal):

```python
positive_readout = (
    dossier.get("has_positive_pr")
    or dossier.get("has_positive_abstract")
    or dossier.get("has_positive_8k")
)
negative_readout = (
    dossier.get("has_negative_pr")
    or dossier.get("has_negative_abstract")
    or dossier.get("has_negative_8k")
)
```

### 3.3 Risks

- **SEC EDGAR full-text fetch is slow** (~1-2s per filing). Batch and cache per (sponsor, fiscal_year).
- **8-K text is verbose** — focus on "Item 8.01 Other Events" + "Item 7.01" sections where trial readouts live.

---

## 4. Lever 8 — Sequence Database Broadening

**Goal:** close the 116/138 sequence misses NOT addressed by Lever 4 (canonical-name interventions where the gap is database coverage, not name resolution). Examples from slice-I audit: vasoactive intestinal peptide, Liraglutide variants, IL-12, autologous dexosomes, HIV-1 C4-V3 polyvalent peptide vaccine — these are real biological entities that should match SOMETHING in UniProt / DRAMP / DBAASP if queried correctly.

**Expected lift:** +5-10pp on sequence (the field that hasn't moved in 5 cycles).

**Effort:** ~1-2 weeks.

### 4.1 Scope

Three orthogonal improvements:

1. **UniProt organism-relaxed search:** currently `peptide_identity` filters to `organism_id:9606` (human) for the primary query; many vaccine/AMP trials use peptides from microbial/viral origin and never match human. Add a second pass with explicit non-human filters (`organism_id:11676` for HIV, `organism_id:1280` for S. aureus, etc.) when the trial title indicates an infectious-disease target.
2. **DRAMP / DBAASP cross-reference:** the AMP-specific databases have peptides UniProt doesn't index. Currently those agents fire only when intervention type is BIOLOGICAL/DRUG. Widen to fire on any peptide-shape intervention OR any classification=AMP trial.
3. **Free-text UniProt fallback (carefully)**: v14 removed this because it returned wrong proteins on common names. Reintroduce ONLY when (a) all structured searches return empty AND (b) the intervention name passes the pharma-code-shape heuristic (a code is unlikely to false-positive on a wrong protein).

### 4.2 Integration

Extends `agents/research/peptide_identity.py`. No new agent needed.

### 4.3 Validation slice

**Slice-L:** 20 NCTs from the 116 sequence misses with canonical-name interventions. Compare sequence accuracy pre-Lever-8 vs post.

### 4.4 Risks

- **Free-text UniProt fallback false-positives** were the original reason for v14 removal. The pharma-code-shape gate is critical — fall back only when structured search yields nothing AND the input looks like a research code.

---

## 5. Decision tree — when to run v42.9

After Jobs #105+#106 complete:

1. **If projected v42.8 outcome lift materializes (~+2.7pp)** → v42.9 work is high-value; outcome still below human IRA, multiple addressable miss classes remain.
2. **If outcome lift is much smaller (<+1pp)** → investigate per-class first. Lever 5 might have over-fired on slice-J; revisit before adding Levers 6-8.
3. **If RfF lift materializes (~+40pp)** → Lever 1 is the canonical win. Score-blindness was masking the gap.
4. **If RfF lift is smaller than projected** → the default-mapping assumption is wrong; investigate per-class accuracy.

### Slice-K (pre-Job-#104 sanity)

Before firing Job #104 (test-batch certification, 50 NCTs, single-shot), run **slice-K**: 10 fresh non-test-batch NCTs picked for outcome class diversity (positive / unknown / terminated / withdrawn / failed-completed each represented). Purpose: catch any v42.8-regression-not-seen-in-slice-G-through-J. Cost: ~2 hours. If slice-K aligns with full-corpus projections, fire Job #104.

---

## 6. Pre-built scoring harness (do this while #105 runs)

Pre-write `scripts/score_v42_8_full_corpus.py` that:

1. Loads Job #105 + #106 result JSONs
2. Merges into a single 630-NCT result
3. Scores against `human_ground_truth_train_df.csv` with the standard consensus rule
4. Produces per-field accuracy + CI + per-class breakdown
5. **NEW:** also reports TRUE RfF accuracy (counting blank-when-GT-had as a miss) alongside the gate-scorer number, so the Lever-1 lift is visible

This means when #106 completes, scoring is one command — no analysis lag.

---

## 7. Open questions for the v42.9 cycle

- Should Lever 5 expand its query strategy to use the resolved-name list from Lever 4? Currently Lever 5 queries Google News with the original intervention name; if Lever 4 resolved "PLG0206 → WLBU2", Lever 5 querying "WLBU2" might surface more results.
- Should EDAM cache Lever 5 results too? Currently press releases are queried fresh per NCT, but trials sharing the same drug (50+ semaglutide trials, etc.) waste queries.
- Conference abstract licensing — ASCO/ASH/AAD are public-access; do their TOS allow programmatic scraping at our query rate? Check before building.
