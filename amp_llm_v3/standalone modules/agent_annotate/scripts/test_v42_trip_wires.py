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
    idx = src.find("v42.7.14")
    assert idx > 0, "v42.7.14 marker missing in outcome.py"
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


def test_v42_7_23_openfda_route_filter():
    """v42.7.23 (2026-04-29): when the protocol intervention description
    explicitly states a route, the OpenFDA structured-route path
    (delivery_mode.py:357-377) restricts results to that set —
    skipping spurious formulations of the same active ingredient.
    Job #99 had 2× and Job #100 milestone had 5× spurious-oral cases
    (NCT01704781/NCT03018665/NCT05096481/NCT05218915/NCT05995704)
    where OpenFDA returned both Ozempic-style SC and Rybelsus-style
    oral routes for the same generic_name. Removing this gate
    recreates the regression.
    """
    src = (PKG_ROOT / "agents" / "annotation" / "delivery_mode.py").read_text()
    assert "v42.7.23" in src, "v42.7.23 marker missing in delivery_mode.py"
    # The fix spans ~60 lines (intervention_descs scan + OpenFDA gate);
    # check the file as a whole rather than a narrow window.
    assert "protocol_routes_explicit" in src, \
        "v42.7.23 trip-wire: must build protocol_routes_explicit set from intervention_descs"
    assert "delivery_value not in protocol_routes_explicit" in src, \
        "v42.7.23 trip-wire: must skip OpenFDA routes not in protocol_routes_explicit"
    # Sentinel for the OpenFDA-path location (so future refactors that
    # remove the gate from this path are caught).
    assert "openfda_results" in src and "protocol_routes_explicit" in src, \
        "v42.7.23 trip-wire: gate must be in the OpenFDA structured-route path"
    print("  ✓ v42.7.23: OpenFDA structured-route path gated on protocol_routes_explicit")


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
        test_v42_7_23_openfda_route_filter,
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
