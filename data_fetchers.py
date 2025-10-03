import os
import json
import requests
from serpapi.google_search import GoogleSearch
from bs4 import BeautifulSoup


def search_web(query, api_key=None, num_results=5):
    """
    Perform a Google search using SerpAPI and return summarized results.

    Args:
        query (str): The search query.
        api_key (str, optional): SerpAPI API key. If None, will look in env var SERPAPI_API_KEY.
        num_results (int, optional): Number of results to fetch.

    Returns:
        list of dict: Each dict contains 'title', 'link', and 'snippet'.
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


def fetch_pubmed_study(pmid):
    """
    Fetch basic PubMed article details given a PubMed ID (PMID).

    Args:
        pmid (str): PubMed ID.

    Returns:
        dict: Metadata about the study, or dict with 'error' key if failed.
    """
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        return {"error": f"Network or HTTP error fetching PubMed page: {e}"}

    soup = BeautifulSoup(response.text, 'html.parser')

    title_tag = soup.find("h1", class_="heading-title")
    title = title_tag.get_text(strip=True) if title_tag else None

    abstract_tag = soup.find("div", class_="abstract-content selected")
    abstract = abstract_tag.get_text(strip=True) if abstract_tag else None

    authors = []
    authors_section = soup.find("div", class_="authors-list")
    if authors_section:
        author_tags = authors_section.find_all("a", class_="full-name")
        authors = [a.get_text(strip=True) for a in author_tags]

    journal_tag = soup.find("button", class_="journal-actions-trigger")
    journal = journal_tag.get_text(strip=True) if journal_tag else None

    pub_date_tag = soup.find("span", class_="cit")
    publication_date = pub_date_tag.get_text(strip=True) if pub_date_tag else None

    if not title:
        return {"error": "Failed to extract PubMed study title."}

    return {
        "pmid": pmid,
        "title": title,
        "abstract": abstract or "",
        "authors": authors,
        "journal": journal or "",
        "publication_date": publication_date or "",
        "url": url,
    }


def create_payload(data_type, data):
    """
    Create a JSON-serializable payload dict for bulk LLM input.

    Args:
        data_type (str): Type of data, e.g. 'pubmed_study', 'web_search'.
        data (dict or list): Data fetched from either fetch_pubmed_study or search_web.

    Returns:
        dict: JSON-serializable payload suitable for LLM input batch processing.
    """
    payload = {
        "type": data_type,
        "data": data,
    }
    return payload
