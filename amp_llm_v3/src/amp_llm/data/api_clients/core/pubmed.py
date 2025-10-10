"""
PubMed API client - refactored with base class.
"""
import xml.etree.ElementTree as ET
from typing import Dict, List, Any

from amp_llm.data.api_clients.base import BaseAPIClient, APIConfig
from amp_llm.config import get_logger

logger = get_logger(__name__)


class PubMedClient(BaseAPIClient):
    """
    PubMed client using NCBI E-utilities.
    
    Replaces: data/clinical_trials/fetchers/pubmed.py
    """
    
    @property
    def name(self) -> str:
        return "PubMed"
    
    @property
    def base_url(self) -> str:
        return "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
    
    async def search(self, query: str, max_results: int = None) -> Dict[str, Any]:
        """
        Search PubMed using esearch.
        
        Args:
            query: Search query
            max_results: Maximum results (defaults to config)
            
        Returns:
            Dictionary with PMIDs
        """
        max_results = max_results or self.config.max_results
        
        url = f"{self.base_url}/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": max_results
        }
        
        logger.info(f"{self.name}: Searching for '{query[:100]}'...")
        
        try:
            async with await self._request("GET", url, params=params) as resp:
                data = await resp.json()
                pmids = data.get("esearchresult", {}).get("idlist", [])
                
                logger.info(f"{self.name}: Found {len(pmids)} result(s)")
                
                return {
                    "pmids": pmids,
                    "count": len(pmids),
                    "query": query
                }
        
        except Exception as e:
            logger.error(f"{self.name} search error: {e}")
            return {"error": str(e), "pmids": []}
    
    async def fetch_by_id(self, pmid: str, **kwargs) -> Dict[str, Any]:
        """
        Fetch PubMed article by PMID.
        
        Args:
            pmid: PubMed ID
            
        Returns:
            Article metadata
        """
        url = f"{self.base_url}/efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml"
        }
        
        logger.info(f"{self.name}: Fetching PMID {pmid}")
        
        try:
            async with await self._request("GET", url, params=params) as resp:
                xml_content = await resp.text()
                metadata = self._parse_xml(xml_content, pmid)
                
                logger.info(f"{self.name}: Retrieved {pmid}")
                return metadata
        
        except Exception as e:
            logger.error(f"{self.name} fetch error for {pmid}: {e}")
            return {"error": str(e), "pmid": pmid}
    
    async def search_by_title_authors(
        self,
        title: str,
        authors: List[str]
    ) -> str:
        """
        Search PubMed by title and authors.
        
        Args:
            title: Article title
            authors: List of author names
            
        Returns:
            First PMID or empty string
        """
        # Build query
        query_parts = []
        
        if title:
            title_words = title.split()[:5]
            query_parts.append(" ".join(title_words))
        
        if authors:
            author = authors[0]
            if "," in author:
                last_name = author.split(",")[0].strip()
            else:
                parts = author.split()
                last_name = parts[-1] if parts else author
            query_parts.append(f"{last_name}[Author]")
        
        query = " AND ".join(query_parts)
        
        result = await self.search(query, max_results=1)
        pmids = result.get("pmids", [])
        
        return pmids[0] if pmids else ""
    
    def _parse_xml(self, xml_content: str, pmid: str) -> Dict[str, Any]:
        """Parse PubMed XML response."""
        try:
            root = ET.fromstring(xml_content)
            article = root.find(".//Article")
            
            if article is None:
                return {"pmid": pmid, "error": "No article data"}
            
            # Extract fields
            title_elem = article.find(".//ArticleTitle")
            title = title_elem.text if title_elem is not None else ""
            
            journal_elem = article.find(".//Journal/Title")
            journal = journal_elem.text if journal_elem is not None else ""
            
            pub_date = article.find(".//PubDate")
            year = ""
            if pub_date is not None:
                year_elem = pub_date.find("Year")
                year = year_elem.text if year_elem is not None else ""
            
            # Extract authors
            authors = []
            for author in article.findall(".//Author"):
                last = author.find("LastName")
                first = author.find("ForeName")
                if last is not None and first is not None:
                    authors.append(f"{last.text}, {first.text}")
                elif last is not None:
                    authors.append(last.text)
            
            # Extract abstract
            abstract_elem = article.find(".//Abstract/AbstractText")
            abstract = abstract_elem.text if abstract_elem is not None else ""
            
            return {
                "pmid": pmid,
                "title": title,
                "journal": journal,
                "publication_date": year,
                "authors": authors,
                "abstract": abstract,
                "source": "pubmed"
            }
        
        except Exception as e:
            logger.error(f"XML parse error for {pmid}: {e}")
            return {"pmid": pmid, "error": str(e)}