"""
Sequence Annotation Agent (v13).

Extracts amino acid sequences from research dossier data.
Purely deterministic — no LLM needed. Sequences come from UniProt,
DRAMP, EBI Proteins, APD, and other protein databases.

v13 changes:
  - Prioritize DRAMP/DBAASP/APD citation snippets (actual peptide sequences)
    over UniProt full precursor proteins
  - For UniProt entries, extract mature peptide/chain features instead of
    full precursor sequence (which can be 500-5000+ AA)
  - Cap full sequences at 200 AA (skip precursor-length ones)
  - Filter pipe-separated output to ≤100 AA per fragment

Normalization:
  - Uppercase all amino acid letters
  - Strip spaces within sequences
  - Remove modification prefixes/suffixes (Ac-, -NH2, etc.)
  - Pipe-separate multiple sequences
  - Preserve non-standard AAs (X, B, Z, J, U, O)
"""

import re
import logging
from typing import Optional

from agents.base import BaseAnnotationAgent
from app.models.research import ResearchResult, SourceCitation
from app.models.annotation import FieldAnnotation

logger = logging.getLogger("agent_annotate.annotation.sequence")

# Standard amino acid letters + common non-standard codes
_AA_PATTERN = re.compile(r"[ACDEFGHIKLMNPQRSTVWYBZXUOJ]{3,}", re.IGNORECASE)

# Modification prefixes/suffixes to strip
_MOD_PREFIXES = re.compile(r"^(Ac-|H-|Fmoc-|Boc-|D-|L-|cyclo\()", re.IGNORECASE)
_MOD_SUFFIXES = re.compile(r"(-NH2|-OH|-COOH|-amide|-acid)$", re.IGNORECASE)


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
    cleaned = _MOD_PREFIXES.sub("", raw.strip())
    cleaned = _MOD_SUFFIXES.sub("", cleaned)

    # Remove spaces (human annotators space every 5 chars)
    cleaned = cleaned.replace(" ", "")

    # Remove dashes that are part of single-letter notation (K-K-W-W → KKWW)
    # but only if it looks like single-AA-dash notation
    if re.match(r"^[A-Z]-[A-Z]-", cleaned):
        cleaned = cleaned.replace("-", "")

    # Uppercase
    cleaned = cleaned.upper()

    # Validate: must contain at least 3 consecutive amino acid letters
    if not _AA_PATTERN.search(cleaned):
        return ""

    return cleaned


def extract_sequences_from_text(text: str) -> list[str]:
    """Extract amino acid sequences from free text.

    Finds stretches of 3+ amino acid characters, filters out
    common English words that happen to match.
    """
    if not text:
        return []

    # Common false positives (English words matching AA pattern)
    _FALSE_POSITIVES = {
        "THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT", "HAVE",
        "WILL", "WHICH", "THEIR", "EACH", "WERE", "BEEN", "THAN",
        "LENGTH", "PROTEIN", "PEPTIDE", "SEQUENCE", "TRIAL", "STUDY",
        "DRUG", "ACTIVE", "CLINICAL", "RESULTS", "PHASE", "SEARCH",
    }

    matches = _AA_PATTERN.findall(text)
    sequences = []
    for m in matches:
        upper = m.upper()
        if upper not in _FALSE_POSITIVES and len(upper) >= 5:
            sequences.append(upper)
    return sequences


class SequenceAgent(BaseAnnotationAgent):
    """Deterministic sequence extraction from research data."""

    field_name = "sequence"

    async def annotate(
        self,
        nct_id: str,
        research_results: list[ResearchResult],
        metadata: Optional[dict] = None,
    ) -> FieldAnnotation:
        """Extract sequence from research results. No LLM call.

        v13: Priority order for sequence extraction:
        1. DRAMP/DBAASP/APD citation snippets (actual peptide sequences)
        2. UniProt mature peptide/chain features (processed fragments)
        3. UniProt full sequence ONLY if ≤200 AA (skip precursors)
        4. Citation snippet parsing for explicit "Sequence: ..." strings
        """

        sequences: list[str] = []
        evidence: list[SourceCitation] = []
        reasoning_parts: list[str] = []

        # --- Phase 1: DRAMP/DBAASP/APD citation snippets (highest priority) ---
        # These databases contain actual peptide sequences, not precursors
        for result in research_results:
            if result.error:
                continue
            for citation in result.citations:
                if citation.source_name in ("dramp", "dbaasp", "apd"):
                    snippet = citation.snippet or ""
                    found = extract_sequences_from_text(snippet)
                    for seq in found:
                        norm = normalize_sequence(seq)
                        if norm and norm not in sequences and len(norm) >= 5:
                            sequences.append(norm)
                            reasoning_parts.append(
                                f"{citation.source_name}: extracted {len(norm)} aa from snippet"
                            )
                            evidence.append(citation)

        # --- Phase 2: UniProt processed features (Chain, Peptide) ---
        # These are the mature drug fragments, not the full precursor protein
        for result in research_results:
            if result.error:
                continue
            for key, val in (result.raw_data or {}).items():
                if not isinstance(val, list):
                    continue
                for entry in val:
                    if not isinstance(entry, dict):
                        continue

                    accession = entry.get("primaryAccession", "")
                    protein = ""
                    pd = entry.get("proteinDescription", {})
                    rn = pd.get("recommendedName", {})
                    if rn:
                        protein = rn.get("fullName", {}).get("value", "")

                    full_seq = ""
                    seq_obj = entry.get("sequence", {})
                    if isinstance(seq_obj, dict):
                        full_seq = seq_obj.get("value", "")

                    # Check for mature peptide/chain features
                    features = entry.get("features", [])
                    best_fragment = None
                    best_fragment_len = float("inf")

                    for feat in features:
                        if not isinstance(feat, dict):
                            continue
                        feat_type = feat.get("type", "")
                        if feat_type not in ("Chain", "Peptide"):
                            # Skip Signal peptide — that's the cleaved leader, not the drug
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
                            fragment = full_seq[start - 1:end]  # 1-based to 0-based
                            frag_len = len(fragment)
                            # Use the shortest non-signal fragment as the drug
                            if 2 <= frag_len <= 200 and frag_len < best_fragment_len:
                                best_fragment = fragment
                                best_fragment_len = frag_len

                    if best_fragment:
                        norm = normalize_sequence(best_fragment)
                        if norm and norm not in sequences:
                            sequences.append(norm)
                            reasoning_parts.append(
                                f"UniProt {accession}: {protein} — mature fragment ({len(norm)} aa from features)"
                            )
                            evidence.append(SourceCitation(
                                source_name="uniprot",
                                source_url=f"https://www.uniprot.org/uniprotkb/{accession}",
                                identifier=accession,
                                title=protein or accession,
                                snippet=f"Sequence (feature): {norm[:60]}{'...' if len(norm) > 60 else ''} ({len(norm)} aa)",
                                quality_score=0.95,
                            ))
                    elif full_seq:
                        # Phase 3: Fall back to full sequence ONLY if ≤200 AA
                        # Anything longer is a precursor protein, not useful
                        norm = normalize_sequence(full_seq)
                        if norm and norm not in sequences and len(norm) <= 200:
                            sequences.append(norm)
                            reasoning_parts.append(
                                f"UniProt {accession}: {protein} ({len(norm)} aa, full sequence ≤200)"
                            )
                            evidence.append(SourceCitation(
                                source_name="uniprot",
                                source_url=f"https://www.uniprot.org/uniprotkb/{accession}",
                                identifier=accession,
                                title=protein or accession,
                                snippet=f"Sequence: {norm[:60]}{'...' if len(norm) > 60 else ''} ({len(norm)} aa)",
                                quality_score=0.95,
                            ))
                        elif norm and len(norm) > 200:
                            reasoning_parts.append(
                                f"UniProt {accession}: skipped precursor ({len(norm)} aa > 200 cap)"
                            )

        # --- Phase 4: Parse citation snippets for explicit sequence strings ---
        # The peptide_identity agent includes "Sequence: ..." in UniProt snippets
        for result in research_results:
            if result.error:
                continue
            for citation in result.citations:
                if citation.source_name in ("uniprot", "ebi_proteins"):
                    snippet = citation.snippet or ""
                    # Look for explicit "Sequence: XXXX" in snippet
                    seq_match = re.search(r"Sequence:\s*([A-Za-z]{5,})", snippet)
                    if seq_match:
                        raw_seq = seq_match.group(1)
                        norm = normalize_sequence(raw_seq)
                        if norm and norm not in sequences and len(norm) <= 200:
                            sequences.append(norm)
                            reasoning_parts.append(
                                f"{citation.source_name}: extracted {len(norm)} aa from citation snippet"
                            )
                            evidence.append(citation)
                    else:
                        # Fall back to general sequence extraction from snippet
                        found = extract_sequences_from_text(snippet)
                        for seq in found:
                            norm = normalize_sequence(seq)
                            if norm and norm not in sequences and 5 <= len(norm) <= 200:
                                sequences.append(norm)
                                reasoning_parts.append(
                                    f"{citation.source_name}: extracted {len(norm)} aa from snippet"
                                )
                                evidence.append(citation)

        # --- Filter: only include sequences ≤100 AA in pipe-separated output ---
        filtered_sequences = [s for s in sequences if len(s) <= 100]
        if not filtered_sequences and sequences:
            # If all sequences were >100 AA, keep the shortest one as a fallback
            shortest = min(sequences, key=len)
            if len(shortest) <= 200:
                filtered_sequences = [shortest]
                reasoning_parts.append(
                    f"All sequences >100 aa; kept shortest ({len(shortest)} aa) as fallback"
                )

        # Build result
        if filtered_sequences:
            # Pipe-separate multiple sequences (matching human annotation format)
            value = " | ".join(filtered_sequences)
            confidence = min(0.95, 0.7 + 0.05 * len(evidence))
            reasoning = f"[Deterministic v13] Extracted {len(filtered_sequences)} sequence(s) from research data. " + "; ".join(reasoning_parts)
        else:
            value = ""
            confidence = 0.0
            reasoning = "[Deterministic v13] No amino acid sequence found in research data."
            if reasoning_parts:
                reasoning += " Notes: " + "; ".join(reasoning_parts)

        return FieldAnnotation(
            field_name="sequence",
            value=value,
            confidence=confidence,
            reasoning=reasoning,
            evidence=evidence,
            model_name="deterministic",
            skip_verification=True,  # Database extraction, no LLM verification needed
        )
