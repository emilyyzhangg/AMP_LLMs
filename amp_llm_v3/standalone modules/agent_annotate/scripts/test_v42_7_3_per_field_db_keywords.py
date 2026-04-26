#!/usr/bin/env python3
"""
Tests for v42.7.3 per-field _DB_KEYWORDS (2026-04-26).

Job #83 commit_accuracy report showed db_confirmed at 71% for classification
but llm at 100%, because ChEMBL/UniProt hits were triggering db_confirmed
on AMP classification — a non-AMP-specific signal. Each field now has its
own list of authoritative DBs:
  classification — DRAMP/DBAASP/APD only (AMP-specific)
  peptide+sequence — broad structural DBs (UniProt/DRAMP/DBAASP/APD/ChEMBL/
                     RCSB/EBI/PDBe)
  outcome+RfF — regulatory (FDA Drugs, SEC EDGAR)
"""
from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PKG_ROOT = THIS_DIR.parent
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))


def test_orchestrator_has_per_field_db_keyword_dict():
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    assert "_DB_KEYWORDS_BY_FIELD" in src, "_DB_KEYWORDS_BY_FIELD dict missing"
    assert "_DB_KEYWORDS_DEFAULT" in src, "_DB_KEYWORDS_DEFAULT fallback missing"
    print("  ✓ orchestrator defines _DB_KEYWORDS_BY_FIELD + default fallback")


def test_classification_keyword_set_is_amp_only():
    """For AMP/Other classification, only DRAMP/DBAASP/APD should be authoritative."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    # Find the classification entry
    import re
    m = re.search(
        r'"classification":\s*\(([^)]*)\)', src
    )
    assert m, "classification entry not found in _DB_KEYWORDS_BY_FIELD"
    entry = m.group(1).lower()
    # Must include AMP databases
    for amp_db in ("dramp", "dbaasp", "apd"):
        assert amp_db in entry, f"classification keyword set missing {amp_db}"
    # Must NOT include non-AMP databases
    for non_amp in ("uniprot", "chembl", "rcsb", "ebi_proteins", "pdbe",
                    "fda_drugs", "sec_edgar"):
        assert non_amp not in entry, (
            f"classification keyword set includes non-AMP DB: {non_amp}"
        )
    print("  ✓ classification _DB_KEYWORDS = (dramp, dbaasp, apd) — AMP-only")


def test_outcome_keyword_set_is_regulatory():
    """outcome should require fda_drugs/sec_edgar — non-AMP DBs don't tell us
    if a trial succeeded."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    import re
    m = re.search(r'"outcome":\s*\(([^)]*)\)', src)
    assert m
    entry = m.group(1).lower()
    for kw in ("fda_drugs", "sec_edgar"):
        assert kw in entry, f"outcome keyword set missing {kw}"
    # AMP DBs shouldn't grade outcome as db_confirmed
    for non_outcome in ("dramp", "dbaasp", "apd", "uniprot", "chembl"):
        assert non_outcome not in entry, (
            f"outcome should not have {non_outcome} as authoritative"
        )
    print("  ✓ outcome _DB_KEYWORDS = (fda_drugs, sec_edgar) — regulatory only")


def test_peptide_keeps_broad_structural_set():
    """peptide=True/False uses broad structural DBs — UniProt/DRAMP/DBAASP/
    APD/ChEMBL/RCSB/EBI/PDBe all confirm 'is a peptide.'"""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    import re
    m = re.search(r'"peptide":\s*\(([^)]*)\)', src)
    assert m
    entry = m.group(1).lower()
    for kw in ("uniprot", "dramp", "dbaasp", "apd", "chembl", "rcsb"):
        assert kw in entry, f"peptide keyword set missing {kw}"
    print("  ✓ peptide _DB_KEYWORDS = broad structural set")


def test_grader_uses_per_field_dict():
    """Source check: _grade pass uses _DB_KEYWORDS_BY_FIELD.get(field_name, ...)."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    assert "_DB_KEYWORDS_BY_FIELD.get(" in src, \
        "grader doesn't dispatch by field name"
    print("  ✓ grader dispatches keyword set by field_name")


def test_default_fallback_covers_all_fields():
    """The default tuple should include the union — used when field not in dict."""
    src = (PKG_ROOT / "app" / "services" / "orchestrator.py").read_text()
    import re
    m = re.search(
        r'_DB_KEYWORDS_DEFAULT\s*=\s*\(([^)]*)\)', src
    )
    assert m
    entry = m.group(1).lower()
    # Default should be the broad union for backward compat
    for kw in ("uniprot", "dramp", "dbaasp", "chembl", "apd", "rcsb",
               "sec_edgar", "fda_drugs"):
        assert kw in entry, f"default missing {kw}"
    print("  ✓ _DB_KEYWORDS_DEFAULT covers broad union (backward compat)")


def main() -> int:
    print("v42.7.3 per-field _DB_KEYWORDS tests")
    print("-" * 60)
    tests = [
        test_orchestrator_has_per_field_db_keyword_dict,
        test_classification_keyword_set_is_amp_only,
        test_outcome_keyword_set_is_regulatory,
        test_peptide_keeps_broad_structural_set,
        test_grader_uses_per_field_dict,
        test_default_fallback_covers_all_fields,
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
