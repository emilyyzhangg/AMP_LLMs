#!/usr/bin/env python3
"""
v42 trip-wire regression tests (2026-04-26).

These are SOURCE-LEVEL assertions pinned to specific past-bug fixes.
Each assertion encodes a bug we already paid prod time to find: the
test fails the moment someone reverts or refactors the fix without
realizing.

Trip wires are cheaper than re-running a 5-NCT smoke for every code
change. They run in milliseconds, catch regressions at the source-code
diff stage, and give a one-line pointer to the original incident.

If you intentionally need to remove one of these patterns, delete the
trip-wire here in the same commit AND log the decision in
docs/AGENT_STRATEGY_ROADMAP.md §9 (Decision log).
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_v42_6_14_no_bare_approved_in_strong_efficacy():
    """v42.6.14 (2026-04-24): bare 'approved' caused NCT04527575
    EpiVacCorona to flip Unknown → Positive on a review snippet
    'EpiVacCorona was approved for emergency use in Russia.'

    Strong-efficacy must require regulatory-qualified phrases, not the
    bare word 'approved'.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    # _STRONG_EFFICACY must exist
    assert "_STRONG_EFFICACY" in src, "_STRONG_EFFICACY tuple missing"
    # Must require qualified phrases for regulatory wins
    qualified_present = any(
        phrase in src for phrase in (
            "fda approved", "ema approved", "regulatory approval",
            "received approval", "marketing authorization",
        )
    )
    assert qualified_present, (
        "v42.6.14 trip-wire: regulatory-qualified approval phrases must "
        "be in outcome.py (fda approved / ema approved / regulatory "
        "approval / received approval / marketing authorization)."
    )
    print("  ✓ v42.6.14: regulatory-qualified approval phrases present")


def test_v42_6_18_known_sequences_has_glp1():
    """v42.6.18 (2026-04-25): GLP-1 was being matched to glucagon
    (HSQG...) because the iteration order over _KNOWN_SEQUENCES picked
    'glucagon' before 'glucagon-like peptide 1'. Both call sites must
    use longest-first iteration, and the GLP-1 entry must be present."""
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert "_KNOWN_SEQUENCES" in src, "_KNOWN_SEQUENCES dict missing"
    assert "glucagon-like peptide" in src.lower(), \
        "v42.6.18 trip-wire: GLP-1 entry missing from _KNOWN_SEQUENCES"
    # GLP-1's correct sequence starts with HAEG (His-Ala-Glu-Gly...).
    assert "HAEGTFTSDVSSYLEGQAAKEFIAWLVKGR" in src, \
        "v42.6.18 trip-wire: GLP-1 30-aa canonical sequence missing"
    # Longest-first sort is the disambiguator. We expect either an
    # explicit `sorted(..., key=len, reverse=True)` or `sorted(..., key=lambda` form.
    assert any(p in src for p in (
        "key=len, reverse=True", "key=lambda k: len(k)", "key=lambda x: len(x)",
        "len, reverse=True",
    )), (
        "v42.6.18 trip-wire: longest-first iteration sentinel missing in "
        "sequence.py — GLP-1 will be shadowed by glucagon."
    )
    print("  ✓ v42.6.18: GLP-1 entry + longest-first iteration present")


def test_v42_7_4_two_tier_pub_agents():
    """v42.7.4 (2026-04-26): keyword-scan branch must use
    _PUB_AGENTS_HIGH_QUALITY (literature + openalex), not the broad
    _PUB_AGENTS — preprints/aggregators add noise to deterministic
    outcome overrides.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "_PUB_AGENTS_HIGH_QUALITY = (" in src, \
        "v42.7.4 trip-wire: _PUB_AGENTS_HIGH_QUALITY tuple missing"
    # Must restrict to literature + openalex
    import re
    m = re.search(r"_PUB_AGENTS_HIGH_QUALITY = \(([^)]*)\)", src)
    assert m
    members = {a.strip().strip('"\'') for a in m.group(1).split(",") if a.strip()}
    assert "literature" in members and "openalex" in members
    assert "biorxiv" not in members and "semantic_scholar" not in members
    print(f"  ✓ v42.7.4: _PUB_AGENTS_HIGH_QUALITY = {sorted(members)}")


def test_v42_7_3_per_field_db_keywords():
    """v42.7.3 (2026-04-26): commit_accuracy report inverted db_confirmed
    vs llm because UniProt/ChEMBL hits triggered db_confirmed for AMP
    classification but only confirm peptide-ness, not AMP-ness.

    The fix is per-field _DB_KEYWORDS_BY_FIELD dispatch.
    """
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    assert "_DB_KEYWORDS_BY_FIELD" in src, \
        "v42.7.3 trip-wire: _DB_KEYWORDS_BY_FIELD dispatch missing"
    # Classification db_confirmed must be AMP-specific only.
    assert '"classification":' in src
    # Outcome db_confirmed must be regulatory-only.
    assert '"outcome":' in src and "fda_drugs" in src and "sec_edgar" in src
    print("  ✓ v42.7.3: per-field _DB_KEYWORDS_BY_FIELD dispatch present")


def test_v42_7_5_boot_commit_captured_at_module_load():
    """v42.7.5 (2026-04-26): autoupdater skips restart while jobs are
    active, so smokes silently ran on stale code. Fix is to capture
    BOOT_COMMIT_FULL once at module load (NOT lazily).
    """
    src = (PKG_ROOT / "app" / "services" / "version_service.py").read_text()
    assert "BOOT_COMMIT_FULL: str = _git_rev_parse(short=False)" in src, \
        "v42.7.5 trip-wire: BOOT_COMMIT_FULL must be captured at module load"
    assert "is_code_in_sync" in src
    print("  ✓ v42.7.5: BOOT_COMMIT_FULL captured at import")


def test_v42_7_9_fda_query_includes_products_fields():
    """v42.7.9 (2026-04-27): the FDA Drugs Lucene query must include
    `products.brand_name` and `products.active_ingredients.name` so that
    pre-2010 approvals (with empty openfda.* blocks) are matched.
    Removing these regresses the v42.7.0 enfuvirtide/Fuzeon miss."""
    src = (PKG_ROOT / "agents" / "research" / "fda_drugs_client.py").read_text()
    assert "products.brand_name" in src, \
        "v42.7.9 trip-wire: query must include products.brand_name"
    assert "products.active_ingredients.name" in src, \
        "v42.7.9 trip-wire: query must include products.active_ingredients.name"
    print("  ✓ v42.7.9: FDA Drugs query covers both openfda.* and products.* (pre-2010 records)")


def test_v42_7_16_sequence_canonicaliser_strips_chemistry_suffix():
    """v42.7.16 (2026-04-27): sequence canonicalization must strip
    terminal -OH / -NH2 / -NH₂ chemistry suffixes BEFORE the general
    hyphen removal. Without this, GT "(glp)lyenkprrpyil-oh"
    canonicalizes to "LYENKPRRPYILOH" (treating OH as Ornithine-
    Histidine residues) and disagrees with the agent's
    "LYENKPRRPYIL" — false sequence miss.
    """
    src = (PKG_ROOT / "app" / "services" / "concordance_service.py").read_text()
    assert "v42.7.16" in src, "v42.7.16 trip-wire: marker missing in concordance_service"
    assert "NH2|NH₂|OH" in src, \
        "v42.7.16 trip-wire: chemistry-suffix regex missing"
    print("  ✓ v42.7.16: sequence canonicaliser strips -OH/-NH2 terminal suffixes")


def test_v42_7_15_negative_keyword_tightened():
    """v42.7.15 (2026-04-27): _NEGATIVE_KW must NOT include bare 'failed'
    or bare 'negative'. Both fire on patient-cohort descriptions and
    mechanistic terminology that have nothing to do with trial outcome
    ('treatment-failed patients', 'negative control', 'negative regulator').
    Outcome-specific 'failed X' / 'X not met' phrases retained."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    import re
    m = re.search(r"_NEGATIVE_KW = \[\s*((?:[^]])*?)\s*\]", src, re.DOTALL)
    assert m, "v42.7.15 trip-wire: _NEGATIVE_KW list missing"
    items = re.findall(r'"([^"]+)"', m.group(1))
    assert "failed" not in items, \
        "v42.7.15 trip-wire: bare 'failed' must not be in _NEGATIVE_KW"
    assert "negative" not in items, \
        "v42.7.15 trip-wire: bare 'negative' must not be in _NEGATIVE_KW"
    # The qualified outcome-specific phrases must still be there
    assert "failed to meet" in items, \
        "v42.7.15 trip-wire: 'failed to meet' must remain in _NEGATIVE_KW"
    assert "trial failed" in items, \
        "v42.7.15 trip-wire: 'trial failed' must remain in _NEGATIVE_KW"
    print("  ✓ v42.7.15: _NEGATIVE_KW lacks bare 'failed'/'negative', has qualifiers")


def test_v42_7_14_failed_override_status_gated():
    """v42.7.14 (2026-04-27): the 'trial-specific + neg + no efficacy →
    Failed' path must be gated on registry status. Pre-v42.7.14 it
    fired regardless of status — Job #92 NCT03018665 (status=UNKNOWN,
    mixed pubs) got mis-called Failed when GT was Unknown. The gate
    must restrict to terminal statuses (COMPLETED / TERMINATED /
    WITHDRAWN). Removing it recreates the over-call class."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    # v42.8.2 mention 'v42.7.14 lesson' in its comment — search for the
    # specific v42.7.14 BLOCK marker, not the bare version string.
    idx = src.find("v42.7.14 (2026-04-27): Trial-specific publications")
    assert idx > 0, "v42.7.14 block marker missing in outcome.py"
    block = src[idx:idx + 1500]
    assert 'status in ("COMPLETED", "TERMINATED", "WITHDRAWN")' in block, \
        "v42.7.14 trip-wire: Failed override must remain gated on terminal status"
    print("  ✓ v42.7.14: Failed override gated on terminal status")


def test_v42_7_12_indication_match_and_registered_pubs():
    """v42.7.12 (2026-04-27): two override-tightenings to fix Job #92's
    over-call class. (a) FDA-approved override must require strong-efficacy
    keywords (treats FDA-approval as multiplier, not sole trigger).
    (b) Vaccine override must require ≥1 CT.gov-registered publication
    (PMIDs in protocolSection.referencesModule, proven trial-specific).
    Removing either gate recreates the Job #92 over-call regression
    (calcitonin/exenatide/decitabine cross-indication or off-label cases).
    """
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    # v42.7.12 FDA-approved override requires strong-efficacy
    fda_idx = src.find("FDA-approved drug override (TIGHTENED in v42.7.12)")
    assert fda_idx > 0, "v42.7.12 trip-wire: FDA-approved override TIGHTENING comment missing"
    fda_block = src[fda_idx:fda_idx + 1500]
    assert "_has_strong_efficacy(efficacy)" in fda_block, \
        "v42.7.12 trip-wire: FDA-approved override must require strong-efficacy"
    # v42.7.12 vaccine override requires registered_trial_pubs_count >= 1
    vac_idx = src.find("vaccine-immunogenicity gate (TIGHTENED in v42.7.12)")
    assert vac_idx > 0, "v42.7.12 trip-wire: vaccine override TIGHTENING comment missing"
    vac_block = src[vac_idx:vac_idx + 1500]
    assert "registered_trial_pubs_count" in vac_block, \
        "v42.7.12 trip-wire: vaccine override must require registered pubs"
    # Dossier must capture registered_pmids
    assert '"registered_pmids"' in src
    # FDA Drugs client must fetch label.json indications
    fda_src = (PKG_ROOT / "agents" / "research" / "fda_drugs_client.py").read_text()
    assert "FDA_LABEL_URL" in fda_src and "drug/label.json" in fda_src, \
        "v42.7.12 trip-wire: FDA Drugs client must fetch label.json indications"
    print("  ✓ v42.7.12: indication-match + registered-pubs gates intact")


def test_v42_7_10_intervention_type_preserved():
    """v42.7.10 (2026-04-27): orchestrator._run_research must include the
    `type` field when building intervention metadata for research agents.
    Earlier versions only kept `name`, causing SEC EDGAR / FDA Drugs /
    NIH RePORTER to filter every intervention out (their extractor
    requires type in DRUG/BIOLOGICAL). v42.7.0/v42.7.6 agents looked
    healthy in unit tests but were silently no-op-ing in prod for ~2 days
    because of this gap."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    idx = src.find("Extract intervention names from raw protocol data")
    assert idx > 0, "intervention extraction block missing"
    block = src[idx:idx + 2500]
    assert 'interv.get("type"' in block, \
        "v42.7.10 trip-wire: orchestrator must preserve interv['type'] " \
        "in research metadata; without this, SEC EDGAR / FDA Drugs / " \
        "NIH RePORTER receive empty interventions and skip every trial."
    print("  ✓ v42.7.10: orchestrator preserves interv['type'] in research metadata")


def test_v42_7_8_fda_drugs_signal_wired():
    """v42.7.8 (2026-04-27): FDA Drugs / SEC EDGAR raw_data flags must
    flow into the outcome dossier. The dossier must consume the
    `fda_drugs_<name>_approved` boolean and the FDA-approved override
    must remain present. Removing this regresses to v42.7.0 plumbing
    gap where the new agents fired but their output was discarded."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert '"fda_approved_drugs"' in src, \
        "v42.7.8 trip-wire: dossier must define fda_approved_drugs field"
    assert 'result.agent_name == "fda_drugs"' in src, \
        "v42.7.8 trip-wire: outcome dossier must extract from fda_drugs raw_data"
    assert 'result.agent_name == "sec_edgar"' in src, \
        "v42.7.8 trip-wire: outcome dossier must consume sec_edgar citations"
    assert "FDA-approved drug override" in src, \
        "v42.7.8 trip-wire: FDA-approved Positive override must remain"
    print("  ✓ v42.7.8: FDA Drugs + SEC EDGAR raw_data flow into outcome dossier")


def test_v42_7_7_vaccine_immunogenicity_override():
    """v42.7.7 (2026-04-27): vaccine-immunogenicity Positive override.
    The override must be tightly gated on is_vaccine_trial — removing
    that gate recreates the v41 over-call regression. Both the
    is_vaccine_trial dossier field AND the prompt's Rule 7 exception
    must remain in place."""
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "_IMMUNOGENICITY_KW" in src and "_VACCINE_NAME_TOKENS" in src, \
        "v42.7.7 trip-wire: vaccine + immunogenicity keyword sets missing"
    assert 'dossier.get("is_vaccine_trial")' in src, \
        "v42.7.7 trip-wire: override must gate on is_vaccine_trial"
    assert "EXCEPTION (vaccine" in src, \
        "v42.7.7 trip-wire: prompt Rule 7 must keep the vaccine EXCEPTION"
    print("  ✓ v42.7.7: vaccine+immunogenicity gate intact (is_vaccine_trial guard preserved)")


def test_v42_7_6_nih_reporter_uses_advanced_text_search():
    """v42.7.6 (2026-04-26): the documented `clinical_trial_ids` filter
    on api.reporter.nih.gov silently no-ops. Only `advanced_text_search`
    actually filters. The agent must use the correct criterion."""
    src = (PKG_ROOT / "agents" / "research" / "nih_reporter_client.py").read_text()
    assert '"advanced_text_search"' in src, \
        "v42.7.6 trip-wire: must use advanced_text_search criterion"
    # No-op criterion must NOT appear as a JSON key (substring is fine
    # in the docstring describing why we don't use it).
    assert '"clinical_trial_ids"' not in src and "'clinical_trial_ids'" not in src, (
        "v42.7.6 trip-wire: clinical_trial_ids silently returns the "
        "entire 2.9M-row corpus — never use it as a criterion."
    )
    print("  ✓ v42.7.6: advanced_text_search criterion (no-op key avoided)")


def test_v42_7_18_known_sequences_expanded():
    """v42.7.18 (2026-04-28): _KNOWN_SEQUENCES expanded to fill Job #97
    held-out-C peptide=True / sequence=N/A misses. Solnatide (AP301 /
    TIP peptide, NCT03567577), IO103 product-code alias for the existing
    'pd-l1 peptide' entry, and apraglutide backbone (NCT04964986) must
    all remain in _KNOWN_SEQUENCES. Removing them recreates the Job #97
    sequence-extraction gap.

    NOTE: this trip-wire only covers sequences additions. _KNOWN_PEPTIDE_DRUGS
    is frozen per `feedback_frozen_drug_lists.md` — never expand it.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert '"solnatide": "CGQRETPEGAEAKPWYC"' in src, \
        "v42.7.18 trip-wire: solnatide entry missing (NCT03567577)"
    assert '"ap301": "CGQRETPEGAEAKPWYC"' in src, \
        "v42.7.18 trip-wire: ap301 alias missing"
    assert '"tip peptide": "CGQRETPEGAEAKPWYC"' in src, \
        "v42.7.18 trip-wire: tip peptide alias missing"
    assert '"io103": "FMTYWHLLNAFTVTVPKDL"' in src, \
        "v42.7.18 trip-wire: io103 alias missing"
    assert '"apraglutide":' in src and "HGDGSFSDE" in src, \
        "v42.7.18 trip-wire: apraglutide backbone missing"
    print("  ✓ v42.7.18: _KNOWN_SEQUENCES holds solnatide/ap301/tip-peptide/io103/apraglutide")


def test_v42_7_21_known_sequences_expanded():
    """v42.7.21 (2026-04-28): _KNOWN_SEQUENCES expanded to fill Job #98
    held-out-D peptide=True / sequence=N/A misses. CBX129801 (Long-Acting
    C-Peptide, NCT01681290 Type 1 Diabetes neuropathy trial) and SARTATE
    (octreotate analog used in 64Cu-SARTATE, NCT04440956) must both be
    present. Removing them recreates the Job #98 sequence-extraction gap.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert '"cbx129801": "EAEDLQVGQVELGGGPGAGSLQPLALEGSLQ"' in src, \
        "v42.7.21 trip-wire: cbx129801 entry missing (NCT01681290)"
    assert '"long-acting c-peptide":' in src, \
        "v42.7.21 trip-wire: long-acting c-peptide alias missing"
    assert '"sartate": "fCYwKTCT"' in src, \
        "v42.7.21 trip-wire: sartate entry missing (NCT04440956)"
    assert '"octreotate":' in src, \
        "v42.7.21 trip-wire: octreotate alias missing"
    print("  ✓ v42.7.21: _KNOWN_SEQUENCES holds cbx129801 + sartate + octreotate aliases")


def test_v42_7_23_radiotracer_isotope_class_split():
    """v42.7.23 (2026-04-30): radiotracer rule split by isotope class.
    PET (positron-emitting [68Ga], [18F], [124I], etc.) and SPECT
    (gamma-emitting [99mTc], [111In], etc.) are administered IV by
    physics — always Injection/Infusion. Therapeutic isotopes (90Y,
    177Lu, 131I, 225Ac, 211At) CAN be oral (131I capsules for thyroid)
    — defer to explicit injection signal, fall back to v31 'Other'
    for unspecified context. Job #100 surfaced 5 NCTs validating this
    split.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "delivery_mode.py").read_text()
    assert "v42.7.23" in src, "v42.7.23 marker missing in delivery_mode.py"
    assert "_PET_ISOTOPE_PATTERNS" in src, \
        "v42.7.23 trip-wire: _PET_ISOTOPE_PATTERNS tuple missing"
    assert "_SPECT_ISOTOPE_PATTERNS" in src, \
        "v42.7.23 trip-wire: _SPECT_ISOTOPE_PATTERNS tuple missing"
    assert "_THERAPEUTIC_ISOTOPE_PATTERNS" in src, \
        "v42.7.23 trip-wire: _THERAPEUTIC_ISOTOPE_PATTERNS tuple missing"
    # Sentinel for PET/SPECT always-IV behavior
    assert "PET/SPECT radiotracer" in src and 'value="Injection/Infusion"' in src, \
        "v42.7.23 trip-wire: PET/SPECT always-IV branch missing"
    # Sentinel that therapeutic isotope branch still has the v31 Other fallback
    assert "Therapeutic radioisotope" in src, \
        "v42.7.23 trip-wire: therapeutic-isotope branch missing"
    print("  ✓ v42.7.23: PET/SPECT always-Inj + therapeutic isotope explicit-injection check")


def test_v42_7_22_cgrp_disambiguation():
    """v42.7.22 (2026-04-28): NCT03481400 CGRP migraine trial had its
    intervention name 'Calcitonin Gene-Related Peptide' (37aa peptide
    hormone) shadowed by the shorter 'calcitonin' key (32aa, different
    drug). Same v42.6.18 pattern — longest-first iteration is in place,
    but the longer key wasn't in the dict. Adding it disambiguates.
    Reverting recreates the wrong-sequence emission.
    """
    from agents.annotation.sequence import resolve_known_sequence
    result = resolve_known_sequence("calcitonin gene-related peptide")
    assert result is not None, "v42.7.22 trip-wire: CGRP entry missing"
    drug, seq = result
    assert drug == "calcitonin gene-related peptide", \
        f"v42.7.22 trip-wire: longest-first must return CGRP key, got {drug!r}"
    assert seq == "ACDTATCVTHRLAGLLSRSGGVVKNNFVPTNVGSKAF", \
        f"v42.7.22 trip-wire: must return 37aa alpha-CGRP, got {seq!r}"
    print("  ✓ v42.7.22: CGRP / calcitonin disambiguation via longest-first iteration")


def test_v42_7_20_pub_classifier_default_general():
    """v42.7.20 (2026-04-28): _classify_publication default flipped from
    `trial_specific` (v41b) to `general`. Cross-job analysis of Jobs
    #95/#96/#97/#98 showed `positive → unknown` is the dominant outcome
    miss class; spot inspection (NCT01677676 / NCT05137314 / NCT05898763)
    revealed the heuristic was over-tagging field-review pubs as
    [TRIAL-SPECIFIC], systematically confusing the LLM. Tightening to
    require explicit trial signals (phase X, randomized, first-in-human,
    clinical trial, NCT match, etc.) makes [TRIAL-SPECIFIC] tags
    reliable. Reverting recreates the over-tagging confusion class.
    """
    from agents.annotation.outcome import _classify_publication
    # Generic field-review title without explicit trial signal must be
    # tagged general (the v42.7.20 default).
    r = _classify_publication(
        "Computational Approaches to Universal Influenza Vaccines",
        "NCT99999999",
    )
    assert r == "general", \
        f"v42.7.20 trip-wire: ambiguous title must default to 'general' (got {r!r})"
    # Explicit trial signal (phase + first-in-human) must still be trial_specific.
    r = _classify_publication(
        "First-in-human phase I/II dose-escalation study of XYZ",
        "NCT99999999",
    )
    assert r == "trial_specific", \
        f"v42.7.20 trip-wire: explicit-trial-signal title must remain trial_specific (got {r!r})"
    # NCT match always trial_specific.
    r = _classify_publication("Review covering NCT12345678 results", "NCT12345678")
    assert r == "trial_specific", \
        f"v42.7.20 trip-wire: NCT match must override review keyword (got {r!r})"
    print("  ✓ v42.7.20: classifier default flipped to 'general' + NCT/phase signals preserved")


def test_v42_7_19_delivery_ambiguous_keyword_relevance_gate():
    """v42.7.19 (2026-04-28): the delivery_mode protocol-keyword scan
    must skip ambiguous keywords (tablet/capsule from `_AMBIGUOUS_KEYWORDS`)
    when the citation snippet doesn't mention any experimental intervention
    name. Job #92/#95/#96/#97 surfaced 6 distinct NCTs (NCT01673217,
    NCT01704781, NCT03018665, NCT05096481, NCT05965908, NCT05995704)
    where FDA Drugs / OpenAlex citations on similarly-named approved
    drugs (INQOVI, TEMOZOLOMIDE, Metformin) or unrelated publications
    added a spurious 'Oral' route to vaccine/peptide/biologic trials.
    Removing this gate recreates the regression.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "delivery_mode.py").read_text()
    assert "v42.7.19" in src, \
        "v42.7.19 trip-wire: marker missing in delivery_mode.py"
    idx = src.find("v42.7.19")
    block = src[idx:idx + 2500]
    assert "citation_mentions_experimental" in block, \
        "v42.7.19 trip-wire: citation_mentions_experimental flag missing"
    assert "_AMBIGUOUS_KEYWORDS" in block, \
        "v42.7.19 trip-wire: gate must restrict to _AMBIGUOUS_KEYWORDS members"
    print("  ✓ v42.7.19: delivery_mode ambiguous-keyword relevance gate present")


def test_v42_7_24_reasoning_caps_raised():
    """v42.7.24 (2026-05-02): Job #101 production-gate audit found 43-73%
    of stored reasoning fields were truncated mid-thought because of
    legacy 500-char `_parse_reasoning` caps + 400-char pass-text excerpts.
    Decisions unaffected, but publication-grade auditability suffered.
    Caps raised consistently across 5 agents — this trip-wire prevents
    accidental revert to the v25-era 500/400 values.
    """
    targets = [
        ("agents/annotation/outcome.py", [":2000]", ":1200]"]),
        ("agents/annotation/peptide.py", [":2000]", ":1500]"]),
        ("agents/annotation/delivery_mode.py", [":2000]", ":1500]"]),
        ("agents/annotation/classification.py", [":1500]"]),
        ("agents/annotation/failure_reason.py", [":2000]", ":1500]"]),
    ]
    for rel, must_have in targets:
        src = (PKG_ROOT / rel).read_text()
        for token in must_have:
            assert token in src, (
                f"v42.7.24 trip-wire: {rel} missing cap '{token}'. The cap "
                "was probably reverted to 500/400 — revisit Job #101 audit."
            )
        # Also assert the OLD caps are not present in _parse_reasoning context
        if "_parse_reasoning" in src:
            # Find the function and check it doesn't use [:500]
            idx = src.index("_parse_reasoning")
            window = src[idx:idx+800]
            assert "[:500]" not in window, (
                f"v42.7.24 trip-wire: {rel}::_parse_reasoning still caps at 500 chars. "
                "Should be 2000 per Job #101 audit."
            )
    print("  ✓ v42.7.24: reasoning caps 500→2000 / 400→1500 preserved across 5 agents")


def test_v42_7_24_failure_reason_early_return_gated():
    """v42.7.24 (2026-05-02): NCT00001827 on Job #101 had agent
    outcome=Terminated but RfF=blank because Pass 1 read CT.gov "Trial
    Status: COMPLETED" → "no failure detected" → early-return at
    failure_reason.py:198 bypassed the v26 Terminated/Withdrawn safety
    net at line ~238. Fix: gate the early-return on outcome NOT being
    a failure category.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "failure_reason.py").read_text()
    # Must check outcome_result alongside _pass1_says_no_failure to gate the early return
    assert "_pass1_says_no_failure(pass1_output) and outcome_result not in" in src, (
        "v42.7.24 trip-wire: failure_reason.py early-return at _pass1_says_no_failure "
        "no longer gates on outcome_result — v26 safety net (Terminated/Withdrawn → "
        "Business Reason default) will be silently bypassed."
    )
    print("  ✓ v42.7.24: failure_reason early-return gated on outcome_result")


def test_v42_8_2_strong_failure_override():
    """v42.8.2 (2026-05-06): Job #101 audit + full-corpus scoring found
    GT=Failed-completed-trial scored 0/11 = 0%. 5/11 misses were agent
    → Unknown when a trial-specific publication explicitly stated the
    primary endpoint was missed. The pre-existing v42.7.14 publication
    override required `not efficacy_keywords` (any stray review-language
    efficacy mention killed the rule). Fix: introduce a STRONG_FAILURE
    keyword class anchored on explicit primary-endpoint phrases (mirror
    of _STRONG_EFFICACY) and a dedicated override that fires regardless
    of stray efficacy keywords, gated on CT.gov status COMPLETED or
    TERMINATED.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "_STRONG_FAILURE = [" in src, (
        "v42.8.2 trip-wire: _STRONG_FAILURE keyword class missing from "
        "outcome.py — failed-completed-trial 0% miss class will resurface."
    )
    for kw in (
        "did not meet the primary",
        "primary endpoint was not met",
        "primary endpoint was not achieved",
        "failed to meet the primary",
    ):
        assert f'"{kw}"' in src, (
            f"v42.8.2 trip-wire: _STRONG_FAILURE missing required phrase {kw!r} — "
            f"primary-endpoint-anchored failure detection regressed."
        )
    assert "_has_strong_failure(neg)" in src, (
        "v42.8.2 trip-wire: _dossier_publication_override no longer calls "
        "_has_strong_failure(neg); failed-completed override regressed."
    )
    strong_idx = src.find("v42.8.2 (2026-05-06): strong-failure publication override")
    v7_14_idx = src.find("v42.7.14 (2026-04-27): Trial-specific publications")
    assert strong_idx > 0 and v7_14_idx > strong_idx, (
        "v42.8.2 trip-wire: strong-failure override must precede the v42.7.14 "
        "mixed-evidence rule. If v42.7.14 fires first, the strong-failure path "
        "is dead code."
    )
    print("  ✓ v42.8.2: strong-failure override precedes v42.7.14 mixed gate")


def test_v42_8_1_failure_reason_emission_gate():
    """v42.8.1 (2026-05-06): Job #101 audit found 9/12 RfF misses were
    agent-blank when GT had a reason (75% of all RfF misses), and
    GT=Failed-completed-trial scored 0/11 = 0% at full-corpus scale.
    Fix: extend the v26 safety-net default to cover 'Failed - completed
    trial' alongside Terminated/Withdrawn, with per-outcome defaults
    (failed-completed → Ineffective for purpose; terminated/withdrawn
    → Business Reason). The dict FAILURE_DEFAULTS encodes this; if it
    regresses to a hardcoded tuple of just Terminated/Withdrawn we
    silently lose the failed-completed coverage.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "failure_reason.py").read_text()
    assert "FAILURE_DEFAULTS = {" in src, (
        "v42.8.1 trip-wire: FAILURE_DEFAULTS dict missing from failure_reason.py — "
        "the per-outcome emission gate has been replaced; failed-completed-trial "
        "trials will silently emit blank RfF again."
    )
    assert '"Failed - completed trial": "Ineffective for purpose"' in src, (
        "v42.8.1 trip-wire: FAILURE_DEFAULTS missing 'Failed - completed trial' "
        "key — Job #101's 0/11 = 0% miss class will resurface."
    )
    assert '"Terminated": "Business Reason"' in src and '"Withdrawn": "Business Reason"' in src, (
        "v42.8.1 trip-wire: FAILURE_DEFAULTS missing Terminated/Withdrawn keys — "
        "v26 default coverage has regressed."
    )
    print("  ✓ v42.8.1: failure_reason emission gate covers Terminated/Withdrawn/Failed-completed")


def test_v42_8_3_pub_trial_matcher():
    """v42.8.3 (2026-05-07) Lever 3: pub-to-trial matcher must exist as
    a standalone module, classify pubs into 4 buckets via 4 explicit
    signals, and be wired into outcome.py's dossier + the v42.8.2 +
    v42.7.14 publication overrides via `trial_evidence_count`.

    Slice-G failed-completed-trial 0/8 audit (2026-05-07): 3 of 4
    Unknown misses had 0 trial-specific pubs because the heuristic
    classifier rejected everything by default (v42.7.20). The matcher
    surfaces those pubs via NCT/sponsor/intervention/year-window
    convergence — closes the sourcing gap that v42.8.2 alone couldn't.
    """
    from app.services import pub_trial_matcher
    for fn in ("nct_in_pub", "sponsor_match", "intervention_match",
               "year_window_match", "classify_pub_relevance"):
        assert hasattr(pub_trial_matcher, fn), (
            f"v42.8.3 trip-wire: pub_trial_matcher.{fn} missing — "
            f"Lever 3 module structure regressed."
        )

    # Smoke the aggregation rule
    pub = {"pmid": "P1", "text": "First-in-human study of widget-12 in NCT01234567",
           "year": 2020}
    meta = {"nct_id": "NCT01234567", "sponsor_name": "Acme Therapeutics",
            "interventions": ["widget-12"], "start_year": 2018,
            "registered_pmids": []}
    r = pub_trial_matcher.classify_pub_relevance(pub, meta)
    assert r == "matched", (
        f"v42.8.3 trip-wire: 4/4-signal pub returned {r!r}, expected 'matched'."
    )
    r2 = pub_trial_matcher.classify_pub_relevance(
        {"pmid": "X", "text": "Generic review on widgets", "year": 2030},
        meta,
    )
    assert r2 == "unrelated", (
        f"v42.8.3 trip-wire: zero-signal review returned {r2!r}, expected 'unrelated'."
    )

    # Wire-up assertions on outcome.py
    src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "from app.services.pub_trial_matcher import classify_pub_relevance" in src, (
        "v42.8.3 trip-wire: outcome.py no longer imports classify_pub_relevance — "
        "matched-pub computation will silently return zero."
    )
    assert "matched_trial_pubs_count" in src and "trial_evidence_count" in src, (
        "v42.8.3 trip-wire: outcome.py missing matched_trial_pubs_count or "
        "trial_evidence_count — overrides reverted to trial_specific-only gate."
    )
    assert "Matched Trial Publications:" in src, (
        "v42.8.3 trip-wire: dossier prompt no longer surfaces Matched Trial "
        "Publications line — LLM Rule 7 cannot apply the (ii) widening clause."
    )
    # The strong-failure override must use trial_evidence_count, not trial_specific.
    strong_block_start = src.find("v42.8.2 (2026-05-06): strong-failure publication override")
    assert strong_block_start > 0
    strong_block = src[strong_block_start:strong_block_start + 1500]
    assert "trial_evidence_count > 0" in strong_block, (
        "v42.8.3 trip-wire: strong-failure override still gates on trial_specific; "
        "matched pubs will never satisfy the v42.8.2 path."
    )
    print("  ✓ v42.8.3: pub-to-trial matcher wired (4 signals, dossier, overrides)")


def test_v42_8_4_drug_code_resolver():
    """v42.8.4 (2026-05-07) Lever 4: drug-code resolver agent must exist,
    be registered in RESEARCH_AGENTS, and the orchestrator's
    _resolve_drug_names must call into it before falling back to the
    LLM Layer-1 prompt. Slice-H sequence 1/9 = 11.1% was the miss class
    this lever closes."""
    resolver_path = PKG_ROOT / "agents" / "research" / "drug_code_resolver.py"
    assert resolver_path.exists(), (
        "v42.8.4 trip-wire: agents/research/drug_code_resolver.py missing — "
        "Lever 4 module deleted; sequence under-extraction will resurface."
    )
    src = resolver_path.read_text()
    for fn in ("def resolve(", "def _resolve_pubchem(", "def _resolve_rxnorm(",
               "class DrugCodeResolverAgent"):
        assert fn in src, (
            f"v42.8.4 trip-wire: drug_code_resolver.py missing required symbol {fn!r}"
        )
    assert "pubchem.ncbi.nlm.nih.gov" in src, (
        "v42.8.4 trip-wire: PubChem URL missing from drug_code_resolver.py"
    )
    assert "rxnav.nlm.nih.gov" in src, (
        "v42.8.4 trip-wire: RxNorm URL missing from drug_code_resolver.py"
    )
    # v42.8.4b: IUPHAR Tier 3 fallback for research-stage biologicals
    # (AMG 334 / erenumab class) that PubChem + RxNorm don't index.
    assert "guidetopharmacology.org" in src, (
        "v42.8.4b trip-wire: IUPHAR URL missing — Tier 3 fallback for "
        "research-stage biologicals (AMG 334 → erenumab) removed."
    )
    assert "def _resolve_iuphar(" in src, (
        "v42.8.4b trip-wire: _resolve_iuphar() function missing"
    )

    reg_src = (PKG_ROOT / "agents" / "research" / "__init__.py").read_text()
    assert "DrugCodeResolverAgent" in reg_src and '"drug_code_resolver"' in reg_src, (
        "v42.8.4 trip-wire: drug_code_resolver not registered in RESEARCH_AGENTS"
    )

    orch_src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    assert "from agents.research.drug_code_resolver import resolve" in orch_src, (
        "v42.8.4 trip-wire: orchestrator no longer imports drug_code_resolver.resolve"
    )
    assert "_pubchem_resolve" in orch_src, (
        "v42.8.4 trip-wire: orchestrator deterministic-resolver step removed"
    )

    out_src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "resolved_drug_names" in out_src, (
        "v42.8.4 trip-wire: outcome dossier no longer carries resolved_drug_names"
    )
    print("  ✓ v42.8.4: drug-code resolver wired (PubChem + RxNorm, orchestrator + dossier)")


def test_v42_8_5_press_release_agent():
    """v42.8.5 (2026-05-07) Lever 5: press-release / news-aggregator
    agent must exist with classify_headline + fetch_news; be registered;
    outcome dossier must populate press_release_evidence and gate the
    new override on primary-endpoint-anchored phrases (mirror of
    v42.8.2 strong-failure discipline). Targets the recency-driven
    positive→unknown miss class on NCT05+ trials."""
    pr_path = PKG_ROOT / "agents" / "research" / "press_release_client.py"
    assert pr_path.exists(), (
        "v42.8.5 trip-wire: agents/research/press_release_client.py missing"
    )
    src = pr_path.read_text()
    for fn in ("def classify_headline(", "def fetch_news(",
               "class PressReleaseAgent"):
        assert fn in src, f"v42.8.5 trip-wire: {fn!r} missing"
    # Must NOT include bare 'failed' / 'approved' as standalone list entries
    # — repeats v42.6.14 + v42.7.15. A bare list entry shows up as either
    # '"failed",' (with trailing comma) or '"failed"\n' (final entry).
    # Multi-word phrases ('"failed primary endpoint"', '"failed to meet"',
    # '"fda approved"') are explicitly allowed.
    import re as _re
    bad = _re.search(r'"\s*(failed|approved)\s*"\s*[,\]\)]', src)
    assert not bad, (
        "v42.8.5 trip-wire: bare 'failed' / 'approved' detected as standalone "
        f"list entry near {bad.group()!r} — repeats v42.6.14 + v42.7.15 "
        "over-call class. All phrases must be primary-endpoint or "
        "regulatory-qualified (e.g. 'failed primary endpoint', 'fda approves')."
    )
    # Must anchor on primary endpoint
    assert "achieves primary" in src or "achieved primary" in src, (
        "v42.8.5 trip-wire: primary-endpoint anchor phrase missing"
    )
    # Registry
    reg_src = (PKG_ROOT / "agents" / "research" / "__init__.py").read_text()
    assert "PressReleaseAgent" in reg_src and '"press_release"' in reg_src, (
        "v42.8.5 trip-wire: PressReleaseAgent not registered"
    )
    # Dossier wiring
    out_src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "press_release_evidence" in out_src and "has_positive_pr" in out_src, (
        "v42.8.5 trip-wire: outcome dossier missing press-release fields"
    )
    # Override block must precede v42.8.2 strong-failure (positive PR is a
    # primary-readout signal; should fire before negative-only paths).
    pr_idx = max(
        out_src.find("v42.8.5 (2026-05-07) Lever 5: press-release override"),
        out_src.find("v42.8.5a (2026-05-11) Lever 5 press-release override"),
        out_src.find("v42.8.5b (2026-05-11) Lever 5 press-release override"),
    )
    sf_idx = out_src.find("v42.8.2 (2026-05-06): strong-failure publication override")
    assert pr_idx > 0 and sf_idx > pr_idx, (
        "v42.8.5 trip-wire: press-release override must precede v42.8.2 "
        "strong-failure (positive readout takes precedence over deterministic "
        "publication-failure phrasing)."
    )

    # v42.8.5b softening (2026-05-11): the multi-source convergence
    # gate (≥2 PRs OR 1 PR + matched pub) was too strict — slice-K
    # showed only 1/5 high-confidence slice-J wins survived because
    # PR coverage is temporally volatile and the target class has 0
    # matched/registered pubs by definition. v42.8.5b keeps the
    # recency + status gates but drops the multi-source requirement.
    # Recency + status is what actually blocks the false-flip class.
    assert "recency_ok" in out_src, (
        "v42.8.5b trip-wire: completion-date recency gate missing — "
        "old NCTs commonly match recent Google News results about the "
        "same drug but different trial; recency check is required."
    )
    assert "ACTIVE_NOT_RECRUITING" in out_src, (
        "v42.8.5b trip-wire: status gate missing the override scope "
        "(COMPLETED + ACTIVE_NOT_RECRUITING only)."
    )
    print("  ✓ v42.8.5: press-release agent wired (Google News RSS + override + dossier)")


def test_v42_10_peptide_anchor():
    """v42.10 (2026-05-21): evidence-based deterministic peptide anchor.
    extract_peptide_signals + peptide_anchor settle the high-confidence cases
    (INN -tide stem / DB / sequence = True; pure antibody / cell-gene = False),
    deferring the ambiguous middle (None) to the LLM. A peptide signal from any
    arm must beat the exclusions (peptide-vaccine + checkpoint-mAb combos). The
    agent must consume it, and the two crude overrides (pre-cascade
    resolve_known_sequence, N/A-as-3-AA consistency) must respect anchored
    decisions so they can't flip an antibody=False back to True."""
    from agents.annotation.peptide_signals import peptide_anchor
    # antibody alone -> False; cell-gene alone -> False
    assert peptide_anchor({"antibody": True, "n_real_drugs": 1}) == "False"
    assert peptide_anchor({"cell_gene": True, "n_real_drugs": 1}) == "False"
    # peptide signal wins over exclusions (combo with checkpoint mAb)
    assert peptide_anchor({"inn": True, "antibody": True, "n_real_drugs": 2}) == "True"
    # peptide + cell context is the ambiguous edge -> defer to LLM
    assert peptide_anchor({"peptide_in_name": True, "cell_gene": True}) is None
    # INN stem / DB / sequence -> True; nothing -> defer
    assert peptide_anchor({"inn": True}) == "True"
    assert peptide_anchor({"db_peptide": True}) == "True"
    assert peptide_anchor({}) is None
    # agent + orchestrator wiring
    pep = (PKG_ROOT / "agents" / "annotation" / "peptide.py").read_text()
    assert "peptide_anchor" in pep and "v42.10 peptide anchor" in pep, (
        "v42.10 trip-wire: PeptideAgent must consume the anchor"
    )
    orch = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    assert orch.count('"[v42.10 peptide anchor" not in') + orch.count(
        '"[v42.10 peptide anchor" in (peptide.reasoning') >= 2 or \
        orch.count("v42.10 peptide anchor") >= 2, (
        "v42.10 trip-wire: both crude peptide overrides (pre-cascade + N/A-3AA "
        "consistency) must respect anchored decisions."
    )
    print("  ✓ v42.10: peptide anchor (deterministic core + override protection)")


def test_v42_9_completed_not_failed_override():
    """v42.9 (2026-05-20) Lever 6: a COMPLETED trial that shows no failure
    signal is a success. Phase 1/2 safety & PK trials have no efficacy
    endpoint to "meet", so requiring positive-efficacy language strands them
    at Unknown. The override fills Unknown→Positive for COMPLETED trials,
    gated on: no strong-failure publication phrase, no negative press release,
    and no failed primary endpoint. It must NOT overturn a non-Unknown call."""
    out_src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert "v42.9 completed-not-failed" in out_src, (
        "v42.9 trip-wire: completed-not-failed override marker missing"
    )
    # The override must be guarded by all three failure signals.
    idx = out_src.find("v42.9 Lever 6")
    assert idx > 0, "v42.9 trip-wire: override block comment missing"
    block = out_src[idx:idx + 2000]
    for guard in ("_has_strong_failure", "pr_neg == 0", "not failed_endpoint"):
        assert guard in block, (
            f"v42.9 trip-wire: failure guard {guard!r} missing from override — "
            "without it the rule would flip genuinely-failed completed trials."
        )
    # Must only fire when the model left the field Unknown (fill, don't overturn).
    assert 'value == "Unknown" and dossier["registry_status"].upper() == "COMPLETED"' in out_src, (
        "v42.9 trip-wire: override must be gated on value==Unknown + COMPLETED "
        "so it never overturns a Failed/Terminated/Positive determination."
    )
    # Must lock in the result: Job 74f71a5c306d showed the 3-pass verifier flips
    # 17/35 of these Positives back to Unknown. The override must skip
    # verification so the deterministic principle isn't re-litigated and undone.
    assert "v429_completed_positive" in out_src, (
        "v42.9 trip-wire: override must set a flag (v429_completed_positive) and "
        "skip verification — otherwise the verifier pool reverts the principle."
    )
    idx = out_src.find("if v429_completed_positive:")
    assert idx > 0 and "skip_verification = True" in out_src[idx:idx + 200], (
        "v42.9 trip-wire: v429_completed_positive must force skip_verification=True."
    )
    print("  ✓ v42.9: completed-not-failed override (fill Unknown→Positive, failure-gated, verify-locked)")


def test_v42_9_resolved_name_propagation():
    """v42.9 (2026-05-20) P1: Lever-4 resolved canonical drug names must reach
    ChEMBL / FDA Drugs / NIH RePORTER / SEC EDGAR / IUPHAR. Previously these
    agents queried only the raw trial code ("AMG 334") and missed the indexed
    generic ("erenumab"). Each must import the shared resolved_names helper and
    use query_names() for raw->resolved fallback. Also: ChEMBL max_phase must be
    coerced (accept numeric 0; not dropped as falsy), and the outcome consumer
    must read per-intervention `*_molecules` keys (not a flat 'molecules')."""
    helper = PKG_ROOT / "agents" / "research" / "resolved_names.py"
    assert helper.exists(), "P1 trip-wire: agents/research/resolved_names.py missing"
    hsrc = helper.read_text()
    assert "def extract_interventions(" in hsrc and "def query_names(" in hsrc, (
        "P1 trip-wire: resolved_names helper missing extract_interventions/query_names"
    )
    for agent in ("chembl_client", "fda_drugs_client", "nih_reporter_client",
                  "sec_edgar_client", "iuphar_client"):
        src = (PKG_ROOT / "agents" / "research" / f"{agent}.py").read_text()
        assert "from agents.research.resolved_names import" in src, (
            f"P1 trip-wire: {agent} must import the resolved_names helper"
        )
        assert "query_names(" in src, (
            f"P1 trip-wire: {agent} must use query_names() for raw->resolved fallback"
        )
    # ChEMBL max_phase coercion accepts phase 0 (preclinical) and rejects falsy-drop.
    chembl = (PKG_ROOT / "agents" / "research" / "chembl_client.py").read_text()
    assert "_coerce_phase" in chembl, (
        "P1 trip-wire: chembl_client must coerce max_phase via _coerce_phase "
        "(old falsy check dropped valid phase 0 and left drug_max_phase null)."
    )
    # Outcome consumer reads the real per-intervention molecules key.
    out_src = (PKG_ROOT / "agents" / "annotation" / "outcome.py").read_text()
    assert 'endswith("_molecules")' in out_src, (
        "P1 trip-wire: outcome ChEMBL consumer must iterate '*_molecules' keys, "
        "not the flat 'molecules' key that never existed."
    )
    print("  ✓ v42.9 P1: resolved-name propagation + max_phase capture wired")


def test_v42_9_sequence_resolved_lookup_and_fallback():
    """v42.9 (2026-05-20) P2: the sequence agent must consume P1's output.
    P1 made the research agents store sequence data under the resolved
    canonical name (chembl_erenumab_helm), but the sequence agent keyed its
    raw_data lookups on the raw trial code (chembl_'AMG 334'_helm) — a key
    mismatch P1 introduced. The sequence agent must expand its DB-lookup names
    with the Lever-4 resolved names. The LLM sequence fallback must also fire
    for peptide != 'false' (was 'true' only), since peptide=Unknown trials can
    still carry a sequence stated in the research text."""
    src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert "from agents.research.resolved_names import extract_interventions" in src, (
        "P2 trip-wire: sequence.py must import the resolved_names helper to "
        "expand DB-key lookups with Lever-4 resolved names."
    )
    assert "Resolved-name DB lookups added" in src, (
        "P2 trip-wire: sequence.py must append resolved names to the DB-lookup "
        "intervention list (otherwise P1's resolved-name DB hits are unreachable)."
    )
    assert 'peptide_val != "false"' in src, (
        "P2 trip-wire: LLM sequence fallback must fire for peptide != 'false' "
        "(widened from 'true'-only to also cover peptide=Unknown)."
    )
    print("  ✓ v42.9 P2: sequence resolved-name lookup + widened LLM fallback")


def test_v42_9_epitope_resolver():
    """v42.9 (2026-05-20) P2: epitope_resolver recovers tumor/viral vaccine
    epitopes by slicing the canonical UniProt sequence at the antigen residue
    range the protocol states (gp100:209-217, p53:264-272). It must (a) extract
    only antigen-adjacent colon/paren ranges of epitope length, (b) EXCLUDE
    peptide hormones whose numbering is peptide-relative (GLP-1(7-36) etc.), be
    registered + configured, and feed the sequence agent."""
    from agents.research.epitope_resolver import extract_epitope_specs, _is_hormone_antigen
    # Extraction: tumor antigens fire, hormones / decoys don't.
    assert extract_epitope_specs("gp100:209-217") == [("gp100", 209, 217)]
    assert extract_epitope_specs("p53 (264-272)") == [("p53", 264, 272)]
    assert extract_epitope_specs("patients aged 18-65 years") == [], (
        "epitope trip-wire: dose/age ranges must not be extracted"
    )
    assert extract_epitope_specs("GLP-1 (7-36)") == [], (
        "epitope trip-wire: peptide hormones use peptide-relative numbering and "
        "must be excluded (a UniProt-precursor slice would be wrong)"
    )
    assert _is_hormone_antigen("GLP-2") and _is_hormone_antigen("exendin")
    assert not _is_hormone_antigen("gp100") and not _is_hormone_antigen("p53")
    # Registered + configured.
    from agents.research import RESEARCH_AGENTS
    assert "epitope_resolver" in RESEARCH_AGENTS, "epitope_resolver not registered"
    # Sequence agent consumes it; orchestrator passes the protocol summary.
    seq_src = (PKG_ROOT / "agents" / "annotation" / "sequence.py").read_text()
    assert "epitope_resolver_sequences" in seq_src, (
        "epitope trip-wire: sequence agent must consume epitope_resolver_sequences"
    )
    orch_src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    assert "brief_summary" in orch_src and "detailed_description" in orch_src, (
        "epitope trip-wire: orchestrator must pass protocol summary/description "
        "in research metadata so the resolver can find antigen:position specs"
    )
    print("  ✓ v42.9 P2: epitope_resolver (antigen:pos → UniProt slice, hormones excluded)")


def test_v42_9_rff_tier0_whystopped():
    """v42.9 (2026-05-20) P2: reason_for_failure must classify SPECIFIC-cause
    whyStopped deterministically from the registry field. Slice analysis found
    terminated trials with whyStopped='Low enrollment rate' / 'Patient
    recruitment issues' being defaulted to 'Business Reason' because the LLM
    evidence builder never surfaced whyStopped (Pass 1 reported 'Not provided').
    The Tier-0 classifier reads whyStopped directly and maps recruitment / toxic
    / ineffective / covid causes; vague 'business/sponsor' is left to the LLM."""
    from agents.annotation.failure_reason import FailureReasonAgent as _F
    # Specific causes classify; vague business defers (returns "").
    assert _F._classify_whystopped_specific("Low enrollment rate") == "Recruitment issues"
    assert _F._classify_whystopped_specific("Patient recruitment issues") == "Recruitment issues"
    assert _F._classify_whystopped_specific("Stopped for unacceptable toxicity") == "Toxic/Unsafe"
    assert _F._classify_whystopped_specific("terminated for lack of efficacy") == "Ineffective for purpose"
    assert _F._classify_whystopped_specific("Sponsor decision") == "", (
        "vague business whyStopped must defer to the LLM, not classify deterministically"
    )
    assert _F._classify_whystopped_specific("Not due to any safety concerns") == "", (
        "negation filter must prevent 'safety' firing Toxic/Unsafe"
    )
    src = (PKG_ROOT / "agents" / "annotation" / "failure_reason.py").read_text()
    assert "_extract_status_and_whystopped" in src and "Tier-0 whyStopped" in src, (
        "P2 trip-wire: failure_reason must read whyStopped from raw_data and apply "
        "the Tier-0 classifier before the LLM passes."
    )
    print("  ✓ v42.9 P2: RfF Tier-0 specific-cause whyStopped classifier")


def test_audit_trail_wired():
    """Audit trail (2026-05-20): every annotation LLM call's input (prompt +
    system) and raw output must be captured and written to a per-trial
    Markdown document. Verifies the recorder exists, the ollama chokepoint
    feeds it, the orchestrator binds trial/field context and flushes the doc,
    and the persistence layer writes <nct>.audit.md."""
    at_path = PKG_ROOT / "app" / "services" / "audit_trail.py"
    assert at_path.exists(), "audit trip-wire: app/services/audit_trail.py missing"
    at_src = at_path.read_text()
    for fn in ("class AuditRecorder", "def record(", "def render_markdown(",
               "def set_context(", "def pop_calls("):
        assert fn in at_src, f"audit trip-wire: {fn!r} missing from audit_trail.py"
    # Chokepoint feeds the recorder.
    oc_src = (PKG_ROOT / "app" / "services" / "ollama_client.py").read_text()
    assert "audit_recorder.record(" in oc_src, (
        "audit trip-wire: ollama_client.generate must call audit_recorder.record"
    )
    # Orchestrator binds context + flushes the document.
    orch_src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    assert "audit_recorder.set_context(" in orch_src and "save_audit(" in orch_src, (
        "audit trip-wire: orchestrator must set audit context and call save_audit"
    )
    # Persistence writes the markdown file.
    pers_src = (PKG_ROOT / "app" / "services" / "persistence_service.py").read_text()
    assert "def save_audit(" in pers_src and ".audit.md" in pers_src, (
        "audit trip-wire: persistence_service must write <nct>.audit.md"
    )
    print("  ✓ audit-trail: per-trial LLM input/output document wired")


def test_dbaasp_word_boundary_preserved():
    """v25 DBAASP word-boundary fix: 'NS' (normal saline) and short
    drug-name prefixes were matching DBAASP entries by substring, not
    word boundary. The pregate even matched 'Curodont' as a peptide.
    Word-boundary matching is the standing rule.
    """
    p = PKG_ROOT / "agents" / "research" / "dbaasp_client.py"
    if not p.exists():
        print("  ⚠ skipped (dbaasp_client.py absent)")
        return
    src = p.read_text()
    # Some form of \b boundary check or len(name) > N guard must exist
    has_guard = any(p in src for p in (r"\b", "word_boundary", "len(name) >", "len(intervention) >"))
    assert has_guard, (
        "DBAASP trip-wire: word-boundary or minimum-length guard missing — "
        "two-letter substrings will spuriously match peptide entries."
    )
    print("  ✓ DBAASP: word-boundary / length guard present")


def main() -> int:
    print("v42 trip-wire regression tests")
    print("-" * 60)
    tests = [
        test_v42_6_14_no_bare_approved_in_strong_efficacy,
        test_v42_6_18_known_sequences_has_glp1,
        test_v42_7_3_per_field_db_keywords,
        test_v42_7_4_two_tier_pub_agents,
        test_v42_7_5_boot_commit_captured_at_module_load,
        test_v42_7_6_nih_reporter_uses_advanced_text_search,
        test_v42_7_7_vaccine_immunogenicity_override,
        test_v42_7_8_fda_drugs_signal_wired,
        test_v42_7_9_fda_query_includes_products_fields,
        test_v42_7_10_intervention_type_preserved,
        test_v42_7_12_indication_match_and_registered_pubs,
        test_v42_7_14_failed_override_status_gated,
        test_v42_7_15_negative_keyword_tightened,
        test_v42_7_16_sequence_canonicaliser_strips_chemistry_suffix,
        test_v42_7_18_known_sequences_expanded,
        test_v42_7_19_delivery_ambiguous_keyword_relevance_gate,
        test_v42_7_20_pub_classifier_default_general,
        test_v42_7_21_known_sequences_expanded,
        test_v42_7_22_cgrp_disambiguation,
        test_v42_7_23_radiotracer_isotope_class_split,
        test_v42_7_24_reasoning_caps_raised,
        test_v42_7_24_failure_reason_early_return_gated,
        test_v42_8_1_failure_reason_emission_gate,
        test_v42_8_2_strong_failure_override,
        test_v42_8_3_pub_trial_matcher,
        test_v42_8_4_drug_code_resolver,
        test_v42_8_5_press_release_agent,
        test_v42_10_peptide_anchor,
        test_v42_9_completed_not_failed_override,
        test_v42_9_resolved_name_propagation,
        test_v42_9_sequence_resolved_lookup_and_fallback,
        test_v42_9_epitope_resolver,
        test_v42_9_rff_tier0_whystopped,
        test_audit_trail_wired,
        test_dbaasp_word_boundary_preserved,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"  ✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            import traceback as tb
            print(f"  ✗ {t.__name__}: {type(e).__name__}: {e}")
            tb.print_exc()
            failed += 1
    print("-" * 60)
    print(f"{'FAIL' if failed else 'OK'}: {len(tests) - failed}/{len(tests)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
