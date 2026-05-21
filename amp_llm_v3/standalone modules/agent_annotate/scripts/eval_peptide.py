#!/usr/bin/env python3
"""
Standalone peptide-definition evaluation harness.

Runs ONLY the peptide determination against CACHED research from a past job and
scores it against ground truth — instantly, with no LLM calls and no full
pipeline run. This lets us iterate the peptide *definition* (the deterministic
signals) and watch precision/recall move in seconds instead of hours.

Usage:
    python3 scripts/eval_peptide.py <research_job_id> [--errors]

The `classify_peptide(signals)` function below is the proposed evidence-based
definition. Edit it and re-run to gauge the effect. Once it's good, the same
logic moves into agents/annotation/peptide.py.
"""
import json
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GT_PATH = ROOT / "docs" / "human_ground_truth_train_df.csv"

# ---- INN nomenclature stems that mark peptide drugs (WHO INN scheme) ----
# -tide is the general peptide stem; the others are specific peptide families.
_PEPTIDE_INN_STEMS = ("tide", "relin", "relix", "pressin", "actide", "tocin",
                      "gastrin", "cosatide")
# Antibody / fusion-protein stems (NOT peptides — large proteins).
_ANTIBODY_STEMS = ("mab", "cept", "nacht")

# Cell/gene-therapy markers — matched against the INTERVENTION NAME only (not
# the prose, which routinely says "induces a T-cell response" for peptide
# vaccines). These describe the agent itself being cells/genes, not a peptide.
_CELL_GENE_RE = re.compile(
    r"chimeric antigen receptor|car[\s-]?t\b|\bcar[\s-]?t[\s-]?cell|"
    r"dendritic cell|stem cell|t[\s-]?lymphocyte|tumor[\s-]?infiltrating|\btil\b|"
    r"\bnk cell|natural killer cell|gene therapy|oncolytic|car-dc|"
    r"hematopoietic|cell transplant|cell infusion|cell injection", re.I)
# "this drug IS a peptide" — name says peptide/polypeptide, OR prose gives an
# explicit composition (amino-acid count / residue / N-mer).
_PEPTIDE_NAME_RE = re.compile(r"\bpeptid|\bpolypeptid|oligopeptide", re.I)
_COMPOSITION_RE = re.compile(
    r"amino acid sequence|\b\d{1,3}\s*(?:amino acid|residue|aa)\b|\b\d{1,3}-mer\b", re.I)
_AA_SEQ_RE = re.compile(r"\b[ACDEFGHIKLMNPQRSTVWY]{8,}\b")


def norm(s):
    return (s or "").strip().lower()


def consensus(a, b):
    a, b = norm(a), norm(b)
    if a and b:
        return a if a == b else None
    return a or b or None


def load_gt():
    gt = {}
    for r in csv.DictReader(GT_PATH.open()):
        nid = (r.get("nct_id") or "").strip().lower()
        if nid:
            gt[nid] = consensus(r.get("Peptide_ann1"), r.get("Peptide_ann2"))
    return gt


def extract_signals(res):
    """Pull peptide-relevant signals from a trial's cached research results."""
    s = {"names": [], "types": [], "text": "", "inn": False, "antibody": False,
         "cell_gene": False, "db_peptide": False, "peptide_word": False,
         "aa_seq": False, "resolved": []}
    text_parts = []
    for r in res:
        an = r.get("agent_name")
        rd = r.get("raw_data") or {}
        if an == "clinical_protocol":
            ps = rd.get("protocol_section") or rd.get("protocolSection") or {}
            dm = ps.get("descriptionModule", {})
            text_parts.append(dm.get("briefSummary", "") or "")
            text_parts.append(dm.get("detailedDescription", "") or "")
            for iv in ps.get("armsInterventionsModule", {}).get("interventions", []):
                nm = iv.get("name", "") or ""
                s["names"].append(nm)
                s["types"].append((iv.get("type") or "").upper())
                text_parts.append(nm)
                text_parts.append(iv.get("description", "") or "")
        elif an == "drug_code_resolver" and isinstance(rd, dict):
            for k, v in rd.items():
                if "resolved" in k.lower():
                    s["resolved"].append(str(v))
        elif an in ("dbaasp", "apd") and isinstance(rd, dict):
            if any(("sequence" in k.lower()) and rd[k] for k in rd):
                s["db_peptide"] = True
        elif an == "peptide_identity" and r.get("citations"):
            s["db_peptide"] = True
        elif an == "chembl" and isinstance(rd, dict):
            for k, v in rd.items():
                if k.endswith("_molecules") and isinstance(v, list):
                    for m in v:
                        if isinstance(m, dict):
                            mt = norm(m.get("mol_type"))
                            if m.get("helm_notation") or mt in ("protein", "peptide"):
                                s["db_peptide"] = True
                if "helm" in k.lower() and v:
                    s["db_peptide"] = True
        elif an in ("uniprot", "ebi_proteins") and isinstance(rd, dict):
            if any(rd.get(k) for k in rd if "uniprot" in k.lower() or "ebi" in k.lower()):
                # only a weak DB signal — proteins can be >100aa; keep separate
                pass
    s["text"] = " ".join(text_parts)
    # NAME blob = intervention names + resolved names. Exclusions and the
    # "drug-is-a-peptide" word match key on this, NOT the prose.
    name_blob = " ".join(s["names"] + s["resolved"]).lower()

    def has_inn_stem(name):
        for tok in re.split(r"[\s\-/()]+", name.lower()):
            if len(tok) >= 6 and any(tok.endswith(st) for st in _PEPTIDE_INN_STEMS):
                return True
        return False
    s["inn"] = any(has_inn_stem(n) for n in s["names"] + s["resolved"])
    s["antibody"] = any(
        re.split(r"[\s\-/()]+", n.lower())[-1].endswith(_ANTIBODY_STEMS)
        for n in s["names"] if n
    ) or "monoclonal antibody" in name_blob
    s["cell_gene"] = bool(_CELL_GENE_RE.search(name_blob)) or "GENETIC" in s["types"]
    # peptide-identity word in the NAME (high precision), or "peptid" anywhere in
    # prose (sensitive but noisy — this is the band an LLM must adjudicate), or an
    # explicit composition statement.
    s["peptide_word"] = bool(_PEPTIDE_NAME_RE.search(name_blob)) or \
        ("peptid" in s["text"].lower()) or bool(_COMPOSITION_RE.search(s["text"]))
    s["aa_seq"] = bool(_AA_SEQ_RE.search(s["text"]))
    return s


def classify_peptide(s) -> bool:
    """PROPOSED evidence-based peptide definition. Edit + re-run to tune."""
    # ---- Strong-NO exclusions (override supportive signals) ----
    if s["antibody"]:
        return False
    if s["cell_gene"]:
        return False
    # ---- Strong-YES (any one) ----
    if s["inn"]:                       # INN peptide stem (-tide, -relin, ...)
        return True
    if s["db_peptide"]:                # DBAASP/APD/ChEMBL-peptide/HELM/peptide_identity
        return True
    if s["aa_seq"]:                    # explicit amino-acid sequence in protocol
        return True
    # ---- Supportive (needs the word to describe the agent) ----
    if s["peptide_word"]:
        return True
    return False


def main():
    if len(sys.argv) < 2:
        print("usage: eval_peptide.py <research_job_id> [--errors]")
        sys.exit(1)
    job = sys.argv[1]
    show_errors = "--errors" in sys.argv
    rdir = ROOT / "results" / "research" / job
    gt = load_gt()
    tp = fp = fn = tn = 0
    errors = []
    for f in sorted(rdir.glob("*.json")):
        if f.name == "_meta.json":
            continue
        d = json.load(f.open())
        nid = (d.get("nct_id") or f.stem).lower()
        g = gt.get(nid)
        if g not in ("true", "false"):
            continue
        sig = extract_signals(d.get("results") or [])
        pred = classify_peptide(sig)
        gt_true = (g == "true")
        if pred and gt_true:
            tp += 1
        elif pred and not gt_true:
            fp += 1
            errors.append(("FP", nid, sig["names"][:2]))
        elif not pred and gt_true:
            fn += 1
            errors.append(("FN", nid, sig["names"][:2]))
        else:
            tn += 1
    n = tp + fp + fn + tn
    acc = (tp + tn) / max(n, 1)
    prec = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    print(f"job {job}: {n} peptide-GT trials")
    print(f"  accuracy : {tp+tn}/{n} = {acc*100:.1f}%")
    print(f"  precision: {prec*100:.1f}%  recall: {rec*100:.1f}%")
    print(f"  TP={tp} FP={fp} FN={fn} TN={tn}")
    if show_errors:
        for typ, nid, names in errors:
            print(f"  {typ} {nid}: {names}")


if __name__ == "__main__":
    main()
