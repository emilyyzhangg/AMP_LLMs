"""
OpenAlex Research Agent.

Searches OpenAlex (250M+ scholarly works) for publications related to
a clinical trial. Free API with polite pool (10 req/sec with email).

v31: New agent for improved literature coverage, especially for outcome.
"""

import asyncio
import logging
from typing import Optional
from datetime import datetime

import httpx

logger = logging.getLogger("agent_annotate.research.openalex")

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

try:
    from app.config import OPENALEX_EMAIL
except ImportError:
    OPENALEX_EMAIL = ""

API_URL = "https://api.openalex.org/works"


class OpenAlexClient(BaseResearchAgent):
    """Searches OpenAlex for trial-related publications."""

    agent_name = "openalex"
    sources = ["openalex"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        async with httpx.AsyncClient(timeout=20) as client:
            # Strategy 1: Search by NCT ID
            nct_citations = await self._search_by_nct(nct_id, client)
            citations.extend(nct_citations)
            raw_data["openalex_nct_hits"] = len(nct_citations)

            # Strategy 2: Fallback by title + intervention keywords
            if not nct_citations and metadata:
                title = metadata.get("title", "")
                interventions = self._extract_interventions(metadata)
                fallback_citations = await self._search_by_keywords(
                    nct_id, title, interventions, client
                )
                citations.extend(fallback_citations)
                raw_data["openalex_fallback_hits"] = len(fallback_citations)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )

    async def _search_by_nct(
        self, nct_id: str, client: httpx.AsyncClient
    ) -> list[SourceCitation]:
        params = {
            "search": nct_id,
            "per_page": 10,
            "sort": "cited_by_count:desc",
        }
        if OPENALEX_EMAIL:
            params["mailto"] = OPENALEX_EMAIL

        try:
            resp = await resilient_get(API_URL, client=client, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception as e:
            logger.warning(f"OpenAlex NCT search failed for {nct_id}: {e}")
            return []

        return self._parse_results(data, nct_id)

    async def _search_by_keywords(
        self,
        nct_id: str,
        title: str,
        interventions: list[str],
        client: httpx.AsyncClient,
    ) -> list[SourceCitation]:
        # Build query from significant title words + first intervention
        words = [w for w in title.split() if len(w) > 3][:5]
        if interventions:
            words.append(interventions[0])
        if not words:
            return []

        query = " ".join(words)
        params = {
            "search": query,
            "filter": "type:article",
            "per_page": 5,
            "sort": "relevance_score:desc",
        }
        if OPENALEX_EMAIL:
            params["mailto"] = OPENALEX_EMAIL

        try:
            resp = await resilient_get(API_URL, client=client, params=params)
            if resp.status_code != 200:
                return []
            data = resp.json()
        except Exception as e:
            logger.warning(f"OpenAlex keyword search failed for {nct_id}: {e}")
            return []

        return self._parse_results(data, nct_id)

    def _parse_results(self, data: dict, nct_id: str) -> list[SourceCitation]:
        citations = []
        for work in data.get("results", [])[:5]:
            title = work.get("title", "")
            doi = work.get("doi", "")
            pmid = ""
            ids = work.get("ids", {})
            if ids.get("pmid"):
                pmid = ids["pmid"].replace("https://pubmed.ncbi.nlm.nih.gov/", "")

            abstract = self._reconstruct_abstract(work.get("abstract_inverted_index"))
            year = work.get("publication_year", "")
            cited_by = work.get("cited_by_count", 0)

            # Build snippet
            parts = []
            if title:
                parts.append(f"Title: {title}")
            if year:
                parts.append(f"Year: {year}")
            if cited_by:
                parts.append(f"Citations: {cited_by}")
            if abstract:
                parts.append(f"Abstract: {abstract[:250]}")
            snippet = "\n".join(parts)

            identifier = f"PMID:{pmid}" if pmid else (doi or work.get("id", ""))

            citations.append(SourceCitation(
                source_name="openalex",
                source_url=work.get("id", ""),
                identifier=identifier,
                title=title,
                snippet=snippet,
                quality_score=self.compute_quality_score("openalex"),
                retrieved_at=datetime.utcnow().isoformat(),
            ))
        return citations

    @staticmethod
    def _reconstruct_abstract(inverted_index: Optional[dict]) -> str:
        if not inverted_index:
            return ""
        try:
            word_positions = []
            for word, positions in inverted_index.items():
                for pos in positions:
                    word_positions.append((pos, word))
            word_positions.sort()
            return " ".join(w for _, w in word_positions)
        except Exception:
            return ""

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
