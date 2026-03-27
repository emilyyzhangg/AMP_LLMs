"""
Literature Research Agent.

Searches PubMed, PMC, Europe PMC, and Semantic Scholar for published
research related to a clinical trial. Fetches actual abstracts for
high-quality annotation context.
"""

import asyncio
import xml.etree.ElementTree as ET
from typing import Optional
from datetime import datetime

import httpx

from agents.base import BaseResearchAgent
from agents.research.http_utils import resilient_get
from app.models.research import ResearchResult, SourceCitation
from app.config import PUBMED_API_KEY

# NCBI E-utilities
PUBMED_SEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_FETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
PUBMED_SUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"

# Europe PMC (free, no API key, returns abstracts in JSON)
EUROPE_PMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


class LiteratureAgent(BaseResearchAgent):
    """Searches biomedical literature databases for trial-related publications."""

    agent_name = "literature"
    # v8: Removed Semantic Scholar — heavy rate limiting (429 on every
    # batch, exhausts 3 retries). PubMed + PMC + Europe PMC provide
    # sufficient literature coverage for clinical trial annotation.
    sources = ["pubmed", "pmc", "europe_pmc"]

    async def research(self, nct_id: str, metadata: Optional[dict] = None) -> ResearchResult:
        raw_data = {}

        async with httpx.AsyncClient(timeout=30) as client:
            results = await asyncio.gather(
                self._search_pubmed(nct_id, client),
                self._search_pmc(nct_id, client),
                self._search_europe_pmc(nct_id, client),
                return_exceptions=True,
            )

        all_citations = []
        source_names = ["pubmed", "pmc", "europe_pmc"]

        # Check if any source returned results
        any_results = False
        for name, result in zip(source_names, results):
            if isinstance(result, Exception):
                raw_data[f"{name}_error"] = str(result)
            else:
                citations, data = result
                all_citations.extend(citations)
                raw_data.update(data)
                if citations:
                    any_results = True

        # Fallback for old trials: pre-2005 trials often have publications that
        # don't reference the NCT ID, so NCT ID search misses the primary paper.
        # Trigger conditions:
        #   (a) 0 results from NCT ID search — always try fallback
        #   (b) Old trial (NCT number < 100000) — primary paper may predate
        #       ClinicalTrials.gov registration, try title-based search too
        nct_num = int(nct_id.replace("NCT", "").lstrip("0") or "0")
        is_old_trial = nct_num < 100_000
        if (not any_results or is_old_trial) and metadata:
            interventions = metadata.get("interventions", [])
            title = metadata.get("title", "")
            if interventions or title:
                # Prefer trial title keywords (more specific than drug name alone)
                search_terms = []
                if title:
                    # Use up to 5 significant words from title — long enough to be
                    # specific but short enough to not over-constrain the query
                    words = [w for w in title.split() if len(w) > 3][:5]
                    search_terms = words
                if not search_terms:
                    for interv in interventions[:2]:
                        name = interv.get("name", "") if isinstance(interv, dict) else str(interv)
                        if name and len(name) > 3:
                            search_terms.append(name)

                if search_terms:
                    fallback_query = " ".join(search_terms)
                    raw_data["pubmed_fallback_query"] = fallback_query
                    async with httpx.AsyncClient(timeout=30) as client:
                        try:
                            fb_result = await self._search_pubmed_by_query(
                                fallback_query, client, max_results=5
                            )
                            if not isinstance(fb_result, Exception):
                                fb_citations, fb_data = fb_result
                                all_citations.extend(fb_citations)
                                raw_data.update(fb_data)
                        except Exception:
                            pass  # Fallback is best-effort

        all_citations = self._deduplicate_citations(all_citations)

        return ResearchResult(
            agent_name=self.agent_name,
            nct_id=nct_id,
            citations=all_citations,
            raw_data=raw_data,
        )

    # ------------------------------------------------------------------ #
    #  PubMed (with abstract fetching via efetch XML)
    # ------------------------------------------------------------------ #

    async def _search_pubmed(
        self, nct_id: str, client: httpx.AsyncClient
    ) -> tuple[list[SourceCitation], dict]:
        """Search PubMed and fetch abstracts via efetch XML."""
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        params = {
            "db": "pubmed",
            "term": nct_id,
            "retmax": 100,
            "retmode": "json",
            "sort": "relevance",
        }
        if PUBMED_API_KEY:
            params["api_key"] = PUBMED_API_KEY

        resp = await resilient_get(PUBMED_SEARCH_URL, client=client, params=params)
        if resp.status_code != 200:
            raw_data["pubmed_error"] = f"HTTP {resp.status_code}"
            return citations, raw_data

        search_data = resp.json()
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        raw_data["pubmed_ids"] = id_list
        raw_data["pubmed_count"] = int(
            search_data.get("esearchresult", {}).get("count", 0)
        )

        if not id_list:
            return citations, raw_data

        # Fetch full records with abstracts via efetch XML
        fetch_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "rettype": "abstract",
            "retmode": "xml",
        }
        if PUBMED_API_KEY:
            fetch_params["api_key"] = PUBMED_API_KEY

        fetch_resp = await resilient_get(
            PUBMED_FETCH_URL, client=client, params=fetch_params, timeout=45
        )

        if fetch_resp.status_code == 200:
            articles = self._parse_pubmed_xml(fetch_resp.text)
            for pmid in id_list:
                article = articles.get(pmid, {})
                title = article.get("title", "")
                abstract = article.get("abstract", "")
                journal = article.get("journal", "")
                year = article.get("year", "")
                authors = article.get("authors", [])

                snippet = self._build_snippet(
                    title=title, authors=authors, journal=journal,
                    year=year, abstract=abstract,
                )
                quality = self.compute_quality_score(
                    "pubmed", has_content=bool(abstract)
                )
                citations.append(SourceCitation(
                    source_name="pubmed",
                    source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    identifier=f"PMID:{pmid}",
                    title=title or f"PubMed article {pmid}",
                    snippet=snippet,
                    quality_score=quality,
                    retrieved_at=datetime.utcnow().isoformat(),
                ))
        else:
            # Fallback to esummary if efetch fails
            raw_data["pubmed_efetch_error"] = f"HTTP {fetch_resp.status_code}"
            await self._pubmed_summary_fallback(
                id_list, client, citations, raw_data
            )

        return citations, raw_data

    async def _search_pubmed_by_query(
        self, query: str, client: httpx.AsyncClient, max_results: int = 5
    ) -> tuple[list[SourceCitation], dict]:
        """Fallback PubMed search using free text instead of NCT ID.

        v8: For old trials (pre-2005) where publications don't reference
        the NCT ID, search by intervention name or title keywords.
        """
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        params = {
            "db": "pubmed",
            "term": query,
            "retmax": max_results,
            "retmode": "json",
            "sort": "relevance",
        }
        if PUBMED_API_KEY:
            params["api_key"] = PUBMED_API_KEY

        resp = await resilient_get(PUBMED_SEARCH_URL, client=client, params=params)
        if resp.status_code != 200:
            return citations, raw_data

        search_data = resp.json()
        id_list = search_data.get("esearchresult", {}).get("idlist", [])
        raw_data["pubmed_fallback_ids"] = id_list

        if not id_list:
            return citations, raw_data

        fetch_params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "rettype": "abstract",
            "retmode": "xml",
        }
        if PUBMED_API_KEY:
            fetch_params["api_key"] = PUBMED_API_KEY

        fetch_resp = await resilient_get(
            PUBMED_FETCH_URL, client=client, params=fetch_params, timeout=30
        )
        if fetch_resp.status_code == 200:
            articles = self._parse_pubmed_xml(fetch_resp.text)
            for pmid in id_list:
                article = articles.get(pmid, {})
                title = article.get("title", "")
                abstract = article.get("abstract", "")
                journal = article.get("journal", "")
                year = article.get("year", "")
                authors = article.get("authors", [])
                snippet = self._build_snippet(
                    title=title, authors=authors, journal=journal,
                    year=year, abstract=abstract,
                )
                citations.append(SourceCitation(
                    source_name="pubmed",
                    source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                    identifier=f"PMID:{pmid}",
                    title=title or f"PubMed article {pmid}",
                    snippet=snippet,
                    quality_score=self.compute_quality_score(
                        "pubmed", has_content=bool(abstract)
                    ),
                    retrieved_at=datetime.utcnow().isoformat(),
                ))

        return citations, raw_data

    async def _pubmed_summary_fallback(
        self,
        id_list: list[str],
        client: httpx.AsyncClient,
        citations: list[SourceCitation],
        raw_data: dict,
    ) -> None:
        """Fallback to esummary if efetch XML fails."""
        params = {
            "db": "pubmed",
            "id": ",".join(id_list),
            "retmode": "json",
        }
        if PUBMED_API_KEY:
            params["api_key"] = PUBMED_API_KEY

        resp = await resilient_get(PUBMED_SUMMARY_URL, client=client, params=params)
        if resp.status_code != 200:
            return

        results = resp.json().get("result", {})
        for pmid in id_list:
            article = results.get(pmid, {})
            if not isinstance(article, dict) or not article.get("title"):
                continue

            title = article.get("title", "")
            source = article.get("source", "")
            pubdate = article.get("sortpubdate", "")[:4]
            authors = [
                a.get("name", "") for a in article.get("authors", [])[:5]
            ]

            snippet = self._build_snippet(
                title=title, authors=authors, journal=source, year=pubdate,
            )
            citations.append(SourceCitation(
                source_name="pubmed",
                source_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                identifier=f"PMID:{pmid}",
                title=title,
                snippet=snippet,
                quality_score=self.compute_quality_score("pubmed", has_content=False),
                retrieved_at=datetime.utcnow().isoformat(),
            ))

    # ------------------------------------------------------------------ #
    #  PMC (open-access full text, with proper summaries)
    # ------------------------------------------------------------------ #

    async def _search_pmc(
        self, nct_id: str, client: httpx.AsyncClient
    ) -> tuple[list[SourceCitation], dict]:
        """Search PMC for open-access full-text articles."""
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        params = {
            "db": "pmc",
            "term": nct_id,
            "retmax": 50,
            "retmode": "json",
        }
        if PUBMED_API_KEY:
            params["api_key"] = PUBMED_API_KEY

        resp = await resilient_get(PUBMED_SEARCH_URL, client=client, params=params)
        if resp.status_code != 200:
            raw_data["pmc_error"] = f"HTTP {resp.status_code}"
            return citations, raw_data

        pmc_data = resp.json()
        pmc_ids = pmc_data.get("esearchresult", {}).get("idlist", [])
        raw_data["pmc_ids"] = pmc_ids
        raw_data["pmc_count"] = int(
            pmc_data.get("esearchresult", {}).get("count", 0)
        )

        if not pmc_ids:
            return citations, raw_data

        # Fetch summaries for proper titles and metadata
        summary_params = {
            "db": "pmc",
            "id": ",".join(pmc_ids),
            "retmode": "json",
        }
        if PUBMED_API_KEY:
            summary_params["api_key"] = PUBMED_API_KEY

        summary_resp = await resilient_get(
            PUBMED_SUMMARY_URL, client=client, params=summary_params
        )
        if summary_resp.status_code == 200:
            results = summary_resp.json().get("result", {})
            for pmc_id in pmc_ids:
                article = results.get(pmc_id, {})
                if not isinstance(article, dict):
                    continue

                title = article.get("title", f"PMC Article {pmc_id}")
                source = article.get("source", "")
                pubdate = article.get("sortpubdate", "")[:4]
                authors = [
                    a.get("name", "") for a in article.get("authors", [])[:5]
                ]

                snippet = self._build_snippet(
                    title=title, authors=authors, journal=source, year=pubdate,
                )
                citations.append(SourceCitation(
                    source_name="pmc",
                    source_url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmc_id}/",
                    identifier=f"PMC:{pmc_id}",
                    title=title,
                    snippet=snippet,
                    quality_score=self.compute_quality_score("pmc"),
                    retrieved_at=datetime.utcnow().isoformat(),
                ))
        else:
            # Bare citations without summaries
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

        return citations, raw_data

    # ------------------------------------------------------------------ #
    #  Europe PMC (free JSON API with abstracts, no key needed)
    # ------------------------------------------------------------------ #

    async def _search_europe_pmc(
        self, nct_id: str, client: httpx.AsyncClient
    ) -> tuple[list[SourceCitation], dict]:
        """Search Europe PMC for articles citing this NCT ID."""
        citations: list[SourceCitation] = []
        raw_data: dict = {}

        resp = await resilient_get(
            EUROPE_PMC_URL,
            client=client,
            params={
                "query": nct_id,
                "format": "json",
                "pageSize": 50,
                "resultType": "core",
                "sort": "RELEVANCE",
            },
        )
        if resp.status_code != 200:
            raw_data["europe_pmc_error"] = f"HTTP {resp.status_code}"
            return citations, raw_data

        data = resp.json()
        result_list = data.get("resultList", {}).get("result", [])
        raw_data["europe_pmc_count"] = len(result_list)
        raw_data["europe_pmc_total"] = data.get("hitCount", 0)

        for article in result_list:
            pmid = article.get("pmid", "")
            pmcid = article.get("pmcid", "")
            doi = article.get("doi", "")
            title = article.get("title", "")
            abstract = article.get("abstractText", "")
            author_str = article.get("authorString", "")
            journal = article.get("journalTitle", "")
            year = str(article.get("pubYear", ""))

            # Parse author string into list for consistent formatting
            authors = [a.strip() for a in author_str.split(",")[:5]] if author_str else []

            snippet = self._build_snippet(
                title=title, authors=authors, journal=journal,
                year=year, abstract=abstract,
            )

            # Determine identifier and URL
            identifier = ""
            url = ""
            if pmid:
                identifier = f"PMID:{pmid}"
                url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
            elif pmcid:
                identifier = f"PMC:{pmcid}"
                url = f"https://europepmc.org/article/PMC/{pmcid}"
            elif doi:
                identifier = f"DOI:{doi}"
                url = f"https://doi.org/{doi}"

            quality = self.compute_quality_score(
                "europe_pmc", has_content=bool(abstract)
            )
            citations.append(SourceCitation(
                source_name="europe_pmc",
                source_url=url,
                identifier=identifier,
                title=title or "Europe PMC result",
                snippet=snippet,
                quality_score=quality,
                retrieved_at=datetime.utcnow().isoformat(),
            ))

        return citations, raw_data

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_pubmed_xml(xml_text: str) -> dict[str, dict]:
        """Parse PubMed efetch XML to extract titles, abstracts, and metadata."""
        articles: dict[str, dict] = {}
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return articles

        for article_el in root.findall(".//PubmedArticle"):
            pmid_el = article_el.find(".//MedlineCitation/PMID")
            if pmid_el is None or not pmid_el.text:
                continue
            pmid = pmid_el.text

            # Title (may contain inline markup)
            title_el = article_el.find(".//ArticleTitle")
            title = "".join(title_el.itertext()) if title_el is not None else ""

            # Abstract (may have labeled sections: BACKGROUND, METHODS, etc.)
            abstract_parts = []
            for abs_el in article_el.findall(".//Abstract/AbstractText"):
                label = abs_el.get("Label", "")
                text = "".join(abs_el.itertext())
                if label:
                    abstract_parts.append(f"{label}: {text}")
                else:
                    abstract_parts.append(text)
            abstract = " ".join(abstract_parts)

            # Journal
            journal_el = article_el.find(".//Journal/Title")
            journal = journal_el.text if journal_el is not None else ""

            # Year (with MedlineDate fallback)
            year_el = article_el.find(".//PubDate/Year")
            if year_el is None:
                year_el = article_el.find(".//PubDate/MedlineDate")
            year = ""
            if year_el is not None and year_el.text:
                year = year_el.text[:4]

            # Authors (first 5)
            authors = []
            for author_el in article_el.findall(".//AuthorList/Author")[:5]:
                last = author_el.findtext("LastName", "")
                first = author_el.findtext("ForeName", "")
                if last:
                    authors.append(f"{last} {first}".strip())

            articles[pmid] = {
                "title": title,
                "abstract": abstract,
                "journal": journal,
                "year": year,
                "authors": authors,
            }

        return articles

    @staticmethod
    def _build_snippet(
        title: str = "",
        authors: list[str] | None = None,
        journal: str = "",
        year: str = "",
        abstract: str = "",
    ) -> str:
        """Build a structured snippet with labeled fields for LLM clarity."""
        parts = []
        if title:
            parts.append(f"Title: {title}")
        if authors:
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += " et al."
            parts.append(f"Authors: {author_str}")
        if journal or year:
            journal_part = journal or "Unknown journal"
            year_part = f" ({year})" if year else ""
            parts.append(f"Journal: {journal_part}{year_part}")
        if abstract:
            # Cap abstract at 300 chars — the structured evidence builder
            # will further truncate per hardware profile (250 mac_mini, 500 server).
            # Storing a moderate snippet avoids bloating persisted research JSON
            # while giving the server profile enough to work with.
            parts.append(f"Abstract: {abstract[:300]}")
        return "\n".join(parts)

    @staticmethod
    def _deduplicate_citations(
        citations: list[SourceCitation],
    ) -> list[SourceCitation]:
        """Remove duplicate citations by PMID, keeping the one with the best snippet."""
        best_by_pmid: dict[str, SourceCitation] = {}
        non_pmid: list[SourceCitation] = []

        for c in citations:
            if c.identifier and c.identifier.startswith("PMID:"):
                pmid = c.identifier
                if pmid not in best_by_pmid or len(c.snippet) > len(best_by_pmid[pmid].snippet):
                    best_by_pmid[pmid] = c
            else:
                non_pmid.append(c)

        return list(best_by_pmid.values()) + non_pmid
