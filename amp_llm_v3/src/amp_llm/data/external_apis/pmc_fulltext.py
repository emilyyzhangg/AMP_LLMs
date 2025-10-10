"""
PubMed Central (PMC) Full Text API Client
Fetches full-text articles from PMC Open Access Subset.

API Documentation: https://www.ncbi.nlm.nih.gov/pmc/tools/oa-service/
"""
import aiohttp
import asyncio
from typing import Dict, List, Any, Optional
from xml.etree import ElementTree as ET

from amp_llm.config import get_logger

logger = get_logger(__name__)


class PMCFullTextClient:
    """
    PubMed Central Full Text API client.
    
    Provides access to full-text XML of Open Access articles.
    """
    
    def __init__(self, timeout: int = 30, max_results: int = 10):
        """
        Initialize PMC Full Text client.
        
        Args:
            timeout: Request timeout in seconds
            max_results: Maximum results for search operations
        """
        self.base_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        self.oa_service_url = "https://www.ncbi.nlm.nih.gov/pmc/oai/oai.cgi"
        self.timeout = timeout
        self.max_results = max_results
        self.rate_limit_delay = 0.34  # NCBI recommends 3 requests/second
    
    async def search_pmc(self, query: str) -> Dict[str, Any]:
        """
        Search PMC for articles matching query.
        
        Args:
            query: Search query (title, authors, keywords)
            
        Returns:
            Dictionary with PMC IDs and metadata
        """
        print(f"🔍 PMC Full Text: Searching for '{query[:100]}'...")
        
        url = f"{self.base_url}/esearch.fcgi"
        params = {
            "db": "pmc",
            "term": query,
            "retmode": "json",
            "retmax": self.max_results,
            "usehistory": "y"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = data.get("esearchresult", {})
                        ids = result.get("idlist", [])
                        count = result.get("count", "0")
                        
                        print(f"✅ PMC Full Text: Found {len(ids)} article(s) ({count} total)")
                        logger.info(f"PMC search returned {len(ids)} results")
                        
                        await asyncio.sleep(self.rate_limit_delay)
                        
                        return {
                            "pmcids": ids,
                            "total_count": int(count),
                            "webenv": result.get("webenv"),
                            "query_key": result.get("querykey")
                        }
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ PMC Full Text: Error {resp.status}")
                        logger.warning(f"PMC search error {resp.status}: {error_text}")
                        return {"pmcids": [], "error": error_text}
        
        except asyncio.TimeoutError:
            print(f"⚠️ PMC Full Text: Search timed out")
            return {"pmcids": [], "error": "timeout"}
        except Exception as e:
            print(f"❌ PMC Full Text: Search error: {e}")
            logger.error(f"PMC search error: {e}")
            return {"pmcids": [], "error": str(e)}
    
    async def fetch_full_text(self, pmcid: str, format: str = "xml") -> Dict[str, Any]:
        """
        Fetch full text of an article.
        
        Args:
            pmcid: PMC ID (e.g., "PMC6927485" or "6927485")
            format: Output format ("xml" or "text")
            
        Returns:
            Dictionary with full text content
        """
        # Ensure PMC prefix
        if not pmcid.startswith("PMC"):
            pmcid = f"PMC{pmcid}"
        
        print(f"🔍 PMC Full Text: Fetching {pmcid}...")
        
        url = f"{self.base_url}/efetch.fcgi"
        params = {
            "db": "pmc",
            "id": pmcid.replace("PMC", ""),
            "retmode": "xml"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        xml_content = await resp.text()
                        
                        # Parse XML
                        parsed = self._parse_pmc_xml(xml_content, pmcid)
                        
                        print(f"✅ PMC Full Text: Retrieved {pmcid}")
                        logger.info(f"Retrieved full text for {pmcid}")
                        
                        await asyncio.sleep(self.rate_limit_delay)
                        
                        if format == "text":
                            return {
                                "pmcid": pmcid,
                                "title": parsed.get("title", ""),
                                "abstract": parsed.get("abstract", ""),
                                "body": parsed.get("body_text", ""),
                                "full_text": parsed.get("full_text", ""),
                                "sections": parsed.get("sections", [])
                            }
                        else:
                            return {
                                "pmcid": pmcid,
                                "xml": xml_content,
                                "parsed": parsed
                            }
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ PMC Full Text: Error {resp.status} for {pmcid}")
                        logger.warning(f"PMC fetch error {resp.status}: {error_text}")
                        return {"pmcid": pmcid, "error": error_text}
        
        except asyncio.TimeoutError:
            print(f"⚠️ PMC Full Text: Fetch timed out for {pmcid}")
            return {"pmcid": pmcid, "error": "timeout"}
        except Exception as e:
            print(f"❌ PMC Full Text: Fetch error for {pmcid}: {e}")
            logger.error(f"PMC fetch error for {pmcid}: {e}")
            return {"pmcid": pmcid, "error": str(e)}
    
    async def fetch_metadata(self, pmcid: str) -> Dict[str, Any]:
        """
        Fetch metadata for an article without full text.
        
        Args:
            pmcid: PMC ID
            
        Returns:
            Dictionary with article metadata
        """
        if not pmcid.startswith("PMC"):
            pmcid = f"PMC{pmcid}"
        
        print(f"🔍 PMC Full Text: Fetching metadata for {pmcid}...")
        
        url = f"{self.base_url}/esummary.fcgi"
        params = {
            "db": "pmc",
            "id": pmcid.replace("PMC", ""),
            "retmode": "json"
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        result = data.get("result", {})
                        uid = pmcid.replace("PMC", "")
                        
                        if uid in result:
                            article = result[uid]
                            
                            metadata = {
                                "pmcid": pmcid,
                                "pmid": article.get("pmid"),
                                "doi": article.get("doi"),
                                "title": article.get("title"),
                                "authors": [
                                    a.get("name") for a in article.get("authors", [])
                                ],
                                "journal": article.get("fulljournalname"),
                                "pub_date": article.get("pubdate"),
                                "volume": article.get("volume"),
                                "issue": article.get("issue"),
                                "pages": article.get("pages"),
                                "available": article.get("availablefromurl")
                            }
                            
                            print(f"✅ PMC Full Text: Retrieved metadata for {pmcid}")
                            logger.info(f"Retrieved metadata for {pmcid}")
                            
                            await asyncio.sleep(self.rate_limit_delay)
                            
                            return metadata
                        else:
                            print(f"⚠️ PMC Full Text: No metadata found for {pmcid}")
                            return {"pmcid": pmcid, "error": "not_found"}
                    else:
                        error_text = await resp.text()
                        print(f"⚠️ PMC Full Text: Error {resp.status}")
                        return {"pmcid": pmcid, "error": error_text}
        
        except Exception as e:
            print(f"❌ PMC Full Text: Metadata error for {pmcid}: {e}")
            logger.error(f"PMC metadata error: {e}")
            return {"pmcid": pmcid, "error": str(e)}
    
    async def check_open_access(self, pmcid: str) -> bool:
        """
        Check if an article is in the Open Access subset.
        
        Args:
            pmcid: PMC ID
            
        Returns:
            True if article is open access
        """
        metadata = await self.fetch_metadata(pmcid)
        
        if "error" in metadata:
            return False
        
        # Check if available from URL (indicates OA)
        return bool(metadata.get("available"))
    
    async def batch_fetch(
        self,
        pmcids: List[str],
        format: str = "text"
    ) -> Dict[str, Any]:
        """
        Fetch multiple articles concurrently.
        
        Args:
            pmcids: List of PMC IDs
            format: Output format
            
        Returns:
            Dictionary mapping PMC IDs to content
        """
        print(f"🔍 PMC Full Text: Batch fetching {len(pmcids)} article(s)...")
        
        tasks = [
            self.fetch_full_text(pmcid, format=format)
            for pmcid in pmcids
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Organize results
        batch_results = {}
        success_count = 0
        
        for pmcid, result in zip(pmcids, results):
            if isinstance(result, Exception):
                logger.error(f"Batch fetch failed for {pmcid}: {result}")
                batch_results[pmcid] = {"error": str(result)}
            else:
                batch_results[pmcid] = result
                if "error" not in result:
                    success_count += 1
        
        print(f"✅ PMC Full Text: Successfully fetched {success_count}/{len(pmcids)}")
        
        return batch_results
    
    def _parse_pmc_xml(self, xml_content: str, pmcid: str) -> Dict[str, Any]:
        """
        Parse PMC XML to extract structured content.
        
        Args:
            xml_content: Raw XML content
            pmcid: PMC ID
            
        Returns:
            Dictionary with parsed content
        """
        try:
            root = ET.fromstring(xml_content)
            
            # Extract title
            title_elem = root.find(".//article-title")
            title = title_elem.text if title_elem is not None else ""
            
            # Extract abstract
            abstract_parts = []
            for abstract_elem in root.findall(".//abstract//p"):
                if abstract_elem.text:
                    abstract_parts.append(abstract_elem.text)
            abstract = " ".join(abstract_parts)
            
            # Extract body sections
            sections = []
            body_text_parts = []
            
            for sec in root.findall(".//body//sec"):
                section_title_elem = sec.find("title")
                section_title = section_title_elem.text if section_title_elem is not None else "Untitled"
                
                section_text_parts = []
                for p in sec.findall(".//p"):
                    if p.text:
                        section_text_parts.append(p.text)
                        body_text_parts.append(p.text)
                
                if section_text_parts:
                    sections.append({
                        "title": section_title,
                        "text": " ".join(section_text_parts)
                    })
            
            body_text = " ".join(body_text_parts)
            full_text = f"{title}\n\n{abstract}\n\n{body_text}"
            
            # Extract authors
            authors = []
            for contrib in root.findall(".//contrib[@contrib-type='author']"):
                surname = contrib.find(".//surname")
                given_names = contrib.find(".//given-names")
                
                if surname is not None and given_names is not None:
                    authors.append(f"{surname.text}, {given_names.text}")
                elif surname is not None:
                    authors.append(surname.text)
            
            # Extract journal info
            journal_elem = root.find(".//journal-title")
            journal = journal_elem.text if journal_elem is not None else ""
            
            pub_date = root.find(".//pub-date")
            year = ""
            if pub_date is not None:
                year_elem = pub_date.find("year")
                year = year_elem.text if year_elem is not None else ""
            
            return {
                "pmcid": pmcid,
                "title": title,
                "authors": authors,
                "journal": journal,
                "year": year,
                "abstract": abstract,
                "body_text": body_text,
                "full_text": full_text,
                "sections": sections,
                "section_count": len(sections)
            }
        
        except Exception as e:
            logger.error(f"Error parsing PMC XML for {pmcid}: {e}")
            return {
                "pmcid": pmcid,
                "error": f"parse_error: {str(e)}"
            }
    
    async def search_by_clinical_trial(
        self,
        nct_id: str,
        title: str = None
    ) -> Dict[str, Any]:
        """
        Search PMC for articles related to a clinical trial.
        
        Args:
            nct_id: NCT number
            title: Optional trial title for refined search
            
        Returns:
            Dictionary with related articles
        """
        print(f"🔍 PMC Full Text: Searching for articles related to {nct_id}...")
        
        # Build query
        query = nct_id
        if title:
            # Add key terms from title
            title_terms = " ".join(title.split()[:10])
            query = f"{nct_id} OR ({title_terms})"
        
        results = await self.search_pmc(query)
        
        if results.get("pmcids"):
            print(f"✅ Found {len(results['pmcids'])} article(s) for {nct_id}")
        
        return results