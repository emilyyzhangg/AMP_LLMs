"""
Peptide Identity Research Agent.

Looks up peptide/protein information from UniProt and DRAMP databases.

v14 changes:
  - Remove sequence from citation snippets (prevents Phase 4 re-extraction)
  - Add drug-protein relevance verification (_verify_protein_relevance)
  - Remove free-text UniProt search fallback (primary source of wrong proteins)
  - Remove free-text fallback within resolved-name loop
  - Tag results with _verified_relevance score for sequence agent
"""

import logging
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.peptide_identity")

UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"
DRAMP_SEARCH_URL = "http://dramp.cpu-bioinfor.org/browse/search.php"


def _extract_intervention_names(metadata: dict | None) -> list[str]:
    """Extract plain-string intervention names from metadata.

    Handles both list-of-dicts (``[{"name": "Nisin"}]``) and
    list-of-strings (``["Nisin"]``) formats.
    """
    if not metadata:
        return []
    raw = metadata.get("interventions", [])
    if not isinstance(raw, list):
        return []
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("intervention_name") or ""
            if name:
                names.append(str(name))
        elif isinstance(item, str) and item:
            names.append(item)
    return names


def _extract_resolved_names(metadata: dict | None) -> dict[str, list[str]]:
    """Extract resolved drug names (generic + synonyms) for each intervention.

    Returns a dict mapping original intervention name -> list of resolved names.
    Only includes interventions that have a non-empty 'resolved' key.
    """
    if not metadata:
        return {}
    raw = metadata.get("interventions", [])
    if not isinstance(raw, list):
        return {}
    resolved_map: dict[str, list[str]] = {}
    for item in raw:
        if isinstance(item, dict):
            name = item.get("name") or item.get("intervention_name") or ""
            resolved = item.get("resolved", [])
            if name and resolved:
                resolved_map[str(name)] = [str(r) for r in resolved]
    return resolved_map


def _verify_protein_relevance(intervention: str, entry: dict) -> float:
    """Score 0.0-1.0 how relevant a UniProt entry is to the intervention drug.

    Checks protein names, alternative names, gene names, and function
    descriptions against the intervention name. Returns 0.0 if no match
    (the protein is unrelated to the drug).
    """
    intervention_lower = intervention.lower().strip()
    if not intervention_lower:
        return 0.0

    # Collect all searchable text from the UniProt entry
    text_parts: list[str] = []

    # Recommended name
    pd = entry.get("proteinDescription", {}) or {}
    rec_name = pd.get("recommendedName", {}) or {}
    full_name = rec_name.get("fullName", {})
    if isinstance(full_name, dict):
        text_parts.append(full_name.get("value", ""))
    # Short names under recommended
    for sn in rec_name.get("shortNames", []):
        if isinstance(sn, dict):
            text_parts.append(sn.get("value", ""))

    # Alternative names
    for alt in pd.get("alternativeNames", []):
        if isinstance(alt, dict):
            fn = alt.get("fullName", {})
            if isinstance(fn, dict):
                text_parts.append(fn.get("value", ""))
            for sn in alt.get("shortNames", []):
                if isinstance(sn, dict):
                    text_parts.append(sn.get("value", ""))

    # Submitted names
    for sub in pd.get("submittedNames", []):
        if isinstance(sub, dict):
            fn = sub.get("fullName", {})
            if isinstance(fn, dict):
                text_parts.append(fn.get("value", ""))

    # Gene names
    for gene in entry.get("genes", []):
        if isinstance(gene, dict):
            gn = gene.get("geneName", {})
            if isinstance(gn, dict):
                text_parts.append(gn.get("value", ""))
            for syn in gene.get("synonyms", []):
                if isinstance(syn, dict):
                    text_parts.append(syn.get("value", ""))

    # Function description from comments
    for comment in entry.get("comments", []):
        if isinstance(comment, dict) and comment.get("type") == "FUNCTION":
            for text_entry in comment.get("texts", comment.get("text", [])):
                if isinstance(text_entry, dict):
                    text_parts.append(text_entry.get("value", ""))
                elif isinstance(text_entry, str):
                    text_parts.append(text_entry)

    combined = " ".join(t for t in text_parts if t).lower()
    if not combined:
        return 0.0

    # Exact match: intervention name found as-is in combined text
    if intervention_lower in combined:
        return 1.0

    # Check if combined text contains the intervention
    # (e.g., protein "Natriuretic peptides B" for intervention "BNP")
    if any(word in combined for word in intervention_lower.split()
           if len(word) > 3):
        # Partial word match — at least one significant word overlaps
        return 0.5

    # Reverse check: any protein name word appears in intervention
    for part in text_parts:
        part_lower = part.lower().strip()
        if part_lower and len(part_lower) > 3 and part_lower in intervention_lower:
            return 0.5

    return 0.0


class PeptideIdentityAgent(BaseResearchAgent):
    """Identifies peptide/protein entities from UniProt and DRAMP."""

    agent_name = "peptide_identity"
    sources = ["uniprot", "dramp"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # Extract intervention names to search for peptides
        interventions = _extract_intervention_names(metadata)
        # Layer 1: Get resolved drug names (generic + synonyms) for fallback searches
        resolved_names = _extract_resolved_names(metadata)

        if not interventions:
            return ResearchResult(
                agent_name=self.agent_name,
                nct_id=nct_id,
                citations=[],
                raw_data={"note": "No interventions to search"},
            )

        async with httpx.AsyncClient(timeout=20) as client:
            # 1. UniProt search — use protein_name field + human organism filter
            # to avoid returning scorpion/bacterial homologs for human drug queries.
            # v14: Only structured searches, no free-text fallback.
            for intervention in interventions[:3]:
                try:
                    # Structured query: search protein name in human proteome first
                    structured_query = f'(protein_name:"{intervention}") AND (organism_id:9606)'
                    resp = await resilient_get(
                        UNIPROT_SEARCH_URL,
                        client=client,
                        params={
                            "query": structured_query,
                            "format": "json",
                            "fields": "accession,protein_name,organism_name,sequence,ft_chain,ft_peptide",
                            "size": 3,
                        },
                        headers={"Accept": "application/json"},
                    )
                    results = []
                    if resp.status_code == 200:
                        data = resp.json()
                        results = data.get("results", [])

                    # If no human results, try broader search (any organism)
                    # but still use protein_name field, not free text
                    if not results:
                        broader_query = f'(protein_name:"{intervention}")'
                        resp = await resilient_get(
                            UNIPROT_SEARCH_URL,
                            client=client,
                            params={
                                "query": broader_query,
                                "format": "json",
                                "fields": "accession,protein_name,organism_name,sequence,ft_chain,ft_peptide",
                                "size": 3,
                            },
                            headers={"Accept": "application/json"},
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            results = data.get("results", [])

                    # v14: Free-text search REMOVED — it returned wrong proteins
                    # for drugs like "68Ga-RM2", "Albiglutide", "Neoantigen Vaccine".
                    # If structured protein_name searches return nothing, the
                    # intervention is not a natural protein in UniProt.
                    if not results:
                        raw_data[f"uniprot_{intervention}_no_structured_match"] = True

                    # Layer 1: If still no results, try resolved names (generic + synonyms)
                    # e.g., "BNP" returns nothing, but "nesiritide" returns a full entry
                    # v14: Only structured searches for resolved names too.
                    if not results and intervention in resolved_names:
                        for resolved_name in resolved_names[intervention]:
                            # Try structured query with resolved name
                            res_query = f'(protein_name:"{resolved_name}") AND (organism_id:9606)'
                            resp = await resilient_get(
                                UNIPROT_SEARCH_URL,
                                client=client,
                                params={
                                    "query": res_query,
                                    "format": "json",
                                    "fields": "accession,protein_name,organism_name,sequence,ft_chain,ft_peptide",
                                    "size": 3,
                                },
                                headers={"Accept": "application/json"},
                            )
                            if resp.status_code == 200:
                                data = resp.json()
                                results = data.get("results", [])
                            if results:
                                raw_data[f"uniprot_{intervention}_resolved_via"] = resolved_name
                                break

                            # v14: Free-text fallback for resolved names REMOVED.
                            # Structured protein_name search is sufficient.

                    # v14: Filter results by drug-protein relevance and tag scores
                    verified_results = []
                    for entry in results[:3]:
                        score = _verify_protein_relevance(intervention, entry)
                        entry["_verified_relevance"] = score
                        if score > 0.2:
                            verified_results.append(entry)
                        else:
                            acc = entry.get("primaryAccession", "?")
                            logger.info(
                                "  UniProt %s filtered out for '%s' (relevance=%.2f)",
                                acc, intervention, score,
                            )

                    raw_data[f"uniprot_{intervention}"] = verified_results[:3]
                    for entry in verified_results[:2]:
                        accession = entry.get("primaryAccession", "")
                        protein_name = ""
                        if entry.get("proteinDescription", {}).get("recommendedName"):
                            protein_name = entry["proteinDescription"]["recommendedName"].get("fullName", {}).get("value", "")
                        organism = entry.get("organism", {}).get("scientificName", "")
                        length = entry.get("sequence", {}).get("length", "")

                        # v14: Sequence REMOVED from snippet to prevent Phase 4
                        # re-extraction of precursor proteins. Sequence data lives
                        # in raw_data where the annotation agent accesses it structurally.
                        snippet = f"Organism: {organism}. Protein: {protein_name}. Accession: {accession}"
                        if length:
                            snippet += f". Length: {length} aa"

                        citations.append(SourceCitation(
                            source_name="uniprot",
                            source_url=f"https://www.uniprot.org/uniprotkb/{accession}",
                            identifier=accession,
                            title=protein_name or accession,
                            snippet=snippet,
                            quality_score=self.compute_quality_score("uniprot"),
                            retrieved_at=datetime.utcnow().isoformat(),
                        ))
                except Exception as e:
                    raw_data[f"uniprot_{intervention}_error"] = str(e)

            # 2. DRAMP search (antimicrobial peptide database)
            for intervention in interventions[:2]:
                try:
                    resp = await resilient_get(
                        DRAMP_SEARCH_URL,
                        client=client,
                        params={"keyword": intervention},
                        timeout=15,
                    )
                    if resp.status_code == 200:
                        # DRAMP returns HTML; we note the search was attempted
                        raw_data[f"dramp_{intervention}"] = {"searched": True, "status": resp.status_code}
                        citations.append(SourceCitation(
                            source_name="dramp",
                            source_url=f"http://dramp.cpu-bioinfor.org/",
                            identifier=intervention,
                            title=f"DRAMP search: {intervention}",
                            snippet=f"DRAMP antimicrobial peptide database search for: {intervention}",
                            quality_score=self.compute_quality_score("dramp", has_content=False),
                            retrieved_at=datetime.utcnow().isoformat(),
                        ))
                except Exception as e:
                    raw_data[f"dramp_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )
