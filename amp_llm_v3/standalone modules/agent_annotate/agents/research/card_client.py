"""
CARD Research Agent.

Queries the Comprehensive Antibiotic Resistance Database
(https://card.mcmaster.ca) for antibiotic resistance ontology data,
resistance mechanisms, associated antibiotics, and pathogen targets.

CARD uses internal AJAX endpoints (livesearch + load/json) rather than
a formal REST API. Both are free with no authentication.
"""

import re
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

CARD_BASE = "https://card.mcmaster.ca"
CARD_LIVESEARCH_URL = f"{CARD_BASE}/livesearch"
CARD_JSON_URL = f"{CARD_BASE}/load/json"

# Regex to extract ontology IDs and names from livesearch HTML
_LIVESEARCH_RE = re.compile(
    r"<a\s+href=['\"]https?://card\.mcmaster\.ca/ontology/(\d+)['\"]>"
    r"([^<]+)</a>",
    re.IGNORECASE,
)


class CARDClient(BaseResearchAgent):
    """Queries CARD for antibiotic resistance mechanisms and ontology data."""

    agent_name = "card"
    sources = ["card"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        # Extract intervention names to search for resistance-related terms
        interventions: list[str] = []
        if metadata:
            interventions = metadata.get("interventions", [])
            if isinstance(interventions, list):
                interventions = [str(i) for i in interventions]

        if not interventions:
            return ResearchResult(
                agent_name=self.agent_name,
                nct_id=nct_id,
                citations=[],
                raw_data={"note": "No interventions to search"},
            )

        async with httpx.AsyncClient(timeout=15) as client:
            # Load the full ARO JSON once (cached across interventions)
            aro_index = await self._load_aro_index(client, raw_data)

            for intervention in interventions[:3]:
                try:
                    # Step 1: livesearch to find matching ontology entries
                    matches = await self._livesearch(client, intervention, raw_data)
                    raw_data[f"card_{intervention}_matches"] = len(matches)

                    if not matches:
                        continue

                    # Step 2: enrich each match with ARO index data
                    for aro_id, aro_name in matches[:3]:
                        entry = aro_index.get(aro_id, {})
                        citation = self._build_citation(
                            aro_id, aro_name, entry, intervention
                        )
                        if citation:
                            citations.append(citation)

                except Exception as e:
                    raw_data[f"card_{intervention}_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _livesearch(
        self,
        client: httpx.AsyncClient,
        query: str,
        raw_data: dict,
    ) -> list[tuple[str, str]]:
        """Search CARD via livesearch and return (aro_id, name) tuples."""
        try:
            resp = await resilient_get(
                CARD_LIVESEARCH_URL,
                client=client,
                params={"query": query},
                headers={
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            if resp.status_code != 200:
                raw_data[f"card_livesearch_{query}_status"] = resp.status_code
                return []

            data = resp.json()
            html_content = data.get("response", "")
            if not html_content:
                return []

            # Parse ontology IDs and names from the HTML response
            return _LIVESEARCH_RE.findall(html_content)

        except Exception as e:
            raw_data[f"card_livesearch_{query}_error"] = str(e)
            return []

    async def _load_aro_index(
        self,
        client: httpx.AsyncClient,
        raw_data: dict,
    ) -> dict:
        """Load the full ARO JSON index from CARD.

        Returns a dict keyed by ontology ID (str) with entry metadata.
        The response is large but cached by httpx within the session.
        """
        try:
            resp = await resilient_get(
                CARD_JSON_URL,
                client=client,
                headers={
                    "Accept": "application/json",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            if resp.status_code != 200:
                raw_data["card_aro_index_status"] = resp.status_code
                return {}

            data = resp.json()
            if not isinstance(data, dict):
                return {}

            # The response has error=false and data={id: {...}, ...}
            index = data.get("data", data)
            raw_data["card_aro_index_size"] = len(index)
            return index

        except Exception as e:
            raw_data["card_aro_index_error"] = str(e)
            return {}

    def _build_citation(
        self,
        aro_id: str,
        aro_name: str,
        entry: dict,
        intervention: str,
    ) -> Optional[SourceCitation]:
        """Build a SourceCitation from an ARO entry."""
        if not isinstance(entry, dict):
            # Minimal citation from livesearch alone
            return SourceCitation(
                source_name="card",
                source_url=f"{CARD_BASE}/ontology/{aro_id}",
                identifier=f"ARO:{aro_id}",
                title=f"{aro_name} - CARD",
                snippet=f"ARO term: {aro_name}\nSearch term: {intervention}",
                quality_score=self.compute_quality_score("card", has_content=False),
                retrieved_at=datetime.utcnow().isoformat(),
            )

        accession = entry.get("accession", "")
        name = entry.get("name", aro_name)
        comment = entry.get("comment", "")
        synonyms = entry.get("synonym", "")
        short_names = entry.get("CARD_short_names", "")

        # Extract key information from the comment field
        # CARD comments often embed PMIDs, mechanism keywords, and organism names
        resistance_info = self._parse_comment(comment)

        snippet_parts = [f"ARO term: {name}"]
        if accession:
            snippet_parts.append(f"Accession: {accession}")
        if short_names:
            snippet_parts.append(f"Short names: {short_names}")
        if synonyms:
            syn_str = synonyms.strip() if isinstance(synonyms, str) else str(synonyms)
            if syn_str:
                snippet_parts.append(f"Synonyms: {syn_str[:150]}")
        if resistance_info.get("mechanisms"):
            snippet_parts.append(f"Resistance mechanisms: {', '.join(resistance_info['mechanisms'])}")
        if resistance_info.get("antibiotics"):
            snippet_parts.append(f"Associated antibiotics: {', '.join(resistance_info['antibiotics'])}")
        if resistance_info.get("organisms"):
            snippet_parts.append(f"Pathogen targets: {', '.join(resistance_info['organisms'])}")
        if resistance_info.get("pmids"):
            snippet_parts.append(f"References: {', '.join(resistance_info['pmids'][:5])}")

        has_content = bool(name and (resistance_info.get("mechanisms") or comment))
        return SourceCitation(
            source_name="card",
            source_url=f"{CARD_BASE}/ontology/{aro_id}",
            identifier=accession or f"ARO:{aro_id}",
            title=f"{name} - CARD",
            snippet="\n".join(snippet_parts),
            quality_score=self.compute_quality_score("card", has_content=has_content),
            retrieved_at=datetime.utcnow().isoformat(),
        )

    @staticmethod
    def _parse_comment(comment: str) -> dict:
        """Extract structured info from CARD comment fields.

        CARD comments are semi-structured text containing PMIDs, organism
        names, antibiotic names, and mechanism keywords separated by spaces.
        """
        result: dict = {
            "mechanisms": [],
            "antibiotics": [],
            "organisms": [],
            "pmids": [],
        }
        if not comment:
            return result

        # Extract PMIDs
        pmids = re.findall(r"PMID:\d+", comment)
        result["pmids"] = pmids

        # Common resistance mechanism keywords
        mechanism_keywords = [
            "efflux", "beta-lactamase", "target modification",
            "target alteration", "target replacement", "target protection",
            "antibiotic inactivation", "reduced permeability",
            "major facilitator superfamily", "MFS", "ABC transporter",
            "aminoglycoside modifying enzyme", "ribosomal protection",
        ]
        for kw in mechanism_keywords:
            if kw.lower() in comment.lower():
                result["mechanisms"].append(kw)

        # Common antibiotic class keywords
        antibiotic_keywords = [
            "tetracycline", "vancomycin", "penicillin", "cephalosporin",
            "carbapenem", "fluoroquinolone", "aminoglycoside", "macrolide",
            "polymyxin", "colistin", "rifampin", "sulfonamide",
            "trimethoprim", "linezolid", "daptomycin", "lipopeptide",
        ]
        for ab in antibiotic_keywords:
            if ab.lower() in comment.lower():
                result["antibiotics"].append(ab)

        # Common pathogen genus names
        organism_keywords = [
            "Staphylococcus", "Enterococcus", "Escherichia",
            "Klebsiella", "Pseudomonas", "Acinetobacter",
            "Streptococcus", "Clostridioides", "Mycobacterium",
            "Salmonella", "Campylobacter", "Neisseria",
        ]
        for org in organism_keywords:
            if org in comment:
                result["organisms"].append(org)

        return result
