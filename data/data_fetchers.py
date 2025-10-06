import requests
import time
import xml.etree.ElementTree as ET
import json
from pathlib import Path

# ---------------------------------
# Configuration
# ---------------------------------
DEFAULT_TIMEOUT = 15
SLEEP_BETWEEN_REQUESTS = 0.34
CTG_V2_BASE = "https://clinicaltrials.gov/api/v2/studies"
CTG_LEGACY_FULL = "https://clinicaltrials.gov/api/query/full_studies"

# ---------------------------------
# ClinicalTrials.gov (v2-first, with fallback)
# ---------------------------------
def fetch_clinical_trial_data(nct_id):
    nct = nct_id.strip().upper()
    v2_detail_url = f"{CTG_V2_BASE}/{nct}"

    print(f"🔍 ClinicalTrials.gov v2: fetching {v2_detail_url}")
    try:
        resp = requests.get(v2_detail_url, timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            print("✅ ClinicalTrials.gov v2: Study found (detail).")
            return {"nct_id": nct, "clinical_trial_data": data, "source": "clinicaltrials_v2_detail"}
        elif resp.status_code == 404:
            print("⚠️ ClinicalTrials.gov v2: detail endpoint returned 404 — trying search fallback.")
        else:
            resp.raise_for_status()
    except Exception as e:
        print(f"❌ ClinicalTrials.gov v2 detail failed: {e}")

    # v2 search fallback
    try:
        params = {"query.nctId": nct, "pageSize": 1}
        print(f"🔍 ClinicalTrials.gov v2: searching with params {params}")
        resp2 = requests.get(CTG_V2_BASE, params=params, timeout=DEFAULT_TIMEOUT)
        if resp2.status_code == 200:
            data2 = resp2.json()
            studies = data2.get("studies", [])
            if studies:
                print("✅ ClinicalTrials.gov v2: Study found via search.")
                return {"nct_id": nct, "clinical_trial_data": studies[0], "source": "clinicaltrials_v2_search"}
            print("⚠️ ClinicalTrials.gov v2: no results found in search.")
    except Exception as e:
        print(f"❌ ClinicalTrials.gov v2 search failed: {e}")

    # Legacy fallback
    try:
        params = {"expr": nct, "min_rnk": 1, "max_rnk": 1, "fmt": "json"}
        print("🔍 ClinicalTrials.gov legacy fallback: querying full_studies ...")
        resp3 = requests.get(CTG_LEGACY_FULL, params=params, timeout=DEFAULT_TIMEOUT)
        resp3.raise_for_status()
        data3 = resp3.json()
        studies = data3.get("FullStudiesResponse", {}).get("FullStudies", [])
        if studies:
            print("✅ ClinicalTrials.gov legacy: Study found.")
            return {"nct_id": nct, "clinical_trial_data": studies[0].get("Study", {}), "source": "clinicaltrials_legacy_full"}
        else:
            print("❌ ClinicalTrials.gov legacy: no study found.")
            return {"error": f"No study found for {nct}", "source": "clinicaltrials_not_found"}
    except Exception as e:
        print(f"❌ ClinicalTrials.gov legacy error: {e}")
        return {"error": str(e), "source": "clinicaltrials_legacy_error"}


# ---------------------------------
# PubMed Utilities
# ---------------------------------
def fetch_pubmed_by_pmid(pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception as e:
        print(f"❌ PubMed efetch error for PMID {pmid}: {e}")
        return {"error": str(e), "source": "pubmed_api", "pmid": pmid}

    article = root.find(".//PubmedArticle")
    if article is None:
        print(f"⚠️ PubMed: no article data for PMID {pmid}")
        return {"error": "No article found", "source": "pubmed_api", "pmid": pmid}

    title = article.findtext(".//ArticleTitle", default="")
    abstract = "".join([t.text or "" for t in article.findall(".//AbstractText")])
    journal = article.findtext(".//Journal/Title", default="")
    pub_date = article.findtext(".//PubDate/Year", default="")
    authors = [
        f"{a.findtext('ForeName')} {a.findtext('LastName')}".strip()
        for a in article.findall(".//Author")
        if a.findtext("LastName") and a.findtext("ForeName")
    ]
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
        print(f"❌ PubMed esearch error for '{term}': {e}")
        return []


def search_pubmed_by_title_authors(title, authors=None):
    query = f'"{title}"[Title]'
    if authors:
        last_names = [a.split()[-1] for a in authors if a.strip()]
        if last_names:
            query += " AND " + " AND ".join([f"{ln}[Author]" for ln in last_names])
    pmids = search_pubmed_esearch(query, max_results=1)
    if pmids:
        print(f"✅ PubMed: found PMID {pmids[0]}")
        return pmids[0]
    print("⚠️ PubMed: no results found.")
    return None


# ---------------------------------
# PMC Utilities
# ---------------------------------
def search_pmc(query, max_results=5):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pmc", "term": query, "retmode": "json", "retmax": max_results}
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        ids = resp.json().get("esearchresult", {}).get("idlist", [])
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        if ids:
            print(f"✅ PMC: found {len(ids)} matches.")
        else:
            print("⚠️ PMC: no matches found.")
        return ids
    except Exception as e:
        print(f"❌ PMC esearch error: {e}")
        return []


def fetch_pmc_esummary(pmcid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    params = {"db": "pmc", "id": pmcid, "retmode": "json"}
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        time.sleep(SLEEP_BETWEEN_REQUESTS)
        print(f"✅ PMC: fetched metadata for {pmcid}")
        return resp.json()
    except Exception as e:
        print(f"❌ PMC esummary error for {pmcid}: {e}")
        return {"error": str(e), "source": "pmc_esummary", "pmcid": pmcid}


def convert_pmc_summary_to_metadata(esum):
    result = {}
    res = esum.get("result", {})
    for uid in res.get("uids", []):
        rec = res.get(uid, {})
        result[uid] = {
            "title": rec.get("title"),
            "pubdate": rec.get("pubdate"),
            "authors": rec.get("authors"),
            "doi": rec.get("articleids", {}),
            "pmid": rec.get("pmid"),
        }
    return result


# ---------------------------------
# Combined Fetcher
# ---------------------------------
def fetch_clinical_trial_and_pubmed_pmc(nct_id):
    clin = fetch_clinical_trial_data(nct_id)
    if "error" in clin:
        return clin

    ctdata = clin.get("clinical_trial_data", {})
    protocol = ctdata.get("protocolSection", {}) if isinstance(ctdata, dict) else {}
    refs = protocol.get("referencesModule", {}).get("referenceList", [])

    if not refs:
        title = (protocol.get("identificationModule", {}).get("officialTitle") or
                 protocol.get("identificationModule", {}).get("briefTitle"))
        officials = protocol.get("contactsLocationsModule", {}).get("overallOfficials", [])
        authors = [o.get("name") for o in officials if "name" in o]
        if title:
            refs = [{"title": title, "authors": authors}]

    pubmed, pmc = {"pmids": [], "studies": []}, {"pmcids": [], "summaries": []}

    for ref in refs:
        title = ref.get("referenceTitle") or ref.get("title")
        authors = ref.get("authors", [])
        print(f"\n📖 Searching for related publications: '{title}'")

        pmid = search_pubmed_by_title_authors(title, authors)
        if pmid:
            pubmed["pmids"].append(pmid)
            pubmed["studies"].append(fetch_pubmed_by_pmid(pmid))

        pmcids = search_pmc(title)
        for pid in pmcids:
            if pid not in pmc["pmcids"]:
                pmc["pmcids"].append(pid)
                meta = convert_pmc_summary_to_metadata(fetch_pmc_esummary(pid))
                pmc["summaries"].append({"pmcid": pid, "metadata": meta})

    return {
        "nct_id": nct_id,
        "sources": {
            "clinical_trials": {"source": clin.get("source"), "data": ctdata},
            "pubmed": pubmed,
            "pmc": pmc
        }
    }


# ---------------------------------
# Pretty Print
# ---------------------------------
def print_study_summary(result):
    print("\n===== 📊 CLINICAL TRIAL SUMMARY =====")
    protocol = result["sources"]["clinical_trials"]["data"].get("protocolSection", {})
    ident = protocol.get("identificationModule", {})
    print(f"🧪 {ident.get('officialTitle', ident.get('briefTitle', 'Untitled'))}")
    print(f"📅 Status: {protocol.get('statusModule', {}).get('overallStatus')}")
    print(f"🏥 Sponsor: {ident.get('organization', {}).get('fullName')}")
    print(f"📍 Conditions: {', '.join(protocol.get('conditionsModule', {}).get('conditions', []))}")

    pubs = result["sources"]["pubmed"]["studies"]
    if pubs:
        print("\n===== 📚 PUBMED RESULTS =====")
        for p in pubs:
            print(f"🔹 {p['title']} ({p['publication_date']})")
            print(f"   {p['journal']} — PMID: {p['pmid']}")
    else:
        print("\n📭 No PubMed matches found.")

    pmcids = result["sources"]["pmc"]["pmcids"]
    if pmcids:
        print("\n===== 🧾 PMC RESULTS =====")
        for pid in pmcids:
            print(f"🔸 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pid}/")
    else:
        print("\n📭 No PMC matches found.")

def summarize_result(result):
    """Return a compact summary dict for CLI or JSON output."""
    nct_id = result.get("nct_id")
    sources = result.get("sources", {})

    clin = sources.get("clinical_trials", {})
    pubmed = sources.get("pubmed", {})
    pmc = sources.get("pmc", {})

    pmids = pubmed.get("pmids", [])
    pmcids = pmc.get("pmcids", [])

    return {
        "NCT": nct_id,
        "ClinicalTrials.gov Source": clin.get("source"),
        "PubMed Count": len(pmids),
        "PMC Count": len(pmcids),
        "PubMed IDs": ", ".join(pmids) if pmids else "None",
        "PMC IDs": ", ".join(pmcids) if pmcids else "None",
    }

def save_results(result, output_path="data/output"):
    """Save results to JSON file inside output directory."""
    Path(output_path).mkdir(parents=True, exist_ok=True)
    nct_id = result.get("nct_id", "unknown")
    filename = Path(output_path) / f"{nct_id}_results.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"💾 Results saved to {filename}")