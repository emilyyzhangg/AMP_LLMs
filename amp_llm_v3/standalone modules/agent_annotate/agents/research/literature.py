"""
Literature Research Agent.

Searches PubMed, PMC, and PMC BioC for published research related to a clinical trial.
"""

from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from app.models.research import ResearchResult, SourceCitation
from app.config import PUBMED_API_KEY

PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PMC_OA_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi"


class LiteratureAgent(BaseResearchAgent):
    """Searches biomedical literature databases for trial-related publications."""

    agent_name = "literature"
    sources = ["pubmed", "pmc", "pmc_bioc"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        citations = []
        raw_data = {}

        # Build search query from NCT ID and metadata
        query_parts = [nct_id]
        if metadata:
            if metadata.get("conditions"):
                query_parts.extend(metadata["conditions"][:2])
            if metadata.get("interventions"):
                query_parts.extend(str(i) for i in metadata["interventions"][:2])
        search_query = " OR ".join(query_parts)

        # 1. PubMed search
        try:
            params = {
                "db": "pubmed",
                "term": search_query,
                "retmax": 5,
                "retmode": "json",
                "sort": "relevance",
            }
            if PUBMED_API_KEY:
                params["api_key"] = PUBMED_API_KEY

            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(PUBMED_SEARCH_URL, params=params)
                if resp.status_code == 200:
                    search_data = resp.json()
                    id_list = search_data.get("esearchresult", {}).get("idlist", [])
                    raw_data["pubmed_ids"] = id_list

                    # Fetch summaries for found PMIDs
                    if id_list:
                        summary_resp = await client.get(
                            PUBMED_SUMMARY_URL,
                            params={
                                "db": "pubmed",
                                "id": ",".join(id_list),
                                "retmode": "json",
                            },
                        )
                        if summary_resp.status_code == 200:
                            summary_data = summary_resp.json()
                            results = summary_data.get("result", {})
                            for pmid in id_list:
                                article = results.get(pmid, {})
                                if isinstance(article, dict) and article.get("title"):
                                    citations.append(SourceCitation(
                                        source_name="pubmed",
                                        source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                                        identifier=f"PMID:{pmid}",
                                        title=article.get("title", ""),
                                        snippet=article.get("sorttitle", "")[:300],
                                        quality_score=self.compute_quality_score("pubmed"),
                                        retrieved_at=datetime.utcnow().isoformat(),
                                    ))
        except Exception as e:
            raw_data["pubmed_error"] = str(e)

        # 2. PMC search (open access full text)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                pmc_params = {
                    "db": "pmc",
                    "term": f"{nct_id}[Abstract]",
                    "retmax": 3,
                    "retmode": "json",
                }
                resp = await client.get(PUBMED_SEARCH_URL, params=pmc_params)
                if resp.status_code == 200:
                    pmc_data = resp.json()
                    pmc_ids = pmc_data.get("esearchresult", {}).get("idlist", [])
                    raw_data["pmc_ids"] = pmc_ids
                    for pmc_id in pmc_ids:
                        citations.append(SourceCitation(
                            source_name="pmc",
                            source_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/",
                            identifier=f"PMC:{pmc_id}",
                            title=f"PMC Article {pmc_id}",
                            snippet="",
                            quality_score=self.compute_quality_score("pmc", has_content=False),
                            retrieved_at=datetime.utcnow().isoformat(),
                        ))
        except Exception as e:
            raw_data["pmc_error"] = str(e)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=citations,
            raw_data=raw_data,
        )
