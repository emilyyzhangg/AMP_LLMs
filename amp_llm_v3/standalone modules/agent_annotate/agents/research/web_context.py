"""
Web Context Research Agent.

Searches DuckDuckGo, SerpAPI, and Google Scholar for broader context
about clinical trials and their outcomes.

SerpAPI has rate limits (~100 searches/month on free tier, higher on paid).
A global semaphore throttles concurrent SerpAPI calls to avoid 429 errors,
and a delay between calls prevents burst-rate violations.
"""

import logging
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation

logger = logging.getLogger("agent_annotate.research.web_context")

DDG_API_URL = "https://api.duckduckgo.com/"


class WebContextAgent(BaseResearchAgent):
    """Gathers broader web context about a clinical trial."""

    agent_name = "web_context"
    sources = ["duckduckgo"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # Build search query
        query_parts = [nct_id]
        if metadata:
            if metadata.get("title"):
                query_parts.append(metadata["title"][:80])
            elif metadata.get("conditions"):
                query_parts.extend(metadata["conditions"][:2])

        search_query = " ".join(query_parts)

        async with httpx.AsyncClient(timeout=20) as client:
            # 1. DuckDuckGo Instant Answer API
            try:
                resp = await resilient_get(
                    DDG_API_URL,
                    client=client,
                    params={"q": search_query, "format": "json", "no_html": 1},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw_data["duckduckgo"] = data

                    # Extract abstract / related topics
                    abstract = data.get("Abstract", "")
                    if abstract:
                        citations.append(SourceCitation(
                            source_name="duckduckgo",
                            source_url=data.get("AbstractURL", ""),
                            identifier=nct_id,
                            title=data.get("Heading", "DuckDuckGo Result"),
                            snippet=abstract[:500],
                            quality_score=self.compute_quality_score("duckduckgo"),
                            retrieved_at=datetime.utcnow().isoformat(),
                        ))

                    for topic in data.get("RelatedTopics", [])[:3]:
                        if isinstance(topic, dict) and topic.get("Text"):
                            citations.append(SourceCitation(
                                source_name="duckduckgo",
                                source_url=topic.get("FirstURL", ""),
                                identifier=nct_id,
                                title=topic.get("Text", "")[:100],
                                snippet=topic.get("Text", "")[:300],
                                quality_score=self.compute_quality_score("duckduckgo"),
                                retrieved_at=datetime.utcnow().isoformat(),
                            ))
            except Exception as e:
                raw_data["duckduckgo_error"] = str(e)

            # SerpAPI removed — paid service, only free APIs in this design.
            # DuckDuckGo + Europe PMC + PubMed + other free agents provide
            # sufficient web context. Re-enable SerpAPI by uncommenting and
            # setting SERPAPI_KEY in the environment.

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )
