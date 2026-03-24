"""
Sequence Annotation Agent (v12).

Extracts amino acid sequences from research dossier data.
Purely deterministic — no LLM needed. Sequences come from UniProt,
DRAMP, EBI Proteins, APD, and other protein databases.

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
        """Extract sequence from research results. No LLM call."""

        sequences: list[str] = []
        evidence: list[SourceCitation] = []
        reasoning_parts: list[str] = []

        for result in research_results:
            if result.error:
                continue

            # 1. Check raw_data for UniProt sequence fields
            for key, val in (result.raw_data or {}).items():
                if not isinstance(val, list):
                    continue

                for entry in val:
                    if not isinstance(entry, dict):
                        continue

                    # UniProt format: entry.sequence.value
                    seq_obj = entry.get("sequence", {})
                    if isinstance(seq_obj, dict):
                        raw_seq = seq_obj.get("value", "")
                        if raw_seq:
                            norm = normalize_sequence(raw_seq)
                            if norm and norm not in sequences:
                                sequences.append(norm)
                                accession = entry.get("primaryAccession", "")
                                protein = ""
                                pd = entry.get("proteinDescription", {})
                                rn = pd.get("recommendedName", {})
                                if rn:
                                    protein = rn.get("fullName", {}).get("value", "")
                                reasoning_parts.append(
                                    f"UniProt {accession}: {protein} ({len(norm)} aa)"
                                )
                                evidence.append(SourceCitation(
                                    source_name="uniprot",
                                    source_url=f"https://www.uniprot.org/uniprotkb/{accession}",
                                    identifier=accession,
                                    title=protein or accession,
                                    snippet=f"Sequence: {norm[:60]}{'...' if len(norm) > 60 else ''} ({len(norm)} aa)",
                                    quality_score=0.95,
                                ))

            # 2. Check citation snippets for sequence data
            for citation in result.citations:
                if citation.source_name in ("uniprot", "ebi_proteins", "dramp", "dbaasp", "apd"):
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

        # Build result
        if sequences:
            # Pipe-separate multiple sequences (matching human annotation format)
            value = " | ".join(sequences)
            confidence = min(0.95, 0.7 + 0.05 * len(evidence))
            reasoning = f"[Deterministic v12] Extracted {len(sequences)} sequence(s) from research data. " + "; ".join(reasoning_parts)
        else:
            value = ""
            confidence = 0.0
            reasoning = "[Deterministic v12] No amino acid sequence found in research data."

        return FieldAnnotation(
            field_name="sequence",
            value=value,
            confidence=confidence,
            reasoning=reasoning,
            evidence=evidence,
            model_name="deterministic",
            skip_verification=True,  # Database extraction, no LLM verification needed
        )
