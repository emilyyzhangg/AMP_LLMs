#!/usr/bin/env python3
"""
Synthetic unit tests for the Tier 3 Outcome Aggregator (v42, Phase 3).

Builds RegistrySignals + PubCandidate/PubVerdict fixtures covering each of the
R1–R8 rule paths plus the TIER0 short-circuit. No network, no LLM — pure logic
checks. Returns non-zero on any failure.

Usage:
    cd <agent_annotate_dir>
    python3 scripts/test_aggregator.py
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.annotation.outcome_aggregator import (  # noqa: E402
    aggregate,
    OUTCOME_ACTIVE,
    OUTCOME_FAILED,
    OUTCOME_POSITIVE,
    OUTCOME_TERMINATED,
    OUTCOME_UNKNOWN,
)
from agents.annotation.outcome_pub_assessor import (  # noqa: E402
    PubAnswers,
    PubVerdict,
)
from agents.annotation.outcome_pub_classifier import PubCandidate  # noqa: E402
from agents.annotation.outcome_registry_signals import (  # noqa: E402
    PrimaryEndpoint,
    RegistrySignals,
)


# ---- Fixture helpers ----------------------------------------------------- #

def make_pub(
    pmid: str = "1",
    title: str = "",
    snippet: str = "",
    source: str = "pubmed",
) -> PubCandidate:
    return PubCandidate(
        pmid=f"PMID:{pmid}" if pmid else "",
        pmid_bare=pmid,
        title=title,
        snippet=snippet,
        source=source,
    )


def make_verdict(
    pmid: str = "1",
    verdict: str = "POSITIVE",
    specificity: str = "trial_specific",
    q2: str = "YES",
    q3: str = "NA",
    q4: str = "NA",
    q5: str = "UNCLEAR",
) -> PubVerdict:
    return PubVerdict(
        nct_id="NCT_TEST",
        pmid=f"PMID:{pmid}" if pmid else "",
        source="pubmed",
        specificity=specificity,
        answers=PubAnswers(
            q1_reports_results="YES",
            q2_primary_met=q2,
            q3_efficacy=q3,
            q4_failure=q4,
            q5_advanced=q5,
        ),
        verdict=verdict,
    )


def make_signals(
    status: str = "",
    has_results: bool = False,
    phase: str = "",
    days_since: int = 0,
    stale: bool = False,
    drug_max_phase: int | None = None,
    endpoints: list[PrimaryEndpoint] | None = None,
) -> RegistrySignals:
    return RegistrySignals(
        registry_status=status,
        status_normalized=status,
        has_results=has_results if status else None,
        phase=phase,
        phase_normalized=phase,
        days_since_completion=days_since,
        stale_status=stale,
        drug_max_phase=drug_max_phase,
        primary_endpoints=endpoints or [],
    )


# ---- Cases ---------------------------------------------------------------- #

FAIL: list[str] = []
PASS = 0


def check(label: str, actual_rule: str, expected_rule: str,
          actual_value: str, expected_value: str) -> None:
    global PASS
    if actual_rule == expected_rule and actual_value == expected_value:
        PASS += 1
        print(f"  PASS  {label}: {actual_rule}={actual_value}")
    else:
        msg = (
            f"  FAIL  {label}: got rule={actual_rule} value={actual_value!r} "
            f"expected rule={expected_rule} value={expected_value!r}"
        )
        FAIL.append(msg)
        print(msg)


# TIER0 short-circuit
def test_tier0_shortcircuit():
    print("\n[TIER0] pre-label bypasses rules")
    sig = make_signals(status="RECRUITING")
    r = aggregate(sig, [], tier0_label="Recruiting")
    check("tier0-recruiting", r.rule_name, "TIER0", r.value, "Recruiting")


# R1: any POSITIVE + 0 FAILED → Positive
def test_r1_positive_alone():
    print("\n[R1] POSITIVE pub, 0 FAILED")
    sig = make_signals(status="COMPLETED", has_results=True)
    pubs = [
        (make_pub("101"), make_verdict("101", "POSITIVE", "trial_specific")),
    ]
    r = aggregate(sig, pubs)
    check("r1-single-pos", r.rule_name, "R1", r.value, OUTCOME_POSITIVE)


def test_r1_two_positives():
    print("\n[R1] multiple POSITIVE, no FAILED")
    sig = make_signals(status="COMPLETED", has_results=True)
    pubs = [
        (make_pub("101"), make_verdict("101", "POSITIVE", "trial_specific")),
        (make_pub("102"), make_verdict("102", "POSITIVE", "ambiguous", q3="YES")),
    ]
    r = aggregate(sig, pubs)
    check("r1-two-pos", r.rule_name, "R1", r.value, OUTCOME_POSITIVE)


def test_r1_indeterminates_dont_block():
    print("\n[R1] INDETERMINATE pubs don't count")
    sig = make_signals(status="COMPLETED")
    pubs = [
        (make_pub("101"), make_verdict("101", "POSITIVE", "trial_specific")),
        (make_pub("102"), make_verdict("102", "INDETERMINATE", "ambiguous", q2="NA")),
    ]
    r = aggregate(sig, pubs)
    check("r1-with-indeterminate", r.rule_name, "R1", r.value, OUTCOME_POSITIVE)


# R2: any FAILED + 0 POSITIVE → Failed
def test_r2_failed_alone():
    print("\n[R2] FAILED pub, 0 POSITIVE")
    sig = make_signals(status="COMPLETED", has_results=True)
    pubs = [
        (make_pub("201"), make_verdict("201", "FAILED", "trial_specific", q4="YES")),
    ]
    r = aggregate(sig, pubs)
    check("r2-single-fail", r.rule_name, "R2", r.value, OUTCOME_FAILED)


# R3: mixed → most-recent wins
def test_r3_mixed_most_recent_positive():
    print("\n[R3] mixed; most-recent (2021) POSITIVE wins over older FAILED (2015)")
    sig = make_signals(status="COMPLETED", has_results=True)
    pubs = [
        (make_pub("301", snippet="Preliminary failure reported 2015"),
         make_verdict("301", "FAILED", "trial_specific", q4="YES")),
        (make_pub("302", snippet="Updated analysis 2021 showing efficacy"),
         make_verdict("302", "POSITIVE", "trial_specific")),
    ]
    r = aggregate(sig, pubs)
    check("r3-newer-pos", r.rule_name, "R3", r.value, OUTCOME_POSITIVE)


def test_r3_mixed_most_recent_failed():
    print("\n[R3] mixed; most-recent (2023) FAILED wins over older POSITIVE (2018)")
    sig = make_signals(status="COMPLETED", has_results=True)
    pubs = [
        (make_pub("303", snippet="Promising results 2018"),
         make_verdict("303", "POSITIVE", "trial_specific")),
        (make_pub("304", snippet="Final analysis 2023: trial failed primary endpoint"),
         make_verdict("304", "FAILED", "trial_specific", q4="YES")),
    ]
    r = aggregate(sig, pubs)
    check("r3-newer-fail", r.rule_name, "R3", r.value, OUTCOME_FAILED)


# R4: no TS + COMPLETED + drug_max_phase ≥ 3 → Positive
def test_r4_drug_advanced():
    print("\n[R4] no trial-specific pubs, COMPLETED, drug at Phase 3")
    sig = make_signals(status="COMPLETED", has_results=False, drug_max_phase=3)
    pubs = [
        (make_pub("401"), make_verdict("401", "INDETERMINATE", "general")),
    ]
    r = aggregate(sig, pubs)
    check("r4-max-phase-3", r.rule_name, "R4", r.value, OUTCOME_POSITIVE)


def test_r4_drug_approved():
    print("\n[R4] no TS, COMPLETED, drug approved (max_phase=4)")
    sig = make_signals(status="COMPLETED", drug_max_phase=4)
    r = aggregate(sig, [])
    check("r4-max-phase-4", r.rule_name, "R4", r.value, OUTCOME_POSITIVE)


# R5: no TS + COMPLETED + PHASE1 + ≥1 pub → Positive
def test_r5_phase1_completed_with_pubs():
    print("\n[R5] no TS pubs, COMPLETED, PHASE1, 1 general pub exists")
    sig = make_signals(status="COMPLETED", phase="PHASE1", drug_max_phase=1)
    pubs = [
        (make_pub("501"), make_verdict("501", "INDETERMINATE", "general", q2="NA")),
    ]
    r = aggregate(sig, pubs)
    check("r5-phase1-with-pub", r.rule_name, "R5", r.value, OUTCOME_POSITIVE)


def test_r5_no_pubs_blocks():
    print("\n[R5→R8] PHASE1 COMPLETED but no pubs at all → Unknown (R8)")
    sig = make_signals(status="COMPLETED", phase="PHASE1")
    r = aggregate(sig, [])
    check("r5-blocked-nopubs", r.rule_name, "R8", r.value, OUTCOME_UNKNOWN)


# R6: ACTIVE_NOT_RECRUITING, not stale
def test_r6_active():
    print("\n[R6] ACTIVE_NOT_RECRUITING, recent completion")
    sig = make_signals(status="ACTIVE_NOT_RECRUITING", days_since=30, stale=False)
    r = aggregate(sig, [])
    check("r6-active", r.rule_name, "R6", r.value, OUTCOME_ACTIVE)


def test_r6_stale_falls_through():
    print("\n[R6→R8] ACTIVE_NOT_RECRUITING but stale → R8 Unknown")
    sig = make_signals(status="ACTIVE_NOT_RECRUITING", days_since=400, stale=True)
    r = aggregate(sig, [])
    check("r6-stale-falls-thru", r.rule_name, "R8", r.value, OUTCOME_UNKNOWN)


# R7: TERMINATED + no POSITIVE
def test_r7_terminated():
    print("\n[R7] TERMINATED, no POSITIVE pubs")
    sig = make_signals(status="TERMINATED")
    pubs = [
        (make_pub("701"), make_verdict("701", "FAILED", "trial_specific", q4="YES")),
    ]
    # FAILED alone would fire R2 first — need to use only INDETERMINATE pubs
    # or empty to exercise R7. Let's test both the "pure" R7 case and the
    # "FAILED falls to R2 before R7" behavior.
    r = aggregate(sig, [])
    check("r7-terminated-nopos", r.rule_name, "R7", r.value, OUTCOME_TERMINATED)


def test_r7_precedence_over_r2():
    # Design: FAILED pub fires R2 first (explicit atomic evidence wins over
    # registry status). So TERMINATED + FAILED pub should go to R2, NOT R7.
    print("\n[R2 before R7] TERMINATED + FAILED pub → R2 Failed (atomic evidence wins)")
    sig = make_signals(status="TERMINATED")
    pubs = [
        (make_pub("702"), make_verdict("702", "FAILED", "trial_specific", q4="YES")),
    ]
    r = aggregate(sig, pubs)
    check("r2-before-r7", r.rule_name, "R2", r.value, OUTCOME_FAILED)


# R8: fall-through → Unknown
def test_r8_unknown_default():
    print("\n[R8] no signals at all")
    r = aggregate(make_signals(), [])
    check("r8-empty", r.rule_name, "R8", r.value, OUTCOME_UNKNOWN)


def test_r8_completed_no_results_no_drug_signal():
    print("\n[R8] COMPLETED but no pubs, no hasResults, no drug advancement")
    sig = make_signals(status="COMPLETED", has_results=False, phase="PHASE2", drug_max_phase=2)
    r = aggregate(sig, [])
    check("r8-completed-noinfo", r.rule_name, "R8", r.value, OUTCOME_UNKNOWN)


# Confidence sanity
def test_confidence_ranges():
    print("\n[confidence] TIER0 > R1/R2/R6/R7 > R3/R4 > R5 > R8")
    r_tier0 = aggregate(make_signals(status="RECRUITING"), [], tier0_label="Recruiting")
    r_r1 = aggregate(
        make_signals(status="COMPLETED"),
        [(make_pub("1"), make_verdict("1", "POSITIVE"))],
    )
    r_r8 = aggregate(make_signals(), [])
    ok = r_tier0.confidence > r_r1.confidence > r_r8.confidence
    if ok:
        print(f"  PASS  confidence ordering: "
              f"{r_tier0.confidence} > {r_r1.confidence} > {r_r8.confidence}")
        global PASS
        PASS += 1
    else:
        FAIL.append("confidence ordering broken")
        print("  FAIL  confidence ordering")


# ---- Runner -------------------------------------------------------------- #

def main() -> int:
    tests = [
        test_tier0_shortcircuit,
        test_r1_positive_alone,
        test_r1_two_positives,
        test_r1_indeterminates_dont_block,
        test_r2_failed_alone,
        test_r3_mixed_most_recent_positive,
        test_r3_mixed_most_recent_failed,
        test_r4_drug_advanced,
        test_r4_drug_approved,
        test_r5_phase1_completed_with_pubs,
        test_r5_no_pubs_blocks,
        test_r6_active,
        test_r6_stale_falls_through,
        test_r7_terminated,
        test_r7_precedence_over_r2,
        test_r8_unknown_default,
        test_r8_completed_no_results_no_drug_signal,
        test_confidence_ranges,
    ]
    for t in tests:
        t()

    print(f"\n========= aggregator tests =========")
    print(f"  pass: {PASS}")
    print(f"  fail: {len(FAIL)}")
    for msg in FAIL:
        print(msg)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
