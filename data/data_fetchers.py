import requests
import time
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup


# --- ClinicalTrials.gov API Fetch (just fetch and return raw) ---

def fetch_clinical_trial_data(nct_id):
    base_url = "https://clinicaltrials.gov/api/v2/studies/"
    url = f"{base_url}{nct_id}"

    try:
        print("🔍 ClinicalTrials.gov search:")
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        print("\t✅ Found results.")
        return {
            "nct_id": nct_id,
            "clinical_trial_data": data,
            "source": "clinicaltrials_api"
        }
    except requests.exceptions.HTTPError as e:
        print("\t❌ No result found.")
        return {
            "error": f"HTTP error: {e}",
            "source": "clinicaltrials_api"
        }
    except Exception as e:
        print("\t❌ No result found.")
        return {
            "error": str(e),
            "source": "clinicaltrials_api"
        }


# --- PubMed API fetchers and helpers ---

def fetch_pubmed_study_api(pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": pmid,
        "retmode": "xml"
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        return {"error": str(e), "source": "pubmed_api", "pmid": pmid}

    root = ET.fromstring(resp.text)
    article = root.find(".//PubmedArticle")
    if article is None:
        return {"error": "No article found", "source": "pubmed_api", "pmid": pmid}

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
        "source": "pubmed_api"
    }


def convert_doi_to_pmid(doi):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": f"{doi}[DOI]",
        "retmode": "json"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if idlist:
            return idlist[0]
    except Exception:
        pass
    return None


def convert_pmcid_to_pmid(pmcid):
    pmcid_clean = pmcid.upper().strip()
    if not pmcid_clean.startswith("PMC"):
        return None

    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    params = {
        "dbfrom": "pmc",
        "db": "pubmed",
        "id": pmcid_clean,
        "retmode": "json"
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        linksets = data.get("linksets", [])
        if linksets:
            linkset = linksets[0]
            linksetdbs = linkset.get("linksetdbs", [])
            if linksetdbs:
                pmid_list = linksetdbs[0].get("links", [])
                if pmid_list:
                    return pmid_list[0]
    except Exception:
        pass
    return None


def search_pubmed_by_title_authors(title, authors=None):
    query = f'"{title}"[Title]'
    if authors:
        author_last_names = [a.split()[-1] for a in authors if a.strip()]
        if author_last_names:
            author_query = " AND ".join([f"{name}[Author]" for name in author_last_names])
            query = f"{query} AND {author_query}"

    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": query,
        "retmode": "json",
        "retmax": 1
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        idlist = data.get("esearchresult", {}).get("idlist", [])
        if idlist:
            return idlist[0]
    except Exception:
        pass
    return None


# --- Main function to process references and get pubmed info ---

def fetch_pubmed_from_references(reference_list):
    pmids = []
    pubmed_studies = []

    for ref in reference_list:
        pmid = ref.get("pmid")
        if pmid:
            if pmid not in pmids:
                pmids.append(pmid)
        else:
            pmid_converted = None
            doi = ref.get("doi")
            pmcid = ref.get("pmcid")

            if doi:
                pmid_converted = convert_doi_to_pmid(doi)
                time.sleep(0.34)
            if not pmid_converted and pmcid:
                pmid_converted = convert_pmcid_to_pmid(pmcid)
                time.sleep(0.34)

            if pmid_converted:
                if pmid_converted not in pmids:
                    pmids.append(pmid_converted)
            else:
                # Fallback: title + author search
                title = ref.get("referenceTitle") or ref.get("title") or ""
                authors = ref.get("authors") or []

                if title:
                    print(f"🔍 Searching PubMed by title: '{title}'")
                    if authors:
                        print(f"\tWith authors: {authors}")

                    pmid_searched = search_pubmed_by_title_authors(title, authors)
                    time.sleep(0.34)

                    if not pmid_searched:
                        # Try partial title match (e.g. use first 5 words)
                        short_title = " ".join(title.split()[:5])
                        print(f"\t🔄 No result. Retrying with short title: '{short_title}'")
                        pmid_searched = search_pubmed_by_title_authors(short_title, authors)
                        time.sleep(0.34)

                    if not pmid_searched:
                        print("\t❌ No result found.")
                    elif pmid_searched not in pmids:
                        print(f"\t✅ Found PMID: {pmid_searched}")
                        pmids.append(pmid_searched)

    # Now fetch details
    for pmid in pmids:
        study = fetch_pubmed_study_api(pmid)
        pubmed_studies.append(study)
        time.sleep(0.34)

    return {
        "pmids": pmids,
        "pubmed_studies": pubmed_studies,
        "source": "pubmed_api"
    }

# --- Combined helper to fetch clinical trial data AND enrich with pubmed ---

def fetch_clinical_trial_and_pubmed(nct_id):
    clinical_trials_result = fetch_clinical_trial_data(nct_id)

    if "error" in clinical_trials_result:
        return clinical_trials_result  # return only the error

    # Shortcut reference to trial data
    ct_data = clinical_trials_result.get("clinical_trial_data", {})
    protocol = ct_data.get("protocolSection", {})

    # Try extracting referenceList from referencesModule
    reference_list = protocol.get("referencesModule", {}).get("referenceList", [])

    if not reference_list:
        # Fall back to synthesizing a reference from title and study lead
        synthesized_reference = {}

        # Get title
        title = protocol.get("identificationModule", {}).get("officialTitle") or \
                protocol.get("identificationModule", {}).get("briefTitle")

        # Get author(s) from overallOfficials
        officials = protocol.get("contactsLocationsModule", {}).get("overallOfficials", [])
        authors = []
        for official in officials:
            if "name" in official:
                authors.append(official["name"])

        if title:
            synthesized_reference["title"] = title
            synthesized_reference["authors"] = authors
            reference_list = [synthesized_reference]

    # Fetch pubmed info
    pubmed_result = fetch_pubmed_from_references(reference_list)

    return {
        "nct_id": nct_id,
        "sources": {
            "clinical_trials": {
                "source": clinical_trials_result["source"],
                "data": clinical_trials_result["clinical_trial_data"]
            },
            "pubmed": {
                "source": pubmed_result["source"],
                "matches_found": bool(pubmed_result["pubmed_studies"]),
                "pmids": pubmed_result["pmids"],
                "studies": pubmed_result["pubmed_studies"]
            }
        }
    }

