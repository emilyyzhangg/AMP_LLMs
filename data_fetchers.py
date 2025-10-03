import os
from serpapi.google_search import GoogleSearch
import requests
from bs4 import BeautifulSoup

def search_web(query, api_key=None, num_results=5):
    """
    Perform a Google search using SerpAPI and return summarized results.

    Args:
        query (str): The search query.
        api_key (str): Your SerpAPI API key. If None, it will look for SERPAPI_API_KEY env var.
        num_results (int): Number of results to fetch.

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

    # Parse organic results if present
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
        dict: Basic metadata about the study or None if not found.
    """
    url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Error fetching PubMed page for PMID {pmid}. Status code: {response.status_code}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    # Extract title
    title_tag = soup.find("h1", class_="heading-title")
    title = title_tag.get_text(strip=True) if title_tag else "No title found"

    # Extract abstract
    abstract_tag = soup.find("div", class_="abstract-content selected")
    abstract = abstract_tag.get_text(strip=True) if abstract_tag else "No abstract found"

    # Extract authors (optional)
    authors = []
    authors_section = soup.find("div", class_="authors-list")
    if authors_section:
        author_tags = authors_section.find_all("a", class_="full-name")
        authors = [a.get_text(strip=True) for a in author_tags]

    return {
        "pmid": pmid,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "url": url
    }
