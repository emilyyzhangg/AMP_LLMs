"""
Evidence-based peptide signals + deterministic anchors.

Shared by the PeptideAgent and the eval harness so they decide identically.

The design (validated on cached research, scripts/eval_peptide.py):
  - High-precision DETERMINISTIC anchors settle the confident cases:
      * antibody / cell- or gene-therapy (by intervention NAME) -> "False"
      * INN peptide stem, DB/structural confirmation, explicit AA sequence -> "True"
  - The ambiguous middle (the noisy "the word 'peptide' appears in the prose"
    band — present in 42% of NON-peptide protocols too) returns None and is left
    to the LLM, which can read whether the peptide IS the drug vs incidental
    ("cells pulsed WITH peptides", "C-peptide levels", "T-cell response").

Anchors are deliberately keyed on the intervention NAME, not the description —
cancer peptide vaccines routinely describe inducing "T-cell responses," and
matching that prose wrongly excludes them.
"""

from __future__ import annotations

import re
from typing import Optional

# WHO INN stems that mark peptide drugs. -tide is the general peptide stem.
_PEPTIDE_INN_STEMS = ("tide", "relin", "relix", "pressin", "actide", "tocin",
                      "gastrin", "cosatide")
# Antibody / Fc-fusion stems (large proteins — not peptides).
_ANTIBODY_STEMS = ("mab", "cept")

_CELL_GENE_RE = re.compile(
    r"chimeric antigen receptor|car[\s-]?t\b|\bcar[\s-]?t[\s-]?cell|car-dc|"
    r"dendritic cell|stem cell|t[\s-]?lymphocyte|tumor[\s-]?infiltrating|\btil\b|"
    r"\bnk cell|natural killer cell|gene therapy|oncolytic|"
    r"hematopoietic|cell transplant|cell infusion|cell injection", re.I)
_PEPTIDE_NAME_RE = re.compile(r"\bpeptid|\bpolypeptid|oligopeptide", re.I)
_COMPOSITION_RE = re.compile(
    r"amino acid sequence|\b\d{1,3}\s*(?:amino acid|residue|aa)\b|\b\d{1,3}-mer\b",
    re.I)
_AA_SEQ_RE = re.compile(r"\b[ACDEFGHIKLMNPQRSTVWY]{8,}\b")
_PLACEBO = ("placebo", "saline", "vehicle", "normal saline", "standard of care",
            "best supportive care", "observation")


def _norm(s):
    return (s or "").strip().lower()


def _last_token(name):
    toks = [t for t in re.split(r"[\s\-/()]+", (name or "").lower()) if t]
    return toks[-1] if toks else ""


def extract_peptide_signals(research_results, metadata: Optional[dict] = None) -> dict:
    """Pull peptide-relevant signals from research + metadata.

    Accepts ResearchResult objects (agent) or dicts (harness).
    """
    def g(r, attr):
        return getattr(r, attr, None) if not isinstance(r, dict) else r.get(attr)

    names: list[str] = []
    resolved: list[str] = []
    text_parts: list[str] = []
    db_peptide = False

    # intervention names/types/resolved can also arrive via metadata
    if metadata:
        for iv in (metadata.get("interventions") or []):
            if isinstance(iv, dict):
                if iv.get("name"):
                    names.append(iv["name"])
                resolved.extend(str(x) for x in (iv.get("resolved") or []))
            elif isinstance(iv, str):
                names.append(iv)
        for k in ("title", "brief_summary", "detailed_description"):
            if metadata.get(k):
                text_parts.append(str(metadata[k]))

    for r in research_results or []:
        an = g(r, "agent_name")
        rd = g(r, "raw_data") or {}
        cits = g(r, "citations") or []
        if an == "clinical_protocol" and isinstance(rd, dict):
            ps = rd.get("protocol_section") or rd.get("protocolSection") or {}
            dm = ps.get("descriptionModule", {})
            text_parts.append(dm.get("briefSummary", "") or "")
            text_parts.append(dm.get("detailedDescription", "") or "")
            for iv in ps.get("armsInterventionsModule", {}).get("interventions", []):
                nm = iv.get("name", "")
                if nm and nm not in names:
                    names.append(nm)
                text_parts.append(iv.get("description", "") or "")
        elif an == "drug_code_resolver" and isinstance(rd, dict):
            for k, v in rd.items():
                if "resolved" in k.lower() and v:
                    resolved.append(str(v))
        elif an in ("dbaasp", "apd") and isinstance(rd, dict):
            if any("sequence" in k.lower() and rd[k] for k in rd):
                db_peptide = True
        elif an == "peptide_identity" and cits:
            db_peptide = True
        elif an == "chembl" and isinstance(rd, dict):
            for k, v in rd.items():
                if k.endswith("_molecules") and isinstance(v, list):
                    for m in v:
                        if isinstance(m, dict) and (
                            m.get("helm_notation")
                            or _norm(m.get("mol_type")) in ("protein", "peptide")
                        ):
                            db_peptide = True
                if "helm" in k.lower() and v:
                    db_peptide = True

    text = " ".join(p for p in text_parts if p)
    name_blob = " ".join(names + resolved).lower()
    return {
        "names": names,
        "resolved": resolved,
        # INN stem / antibody stem: scan ALL tokens of every name (drug names are
        # often buried in phrases like "Cohort A: Ponsegromab low dose").
        "inn": any(
            len(tok) >= 6 and tok.endswith(_PEPTIDE_INN_STEMS)
            for n in names + resolved
            for tok in re.split(r"[\s\-/()]+", n.lower()) if tok
        ),
        "antibody": any(
            len(tok) >= 5 and tok.endswith(_ANTIBODY_STEMS)
            for n in names for tok in re.split(r"[\s\-/()]+", n.lower()) if tok
        ) or "monoclonal antibody" in name_blob,
        "cell_gene": bool(_CELL_GENE_RE.search(name_blob)),
        "db_peptide": db_peptide,
        "aa_seq": bool(_AA_SEQ_RE.search(text)),
        # "the drug name itself says peptide/polypeptide" — strong identity cue,
        # distinct from the noisy "peptide appears anywhere in prose".
        "peptide_in_name": bool(_PEPTIDE_NAME_RE.search(name_blob)),
        "peptide_word": bool(_PEPTIDE_NAME_RE.search(name_blob))
        or ("peptid" in text.lower())
        or bool(_COMPOSITION_RE.search(text)),
        # count of non-placebo drug interventions — a multi-drug combo means an
        # antibody arm may just be a partner, not the experimental subject.
        "n_real_drugs": sum(
            1 for n in names if n and not any(p in n.lower() for p in _PLACEBO)
        ),
    }


def peptide_anchor(signals: dict) -> Optional[str]:
    """Deterministic high-confidence verdict, or None to defer to the LLM.

    Returns "True", "False", or None (ambiguous).
    """
    peptide_signal = (signals.get("inn") or signals.get("db_peptide")
                      or signals.get("aa_seq") or signals.get("peptide_in_name"))

    # A peptide signal from ANY arm means a peptide is present as an intervention.
    # The exclusions must not force "False" then — peptide-vaccine + checkpoint-mAb
    # combos (pembrolizumab/nivolumab end -mab) and peptide + cell arms are common.
    if peptide_signal:
        # peptide AND cell-context is the genuinely ambiguous edge
        # ("MUC1 peptide vaccine" = peptide drug, True; "dendritic cells loaded
        # with peptides" = cell is the drug, False) — let the LLM read it.
        if signals.get("cell_gene"):
            return None
        return "True"
    # No peptide signal at all. A pure antibody / cell / gene therapy is "False",
    # but in a multi-drug combo the antibody/cell arm may be a partner while the
    # (unrecognized) experimental drug is a peptide — defer those to the LLM.
    if signals.get("antibody") or signals.get("cell_gene"):
        if signals.get("n_real_drugs", 0) > 1:
            return None
        return "False"
    # Nothing decisive -> LLM.
    return None
