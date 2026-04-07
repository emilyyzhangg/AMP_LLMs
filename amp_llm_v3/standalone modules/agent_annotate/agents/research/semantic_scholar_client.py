"""
Semantic Scholar Research Agent.

Searches Semantic Scholar (200M+ papers) for trial-related publications.
Free API, 100 req/5 min unauthenticated. The TLDR field provides an
AI-generated 1-sentence summary uniquely valuable for outcome classification.

v31: Reintroduced as standalone agent (removed from LiteratureAgent in v8
due to 429s). Now uses resilient_get() with conservative concurrency (3).
"""

import logging
from typing import Optional
from datetime import datetime

import httpx

logger = logging.getLogger("agent_annotate.research.semantic_scholar")

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper"
FIELDS = "title,abstract,tldr,citationCount,externalIds,year,url"


class SemanticScholarClient(BaseResearchAgent):
    """Searches Semantic Scholar for trial-related publications with TLDRs."""

    agent_name = "semantic_scholar"
    sources = ["semantic_scholar"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        async with httpx.AsyncClient(timeout=20) as client:
            # Strategy 1: Search by NCT ID
            nct_citations = await self._search(nct_id, client)
            citations.extend(nct_citations)
            raw_data["ss_nct_hits"] = len(nct_citations)

            # Strategy 2: Always try title keywords (SS rarely indexes NCT IDs)
            if metadata:
                title = metadata.get("title", "")
                if title:
                    words = [w for w in title.split() if len(w) > 3][:6]
                    if words:
                        fallback = await self._search(" ".join(words), client)
                        # Deduplicate against NCT results
                        seen_ids = {c.identifier for c in citations if c.identifier}
                        new = [c for c in fallback if c.identifier not in seen_ids]
                        citations.extend(new[:3])
                        raw_data["ss_fallback_hits"] = len(new)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _search(
        self, query: str, client: httpx.AsyncClient
    ) -> list[SourceCitation]:
        params = {
            "query": query,
            "limit": 5,
            "fields": FIELDS,
        }
        try:
            resp = await resilient_get(SEARCH_URL, client=client, params=params)
            if resp.status_code != 200:
                logger.warning(
                    f"Semantic Scholar search returned {resp.status_code} for '{query}'"
                )
                return []
            data = resp.json()
        except Exception as e:
            logger.warning(f"Semantic Scholar search failed for '{query}': {e}")
            return []

        citations = []
        for paper in data.get("data", [])[:5]:
            title = paper.get("title", "")
            abstract = paper.get("abstract", "")
            tldr = paper.get("tldr", {})
            tldr_text = tldr.get("text", "") if isinstance(tldr, dict) else ""
            year = paper.get("year", "")
            cited_by = paper.get("citationCount", 0)
            url = paper.get("url", "")

            ext_ids = paper.get("externalIds", {}) or {}
            pmid = ext_ids.get("PubMed", "")
            doi = ext_ids.get("DOI", "")

            # Build snippet — TLDR is the key value-add
            parts = []
            if title:
                parts.append(f"Title: {title}")
            if tldr_text:
                parts.append(f"TLDR: {tldr_text}")
            if year:
                parts.append(f"Year: {year}")
            if cited_by:
                parts.append(f"Citations: {cited_by}")
            if abstract and not tldr_text:
                parts.append(f"Abstract: {abstract[:200]}")
            snippet = "\n".join(parts)

            identifier = f"PMID:{pmid}" if pmid else (f"DOI:{doi}" if doi else "")

            citations.append(SourceCitation(
                source_name="semantic_scholar",
                source_url=url,
                identifier=identifier,
                title=title,
                snippet=snippet,
                quality_score=self.compute_quality_score("semantic_scholar"),
                retrieved_at=datetime.utcnow().isoformat(),
            ))

        return citations
