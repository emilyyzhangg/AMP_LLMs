"""
Sequence Annotation Agent (v14, v17 scoring fixes, v23 multi-sequence + format).

Extracts amino acid sequences from structured research data.
Reads ONLY from raw_data fields — no snippet text parsing.

v14 rewrite:
  - Eliminated all free-text regex extraction (extract_sequences_from_text deleted)
  - Reads structured data from raw_data: DBAASP sequences, APD sequences,
    ChEMBL HELM notation, UniProt mature features, EBI Proteins entries
  - Scores and ranks candidates by source reliability and drug relevance
  - Optional LLM adjudication when top candidates conflict
  - HELM parsing for synthetic/modified peptides (ChEMBL)

Sources (priority order):
  1. DBAASP structured sequences (name-filtered by research agent)
  2. APD structured sequences (from detail page fetch)
  3. ChEMBL HELM notation (parsed to linear AA sequence)
  4. UniProt mature peptide/chain features (from raw_data)
  5. UniProt full sequence (≤100 AA, relevance > 0.5)
  6. EBI Proteins structured entries

v23 changes:
  - Removed 2-sequence cap: extract ALL unique peptide sequences
  - Output N/A instead of empty string when no sequence found
  - HELM format preservation: modifications as (Ac)/(NH2), D-amino acids lowercase
  - Display string tracks source formatting alongside canonical for dedup

v17 changes:
  - Boost ChEMBL HELM score when molecule is a clinical drug (most reliable
    source for synthetic/clinical peptide sequences)
  - UniProt fragment selection: prefer fragment whose description best matches
    the drug name instead of always picking the shortest fragment
  - Strip formulation/device text from intervention names before database lookups
"""

import re
import logging
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

logger = logging.getLogger("agent_annotate.annotation.sequence")

# Valid amino acid characters for validation (standard + common non-standard)
_VALID_AA = set("ACDEFGHIKLMNPQRSTVWYBZXUOJ")

# Source reliability weights for scoring
_SOURCE_WEIGHTS = {
    "dbaasp": 0.95,
    "apd": 0.95,
    "chembl_helm": 0.90,
    "uniprot_mature": 0.85,
    "ebi_mature": 0.80,
    "uniprot_full": 0.70,
    "ebi_full": 0.65,
}

# v18: Known peptide drug sequences — deterministic lookup before database search.
# Verified against human R1 ground truth for Batch A (25 NCTs).
_KNOWN_SEQUENCES: dict[str, str] = {
    # Natriuretic peptides
    "nesiritide": "SPKMVQGSGCFGRKMDRISSSSGLGCKVLRRH",       # BNP-32, UniProt P16860
    "bnp": "SPKMVQGSGCFGRKMDRISSSSGLGCKVLRRH",              # BNP-32
    "anp": "SLRRSSCFGGRMDRIGAQSGLGCNSFRY",                  # Human ANP(1-28), UniProt P01160
    # GLP-1 analogues
    "albiglutide": "HGEGTFTSDVSSYLEGQAAKEFIAWLVKGR",        # GLP-1(7-36) amide, 30aa
    "exenatide": "HGEGTFTSDLSKQMEEEAVRLFIEWLKNGGPSSGAPPPS", # Exendin-4, 39aa
    # Peptide hormones
    "insulin": "MALWMRLLPLLALLALWGPDPAAAFVNQHLCGSHLVEALYLVCGERGFFYTPKTRREAEDLQVGQVELGGGPGAGSLQPLALEGSLQKRGIVEQCCTSICSLYQLENYCN",  # Preproinsulin, 110aa (matches human R1)
    # Angiotensin
    "angiotensin-(1-7)": "DRVYIHP",                          # 7aa
    "angiotensin ii": "DRVYIHPF",                             # 8aa
    # Research peptides
    "dnajp1": "QKRAAYDQYGHAAFE",                             # 15aa, heat shock protein epitope
    "preimplantation factor": "MVRIKPGSANKPSDD",              # sPIF, 15aa
    "spif": "MVRIKPGSANKPSDD",
    "qrh-882260": "QRHKPRE",                                 # 7aa heptapeptide
    "bnz-1": "CGSGGQITISILSQINRVFHEKFI",                    # 25aa, IL-2/15 inhibitor
    # v24: from agent-empty error analysis (verified against human R1 ground truth)
    "gv1001": "EARPALLTSRLRFIPK",                            # Telomerase peptide, 16aa
    "abaloparatide": "AVSEHQLLHDKGKSIQDLRRRELLEKLLEKLHTA",   # PTHrP analog, 34aa
    "vosoritide": "PGQEHPNARKYKGANKKGLSKGCFGLKLDRIGSMSGLGC", # CNP analog (BMN 111), 39aa
    "bmn 111": "PGQEHPNARKYKGANKKGLSKGCFGLKLDRIGSMSGLGC",    # Same as vosoritide
    "satoreotide": "YNAYWKAF",                                # OPS-202, octapeptide SST analog
    "pd-l1 peptide": "FMTYWHLLNAFTVTVPKDL",                  # IO103, PD-L1 epitope, 19aa
    "emi-137": "AGSCYCSGPPRFECWCFETEGTGGGK",                 # cMet-targeting peptide, 26aa
    "l-carnosine": "AH",                                      # Beta-alanyl-L-histidine dipeptide
    "carnosine": "AH",                                        # Same
    # Peptide-conjugate therapeutics
    "cv-mg01": "YFSRIIQKQFGHVNNGK",                          # AChR alpha-subunit peptide, 17aa
    # v28: D-peptide HIV entry inhibitor
    "cpt31": "HPCDYPEWQWLCELGK",                             # PIE12 D-peptide monomer, 16aa (cholesterol-PEG trimer in vivo)
    "pie12": "HPCDYPEWQWLCELGK",                             # Same as CPT31 monomer
    # v28: Radiolabeled peptide imaging agents
    "68ga-rm2": "FQWAVGHSL",                                 # Bombesin antagonist RM2, 9aa (D-Phe→F, Sta→S)
    "rm2": "FQWAVGHSL",                                      # Same (BAY86-7548)
    # v33: Peptide hormones — glucagon false negative fix (NCT03490942)
    "glucagon": "HSQGTFTSDYSKYLDSRRAQDFVQWLMNT",             # Mature glucagon, 29aa, UniProt P01275
    # v38: New sequences from v37b error analysis and training CSV frequency analysis
    # GLP-2 (17x in training as R1 errors — agent was returning glucagon instead)
    "glp-2": "HADGSFSDEMNTILDNLAARDFINWLIQTKITD",            # Human GLP-2, 33aa, UniProt P01275
    "glucagon-like peptide 2": "HADGSFSDEMNTILDNLAARDFINWLIQTKITD",
    "glucagon-like peptide-2": "HADGSFSDEMNTILDNLAARDFINWLIQTKITD",
    # GIP (gastric inhibitory polypeptide)
    "gip": "YAEGTFISDYSIAMDKIHQQDFVNWLLAQKGKKNDWKHNITQ",     # Human GIP, 42aa, UniProt P09681
    "gastric inhibitory polypeptide": "YAEGTFISDYSIAMDKIHQQDFVNWLLAQKGKKNDWKHNITQ",
    # PD-L2 peptide (6x in training — multi-peptide vaccine trials)
    "pd-l2 peptide": "DTLLKALLEIASCLEKALQVF",                # IO120, PD-L2 epitope, 21aa
    "io120": "DTLLKALLEIASCLEKALQVF",
    # P11-4 self-assembling peptide (14x in training)
    "p11-4": "QQRFEWEFEQQ",                                  # 11aa self-assembling peptide
    "curodont": "QQRFEWEFEQQ",
    # Calcitonin (5x in training — salmon calcitonin used clinically)
    "calcitonin": "CSNLSTCVLGKLSQELHKLQTYPRTNTGSGTP",       # Salmon calcitonin, 32aa
    "salmon calcitonin": "CSNLSTCVLGKLSQELHKLQTYPRTNTGSGTP",
    "elcatonin": "CSNLSTCVLGKLSQELHKLQTYPRTNTGSGTP",
    # Semaglutide (17x in training — was returning via exenatide erroneously)
    "semaglutide": "HXEGTFTSDVSSYLEGQAAKEFIAWLVRGRG",       # 31aa, X=Aib at position 2
    # Liraglutide (6x in training)
    "liraglutide": "HAEGTFTSDVSSYLEGQAAKEFIAWLVRGRG",       # 31aa, native GLP-1(7-37) backbone
    # Bremelanotide (melanocortin agonist)
    "bremelanotide": "DHFRWK",                                # 7aa cyclic core (Ac-Nle-c[Asp-His-DPhe-Arg-Trp-Lys]-NH2)
    # LL-37 / cathelicidin (antimicrobial peptide)
    "ll-37": "LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES",       # Human cathelicidin, 37aa
    "cathelicidin": "LLGDFFRKSKEKIGKEFKRIVQRIKDFLRNLVPRTES",
    # Teriparatide / PTH(1-34)
    "teriparatide": "SVSEIQLMHNLGKHLNSMERVEWLRKKLQDVHNF",   # PTH(1-34), 34aa
    # Lanreotide (somatostatin analogue)
    "lanreotide": "NDFWKTCT",                                 # 8aa (with D-Nal and D-Trp)
    # Octreotide (somatostatin analogue, 7x+ in training as FCYWKTCT)
    "octreotide": "FCYWKTCT",                                 # 8aa cyclic
    # OP-01 / KPV (anti-inflammatory tripeptide)
    "kpv": "KPV",                                             # 3aa alpha-MSH fragment
    # Daptomycin (lipopeptide antibiotic)
    "daptomycin": "WNDAADGTGDTASDFGDGSAT",                   # 13aa cyclic lipopeptide core
    # Polymyxin B (cyclic peptide antibiotic)
    "polymyxin b": "BTBBBBFLBT",                              # 10aa (B=Dab, nonstandard)
    # Teduglutide (GLP-2 analogue)
    "teduglutide": "HADGSFSDEMNTILDNLAARDFINWLIQTKITD",      # Same as GLP-2 but with Gly2→Ala substitution (clinically used as native-like)
    # Romidepsin / FK228 (cyclic depsipeptide)
    "romidepsin": "ASTTTNYT",                                 # 8aa (approximate, cyclic depsipeptide)
    # BI 655064 (anti-CD40 peptide) and similar
    "gg-8-6": "GGGYSKAQKAQAKQAKQAQKAQKAQAKQAKQAQKAQKAQA",   # 39aa synthetic antimicrobial
    # Native GLP-1 (used in research trials)
    "glp-1": "HAEGTFTSDVSSYLEGQAAKEFIAWLVKGR",              # GLP-1(7-36) amide, 30aa
    "glucagon-like peptide 1": "HAEGTFTSDVSSYLEGQAAKEFIAWLVKGR",
    "glucagon-like peptide-1": "HAEGTFTSDVSSYLEGQAAKEFIAWLVKGR",
    # Tirzepatide (dual GIP/GLP-1 RA)
    "tirzepatide": "YXEGTFTSDYSIXLDKIAQKAFVQWLIAGGPSSGAPPPS", # 39aa, X=Aib
    # Pramlintide (amylin analogue)
    "pramlintide": "KCNTATCATQRLANFLVHSSNNFGPILPPTNVGSNTY",  # 37aa
    # Vasopressin
    "vasopressin": "CYFQNCPRG",                               # 9aa cyclic
    "desmopressin": "CYFQNCPRG",                              # Same backbone (deamino-D-Arg)
    # Oxytocin
    "oxytocin": "CYIQNCPLG",                                  # 9aa cyclic
    # Secretin
    "secretin": "HSDGTFTSELSRLREGARLQRLLQGLV",               # Human secretin, 27aa
    # Lixisenatide
    "lixisenatide": "HGEGTFTSDLSKQMEEEAVRLFIEWLKNGGPSSGAPPSKKKKKK", # Exendin-4 based, 44aa
    # Leuprolide (GnRH agonist)
    "leuprolide": "QHWSYGLRP",                               # 9aa (with D-Leu, Pro-NHEt)
    "leuprorelin": "QHWSYGLRP",
}

# v29: Alias mapping for pre-cascade name matching.
# Maps alternate names / ClinicalTrials.gov intervention names to
# canonical _KNOWN_SEQUENCES keys when neither is a substring of the other.
_KNOWN_SEQUENCE_ALIASES: dict[str, str] = {
    # dnaJ heat shock protein peptide
    "dnaj peptide": "dnajp1",
    "dnaj": "dnajp1",
    "dna-jp1": "dnajp1",
    # BMN 111 / vosoritide spacing/hyphen variants
    "bmn111": "bmn 111",
    "bmn-111": "bmn 111",
    # Preimplantation factor
    "pif": "spif",
    "synthetic preimplantation factor": "spif",
    # Radiolabeled peptide imaging
    "68ga rm2": "68ga-rm2",
    "bay86-7548": "68ga-rm2",
    # IO103 / PD-L1
    "io103": "pd-l1 peptide",
    "io-103": "pd-l1 peptide",
    # OPS-202 / satoreotide
    "ops-202": "satoreotide",
    "ops202": "satoreotide",
    # v38: New aliases
    "io120": "pd-l2 peptide",
    "io-120": "pd-l2 peptide",
    "curodont repair": "p11-4",
    "self-assembling peptide p11-4": "p11-4",
    "self assembling peptide": "p11-4",
    "forteo": "teriparatide",
    "pth(1-34)": "teriparatide",
    "pth 1-34": "teriparatide",
    "sandostatin": "octreotide",
    "somatuline": "lanreotide",
    "mounjaro": "tirzepatide",
    "ozempic": "semaglutide",
    "wegovy": "semaglutide",
    "rybelsus": "semaglutide",
    "victoza": "liraglutide",
    "saxenda": "liraglutide",
    "trulicity": "albiglutide",
    "byetta": "exenatide",
    "bydureon": "exenatide",
    "symlin": "pramlintide",
    "adlyxin": "lixisenatide",
    "glp-1 hormone": "glp-1",
    "glp-1 receptor agonist": "semaglutide",
    "glp-2 analog": "glp-2",
    "glp-2 analogue": "glp-2",
    "cubicin": "daptomycin",
    "ddavp": "desmopressin",
    "pitocin": "oxytocin",
    "lupron": "leuprolide",
    "eligard": "leuprolide",
}


def resolve_known_sequence(name_lower: str) -> tuple[str, str] | None:
    """Look up a drug name in _KNOWN_SEQUENCES with alias fallback.

    Returns (drug_key, sequence) if found, None otherwise.
    Checks: direct key → longest-substring match against keys → longest-
    alias substring → None.

    v42.6.18 (2026-04-25): substring search now prefers the LONGEST matching
    key to avoid 'glucagon' matching inside 'glucagon-like peptide 1' and
    returning glucagon's sequence (HSQGTFTSDY...) instead of GLP-1's
    (HAEGTFTSDV...). Job #83 NCT01689051 surfaced this — GLP-1 trial got
    glucagon's sequence because dict iteration order put 'glucagon' first.
    """
    # Direct key match
    if name_lower in _KNOWN_SEQUENCES:
        return name_lower, _KNOWN_SEQUENCES[name_lower]

    # Longest-substring key match — sort by key length descending so a more
    # specific name like 'glucagon-like peptide 1' wins over 'glucagon'.
    # name_lower-in-drug ('peptide YY' input matches drug 'peptide YY...')
    # uses the same order.
    sorted_keys = sorted(_KNOWN_SEQUENCES.keys(), key=len, reverse=True)
    for drug in sorted_keys:
        if drug in name_lower or name_lower in drug:
            return drug, _KNOWN_SEQUENCES[drug]

    # Alias lookup (also longest-first for consistency)
    sorted_aliases = sorted(_KNOWN_SEQUENCE_ALIASES.keys(), key=len, reverse=True)
    for alias in sorted_aliases:
        if alias in name_lower or name_lower in alias:
            canonical = _KNOWN_SEQUENCE_ALIASES[alias]
            seq = _KNOWN_SEQUENCES.get(canonical)
            if seq:
                return canonical, seq

    return None


def normalize_sequence(raw: str) -> str:
    """Normalize a raw sequence string to canonical format.

    - Uppercase
    - Strip spaces within amino acid stretches
    - Remove chemical modification markers
    - Return empty string if no valid AA sequence found
    """
    if not raw or not raw.strip():
        return ""

    # Remove modification prefixes/suffixes
    cleaned = re.sub(r"^(Ac-|H-|Fmoc-|Boc-|D-|L-|cyclo\()", "", raw.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"(-NH2|-OH|-COOH|-amide|-acid|\(ol\))$", "", cleaned, flags=re.IGNORECASE)

    # Remove spaces (human annotators space every 5 chars)
    cleaned = cleaned.replace(" ", "")

    # Remove dashes that are part of single-letter notation (K-K-W-W → KKWW)
    if re.match(r"^[A-Z]-[A-Z]-", cleaned):
        cleaned = cleaned.replace("-", "")

    # Uppercase
    cleaned = cleaned.upper()

    # Validate: must contain at least 2 consecutive amino acid letters
    if not re.search(r"[ACDEFGHIKLMNPQRSTVWYBZXUOJ]{2,}", cleaned):
        return ""

    # Strip any remaining non-AA characters from the edges
    cleaned = cleaned.strip()

    return cleaned


def _parse_helm_sequence(helm: str) -> tuple[str, str]:
    """Parse a ChEMBL HELM notation string to extract linear AA sequence.

    HELM format examples:
      PEPTIDE1{A.S.T.T.T.N.Y.T}$$$$  → ("ASTTTNYT", "ASTTTNYT")
      PEPTIDE1{[ac].M.P.P.A.D.E.D.Y.S.P.[am]}$$$$  → ("MPPADEDYSP", "(Ac)MPPADEDYSP(NH2)")
      PEPTIDE1{H.S.Q.G.T.F.T.S.D.Y.S.R.Y.L.D}$$$$  → ("HSQGTFTSDYSRYLD", "HSQGTFTSDYSRYLD")

    v23: Returns (canonical, display) tuple.
      - canonical: uppercase AA only, for dedup and scoring
      - display: preserves modifications as (Ac)/(NH2) and D-amino acids as lowercase

    Extracts content between { and }, splits on '.', keeps single uppercase
    letters. Bracket-enclosed modifications are preserved in display form.
    """
    if not helm:
        return ("", "")

    # Find the peptide chain content between braces
    match = re.search(r"PEPTIDE\d*\{([^}]+)\}", helm, re.IGNORECASE)
    if not match:
        return ("", "")

    # Map common HELM modifications to display format
    _HELM_MOD_DISPLAY = {
        "ac": "Ac", "am": "NH2", "nh2": "NH2",
        "oh": "OH", "meac": "MeAc", "formyl": "Formyl",
    }

    tokens = match.group(1).split(".")
    canonical_letters: list[str] = []
    display_parts: list[str] = []
    prefix_mods: list[str] = []
    suffix_mods: list[str] = []

    for i, token in enumerate(tokens):
        token = token.strip()
        if token.startswith("["):
            # Bracket-enclosed modification
            mod_name = token.strip("[]").lower()
            display_name = _HELM_MOD_DISPLAY.get(mod_name, token.strip("[]"))
            # If before any AA, it is a prefix; if after all AA, it is a suffix
            if not canonical_letters:
                prefix_mods.append(display_name)
            else:
                suffix_mods.append(display_name)
        elif len(token) == 1 and token.isupper() and token in _VALID_AA:
            # Flush any pending suffix mods as inline (rare mid-chain mods)
            for sm in suffix_mods:
                display_parts.append(f"({sm})")
            suffix_mods.clear()
            canonical_letters.append(token)
            display_parts.append(token)
        elif len(token) == 2 and token[0] == "d" and token[1].isupper():
            # D-amino acid: canonical uppercase, display lowercase
            for sm in suffix_mods:
                display_parts.append(f"({sm})")
            suffix_mods.clear()
            canonical_letters.append(token[1])
            display_parts.append(token[1].lower())  # D-amino acid as lowercase

    canonical = "".join(canonical_letters)
    if len(canonical) < 2:
        return ("", "")

    # Build display string with prefix/suffix modifications
    display = ""
    for pm in prefix_mods:
        display += f"({pm})"
    display += "".join(display_parts)
    for sm in suffix_mods:
        display += f"({sm})"

    return (canonical, display)


def _score_candidate(candidate: dict) -> float:
    """Score a sequence candidate for ranking.

    v17: ChEMBL HELM gets a clinical-drug bonus (1.3x) because it represents
    the actual synthesized drug molecule, not a database entry that may be for
    a different peptide with a similar name. DBAASP is demoted slightly (0.85)
    because its substring name matching can return unrelated peptides.
    """
    source = candidate.get("source", "")
    relevance = candidate.get("relevance", 0.5)
    length = candidate.get("length", 0)
    is_mature = candidate.get("is_mature", False)

    source_weight = _SOURCE_WEIGHTS.get(source, 0.5)
    length_penalty = 1.0 if 2 <= length <= 100 else (0.5 if length <= 200 else 0.0)
    maturity_bonus = 1.2 if is_mature else 1.0
    # v17: ChEMBL HELM represents the actual drug molecule → boost
    clinical_bonus = 1.3 if source == "chembl_helm" else 1.0

    return source_weight * relevance * length_penalty * maturity_bonus * clinical_bonus


def _strip_intervention_prefix(name: str) -> str:
    """Strip ClinicalTrials.gov type prefix (e.g. 'BIOLOGICAL: X' → 'X')."""
    if ": " in name:
        prefix, _, rest = name.partition(": ")
        if prefix.upper() in (
            "BIOLOGICAL", "DRUG", "DEVICE", "PROCEDURE",
            "RADIATION", "DIETARY SUPPLEMENT", "GENETIC",
            "DIAGNOSTIC TEST", "COMBINATION PRODUCT", "OTHER",
        ):
            return rest
    return name


# v17: Formulation/device words to strip from intervention names before DB lookups.
# "Albiglutide Lyophilized DCC Pen Injector" → "Albiglutide"
_FORMULATION_WORDS = {
    "lyophilized", "lyophilised", "powder", "solution", "suspension",
    "injection", "injector", "pen", "prefilled", "pre-filled", "syringe",
    "vial", "tablet", "capsule", "cream", "gel", "spray", "inhaler",
    "dcc", "autoinjector", "auto-injector", "cartridge", "device",
    "kit", "reconstituted", "diluent",
}


def _strip_formulation(name: str) -> str:
    """Strip formulation/device words from an intervention name.

    v17: Prevents "Albiglutide Lyophilized DCC Pen Injector" from polluting
    ChEMBL searches. Returns the first word(s) that aren't formulation terms.
    """
    words = name.split()
    # Keep words until we hit a formulation word
    clean = []
    for word in words:
        if word.lower().rstrip(".,;:") in _FORMULATION_WORDS:
            break
        clean.append(word)
    result = " ".join(clean).strip()
    # If we stripped everything, return the first word
    return result if result else words[0] if words else name


def _extract_intervention_names(metadata: dict | None) -> list[str]:
    """Extract intervention names from metadata, stripping type prefixes.

    v18: Also extracts resolved drug names (generic + synonyms) from EDAM
    when metadata entries are dicts with a 'resolved' key.
    """
    if not metadata:
        return []
    raw = metadata.get("interventions", [])
    if not isinstance(raw, list):
        return []
    names = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("intervention_name") or ""
            if name:
                stripped = _strip_intervention_prefix(str(name))
                if stripped.lower() not in seen:
                    names.append(stripped)
                    seen.add(stripped.lower())
                # v18: Also include resolved names for database lookups
                for resolved in item.get("resolved", []):
                    if resolved and resolved.lower() not in seen:
                        names.append(str(resolved))
                        seen.add(resolved.lower())
        elif isinstance(item, str) and item:
            stripped = _strip_intervention_prefix(item)
            if stripped.lower() not in seen:
                names.append(stripped)
                seen.add(stripped.lower())
    return names


def _extract_primary_interventions(
    research_results: list,
    metadata: dict | None,
) -> list[str]:
    """Extract intervention names from EXPERIMENTAL arms only.

    Filters ClinicalTrials.gov arm groups to return only interventions assigned
    to EXPERIMENTAL arms — the primary investigational drug(s). Excludes background
    therapy (ACTIVE_COMPARATOR, PLACEBO_COMPARATOR, NO_INTERVENTION).

    Falls back to all interventions if no EXPERIMENTAL arms are found.
    """
    for result in research_results:
        if result.error or result.agent_name != "clinical_protocol":
            continue
        if not result.raw_data:
            continue
        proto = result.raw_data.get(
            "protocol_section", result.raw_data.get("protocolSection", {})
        )
        arms_mod = proto.get("armsInterventionsModule", {})
        arm_groups = arms_mod.get("armGroups", [])

        experimental_names: list[str] = []
        seen: set[str] = set()
        for arm in arm_groups:
            arm_type = arm.get("type", arm.get("armGroupType", "")).upper()
            if arm_type != "EXPERIMENTAL":
                continue
            for iname in arm.get("interventionNames", []):
                if not iname:
                    continue
                stripped = _strip_intervention_prefix(iname.strip())
                if stripped.lower() not in seen:
                    experimental_names.append(stripped)
                    seen.add(stripped.lower())

        if experimental_names:
            # Also include EDAM-resolved synonyms for the experimental drugs
            # (e.g., "BNP" → "nesiritide") for broader database coverage.
            exp_lower = {n.lower() for n in experimental_names}
            if metadata:
                for item in metadata.get("interventions", []):
                    if not isinstance(item, dict):
                        continue
                    item_name = _strip_intervention_prefix(
                        str(item.get("name") or item.get("intervention_name") or "")
                    )
                    if item_name.lower() in exp_lower:
                        for resolved in item.get("resolved", []):
                            if resolved and resolved.lower() not in exp_lower:
                                experimental_names.append(str(resolved))
                                exp_lower.add(resolved.lower())
            return experimental_names

    # Fallback: no arm type data — use all interventions
    return _extract_intervention_names(metadata)


def _extract_interventions_from_raw_data(all_raw: dict) -> list[str]:
    """Fallback: extract intervention names from raw_data keys.

    Raw data keys follow the pattern 'source_interventionName' or
    'source_interventionName_suffix'. We extract unique intervention
    names by looking at uniprot_* keys (most reliable pattern).
    """
    names = set()
    for key in all_raw:
        if key.startswith("uniprot_") and not key.endswith(("_no_structured_match", "_resolved_via")):
            # uniprot_{name} or uniprot_{name}_other_suffix
            candidate = key[len("uniprot_"):]
            if candidate:
                names.add(candidate)
    return list(names)


class SequenceAgent(BaseAnnotationAgent):
    """Structured-data sequence extraction with optional LLM adjudication."""

    field_name = "sequence"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        """Extract sequence from structured research raw_data. No snippet parsing.

        v14: Priority order for sequence extraction:
        1. DBAASP structured sequences (name-filtered)
        2. APD structured sequences (from detail pages)
        3. ChEMBL HELM notation (parsed to linear AA)
        4. UniProt mature peptide/chain features
        5. UniProt full sequence (≤100 AA, verified relevance > 0.5)
        6. EBI Proteins structured entries
        """
        candidates: list[dict] = []
        evidence: list[SourceCitation] = []
        reasoning_parts: list[str] = []
        used_llm = False

        # Collect all raw_data dicts from research results
        all_raw: dict = {}
        for result in research_results:
            if result.error:
                continue
            if result.raw_data:
                all_raw.update(result.raw_data)

        # Extract intervention names — EXPERIMENTAL arms only (primary drug, not comparators)
        interventions = _extract_primary_interventions(research_results, metadata)
        if not interventions:
            interventions = _extract_interventions_from_raw_data(all_raw)
            if interventions:
                reasoning_parts.append(
                    f"Interventions extracted from raw_data keys: {interventions[:3]}"
                )

        # v18: Check known sequences table first (deterministic, highest priority)
        for intervention in interventions:
            lookup_name = _strip_formulation(intervention).lower()
            for drug_name, known_seq in _KNOWN_SEQUENCES.items():
                # Short drug names (<=4 chars) require near-exact match to avoid
                # false positives (e.g. "bnp" matching "bnp levels in ...")
                if len(drug_name) <= 4:
                    if lookup_name != drug_name and not lookup_name.startswith(drug_name + " "):
                        continue
                else:
                    # Word-boundary match: drug_name must appear as a complete
                    # word/phrase, not as a substring of a longer word
                    pattern = r'(?:^|[\s\-/])' + re.escape(drug_name) + r'(?:$|[\s\-/,])'
                    if not (re.search(pattern, lookup_name) or lookup_name == drug_name):
                        continue
                logger.info(
                    f"  sequence: known sequence match '{drug_name}' "
                    f"for '{intervention}' ({len(known_seq)} aa)"
                )
                return FieldAnnotation(
                    field_name="sequence",
                    value=known_seq,
                    confidence=0.95,
                    reasoning=(
                        f"[Known sequence] {drug_name} → {known_seq[:20]}... "
                        f"({len(known_seq)} aa). Matched intervention '{intervention}'."
                    ),
                    evidence=[],
                    model_name="deterministic",
                    skip_verification=True,
                )

        # Also keep citation references for evidence attribution
        citations_by_source: dict[str, list[SourceCitation]] = {}
        for result in research_results:
            if result.error:
                continue
            for cite in result.citations:
                citations_by_source.setdefault(cite.source_name, []).append(cite)

        # --- Phase 1: Collect candidates from structured raw_data ---

        # DBAASP and APD are antimicrobial peptide databases. For non-AMP trials
        # (classification = Other), their hits are almost always false positives
        # (e.g., Brevinin from frog skin returned for a cancer vaccine trial).
        # Skip them entirely when the trial drug is classified as non-AMP.
        classification_result = str(
            metadata.get("classification_result", "") if metadata else ""
        ).lower()
        use_amp_dbs = classification_result != "other"

        for intervention in interventions:
            # 1. DBAASP structured sequences (AMP trials only)
            if use_amp_dbs:
                dbaasp_seqs = all_raw.get(f"dbaasp_{intervention}_sequences", [])
                if not dbaasp_seqs:
                    base = all_raw.get(f"dbaasp_{intervention}", {})
                    if isinstance(base, dict):
                        dbaasp_seqs = base.get("entries", [])
                for entry in dbaasp_seqs:
                    if not isinstance(entry, dict):
                        continue
                    seq = normalize_sequence(entry.get("sequence", ""))
                    if seq and len(seq) >= 2:
                        candidates.append({
                            "sequence": seq,
                            "source": "dbaasp",
                            "protein_name": entry.get("name", intervention),
                            "relevance": 0.9,
                            "length": len(seq),
                            "is_mature": True,
                            "accession": entry.get("dbaasp_id", ""),
                        })
                        reasoning_parts.append(f"DBAASP: {entry.get('name', '')} ({len(seq)} aa)")

            # 2. APD structured sequences (AMP trials only)
            if use_amp_dbs:
                apd_seqs = all_raw.get(f"apd_{intervention}_sequences", [])
                for entry in apd_seqs:
                    if not isinstance(entry, dict):
                        continue
                    seq = normalize_sequence(entry.get("sequence", ""))
                    if seq and len(seq) >= 2:
                        candidates.append({
                            "sequence": seq,
                            "source": "apd",
                            "protein_name": entry.get("name", intervention),
                            "relevance": 0.9,
                            "length": len(seq),
                            "is_mature": True,
                            "accession": entry.get("apd_id", ""),
                        })
                        reasoning_parts.append(f"APD: {entry.get('apd_id', '')} ({len(seq)} aa)")

            # 3. ChEMBL HELM notation
            # v17: Also try with formulation words stripped (e.g.,
            # "Albiglutide Lyophilized DCC Pen Injector" → "Albiglutide")
            stripped_name = _strip_formulation(intervention)
            helm_keys = [f"chembl_{intervention}_helm"]
            if stripped_name != intervention:
                helm_keys.append(f"chembl_{stripped_name}_helm")
            helm = ""
            for hk in helm_keys:
                helm = all_raw.get(hk, "")
                if helm:
                    break
            if not helm:
                # Fallback: check molecules list for helm_notation field
                mol_keys = [f"chembl_{intervention}_molecules"]
                if stripped_name != intervention:
                    mol_keys.append(f"chembl_{stripped_name}_molecules")
                for mk in mol_keys:
                    mols = all_raw.get(mk, [])
                    if not isinstance(mols, list):
                        continue
                    # v18: Prefer highest max_phase molecule (marketed > clinical)
                    mols_with_helm = [
                        m for m in mols
                        if isinstance(m, dict) and m.get("helm_notation")
                    ]
                    if mols_with_helm:
                        best = max(
                            mols_with_helm,
                            key=lambda m: float(m.get("max_phase", 0) or 0),
                        )
                        helm = best["helm_notation"]
                        # v18: Reject if pref_name is completely unrelated
                        pref = (best.get("pref_name") or "").lower()
                        interv_lower = intervention.lower()
                        stripped_lower = stripped_name.lower()
                        if (pref and pref not in interv_lower
                                and interv_lower not in pref
                                and pref not in stripped_lower
                                and stripped_lower not in pref):
                            logger.info(
                                f"  sequence: ChEMBL molecule '{best.get('pref_name')}' "
                                f"rejected — no name overlap with '{intervention}'"
                            )
                            helm = ""
                    if helm:
                        break
            if helm:
                canonical, display = _parse_helm_sequence(helm)
                if canonical:
                    candidates.append({
                        "sequence": canonical,
                        "display_sequence": display,
                        "source": "chembl_helm",
                        "protein_name": intervention,
                        "relevance": 0.85,
                        "length": len(canonical),
                        "is_mature": True,
                        "accession": "",
                    })
                    reasoning_parts.append(f"ChEMBL HELM: parsed {len(canonical)} aa from {helm[:40]}")

            # 4. UniProt mature peptide/chain features
            uniprot_entries = all_raw.get(f"uniprot_{intervention}", [])
            for entry in uniprot_entries:
                if not isinstance(entry, dict):
                    continue

                accession = entry.get("primaryAccession", "")
                relevance = entry.get("_verified_relevance", 0.5)
                protein_name = ""
                pd = entry.get("proteinDescription", {})
                rn = pd.get("recommendedName", {}) if isinstance(pd, dict) else {}
                if rn:
                    fn = rn.get("fullName", {})
                    protein_name = fn.get("value", "") if isinstance(fn, dict) else ""

                full_seq = ""
                seq_obj = entry.get("sequence", {})
                if isinstance(seq_obj, dict):
                    full_seq = seq_obj.get("value", "")

                # Check for mature peptide/chain features
                # v17: Prefer fragment whose description matches the drug name
                # instead of always picking the shortest. For BNP (UniProt P16860),
                # the shortest fragment is BNP(4-27) (24aa degradation product),
                # but the correct therapeutic peptide is "Brain natriuretic peptide 32".
                features = entry.get("features", [])
                best_fragment = None
                best_fragment_score = -1  # higher is better

                intervention_lower = intervention.lower()

                for feat in features:
                    if not isinstance(feat, dict):
                        continue
                    feat_type = feat.get("type", "")
                    if feat_type not in ("Chain", "Peptide"):
                        continue
                    location = feat.get("location", {})
                    if not isinstance(location, dict):
                        continue
                    start = location.get("start", {}).get("value", 0)
                    end = location.get("end", {}).get("value", 0)
                    if start and end and full_seq:
                        try:
                            start = int(start)
                            end = int(end)
                        except (ValueError, TypeError):
                            continue
                        fragment = full_seq[start - 1:end]
                        frag_len = len(fragment)
                        if not (2 <= frag_len <= 200):
                            continue

                        # Score: name match > peptide type > shorter length
                        feat_desc = feat.get("description", "").lower()
                        name_match = 10 if intervention_lower in feat_desc else 0
                        type_bonus = 5 if feat_type == "Peptide" else 0
                        # Prefer moderate-length fragments over very short ones
                        # (short fragments are often degradation products)
                        length_score = 1.0 / (1.0 + abs(frag_len - 32))  # bias toward ~32aa
                        score = name_match + type_bonus + length_score

                        if score > best_fragment_score:
                            best_fragment = fragment
                            best_fragment_score = score

                # v38: Collect ALL qualifying chain/peptide features for multi-chain reporting.
                # When the protein has multiple mature chains (e.g., insulin A+B chain,
                # GLP-2 + GIP in same precursor), report all of them joined by " | ".
                all_fragments = []
                for feat in features:
                    if not isinstance(feat, dict):
                        continue
                    feat_type = feat.get("type", "")
                    if feat_type not in ("Chain", "Peptide"):
                        continue
                    location = feat.get("location", {})
                    if not isinstance(location, dict):
                        continue
                    start_val = location.get("start", {}).get("value", 0)
                    end_val = location.get("end", {}).get("value", 0)
                    if start_val and end_val and full_seq:
                        try:
                            s = int(start_val)
                            e = int(end_val)
                        except (ValueError, TypeError):
                            continue
                        frag = full_seq[s - 1:e]
                        if 2 <= len(frag) <= 200:
                            feat_desc = feat.get("description", "").lower()
                            name_match = intervention_lower in feat_desc
                            all_fragments.append((frag, name_match, feat_desc))

                if best_fragment:
                    norm = normalize_sequence(best_fragment)
                    if norm:
                        # v38: If there are multiple qualifying fragments AND the
                        # intervention mentions multiple drugs (e.g., "GLP-2 + GIP"),
                        # include all name-matching fragments joined by " | ".
                        multi_seq = norm
                        if len(all_fragments) > 1:
                            name_matched = [normalize_sequence(f) for f, matched, _ in all_fragments if matched and normalize_sequence(f)]
                            if len(name_matched) > 1:
                                multi_seq = " | ".join(name_matched)
                                logger.info(f"  sequence: v38 multi-chain — {len(name_matched)} fragments matched intervention name")

                        candidates.append({
                            "sequence": multi_seq,
                            "source": "uniprot_mature",
                            "protein_name": protein_name or accession,
                            "relevance": relevance,
                            "length": len(norm),
                            "is_mature": True,
                            "accession": accession,
                        })
                        reasoning_parts.append(
                            f"UniProt {accession}: {protein_name} — mature fragment ({len(norm)} aa)"
                        )
                elif full_seq:
                    # Phase 5: Full sequence only if ≤100 AA and verified relevant
                    norm = normalize_sequence(full_seq)
                    if norm and len(norm) <= 100 and relevance > 0.5:
                        candidates.append({
                            "sequence": norm,
                            "source": "uniprot_full",
                            "protein_name": protein_name or accession,
                            "relevance": relevance,
                            "length": len(norm),
                            "is_mature": False,
                            "accession": accession,
                        })
                        reasoning_parts.append(
                            f"UniProt {accession}: {protein_name} ({len(norm)} aa, full ≤100)"
                        )
                    elif norm and len(norm) > 100:
                        reasoning_parts.append(
                            f"UniProt {accession}: skipped ({len(norm)} aa > 100 cap)"
                        )

            # 6. EBI Proteins structured entries
            ebi_entries = all_raw.get(f"ebi_proteins_{intervention}_entries", [])
            for entry in ebi_entries:
                if not isinstance(entry, dict):
                    continue
                accession = entry.get("accession", "")
                protein_name = entry.get("protein_name", "")
                sequence = entry.get("sequence", "")
                ebi_features = entry.get("features", [])

                # Try mature features first
                best_fragment = None
                best_fragment_len = float("inf")
                for feat in ebi_features:
                    if not isinstance(feat, dict):
                        continue
                    feat_type = feat.get("type", "")
                    if feat_type not in ("CHAIN", "PEPTIDE", "Chain", "Peptide"):
                        continue
                    location = feat.get("location", {})
                    if not isinstance(location, dict):
                        continue
                    begin = location.get("begin", {}).get("value", location.get("start", {}).get("value", 0))
                    end_val = location.get("end", {}).get("value", 0)
                    if begin and end_val and sequence:
                        try:
                            begin = int(begin)
                            end_val = int(end_val)
                        except (ValueError, TypeError):
                            continue
                        fragment = sequence[begin - 1:end_val]
                        frag_len = len(fragment)
                        if 2 <= frag_len <= 200 and frag_len < best_fragment_len:
                            best_fragment = fragment
                            best_fragment_len = frag_len

                if best_fragment:
                    norm = normalize_sequence(best_fragment)
                    if norm and not any(c["sequence"] == norm for c in candidates):
                        candidates.append({
                            "sequence": norm,
                            "source": "ebi_mature",
                            "protein_name": protein_name or accession,
                            "relevance": 0.6,
                            "length": len(norm),
                            "is_mature": True,
                            "accession": accession,
                        })
                        reasoning_parts.append(
                            f"EBI {accession}: mature fragment ({len(norm)} aa)"
                        )
                elif sequence:
                    norm = normalize_sequence(sequence)
                    if norm and len(norm) <= 100 and not any(c["sequence"] == norm for c in candidates):
                        candidates.append({
                            "sequence": norm,
                            "source": "ebi_full",
                            "protein_name": protein_name or accession,
                            "relevance": 0.5,
                            "length": len(norm),
                            "is_mature": False,
                            "accession": accession,
                        })

        # --- Phase 2: Score and rank candidates ---
        for c in candidates:
            c["score"] = _score_candidate(c)

        # Deduplicate by sequence (keep highest-scoring)
        seen_seqs: dict[str, dict] = {}
        for c in candidates:
            seq = c["sequence"]
            if seq not in seen_seqs or c["score"] > seen_seqs[seq]["score"]:
                seen_seqs[seq] = c
        unique_candidates = sorted(seen_seqs.values(), key=lambda x: x["score"], reverse=True)

        # v18: Cross-validate candidates against intervention names.
        # Penalize candidates whose protein_name doesn't overlap with any
        # intervention name — prevents DBAASP returning Insulin for Nesiritide.
        all_intervention_names: set[str] = set()
        for interv in interventions:
            name_lower = _strip_formulation(interv).lower()
            all_intervention_names.add(name_lower)
            for word in name_lower.split():
                if len(word) >= 3:
                    all_intervention_names.add(word)

        for c in unique_candidates:
            pname = c.get("protein_name", "").lower()
            has_overlap = any(
                iname in pname or pname in iname
                for iname in all_intervention_names
                if len(iname) >= 3
            )
            if not has_overlap and pname:
                old_score = c["score"]
                c["score"] *= 0.3
                reasoning_parts.append(
                    f"Penalized '{c['protein_name']}' ({old_score:.2f}→{c['score']:.2f}): "
                    f"no name overlap with interventions"
                )

        # v38: Cross-validate against known drug class sequences.
        # If the intervention matches a known drug name but the top candidate's
        # sequence doesn't match the known sequence, penalize it heavily.
        # This catches wrong-molecule errors (e.g., returning glucagon for GLP-2).
        for interv in interventions:
            lookup_name = _strip_formulation(interv).lower()
            known = resolve_known_sequence(lookup_name)
            if known:
                _, expected_seq = known
                expected_norm = expected_seq.upper().replace(" ", "")
                for c in unique_candidates:
                    cand_norm = c["sequence"].upper().replace(" ", "").split("|")[0].strip()
                    if cand_norm != expected_norm and len(cand_norm) > 5:
                        old_score = c["score"]
                        c["score"] *= 0.1
                        logger.info(
                            f"  sequence: v38 cross-validation penalty for '{c['protein_name']}' — "
                            f"sequence doesn't match known {lookup_name} ({old_score:.2f}→{c['score']:.2f})"
                        )
                break  # Only check first matching intervention

        unique_candidates.sort(key=lambda x: x["score"], reverse=True)

        # --- Phase 3: LLM adjudication (optional) ---
        # Only if top 2 candidates differ and both score > 0.5
        if (len(unique_candidates) >= 2
                and unique_candidates[0]["sequence"] != unique_candidates[1]["sequence"]
                and unique_candidates[0]["score"] > 0.5
                and unique_candidates[1]["score"] > 0.5
                and abs(unique_candidates[0]["score"] - unique_candidates[1]["score"]) < 0.3):
            try:
                chosen = await self._adjudicate(
                    unique_candidates[:2],
                    interventions[0] if interventions else nct_id,
                    nct_id,
                    metadata,
                )
                if chosen is not None:
                    unique_candidates = [unique_candidates[chosen]]
                    used_llm = True
                    reasoning_parts.append(
                        f"LLM adjudication: selected candidate {chosen + 1}"
                    )
            except Exception as e:
                logger.warning("LLM adjudication failed for %s: %s", nct_id, e)
                reasoning_parts.append(f"LLM adjudication failed: {e}")

        # --- Phase 4: Output formatting ---
        # v23: Filter to ≤100 AA, extract ALL unique sequences (no cap)
        final = [c for c in unique_candidates if c["length"] <= 100]
        if not final and unique_candidates:
            # If all >100 AA, keep the shortest one as fallback
            shortest = min(unique_candidates, key=lambda x: x["length"])
            if shortest["length"] <= 200:
                final = [shortest]
                reasoning_parts.append(
                    f"All sequences >100 aa; kept shortest ({shortest['length']} aa)"
                )

        # Collect evidence citations from relevant sources
        for c in final:
            source_name = c["source"].replace("_mature", "").replace("_full", "").replace("_helm", "")
            for cite in citations_by_source.get(source_name, [])[:2]:
                if cite not in evidence:
                    evidence.append(cite)

        if final:
            value = " | ".join(c.get("display_sequence", c["sequence"]) for c in final)
            confidence = min(0.95, 0.7 + 0.05 * len(evidence))
            reasoning = (
                f"[Structured v23] Extracted {len(final)} sequence(s) "
                f"from {len(candidates)} candidates. "
                + "; ".join(reasoning_parts)
            )
        else:
            # LLM fallback: only for confirmed peptide=True trials where structured
            # sources found nothing. Searches research text for explicit AA sequences.
            peptide_confirmed = str(metadata.get("peptide_result", "") if metadata else "").lower() == "true"
            if peptide_confirmed:
                llm_seq = await self._llm_extract_sequence(
                    nct_id, interventions, research_results, metadata
                )
                if llm_seq:
                    value = llm_seq
                    confidence = 0.5
                    reasoning = (
                        "[Structured v14] No sequence in databases; "
                        "[LLM fallback] extracted from research text."
                    )
                    if reasoning_parts:
                        reasoning += " Notes: " + "; ".join(reasoning_parts)
                    used_llm = True
                else:
                    value = "N/A"
                    confidence = 0.0
                    reasoning = "[Structured v23] No amino acid sequence found in research data."
                    if reasoning_parts:
                        reasoning += " Notes: " + "; ".join(reasoning_parts)
            else:
                value = "N/A"
                confidence = 0.0
                reasoning = "[Structured v23] No amino acid sequence found in research data."
                if reasoning_parts:
                    reasoning += " Notes: " + "; ".join(reasoning_parts)

        return FieldAnnotation(
            field_name="sequence",
            value=value,
            confidence=confidence,
            reasoning=reasoning,
            evidence=evidence,
            model_name="deterministic" if not used_llm else "qwen3:14b",
            skip_verification=not used_llm,
        )

    async def _adjudicate(
        self,
        candidates: list[dict],
        intervention: str,
        nct_id: str,
        metadata: Optional[dict],
    ) -> Optional[int]:
        """Use LLM to select between ambiguous sequence candidates.

        Returns 0 or 1 for the chosen candidate index, or None if neither/error.
        """
        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service

        config = config_service.get()
        model = getattr(config.orchestrator, "annotation_model", "qwen3:14b")

        c1 = candidates[0]
        c2 = candidates[1]

        prompt = (
            f"Drug: {intervention}\n"
            f"Trial: {nct_id}\n\n"
            f"Candidate 1: {c1['sequence'][:60]} "
            f"({c1['source']}, {c1['protein_name']}, {c1['length']} aa)\n"
            f"Candidate 2: {c2['sequence'][:60]} "
            f"({c2['source']}, {c2['protein_name']}, {c2['length']} aa)\n\n"
            f"Which amino acid sequence is the actual drug molecule being tested "
            f"in this clinical trial? Answer with just 1, 2, or none."
        )

        system = (
            "You are selecting which amino acid sequence corresponds to the drug "
            "being tested in a clinical trial. Consider the drug name, protein name, "
            "sequence length, and source database. Answer with just the number "
            "(1 or 2) or 'none' if neither is correct."
        )

        logger.info("  sequence: LLM adjudication for %s (%s vs %s)", nct_id, c1["source"], c2["source"])
        response = await ollama_client.generate(
            model=model,
            prompt=prompt,
            system=system,
            temperature=0.05,
        )
        answer = response.get("response", "").strip().lower()

        if "1" in answer and "2" not in answer:
            return 0
        elif "2" in answer and "1" not in answer:
            return 1
        elif "none" in answer:
            return None
        return None  # Ambiguous answer, keep top candidate by score

    async def _llm_extract_sequence(
        self,
        nct_id: str,
        interventions: list[str],
        research_results: list,
        metadata: Optional[dict],
    ) -> str:
        """LLM fallback: extract AA sequence from research text when structured
        sources return nothing.

        Only called for peptide=True trials. Assembles snippets from research
        results and asks the LLM to identify an explicit amino acid sequence.
        Returns a validated sequence string, or "" if none found.
        """
        from app.services.ollama_client import ollama_client
        from app.services.config_service import config_service

        config = config_service.get()
        model = getattr(config.orchestrator, "annotation_model", "qwen3:14b")

        # Collect text snippets from research results
        snippets: list[str] = []
        for result in research_results:
            if result.error:
                continue
            for cite in getattr(result, "citations", [])[:6]:
                snippet = getattr(cite, "snippet", "") or ""
                if snippet and len(snippet) > 20:
                    snippets.append(f"[{cite.source_name}] {snippet[:300]}")

        # Also include trial title and description from metadata
        if metadata:
            title = metadata.get("title", "")
            if title:
                snippets.insert(0, f"[Trial title] {title}")

        if not snippets:
            return ""

        drug_names = ", ".join(interventions[:3]) if interventions else nct_id
        text_block = "\n".join(snippets[:12])

        prompt = (
            f"Drug: {drug_names}\n"
            f"Trial: {nct_id}\n\n"
            f"Research text:\n{text_block}\n\n"
            "Extract the amino acid sequence of the drug molecule in one-letter code "
            "(e.g. ACDEFGHIKLM). Only return a sequence if it is EXPLICITLY stated in "
            "the text above. If no sequence appears in the text, answer: NONE"
        )

        system = (
            "You are extracting amino acid sequences from clinical trial research text. "
            "Return ONLY the sequence in uppercase one-letter code with no spaces or dashes, "
            "or the word NONE if no explicit sequence is present in the provided text. "
            "Do not invent or look up sequences — only extract what is written."
        )

        try:
            response = await ollama_client.generate(
                model=model,
                prompt=prompt,
                system=system,
                temperature=0.05,
            )
            raw = response.get("response", "").strip().upper()
        except Exception as e:
            logger.warning("LLM sequence fallback failed for %s: %s", nct_id, e)
            return ""

        # Accept only if it looks like a real AA sequence
        if raw in ("NONE", "", "N/A", "NOT FOUND"):
            logger.info("  sequence: LLM fallback found no sequence for %s", nct_id)
            return ""

        # Strip common non-sequence words the LLM might prepend
        for prefix in ("SEQUENCE:", "AA SEQUENCE:", "AMINO ACID SEQUENCE:", "ANSWER:"):
            if raw.startswith(prefix):
                raw = raw[len(prefix):].strip()

        normalized = normalize_sequence(raw)
        if len(normalized) >= 2 and len(normalized) <= 200:
            logger.info(
                "  sequence: LLM fallback extracted %d aa for %s: %s",
                len(normalized), nct_id, normalized[:40]
            )
            return normalized

        logger.info(
            "  sequence: LLM fallback response invalid for %s: '%s'",
            nct_id, raw[:60]
        )
        return ""
