#!/usr/bin/env python3
"""
Unit tests for B2 (classification_atomic) and B3 (reason_for_failure_atomic)
aggregators + whyStopped parser. Pure deterministic — no LLM calls.

Usage:
    cd <agent_annotate_dir>
    python3 scripts/test_atomic_b2_b3.py
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from agents.annotation.classification_atomic import (
    RegistryHits, AtomicAnswers as ClsAns, aggregate as cls_agg,
)
from agents.annotation.failure_reason_atomic import (
    AtomicAnswers as FrAns, aggregate as fr_agg, _parse_why_stopped,
)


def _check(label: str, got, want) -> bool:
    ok = got == want
    status = "PASS" if ok else "FAIL"
    print(f"  {status}  {label}: got={got!r} want={want!r}")
    return ok


def test_cls():
    print("---- classification_atomic aggregator ----")
    passes = 0
    total = 0

    r = cls_agg(RegistryHits(dramp=["DRAMP0001"]), ClsAns())
    total += 1; passes += _check("R1 DRAMP hit", (r.value, r.rule_name, r.confidence), ("AMP", "R1", 0.95))

    r = cls_agg(RegistryHits(apd=["AP00001"]), ClsAns())
    total += 1; passes += _check("R1 APD hit", (r.value, r.rule_name), ("AMP", "R1"))

    r = cls_agg(
        RegistryHits(),
        ClsAns(q1_has_peptide_sequence="YES", q2_antimicrobial_mechanism="YES", q3_infection_indication="YES"),
    )
    total += 1; passes += _check("R2 3/3 YES", (r.value, r.rule_name), ("AMP", "R2"))

    r = cls_agg(
        RegistryHits(),
        ClsAns(q1_has_peptide_sequence="YES", q2_antimicrobial_mechanism="YES", q3_infection_indication="UNCLEAR"),
    )
    total += 1; passes += _check("R3 2 YES, 0 NO", (r.value, r.rule_name), ("AMP", "R3"))

    r = cls_agg(
        RegistryHits(),
        ClsAns(q1_has_peptide_sequence="NO", q2_antimicrobial_mechanism="NO", q3_infection_indication="NO"),
    )
    total += 1; passes += _check("R4 3/3 NO", (r.value, r.rule_name), ("Other", "R4"))

    r = cls_agg(
        RegistryHits(),
        ClsAns(q1_has_peptide_sequence="NO", q2_antimicrobial_mechanism="NO", q3_infection_indication="UNCLEAR"),
    )
    total += 1; passes += _check("R5 2 NO, 0 YES", (r.value, r.rule_name), ("Other", "R5"))

    r = cls_agg(
        RegistryHits(),
        ClsAns(q1_has_peptide_sequence="YES", q2_antimicrobial_mechanism="NO"),
    )
    total += 1; passes += _check("R6 mixed (1 YES, 1 NO)", (r.value, r.rule_name), ("Other", "R6"))

    r = cls_agg(RegistryHits(), ClsAns())
    total += 1; passes += _check("R6 all UNCLEAR", (r.value, r.rule_name), ("Other", "R6"))

    return passes, total


def test_fr():
    print("---- failure_reason_atomic aggregator ----")
    passes = 0
    total = 0

    # whyStopped parser
    total += 1; passes += _check("covid parser",
        _parse_why_stopped("Trial halted due to the COVID-19 pandemic."), "Due to covid")
    total += 1; passes += _check("toxicity parser",
        _parse_why_stopped("terminated due to adverse events"), "Toxic/Unsafe")
    total += 1; passes += _check("recruitment parser",
        _parse_why_stopped("slow accrual of patients"), "Recruitment issues")
    total += 1; passes += _check("efficacy parser",
        _parse_why_stopped("futility analysis showed no benefit"), "Ineffective for purpose")
    total += 1; passes += _check("business parser",
        _parse_why_stopped("sponsor's strategic portfolio decision"), "Business Reason")
    total += 1; passes += _check("empty parser", _parse_why_stopped(""), None)
    total += 1; passes += _check("no-match parser",
        _parse_why_stopped("the trial ended as planned"), None)

    # Priority ordering — safety wins over efficacy
    r = fr_agg("", None, FrAns(q1_safety="YES", q2_efficacy_failure="YES"))
    total += 1; passes += _check("priority safety > efficacy", (r.value, r.rule_name), ("Toxic/Unsafe", "R2"))

    # Priority ordering — efficacy wins over covid
    r = fr_agg("", None, FrAns(q2_efficacy_failure="YES", q3_covid="YES"))
    total += 1; passes += _check("priority efficacy > covid", (r.value, r.rule_name), ("Ineffective for purpose", "R3"))

    # COVID alone
    r = fr_agg("", None, FrAns(q3_covid="YES"))
    total += 1; passes += _check("covid alone", (r.value, r.rule_name), ("Due to covid", "R4"))

    # Recruitment alone
    r = fr_agg("", None, FrAns(q4_recruitment="YES"))
    total += 1; passes += _check("recruitment alone", (r.value, r.rule_name), ("Recruitment issues", "R5"))

    # Business alone
    r = fr_agg("", None, FrAns(q5_business="YES"))
    total += 1; passes += _check("business alone", (r.value, r.rule_name), ("Business Reason", "R6"))

    # Default empty
    r = fr_agg("", None, FrAns())
    total += 1; passes += _check("R7 default empty", (r.value, r.rule_name), ("", "R7"))

    # Tier 0 short-circuits atomic priority
    r = fr_agg("stopped due to toxicity", "Toxic/Unsafe",
               FrAns(q2_efficacy_failure="YES"))
    total += 1; passes += _check("Tier 0 overrides atomic", (r.value, r.rule_name), ("Toxic/Unsafe", "R1"))

    return passes, total


def main():
    total_pass = total_n = 0
    for suite in (test_cls, test_fr):
        p, n = suite()
        total_pass += p
        total_n += n
        print()
    print("=" * 50)
    print(f" {total_pass}/{total_n} tests passed")
    return 0 if total_pass == total_n else 1


if __name__ == "__main__":
    sys.exit(main())
