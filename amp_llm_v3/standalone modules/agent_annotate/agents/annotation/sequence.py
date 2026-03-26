"""
Sequence Annotation Agent (v14, v17 scoring fixes).

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


def _parse_helm_sequence(helm: str) -> str:
    """Parse a ChEMBL HELM notation string to extract linear AA sequence.

    HELM format examples:
      PEPTIDE1{A.S.T.T.T.N.Y.T}$$$$  → ASTTTNYT
      PEPTIDE1{[ac].M.P.P.A.D.E.D.Y.S.P.[am]}$$$$  → MPPADEDYSP
      PEPTIDE1{H.S.Q.G.T.F.T.S.D.Y.S.R.Y.L.D}$$$$  → HSQGTFTSDYSRYLD

    Extracts content between { and }, splits on '.', keeps single uppercase
    letters, discards bracket-enclosed modifications like [ac], [am], [dR].
    """
    if not helm:
        return ""

    # Find the peptide chain content between braces
    match = re.search(r"PEPTIDE\d*\{([^}]+)\}", helm, re.IGNORECASE)
    if not match:
        return ""

    tokens = match.group(1).split(".")
    aa_letters = []
    for token in tokens:
        token = token.strip()
        # Skip bracket-enclosed modifications: [ac], [am], [dR], [Aib], etc.
        if token.startswith("["):
            continue
        # Single uppercase letter = standard amino acid
        if len(token) == 1 and token.isupper() and token in _VALID_AA:
            aa_letters.append(token)
        # Two-char token starting with lowercase d = D-amino acid, take the AA letter
        elif len(token) == 2 and token[0] == "d" and token[1].isupper():
            aa_letters.append(token[1])

    seq = "".join(aa_letters)
    return seq if len(seq) >= 2 else ""


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
    """Extract intervention names from metadata, stripping type prefixes."""
    if not metadata:
        return []
    raw = metadata.get("interventions", [])
    if not isinstance(raw, list):
        return []
    names = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("intervention_name") or ""
            if name:
                names.append(_strip_intervention_prefix(str(name)))
        elif isinstance(item, str) and item:
            names.append(_strip_intervention_prefix(item))
    return names


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

        # Extract intervention names — try metadata first, fall back to raw_data keys
        interventions = _extract_intervention_names(metadata)
        if not interventions:
            interventions = _extract_interventions_from_raw_data(all_raw)
            if interventions:
                reasoning_parts.append(
                    f"Interventions extracted from raw_data keys: {interventions[:3]}"
                )

        # Also keep citation references for evidence attribution
        citations_by_source: dict[str, list[SourceCitation]] = {}
        for result in research_results:
            if result.error:
                continue
            for cite in result.citations:
                citations_by_source.setdefault(cite.source_name, []).append(cite)

        # --- Phase 1: Collect candidates from structured raw_data ---

        for intervention in interventions:
            # 1. DBAASP structured sequences
            # Key is dbaasp_{name}_sequences when matches exist
            dbaasp_seqs = all_raw.get(f"dbaasp_{intervention}_sequences", [])
            if not dbaasp_seqs:
                # Fallback: some versions store entries under the base key
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
                        "relevance": 0.9,  # Already name-filtered by research agent
                        "length": len(seq),
                        "is_mature": True,
                        "accession": entry.get("dbaasp_id", ""),
                    })
                    reasoning_parts.append(f"DBAASP: {entry.get('name', '')} ({len(seq)} aa)")

            # 2. APD structured sequences
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
                    for mol in (mols if isinstance(mols, list) else []):
                        if isinstance(mol, dict) and mol.get("helm_notation"):
                            helm = mol["helm_notation"]
                            break
                    if helm:
                        break
            if helm:
                seq = _parse_helm_sequence(helm)
                if seq:
                    candidates.append({
                        "sequence": seq,
                        "source": "chembl_helm",
                        "protein_name": intervention,
                        "relevance": 0.85,
                        "length": len(seq),
                        "is_mature": True,
                        "accession": "",
                    })
                    reasoning_parts.append(f"ChEMBL HELM: parsed {len(seq)} aa from {helm[:40]}")

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

                if best_fragment:
                    norm = normalize_sequence(best_fragment)
                    if norm:
                        candidates.append({
                            "sequence": norm,
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
        # Filter to ≤100 AA, take at most 2
        final = [c for c in unique_candidates if c["length"] <= 100][:2]
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
            value = " | ".join(c["sequence"] for c in final)
            confidence = min(0.95, 0.7 + 0.05 * len(evidence))
            reasoning = (
                f"[Structured v14] Extracted {len(final)} sequence(s) "
                f"from {len(candidates)} candidates. "
                + "; ".join(reasoning_parts)
            )
        else:
            value = ""
            confidence = 0.0
            reasoning = "[Structured v14] No amino acid sequence found in research data."
            if reasoning_parts:
                reasoning += " Notes: " + "; ".join(reasoning_parts)

        return FieldAnnotation(
            field_name="sequence",
            value=value,
            confidence=confidence,
            reasoning=reasoning,
            evidence=evidence,
            model_name="deterministic" if not used_llm else "qwen2.5:14b",
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
        model = getattr(config.orchestrator, "annotation_model", "qwen2.5:14b")

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
