import os
import json
import requests
from bs4 import BeautifulSoup
from serpapi.google_search import GoogleSearch
import xml.etree.ElementTree as ET


# -----------------------------------
# SerpAPI Web Search
# -----------------------------------

def search_web(query, api_key=None, num_results=5):
    """
    Perform a Google search using SerpAPI and return summarized results.
    """
    if api_key is None:
        api_key = os.getenv("SERPAPI_API_KEY")
        if not api_key:
            raise ValueError("SerpAPI API key not provided and SERPAPI_API_KEY env var not set.")

    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "num": num_results,
    }

    search = GoogleSearch(params)
    results = search.get_dict()

    organic_results = results.get("organic_results", [])
    output = []
    for item in organic_results[:num_results]:
        output.append({
            "title": item.get("title"),
            "link": item.get("link"),
            "snippet": item.get("snippet"),
        })
    return output


# -----------------------------------
# PubMed: API Fetch (EFetch)
# -----------------------------------

def fetch_pubmed_study_api(pmid):
    """
    Fetch study info from PubMed using the official EFetch API.
    """
    url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml"
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        return {"error": str(e), "source": "api"}

    root = ET.fromstring(resp.text)
    article = root.find(".//PubmedArticle")
    if article is None:
        return {"error": "No article found", "source": "api"}

    title = article.findtext(".//ArticleTitle", default="")
    abstract = "".join([t.text or "" for t in article.findall(".//AbstractText")])
    journal = article.findtext(".//Journal/Title", default="")
    pub_date = article.findtext(".//PubDate/Year", default="")
    authors = []
    for author in article.findall(".//Author"):
        last = author.findtext("LastName")
        first = author.findtext("ForeName")
        if last and first:
            authors.append(f"{first} {last}")

    return {
        "pmid": pmid,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "journal": journal,
        "publication_date": pub_date,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "source": "api"
    }


# -----------------------------------
# PubMed: HTML Scrape
# -----------------------------------

def fetch_pubmed_study_scrape(pmid):
    """
    Scrape metadata from the PubMed HTML page.
    """
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Network or HTTP error: {e}", "source": "scrape"}

    soup = BeautifulSoup(response.text, 'html.parser')

    title_tag = soup.find("h1", class_="heading-title")
    title = title_tag.get_text(strip=True) if title_tag else ""

    abstract_tag = soup.find("div", class_="abstract-content selected")
    abstract = abstract_tag.get_text(strip=True) if abstract_tag else ""

    authors = []
    authors_section = soup.find("div", class_="authors-list")
    if authors_section:
        author_tags = authors_section.find_all("a", class_="full-name")
        authors = [a.get_text(strip=True) for a in author_tags]

    journal_tag = soup.find("button", class_="journal-actions-trigger")
    journal = journal_tag.get_text(strip=True) if journal_tag else ""

    pub_date_tag = soup.find("span", class_="cit")
    publication_date = pub_date_tag.get_text(strip=True) if pub_date_tag else ""

    return {
        "pmid": pmid,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "journal": journal,
        "publication_date": publication_date,
        "url": url,
        "source": "scrape"
    }


# -----------------------------------
# Merge API + Scraped PubMed Data
# -----------------------------------

def merge_pubmed_data(api_data, scraped_data):
    """
    Combine both API and scraped PubMed data, preferring more complete fields.
    Annotates which source each field came from.
    """
    merged = {}
    field_sources = {}

    def choose(field):
        val_api = api_data.get(field, "")
        val_scrape = scraped_data.get(field, "")
        if len(val_scrape) > len(val_api):
            field_sources[field] = "scrape"
            return val_scrape
        else:
            field_sources[field] = "api"
            return val_api

    merged["pmid"] = api_data.get("pmid") or scraped_data.get("pmid")
    field_sources["pmid"] = "api" if "pmid" in api_data else "scrape"

    merged["title"] = choose("title")
    merged["abstract"] = choose("abstract")
    merged["authors"] = scraped_data.get("authors") or api_data.get("authors", [])
    field_sources["authors"] = "scrape" if scraped_data.get("authors") else "api"

    merged["journal"] = choose("journal")
    merged["publication_date"] = choose("publication_date")
    merged["url"] = api_data.get("url") or scraped_data.get("url")
    field_sources["url"] = "api" if "url" in api_data else "scrape"

    # Track the sources used
    merged["_field_sources"] = field_sources
    return merged


# -----------------------------------
# LLM Payload Builder
# -----------------------------------

def create_payload(data_type, data):
    """
    Create a JSON-serializable payload dict for LLM input.
    """
    return {
        "type": data_type,
        "data": data,
    }


def fetch_pubmed_combined_payload(pmid):
    """
    Fetch both API and scraped PubMed data, merge, and return payload.
    """
    api_data = fetch_pubmed_study_api(pmid)
    scraped_data = fetch_pubmed_study_scrape(pmid)

    if "error" in api_data and "error" in scraped_data:
        raise ValueError(f"Failed to fetch PMID {pmid} from both API and HTML.")

    merged_data = merge_pubmed_data(api_data, scraped_data)
    return create_payload("pubmed_study_combined", merged_data)
