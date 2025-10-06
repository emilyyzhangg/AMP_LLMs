# data/data_fetchers.py
import requests
import time
import xml.etree.ElementTree as ET

# Config
DEFAULT_TIMEOUT = 10
SLEEP_BETWEEN_REQUESTS = 0.34
CTG_V2_BASE = "https://clinicaltrials.gov/api/v2/studies"
CTG_LEGACY_FULL = "https://clinicaltrials.gov/api/query/full_studies"


# -------------------------
# ClinicalTrials.gov fetch (v2 primary, robust fallbacks)
# -------------------------
def fetch_clinical_trial_data(nct_id):
    """
    Fetch ClinicalTrials.gov record for nct_id.
    Strategy:
      1) Try v2 detail endpoint: /api/v2/studies/{NCT}
      2) If 404 or no result, try v2 search endpoint: /api/v2/studies?query.nctId={NCT}
      3) If still not found, try legacy API full_studies endpoint as a last resort.
    Returns a dict with either clinical_trial_data or an 'error' key.
    """
    nct = nct_id.strip().upper()
    # 1) v2 detail endpoint
    v2_detail_url = f"{CTG_V2_BASE}/{nct}"
    try:
        print(f"🔍 ClinicalTrials.gov v2: fetching {v2_detail_url}")
        resp = requests.get(v2_detail_url, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            print("✅ ClinicalTrials.gov v2: Study found (detail).")
            return {"nct_id": nct, "clinical_trial_data": data, "source": "clinicaltrials_v2_detail"}
        elif resp.status_code == 404:
            print("⚠️ ClinicalTrials.gov v2: detail endpoint returned 404 — will try v2 search fallback.")
        else:
            resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        # allow fallbacks for 404; otherwise return error on other HTTP problems
        if resp.status_code != 404:
            print(f"❌ ClinicalTrials.gov v2: HTTP error: {e}")
            return {"error": f"HTTP error: {e}", "source": "clinicaltrials_v2_detail"}
    except Exception as e:
        # network / other issue — keep trying fallbacks but print
        print(f"❌ ClinicalTrials.gov v2 detail request failed: {e}")

    # 2) v2 search endpoint fallback (query.nctId)
    try:
        params = {"query.nctId": nct, "pageSize": 1}
        print(f"🔍 ClinicalTrials.gov v2: searching with params {params}")
        resp2 = requests.get(CTG_V2_BASE, params=params, timeout=DEFAULT_TIMEOUT)
        if resp2.status_code == 200:
            data2 = resp2.json()
            studies = data2.get("studies") or data2.get("results") or []
            if studies:
                # sometimes the search response wraps studies differently; we pick the first
                study = studies[0]
                print("✅ ClinicalTrials.gov v2: Study found via search endpoint.")
                return {"nct_id": nct, "clinical_trial_data": study, "source": "clinicaltrials_v2_search"}
            else:
                print("⚠️ ClinicalTrials.gov v2 search returned no studies.")
        else:
            print(f"⚠️ ClinicalTrials.gov v2 search returned status {resp2.status_code}")
    except Exception as e:
        print(f"❌ ClinicalTrials.gov v2 search failed: {e}")

    # 3) Legacy API fallback (full_studies)
    try:
        params = {"expr": nct, "min_rnk": 1, "max_rnk": 1, "fmt": "json"}
        print(f"🔍 ClinicalTrials.gov legacy API fallback: querying full_studies with {params}")
        resp3 = requests.get(CTG_LEGACY_FULL, params=params, timeout=DEFAULT_TIMEOUT)
        resp3.raise_for_status()
        data3 = resp3.json()
        studies = data3.get("FullStudiesResponse", {}).get("FullStudies", [])
        if studies:
            # legacy returns a list of wrapper objects with "Study" inside
            study_wrapper = studies[0]
            study = study_wrapper.get("Study", {})
            print("✅ ClinicalTrials.gov legacy API: Study found.")
            return {"nct_id": nct, "clinical_trial_data": study, "source": "clinicaltrials_legacy_full"}
        else:
            print("❌ ClinicalTrials.gov: No study found in legacy fallback.")
            return {"error": f"No study found for {nct}", "source": "clinicaltrials_not_found"}
    except Exception as e:
        print(f"❌ ClinicalTrials.gov legacy API error: {e}")
        return {"error": f"HTTP error: {e}", "source": "clinicaltrials_legacy_error"}


# -------------------------
# PubMed utilities (unchanged behavior but consistent)
# -------------------------
def fetch_pubmed_by_pmid(pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ PubMed efetch error for PMID {pmid}: {e}")
        return {"error": str(e), "source": "pubmed_api", "pmid": pmid}

    try:
        root = ET.fromstring(resp.text)
    except Exception as e:
        return {"error": f"Malformed XML: {e}", "source": "pubmed_api", "pmid": pmid}

    article = root.find(".//PubmedArticle")
    if article is None:
        print(f"❌ PubMed: No article data found for PMID {pmid}")
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

    print(f"✅ PubMed: fetched metadata for PMID {pmid}")
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


def search_pubmed_esearch(term, max_results=5):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pubmed", "term": term, "retmode": "json", "retmax": max_results}
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"❌ PubMed esearch error for term '{term}': {e}")
        return []


def search_pubmed_by_title_authors(title, authors=None):
    query = f'"{title}"[Title]'
    if authors:
        last_names = [a.split()[-1] for a in authors if a.strip()]
        if last_names:
            author_q = " AND ".join([f"{ln}[Author]" for ln in last_names])
            query = f"{query} AND {author_q}"
    pmids = search_pubmed_esearch(query, max_results=1)
    if pmids:
        print(f"✅ PubMed: title/authors search found PMID {pmids[0]}")
        return pmids[0]
    print("❌ PubMed: title/authors search found nothing.")
    return None


def convert_doi_to_pmid(doi):
    term = f"{doi}[DOI]"
    pmids = search_pubmed_esearch(term, max_results=1)
    if pmids:
        print(f"✅ PubMed: DOI → PMID conversion: {doi} → {pmids[0]}")
        return pmids[0]
    print(f"❌ PubMed: DOI to PMID returned no result for {doi}")
    return None


def convert_pmcid_to_pmid(pmcid):
    pmcid_clean = pmcid.upper().strip()
    if not pmcid_clean.startswith("PMC"):
        print(f"❌ Invalid PMCID format: {pmcid}")
        return None
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
    params = {"dbfrom": "pmc", "db": "pubmed", "id": pmcid_clean, "retmode": "json"}
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        linksets = data.get("linksets", [])
        if linksets:
            dbs = linksets[0].get("linksetdbs", [])
            if dbs:
                links = dbs[0].get("links", [])
                if links:
                    print(f"✅ PubMed: PMCID → PMID: {pmcid_clean} → {links[0]}")
                    return links[0]
    except Exception as e:
        print(f"❌ PubMed: error converting PMCID {pmcid}: {e}")
    print(f"❌ PubMed: no PMID from PMCID {pmcid}")
    return None


# -------------------------
# PMC utilities
# -------------------------
def search_pmc(query, max_results=5):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pmc", "term": query, "retmode": "json", "retmax": max_results}
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        ids = data.get("esearchresult", {}).get("idlist", [])
        if ids:
            print(f"✅ PMC: search for '{query}' found PMCIDs: {ids}")
        else:
            print(f"❌ PMC: search for '{query}' found no PMCIDs")
        return ids
    except Exception as e:
        print(f"❌ PMC esearch error for '{query}': {e}")
        return []


def fetch_pmc_esummary(pmcid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pmc", "id": pmcid, "retmode": "json"}
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        print(f"✅ PMC: fetched esummary for PMCID {pmcid}")
        return resp.json()
    except Exception as e:
        print(f"❌ PMC: esummary fetch error for PMCID {pmcid}: {e}")
        return {"error": str(e), "source": "pmc_esummary", "pmcid": pmcid}


def convert_pmc_summary_to_metadata(esum):
    result = {}
    res = esum.get("result", {})
    uids = res.get("uids", [])
    for uid in uids:
        rec = res.get(uid, {})
        result[uid] = {
            "title": rec.get("title"),
            "pubdate": rec.get("pubdate"),
            "source_db": rec.get("source_db"),
            "authors": rec.get("authors"),
            "doi": rec.get("articleids", {}),
            "pmid": rec.get("pmid")
        }
    return result


# -------------------------
# Combined logic: PubMed + PMC lookup pipeline
# -------------------------
def fetch_pubmed_with_order(ref):
    """Return (pmid, method)."""
    if ref.get("pmid"):
        print(f"🔍 PubMed: direct PMID search: {ref['pmid']}")
        return ref["pmid"], "pmid_direct"
    if ref.get("doi"):
        pmid = convert_doi_to_pmid(ref["doi"])
        if pmid:
            return pmid, "doi_to_pmid"
    if ref.get("pmcid"):
        pmid = convert_pmcid_to_pmid(ref["pmcid"])
        if pmid:
            return pmid, "pmcid_to_pmid"
    title = ref.get("referenceTitle") or ref.get("title")
    authors = ref.get("authors")
    if title:
        print(f"🔍 PubMed: title/authors fallback: '{title}'")
        pmid = search_pubmed_by_title_authors(title, authors)
        if pmid:
            return pmid, "title_author"
    return None, "no_match"


def fetch_pmc_with_order(ref):
    """Return (pmcid_list, method)."""
    if ref.get("pmcid"):
        print(f"🔍 PMC: direct PMCID: {ref['pmcid']}")
        return [ref["pmcid"]], "pmcid_direct"
    title = ref.get("referenceTitle") or ref.get("title")
    if title:
        print(f"🔍 PMC: title fallback: '{title}'")
        ids = search_pmc(title)
        if ids:
            return ids, "title_search"
        short = " ".join(title.split()[:5])
        print(f"\t🔄 PMC: retry short title: '{short}'")
        ids2 = search_pmc(short)
        if ids2:
            return ids2, "short_title_search"
    return [], "no_match"


def fetch_clinical_trial_and_pubmed_pmc(nct_id):
    """
    Canonical combined function: fetch clinical trial (v2-first) and then enrich via PubMed + PMC.
    """
    clin = fetch_clinical_trial_data(nct_id)
    if "error" in clin:
        return clin

    ctdata = clin.get("clinical_trial_data", {})
    protocol = ctdata.get("protocolSection", {}) if isinstance(ctdata, dict) else {}
    refs = protocol.get("referencesModule", {}).get("referenceList", []) if protocol else []

    if not refs:
        synthesized = {}
        title = (protocol.get("identificationModule", {}).get("officialTitle")
                 or protocol.get("identificationModule", {}).get("briefTitle")) if protocol else ""
        officials = protocol.get("contactsLocationsModule", {}).get("overallOfficials", []) if protocol else []
        authors = [o.get("name") for o in officials if "name" in o] if officials else []
        if title:
            synthesized["title"] = title
            synthesized["authors"] = authors
            refs = [synthesized]

    pubmed = {"pmids": [], "studies": [], "search_methods": []}
    pmc = {"pmcids": [], "summaries": [], "search_methods": []}

    for ref in refs:
        pmid, method = fetch_pubmed_with_order(ref)
        pubmed["search_methods"].append(method)
        if pmid and pmid not in pubmed["pmids"]:
            pubmed["pmids"].append(pmid)
            study = fetch_pubmed_by_pmid(pmid)
            pubmed["studies"].append(study)

        pmcids, pmc_method = fetch_pmc_with_order(ref)
        pmc["search_methods"].append(pmc_method)
        for pid in pmcids:
            if pid not in pmc["pmcids"]:
                pmc["pmcids"].append(pid)
                summary_json = fetch_pmc_esummary(pid)
                metadata = convert_pmc_summary_to_metadata(summary_json)
                pmc["summaries"].append({"pmcid": pid, "metadata": metadata})

    return {
        "nct_id": nct_id,
        "sources": {
            "clinical_trials": {"source": clin.get("source", "clinicaltrials_api"),
                                "data": clin.get("clinical_trial_data", {})},
            "pubmed": {"source": "pubmed_api", "pmids": pubmed["pmids"],
                       "studies": pubmed["studies"], "search_methods": pubmed["search_methods"]},
            "pmc": {"source": "pmc", "pmcids": pmc["pmcids"],
                    "summaries": pmc["summaries"], "search_methods": pmc["search_methods"]},
        }
    }
