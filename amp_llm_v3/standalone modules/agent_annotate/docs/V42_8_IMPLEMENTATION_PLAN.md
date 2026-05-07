# v42.8 Implementation Plan — Levers 3, 4, 5

_Authored 2026-05-06. Levers 1+2 already landed (commits `9b8ed95c`, `91e4cbe0`). This document is the executable spec for the remaining three levers — each future session opens this file, picks the next lever, follows the implementation steps verbatim, and lands the change._

---

## 0. Preamble — what's locked in already

- **Agent code freeze for v42.7 publication target:** main `82a88146` + report `8537c540`
- **v42.8 levers landed on dev:**
  - v42.8.1 (commit `9b8ed95c`): RfF emission gate — `FAILURE_DEFAULTS` dict in `failure_reason.py` covers Failed-completed-trial / Terminated / Withdrawn
  - v42.8.2 (commit `91e4cbe0`): strong-failure publication override — `_STRONG_FAILURE` keyword class in `outcome.py` + `_has_strong_failure(neg)` classmethod + override before v42.7.14 mixed gate
- **Validation slice for v42.8.1+v42.8.2:** `scripts/holdout_outcome_slice_g_v42_8_validation.json` (20 NCTs) submitted on dev as `43d3739fd0b1`. Score with `python3 scripts/score_full_corpus.py 43d3739fd0b1` after completion.
- **Test_batch (50 NCTs, single-shot held-out):** stays locked through this entire cycle. Job #104 is the FINAL run — fires only after the v42.8 stack is fully merged to main and a fresh full-corpus run (Jobs #105+#106) confirms the new accuracy floor.

## 1. Sequencing rules (apply to every lever)

1. **One lever per session.** Levers 3, 4, 5 are each multi-week scope. Don't try to combine.
2. **Hold-out validation between levers.** After lever N lands on dev with trip-wires green, build a fresh held-out slice (`holdout_outcome_slice_h_v42_8_3.json`, etc.) and submit on dev. Compare per-field accuracy to the prior slice's numbers (slice-G, then slice-H, etc.). If a lever doesn't move the needle on the field it was supposed to fix, investigate before merging.
3. **Merge to main only after held-out validates.** Don't accumulate unmerged dev work — the longer dev diverges from main, the higher the merge-conflict risk and the messier the production-gate report becomes.
4. **No drug-name lookups, no NCT shortcuts, no prompt cheat-sheets.** This is hard discipline (`feedback_no_cheat_sheets.md`, `feedback_frozen_drug_lists.md`, `feedback_no_verifier_cheatsheet.md`). Every lever in this plan is reasoning-grounded or new external API integration; if a session is tempted to shortcut, abort the lever and re-scope.
5. **Trip-wire test for every code change.** Add a `test_v42_8_X_*` function to `scripts/test_v42_trip_wires.py` registered in the main() list; the test should fail loudly if the change is reverted or refactored away.
6. **Atomic commit + push.** Commit and push together — the dev-llm autoupdater wipes uncommitted working trees (`feedback_autoupdater_commit_strategy.md`).

---

## 2. Lever 3 — Pub-to-Trial Matcher

**Goal:** classify a publication as trial-specific via NCT-mention scan, sponsor name match, intervention-drug match, and year-window match — independent of CT.gov registration. Currently the only path to "this pub is about this trial" is `protocolSection.referencesModule.references[]`, which sponsors don't always populate (especially for Phase I trials). Many Phase I pubs that exist in the literature are never linked back to their CT.gov record, so the agent's Rule 7 ("default Unknown if Registered Trial Publications: 0") fires too aggressively.

**Expected lift:** catches 15-25 of 65 positive→unknown misses on full corpus. Estimated +4-7pp on outcome accuracy.

**Effort:** ~1-2 weeks.

### 2.1 Scope

- New module: `app/services/pub_trial_matcher.py`
- Function: `classify_pub_relevance(publication, trial_metadata) -> Literal["registered", "matched", "candidate", "unrelated"]`
  - `registered`: PMID is in `protocolSection.referencesModule.references[]` (existing path)
  - `matched`: at least 2 of 4 signals (NCT, sponsor, intervention, year-window) confirm the pub is about this trial
  - `candidate`: 1 of 4 signals confirms; insufficient alone but useful for the LLM to consider
  - `unrelated`: 0 signals, no further weight

### 2.2 The four signals (in detail)

#### 2.2.1 NCT-mention signal
- Look for the trial's NCT ID in the publication abstract / full-text snippet
- Exact match `NCT\d{8}` regex
- Strongest single signal — almost never false positive
- Implementation: `nct_in_pub(pub_text, nct_id) -> bool`

#### 2.2.2 Sponsor signal
- Compare the trial's `sponsor.name` (from CT.gov `protocolSection.identificationModule.organization`) to publication author affiliations
- Normalize: lowercase, strip punctuation, collapse "Inc.", "LLC", etc.
- Match if any author affiliation contains the sponsor name as a substring (with min length guard to avoid 2-letter false positives — same lesson as DBAASP word-boundary trip-wire)
- Implementation: `sponsor_match(sponsor_name, pub_authors) -> bool`

#### 2.2.3 Intervention-drug signal
- Compare the trial's `protocolSection.armsInterventionsModule.interventions[]` (drug names + intervention names) to the publication title + abstract
- Use existing `_KNOWN_PEPTIDE_DRUGS` mapping from `peptide.py` to canonicalize aliases (e.g. CBX129801 ↔ semaglutide)
- Match if any intervention name appears in pub text with word-boundary
- Implementation: `intervention_match(interventions, pub_text) -> bool`

#### 2.2.4 Year-window signal
- A pub published 2-7 years after a trial's `startDate` is plausibly the trial's primary publication. Outside that window: not the primary readout.
- Implementation: `year_window_match(trial_start_year, pub_year) -> bool`

### 2.3 Aggregation rule

```python
def classify_pub_relevance(pub, trial_meta) -> str:
    if pub.pmid in trial_meta["registered_pmids"]:
        return "registered"
    signals = sum([
        nct_in_pub(pub.text, trial_meta["nct_id"]),
        sponsor_match(trial_meta["sponsor_name"], pub.authors),
        intervention_match(trial_meta["interventions"], pub.text),
        year_window_match(trial_meta["start_year"], pub.year),
    ])
    if signals >= 2:
        return "matched"
    if signals == 1:
        return "candidate"
    return "unrelated"
```

The 2-of-4 threshold is the key discipline. False positives (calling a review article "matched") are expensive — they would re-introduce the v42.7.13 over-call class. 2-of-4 makes review articles unlikely to qualify (a review article on cancer immunotherapy isn't co-published with the sponsor's name in author affiliations AND the specific intervention name AND in the trial's year window — at most 2 signals if the review explicitly discusses this trial, which is by definition trial-specific).

### 2.4 Wire-up points

#### 2.4.1 Dossier construction (`_build_evidence_dossier` in `outcome.py`)

Currently the dossier counts `trial_specific_count` based on `_classify_publication`. Extend to track separately:
```python
"matched_trial_pubs": [],  # v42.8.3: pubs flagged "matched" (≥2 signals)
"matched_trial_pubs_count": 0,
```

When `_classify_publication` is called, also call `pub_trial_matcher.classify_pub_relevance` and populate the new field. The existing `_classify_publication`'s "trial_specific" tag stays as-is (heuristic), but the new field is explicit-evidence-driven.

#### 2.4.2 LLM dossier prompt (`_format_dossier_for_llm`)

Currently the prompt shows:
```
Registered Trial Publications: N (PMIDs: ...)
```

Add:
```
Registered Trial Publications: N (PMIDs: ...)
Matched Trial Publications (≥2 NCT/sponsor/intervention/year signals): M (PMIDs: ...)
```

Update Rule 7 in the prompt:
```
Rule 7 (revised v42.8.3): Default to Unknown if BOTH:
  (a) Registered Trial Publications: 0 AND
  (b) Matched Trial Publications: 0 AND
  (c) no pub title contains drug name + phase descriptor (existing condition (b2))
```

The (b) clause is new. This relaxes Rule 7 in exactly the case the audit identified: pub clearly about this trial (multi-signal match), just not formally registered.

#### 2.4.3 Publication-priority override (`_dossier_publication_override`)

Update the v42.8.2 strong-failure rule and the v42.7.14 mixed-evidence rule to consider matched pubs alongside registered+trial_specific:
```python
# v42.8.3: count matched_trial_pubs alongside registered for the
# "trial-specific evidence base" used by overrides.
trial_evidence_count = (
    dossier.get("registered_trial_pubs_count", 0)
    + dossier.get("matched_trial_pubs_count", 0)
)
```
Replace `trial_specific > 0` with `trial_evidence_count > 0` in those two rules.

### 2.5 Tests

#### 2.5.1 Unit tests (`scripts/test_v42_8_3_pub_trial_matcher.py`)

```python
# Single-signal cases
assert classify_pub_relevance(pub_with_nct_only, meta) == "candidate"
assert classify_pub_relevance(pub_with_sponsor_only, meta) == "candidate"
# Two-signal cases → matched
assert classify_pub_relevance(pub_with_nct_and_sponsor, meta) == "matched"
assert classify_pub_relevance(pub_with_intervention_and_year, meta) == "matched"
# Negative
assert classify_pub_relevance(unrelated_review, meta) == "unrelated"
# False-positive resistance
assert classify_pub_relevance(generic_cancer_review, oncology_trial_meta) == "unrelated"
```

#### 2.5.2 Trip-wire (`test_v42_8_3_pub_trial_matcher_signal_threshold`)

```python
src = (PKG_ROOT / "app/services/pub_trial_matcher.py").read_text()
assert "if signals >= 2:" in src and 'return "matched"' in src, (
    "v42.8.3 trip-wire: matcher must require ≥2 signals to call 'matched'. "
    "Lowering this re-introduces the v42.7.13 over-call class."
)
```

### 2.6 Validation slice

Build slice-H, 20 NCTs, biased toward GT=Positive trials with `registered_trial_pubs_count = 0` (i.e. exactly the class lever 3 should fix). Submit on dev. Compare:
- Outcome accuracy on slice-H vs slice-G's outcome accuracy
- Specifically check the positive→unknown miss rate among slice-H NCTs

**Decision rule:** if outcome on slice-H improves by ≥3pp AND classification/peptide/delivery/RfF don't regress beyond their CIs, lever 3 is validated. Merge to main.

### 2.7 Risks

- **Over-call regression.** Most likely failure mode. If the matcher tags review articles as "matched", outcome flips Unknown → Positive on trials that didn't succeed. Mitigation: 2-of-4 signal threshold + the year-window constraint + trip-wire on the threshold.
- **Sponsor false-positives.** Big pharma sponsors (Pfizer, Merck) appear on many unrelated pubs. Mitigation: sponsor-match alone is only 1 signal, never enough to flip "matched" by itself.
- **NCT mention in review articles.** Review articles do sometimes cite NCT IDs as references. NCT-only is 1 signal, not 2. Mitigation: same — single-signal is "candidate", not "matched".

---

## 3. Lever 4 — Drug-Code → Biological-Name Resolver

**Goal:** resolve pharma drug codes (PLG0206, CBX129801, "64Cu-SARTATE", GT-001, etc.) to biological names that UniProt / DrugBank actually index. Currently the `peptide_identity` agent returns "no_structured_match" for these, blocking downstream sequence extraction and weakening the outcome signal (drug_max_phase from ChEMBL would also benefit).

**Expected lift:** unblocks UniProt on ~40% of currently-N/A sequence cases. Estimated +15-20pp on sequence accuracy. Secondary benefit on outcome via richer ChEMBL signals.

**Effort:** ~1-2 weeks.

### 3.1 Scope

- New research agent: `agents/research/drug_code_resolver.py`
- External APIs: RxNorm REST (https://rxnav.nlm.nih.gov/REST/), DrugBank Open API (https://go.drugbank.com/releases/latest)
- Output: for each drug code, list of (canonical_name, source, confidence) tuples
- Integration: results flow into the dossier and are consumed by `peptide_identity`, `sequence`, and `outcome` agents

### 3.2 API design

#### 3.2.1 RxNorm path

```python
async def rxnorm_resolve(drug_code: str) -> list[dict]:
    """Resolve a drug code to canonical names via RxNorm.

    RxNorm exposes /approximateTerm.json which fuzzy-matches across
    brand/generic/code names. For pharma codes (PLG0206), it usually
    returns the generic name + RXCUI. From RXCUI, /related.json with
    tty=IN gives the ingredient name.
    """
    # Step 1: fuzzy match the code to candidates
    url = f"https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term={drug_code}&maxEntries=5"
    # Step 2: for each RXCUI, fetch the ingredient
    # Step 3: return list of {name, rxcui, source: 'rxnorm', confidence: <score>}
```

#### 3.2.2 DrugBank path (fallback / cross-reference)

DrugBank Open Data is a static download (CSV/JSON). Pre-cache on first agent boot:
```python
def _load_drugbank_codes() -> dict[str, str]:
    """Map secondary IDs / drug codes → DrugBank ID → name.

    Cached at app boot in app/services/memory/drug_code_cache.py.
    Refreshed weekly via a background task (or manually).
    """
```

### 3.3 Integration

#### 3.3.1 `peptide_identity` agent

Currently calls UniProt with the intervention name. Add a pre-resolution step:
```python
resolved_names = await drug_code_resolver.resolve(intervention.name)
# Try UniProt with each resolved name in order of confidence
for name, _, _ in resolved_names:
    uniprot_result = await uniprot_client.search(name)
    if uniprot_result.matches:
        return uniprot_result
```

#### 3.3.2 Dossier (`_build_evidence_dossier`)

Add field:
```python
"resolved_drug_names": {},  # intervention_name -> [(canonical, source, confidence)]
```

The LLM prompt then sees:
```
Interventions: PLG0206 → resolved to: plectasin (UniProt P0DPI2)
```

### 3.4 Risk: API failure modes

- RxNorm rate limit: 20 req/sec public limit. Trial has ~3 interventions average, ~10 trials/min batch processing → 30 req/min, well within limit. Add a 0.05s sleep between calls anyway.
- RxNorm returns nothing for very new codes: fallback to DrugBank cache
- DrugBank cache stale: refresh weekly, log when cache is older than 14 days
- Connection failure: graceful degradation — agent returns empty resolved list, downstream agents fall back to current behavior. NEVER raise from this agent (it's evidence augmentation, not gating).

### 3.5 Tests

#### 3.5.1 Live API integration test (`scripts/test_v42_8_4_drug_code_resolver_live.py`)

```python
# Known codes from the v42.7 audit
assert "plectasin" in [r[0].lower() for r in await resolve("PLG0206")]
assert "semaglutide" in [r[0].lower() for r in await resolve("CBX129801")]
assert "octreotate" in [r[0].lower() for r in await resolve("64Cu-SARTATE")]
# Negative case
assert await resolve("FAKE-NONSENSE-12345") == []
```

#### 3.5.2 Trip-wire (`test_v42_8_4_drug_code_resolver_present`)

```python
src = (PKG_ROOT / "app/services/pub_trial_matcher.py").read_text()  # if added there
# OR the new module path
assert (PKG_ROOT / "agents/research/drug_code_resolver.py").exists(), (
    "v42.8.4 trip-wire: drug_code_resolver agent missing. "
    "Sequence under-extraction class will resurface."
)
```

### 3.6 Validation slice

Build slice-I, 20 NCTs, biased toward GT-sequence trials with currently `sequence=N/A` from full-corpus (these are the targets). Submit on dev. Compare sequence accuracy on slice-I vs slice-G. **Decision rule:** if sequence improves by ≥10pp AND outcome doesn't regress, validated. Merge to main.

### 3.7 Risks

- **Wrong canonical resolution.** RxNorm might map a code to the wrong drug. Mitigation: the resolver returns a list of candidates with confidence scores; downstream agents try them in order and accept the first UniProt-matching one. If none match, fall back to current behavior (no harm done).
- **Performance.** Two new API calls per intervention adds latency. Mitigation: cache results in memory_store with TTL.
- **API key requirements.** RxNorm is fully public. DrugBank Open Data is public (CC0); the licensed full DrugBank requires academic registration. Use Open Data only.

---

## 4. Lever 5 — Press-Release / Conference-Abstract Agent

**Goal:** capture positive-result reporting that doesn't reach peer-reviewed literature within Phase I trial timelines. Sponsors often announce trial readouts via press releases (sponsor newsroom, BusinessWire, PR Newswire) or conference abstracts (ASCO, ASH, AAD, SfN, AHA) months before — or instead of — a peer-reviewed publication. This is the dominant evidence source for the recency-driven outcome miss class on NCT05+ trials.

**Expected lift:** 10-15 of 65 positive→unknown misses on full corpus. Estimated +3-4pp on outcome accuracy. Particularly impactful for the 2021+ trial cohort where literature is sparse.

**Effort:** ~2-3 weeks.

### 4.1 Scope

- New research agent: `agents/research/press_release_client.py`
- Sources (in priority order):
  1. Sponsor newsroom pages (deep search via web fetch + content extraction)
  2. PR Newswire / BusinessWire (structured search APIs)
  3. ASCO, ASH, AAD, SfN, AHA, ESMO, AACR conference abstract databases
  4. SEC filings (8-K trial readout disclosures) — partial overlap with existing `sec_edgar_client`, but surface trial-readout-specific content

### 4.2 Per-source design

#### 4.2.1 Sponsor newsroom

Hardest source: sponsor websites are heterogeneous. Approach:
1. Resolve sponsor name → primary domain (use a small curated map for the top 50 pharma sponsors; fallback to web search)
2. Fetch the sponsor's `/news`, `/press-releases`, `/investors/news` paths
3. Filter results for the trial's NCT ID, drug name, indication
4. Extract publication date + headline + first paragraph

```python
SPONSOR_DOMAIN_MAP = {
    "pfizer inc.": "pfizer.com",
    "merck sharp & dohme corp.": "merck.com",
    # ... ~50 entries; refresh quarterly
}
```

NB: this map is sponsor name → domain, NOT a drug-name lookup. It's metadata about sponsor identity, which is in the trial's CT.gov record already. Per discipline rules, this is acceptable.

#### 4.2.2 PR Newswire / BusinessWire

Public search APIs:
- PR Newswire: structured news search at `https://www.prnewswire.com/news-search/?query=...`
- BusinessWire: equivalent at `https://www.businesswire.com/portal/site/home/news/`

Both support keyword + date-range search. Query with: `"<drug_name>" + ("trial" OR "results" OR "data")`. Filter results for the trial's NCT ID or sponsor + drug match.

#### 4.2.3 Conference abstracts

ASCO Meeting Library: https://meetinglibrary.asco.org/api/...
ASH Annual Meeting: https://ashpublications.org/blood/issue (Blood supplements include abstracts)
ESMO: https://oncologypro.esmo.org/meeting-resources

Each has a different access pattern. Phase 1: ASCO + ASH only (highest yield for drug trials). Phase 2 (later): expand to ESMO/AACR.

Query: drug name + year-window. Match abstract authors against trial sponsor + investigator names.

#### 4.2.4 SEC 8-K (already exists)

Extend the existing `sec_edgar_client.py` to also surface 8-K disclosure language about trial readouts. Look for headlines like:
- "announces top-line results"
- "reports positive Phase 2 data"
- "achieves primary endpoint"
- "discontinues development of"

### 4.3 Output schema

```python
@dataclass
class PressReleaseEvidence:
    source: str  # "sponsor", "prnewswire", "asco", "ash", "sec_8k"
    url: str
    date: datetime
    headline: str
    snippet: str  # first 1000 chars of body
    confidence: float  # how sure are we this is about THIS trial
    signals: dict  # which match signals fired
```

### 4.4 Integration

#### 4.4.1 Dossier (`_build_evidence_dossier`)

```python
"press_release_evidence": [],  # list of PressReleaseEvidence
"press_release_count": 0,
"has_positive_pr": False,  # any with positive-result phrases
"has_negative_pr": False,  # any with discontinuation / failure phrases
```

#### 4.4.2 Outcome aggregation

A new override rule, BEFORE the v42.6.11 publication-priority gate:
```python
# v42.8.5: positive press-release override. When a sponsor has formally
# announced positive trial readouts (PR Newswire / sponsor newsroom)
# AND no contradicting negative PR exists, treat as Positive even when
# peer-reviewed literature is sparse. This is the v42.7-uncovered case
# where the trial's results are public but not yet in journals.
if (dossier.get("has_positive_pr")
        and not dossier.get("has_negative_pr")
        and dossier.get("press_release_count", 0) >= 1
        and current_value in ("Unknown", None)):
    return "Positive"
```

Symmetric rule for negative press releases (announced trial halts, discontinuations) → "Failed - completed trial" or "Terminated" depending on registry status.

### 4.5 Tests

#### 4.5.1 Live API integration tests

For each source (sponsor, prnewswire, asco, ash, sec_8k), one known-good NCT that should surface evidence + one known-negative that shouldn't.

#### 4.5.2 Trip-wire (`test_v42_8_5_press_release_override_present`)

```python
src = (PKG_ROOT / "agents/annotation/outcome.py").read_text()
assert "v42.8.5: positive press-release override" in src, (
    "v42.8.5 trip-wire: press-release override missing from "
    "_dossier_publication_override. Recency-class outcome misses "
    "(positive→unknown on 2021+ trials) will resurface."
)
assert "has_positive_pr" in src and "has_negative_pr" in src, (
    "v42.8.5 trip-wire: dossier has_positive_pr/has_negative_pr fields "
    "missing from outcome.py."
)
```

### 4.6 Validation slice

Build slice-J, 20 NCTs, biased toward 2021+ NCTs with GT=Positive and `registered_trial_pubs_count = 0` (the recency-class miss group). Submit on dev. **Decision rule:** if outcome on slice-J improves by ≥5pp on the post-2021 cohort AND no regression on pre-2021 trials, validated. Merge to main.

### 4.7 Risks

- **PR over-trust.** Sponsors are biased communicators; "positive results" in a press release sometimes means "the secondary endpoint moved in the right direction" while the primary endpoint failed. Mitigation: extract the specific phrase and require it to mention "primary endpoint" or "topline" before counting as positive evidence. Otherwise, downgrade to "candidate" — visible to LLM but not auto-flipping.
- **PR/abstract scraping fragility.** Conference websites and sponsor pages change layouts. Mitigation: each source has a per-source extractor with a fallback to "nothing found" rather than crashing the agent. Log structure-change warnings.
- **Rate limiting.** Sponsor sites may block aggressive scraping. Mitigation: 1-second sleep between sponsor newsroom requests, and cache responses for 7 days.
- **License/legal questions about sponsor content scraping.** Press releases are intended for public consumption and re-distribution; sponsor newsroom content is generally fair-use for research. Conference abstracts are typically free abstracts (the full paper requires registration). DO NOT scrape paywalled content.

---

## 5. Closing the cycle

After all three levers land + their per-lever validation slices pass:

1. **Fresh full-corpus run (Jobs #105 + #106).** Same 630 NCTs as #102+#103. Submit batches sequentially on prod. ~4 days clock time.
2. **Score** with `score_full_corpus.py --merged-json`. Compare per-field accuracy to v42.7-frozen full-corpus numbers. Document the lift by lever (compare against the slice-G/H/I/J results to attribute deltas).
3. **Merge dev to main.** Single merge commit covering the entire v42.8 stack.
4. **Update `PRODUCTION_GATE_REPORT.md`** with v42.8 full-corpus numbers as canonical. Mark v42.7 numbers as historical.
5. **Fire Job #104 (test-batch certification, 50 NCTs).** Single overnight run on prod. This is the unbiased final measurement.
6. **Score Job #104.** Compare per-field accuracy to v42.8 full-corpus CIs. If within CI, the publication claim is certified on truly unseen data.
7. **Publication.** Headline: "agent matches or exceeds human inter-rater agreement on N/M fields, validated on a 50-NCT held-out test set never seen during development."

## 6. Pool budget sanity (don't run out of slices)

| Resource | Reserved | Used | Remaining |
|---|---|---|---|
| Total GT-scoreable NCTs (training_csv minus test_batch) | 630 | 630 (full-corpus) | 0 (controlled re-use only) |
| test_batch (single-shot) | 50 | 0 | 50 |
| Iteration slices remaining | n/a | 6 retired (A-G) | controlled re-use OK with overfitting caveat documented |

Slices H, I, J for levers 3, 4, 5 will be controlled re-use of full-corpus NCTs (each picked to exercise the specific fix being validated). The discipline is: each NCT is used in at most one iteration slice per lever, and iteration prompts never read GT-side feedback.

## 7. Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-06 | Option B chosen — defer Job #104 until v42.8 stack complete | test_batch is single-shot; v42.7's 42.3% outcome makes that version a weak publication target; v42.8 levers plausibly bring outcome above human IRA |
| 2026-05-06 | Levers 1+2 land first (lowest scope, biggest single fix) | RfF emission gate + strong-failure override are clean reasoning changes; together address ~30pp RfF + ~1.5pp outcome lift on full corpus |
| 2026-05-06 | Slice-G (20 NCTs, failure-class biased) for v42.8.1+v42.8.2 validation | Targeted exercise of both new gates; controlled full-corpus re-use |
| (pending) | Levers 3, 4, 5 sequenced one-per-session with validation slice between | Avoids over-stacking unmerged changes; isolates lever-specific lift in measurement |

---

_End of plan. Future sessions opening this file: read §0 + §1 first, then jump to the lever you're picking up._
