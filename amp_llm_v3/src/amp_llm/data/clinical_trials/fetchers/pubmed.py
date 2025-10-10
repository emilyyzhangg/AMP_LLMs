"""
PubMed data fetcher.
Handles searching and fetching metadata from PubMed via NCBI E-utilities.
"""
import requests
import time
from typing import Dict, List

# Configuration
DEFAULT_TIMEOUT = 15
SLEEP_BETWEEN_REQUESTS = 0.34


def search_pubmed_esearch(query: str, max_results: int = 5) -> List[str]:
    """
    Search PubMed using esearch.
    
    Args:
        query: Search query
        max_results: Maximum number of results
        
    Returns:
        List of PMIDs
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": query, "retmode": "json", "retmax": max_results}
    
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        
        if ids:
            print(f"✅ PubMed: found {len(ids)} matches.")
        else:
            print("⚠️ PubMed: no matches found.")
        
        return ids
    except Exception as e:
        print(f"❌ PubMed esearch error: {e}")
        return []


def fetch_pubmed_by_pmid(pmid: str) -> Dict:
    """
    Fetch PubMed metadata using efetch.
    
    Args:
        pmid: PubMed ID
        
    Returns:
        Dictionary with PubMed metadata
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        
        xml_content = resp.text
        metadata = _parse_pubmed_xml(xml_content, pmid)
        
        print(f"✅ PubMed: fetched metadata for {pmid}")
        return metadata
    except Exception as e:
        print(f"❌ PubMed efetch error for {pmid}: {e}")
        return {"error": str(e), "source": "pubmed_efetch", "pmid": pmid}


def search_pubmed_by_title_authors(title: str, authors: List[str]) -> str:
    """
    Search PubMed by title and authors, return first PMID.
    
    Args:
        title: Article title
        authors: List of author names
        
    Returns:
        PMID string or empty string if not found
    """
    # Build search query
    query_parts = []
    
    if title:
        # Use first 5 words of title
        title_words = title.split()[:5]
        query_parts.append(" ".join(title_words))
    
    if authors:
        # Use first author
        author = authors[0]
        # Extract last name
        if "," in author:
            last_name = author.split(",")[0].strip()
        else:
            parts = author.split()
            last_name = parts[-1] if parts else author
        query_parts.append(f"{last_name}[Author]")
    
    query = " AND ".join(query_parts)
    
    print(f"🔍 PubMed: searching for '{query}'")
    
    pmids = search_pubmed_esearch(query, max_results=1)
    
    return pmids[0] if pmids else ""


def _parse_pubmed_xml(xml_content: str, pmid: str) -> Dict:
    """
    Parse PubMed XML response.
    
    Args:
        xml_content: XML response from efetch
        pmid: PubMed ID
        
    Returns:
        Dictionary with parsed metadata
    """
    try:
        from xml.etree import ElementTree as ET
        
        root = ET.fromstring(xml_content)
        article = root.find(".//Article")
        
        if article is None:
            return {"pmid": pmid, "error": "No article data found"}
        
        # Extract title
        title_elem = article.find(".//ArticleTitle")
        title = title_elem.text if title_elem is not None else ""
        
        # Extract journal
        journal_elem = article.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None else ""
        
        # Extract publication date
        pub_date = article.find(".//PubDate")
        pub_year = ""
        if pub_date is not None:
            year_elem = pub_date.find("Year")
            pub_year = year_elem.text if year_elem is not None else ""
        
        # Extract authors
        authors = []
        author_list = article.findall(".//Author")
        for author in author_list:
            last_name = author.find("LastName")
            fore_name = author.find("ForeName")
            if last_name is not None and fore_name is not None:
                authors.append(f"{last_name.text}, {fore_name.text}")
            elif last_name is not None:
                authors.append(last_name.text)
        
        # Extract abstract
        abstract_elem = article.find(".//Abstract/AbstractText")
        abstract = abstract_elem.text if abstract_elem is not None else ""
        
        return {
            "pmid": pmid,
            "title": title,
            "journal": journal,
            "publication_date": pub_year,
            "authors": authors,
            "abstract": abstract,
            "source": "pubmed_efetch"
        }
    
    except Exception as e:
        print(f"⚠️ Error parsing PubMed XML: {e}")
        return {
            "pmid": pmid,
            "error": str(e),
            "source": "pubmed_parse_error"
        }