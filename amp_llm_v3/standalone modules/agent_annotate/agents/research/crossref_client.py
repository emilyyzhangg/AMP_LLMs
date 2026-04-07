"""
CrossRef Research Agent.

Searches CrossRef for publications related to a clinical trial.
Free API, no auth needed. Email in User-Agent for polite pool.
Fills gaps for papers not indexed in PubMed (preprints, non-indexed journals).

v31: New agent for supplementary literature coverage.
"""

import logging
from typing import Optional
from datetime import datetime

import httpx

logger = logging.getLogger("agent_annotate.research.crossref")

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

try:
    from app.config import CROSSREF_EMAIL
except ImportError:
    CROSSREF_EMAIL = ""

WORKS_URL = "https://api.crossref.org/works"


class CrossRefClient(BaseResearchAgent):
    """Searches CrossRef for trial-related publications."""

    agent_name = "crossref"
    sources = ["crossref"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        headers = {}
        if CROSSREF_EMAIL:
            headers["User-Agent"] = f"agent-annotate/31 (mailto:{CROSSREF_EMAIL})"

        async with httpx.AsyncClient(timeout=20) as client:
            # Strategy 1: Search by NCT ID
            nct_citations = await self._search(nct_id, client, headers)
            citations.extend(nct_citations)
            raw_data["crossref_nct_hits"] = len(nct_citations)

            # Strategy 2: Always try title keywords (NCT IDs rarely in CrossRef)
            if metadata:
                title = metadata.get("title", "")
                if title:
                    words = [w for w in title.split() if len(w) > 3][:5]
                    interventions = self._extract_interventions(metadata)
                    if interventions:
                        words.append(interventions[0])
                    if words:
                        query = " ".join(words)
                        fallback = await self._search(query, client, headers)
                        citations.extend(fallback[:3])
                        raw_data["crossref_fallback_hits"] = len(fallback)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _search(
        self, query: str, client: httpx.AsyncClient, headers: dict
    ) -> list[SourceCitation]:
        params = {
            "query": query,
            "rows": 5,
            "sort": "relevance",
        }
        try:
            resp = await resilient_get(
                WORKS_URL, client=client, params=params, headers=headers
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception as e:
            logger.warning(f"CrossRef search failed for '{query}': {e}")
            return []

        items = data.get("message", {}).get("items", [])
        citations = []
        for item in items[:5]:
            title_list = item.get("title", [])
            title = title_list[0] if title_list else ""
            doi = item.get("DOI", "")
            abstract = item.get("abstract", "")
            # CrossRef abstracts sometimes have JATS XML tags
            if abstract:
                import re
                abstract = re.sub(r"<[^>]+>", "", abstract)

            journal = ""
            container = item.get("container-title", [])
            if container:
                journal = container[0]

            year = ""
            date_parts = item.get("published", {}).get("date-parts", [[]])
            if date_parts and date_parts[0]:
                year = str(date_parts[0][0])

            parts = []
            if title:
                parts.append(f"Title: {title}")
            if journal:
                parts.append(f"Journal: {journal}")
            if year:
                parts.append(f"Year: {year}")
            if abstract:
                parts.append(f"Abstract: {abstract[:250]}")
            snippet = "\n".join(parts)

            identifier = f"DOI:{doi}" if doi else ""

            citations.append(SourceCitation(
                source_name="crossref",
                source_url=f"https://doi.org/{doi}" if doi else "",
                identifier=identifier,
                title=title,
                snippet=snippet,
                quality_score=self.compute_quality_score("crossref"),
                retrieved_at=datetime.utcnow().isoformat(),
            ))

        return citations

    @staticmethod
    def _extract_interventions(metadata: dict) -> list[str]:
        interventions = metadata.get("interventions", [])
        names = []
        for item in interventions[:3]:
            if isinstance(item, dict):
                names.append(item.get("name", ""))
            elif isinstance(item, str):
                names.append(item)
        return [n for n in names if n]
