"""
Hybrid async/sync data fetchers for clinical trial and PubMed/PMC data.
Uses proven synchronous requests library wrapped in async executor to avoid rate limiting issues.
Maintains original emoji output format.
"""
import requests
import time
import xml.etree.ElementTree as ET
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional
from functools import partial

# Configuration
DEFAULT_TIMEOUT = 15
SLEEP_BETWEEN_REQUESTS = 0.34
CTG_V2_BASE = "https://clinicaltrials.gov/api/v2/studies"
CTG_LEGACY_FULL = "https://clinicaltrials.gov/api/query/full_studies"

# ---------------------------------
# ClinicalTrials.gov (synchronous - proven to work)
# ---------------------------------
def _sync_fetch_clinical_trial_data(nct_id):
    """Synchronous version that actually works."""
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
        params = {"query.term": nct, "pageSize": 1}
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
# PubMed Utilities (synchronous - proven to work)
# ---------------------------------
def _sync_fetch_pubmed_by_pmid(pmid):
    """Fetch and parse full metadata from PubMed efetch."""
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

    # Core metadata
    art = article.find(".//Article")
    title = art.findtext("ArticleTitle", default="")
    abstract_elems = art.findall(".//AbstractText")
    abstract = " ".join([a.text or "" for a in abstract_elems])

    # Extract structured abstract labels
    if any("Label" in a.attrib for a in abstract_elems):
        abstract = " ".join([
            f"{a.attrib.get('Label', '')}: {a.text or ''}".strip()
            for a in abstract_elems
        ])

    journal = art.findtext(".//Journal/Title", default="")
    journal_issn = art.findtext(".//Journal/ISSN", default="")
    pub_date = (
        art.findtext(".//PubDate/Year") or
        art.findtext(".//ArticleDate/Year") or
        ""
    )

    # DOI & identifiers
    doi = None
    for aid in article.findall(".//ArticleId"):
        if aid.attrib.get("IdType") == "doi":
            doi = aid.text
            break

    # Authors + Affiliations
    authors_data = []
    for a in art.findall(".//Author"):
        last = a.findtext("LastName")
        fore = a.findtext("ForeName")
        name = f"{fore} {last}".strip() if fore and last else (last or fore or "")
        affs = [aff.text for aff in a.findall(".//Affiliation") if aff.text]
        authors_data.append({"name": name, "affiliations": affs})

    # Keywords
    keywords = [kw.text for kw in article.findall(".//Keyword") if kw.text]

    # MeSH terms
    mesh_terms = [
        mh.findtext("DescriptorName") for mh in article.findall(".//MeshHeading")
    ]

    # Grant info
    grants = [
        {
            "agency": g.findtext("Agency"),
            "grant_id": g.findtext("GrantID"),
            "country": g.findtext("Country")
        }
        for g in article.findall(".//Grant")
    ]

    # Publication types
    pub_types = [pt.text for pt in art.findall(".//PublicationType") if pt.text]

    language = art.findtext(".//Language", default="")

    print(f"✅ PubMed: fetched full metadata for PMID {pmid}")

    return {
        "pmid": pmid,
        "title": title,
        "abstract": abstract,
        "journal": journal,
        "journal_issn": journal_issn,
        "publication_date": pub_date,
        "doi": doi,
        "authors": authors_data,
        "keywords": keywords,
        "mesh_terms": mesh_terms,
        "publication_types": pub_types,
        "language": language,
        "grants": grants,
        "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "source": "pubmed_api"
    }


def _sync_search_pubmed_esearch(term, max_results=5):
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


def _sync_search_pubmed_by_title_authors(title, authors=None):
    query = f'"{title}"[Title]'
    if authors:
        last_names = [a.split()[-1] for a in authors if a.strip()]
        if last_names:
            query += " AND " + " AND ".join([f"{ln}[Author]" for ln in last_names])
    pmids = _sync_search_pubmed_esearch(query, max_results=1)
    if pmids:
        print(f"✅ PubMed: found PMID {pmids[0]}")
        return pmids[0]
    print("⚠️ PubMed: no results found.")
    return None


# ---------------------------------
# PMC Utilities (synchronous - proven to work)
# ---------------------------------
def _sync_search_pmc(query, max_results=5):
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


def _sync_fetch_pmc_esummary(pmcid):
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
    """Extract detailed metadata from PMC esummary response."""
    result = {}
    res = esum.get("result", {})
    for uid in res.get("uids", []):
        rec = res.get(uid, {})
        result[uid] = {
            "title": rec.get("title"),
            "journal": rec.get("source"),
            "pubdate": rec.get("pubdate"),
            "authors": [a.get("name") for a in rec.get("authors", []) if a.get("name")],
            "doi": [aid.get("value") for aid in rec.get("articleids", []) if aid.get("idtype") == "doi"],
            "pmid": rec.get("pmid"),
            "pmcid": rec.get("pmcid"),
            "volume": rec.get("volume"),
            "issue": rec.get("issue"),
            "pages": rec.get("pages"),
            "fulljournalname": rec.get("fulljournalname"),
            "sortpubdate": rec.get("sortpubdate"),
            "epubdate": rec.get("epubdate"),
            "essn": rec.get("essn"),
            "issn": rec.get("issn"),
        }
    return result


# ---------------------------------
# Async wrappers for synchronous functions
# ---------------------------------
async def fetch_clinical_trial_and_pubmed_pmc(nct_id: str) -> Dict[str, Any]:
    """
    Async wrapper that runs synchronous code in thread pool.
    This avoids blocking the event loop while using proven working code.
    """
    loop = asyncio.get_event_loop()
    
    # Fetch clinical trial data
    clin = await loop.run_in_executor(None, _sync_fetch_clinical_trial_data, nct_id)
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

        # Run PubMed search in executor
        pmid = await loop.run_in_executor(
            None, _sync_search_pubmed_by_title_authors, title, authors
        )
        if pmid:
            pubmed["pmids"].append(pmid)
            pubmed_data = await loop.run_in_executor(
                None, _sync_fetch_pubmed_by_pmid, pmid
            )
            pubmed["studies"].append(pubmed_data)

        # Run PMC search in executor
        pmcids = await loop.run_in_executor(None, _sync_search_pmc, title)
        for pid in pmcids:
            if pid not in pmc["pmcids"]:
                pmc["pmcids"].append(pid)
                pmc_meta = await loop.run_in_executor(
                    None, _sync_fetch_pmc_esummary, pid
                )
                pmc["summaries"].append({
                    "pmcid": pid,
                    "metadata": convert_pmc_summary_to_metadata(pmc_meta)
                })

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
def print_study_summary(result: Dict[str, Any]):
    print("\n===== 📊 CLINICAL TRIAL SUMMARY =====")
    protocol = result["sources"]["clinical_trials"]["data"].get("protocolSection", {})
    ident = protocol.get("identificationModule", {})
    print(f"🧪 {ident.get('officialTitle', ident.get('briefTitle', 'Untitled'))}")
    print(f"📅 Status: {protocol.get('statusModule', {}).get('overallStatus')}")
    print(f"🏥 Sponsor: {ident.get('organization', {}).get('fullName')}")
    print(f"🔬 Conditions: {', '.join(protocol.get('conditionsModule', {}).get('conditions', []))}")

    pubs = result["sources"]["pubmed"]["studies"]
    if pubs:
        print("\n===== 📚 PUBMED RESULTS =====")
        for p in pubs:
            print(f"🔹 {p['title']} ({p['publication_date']})")
            print(f"   {p['journal']} — PMID: {p['pmid']}")
    else:
        print("\n🔭 No PubMed matches found.")

    pmcids = result["sources"]["pmc"]["pmcids"]
    if pmcids:
        print("\n===== 🧾 PMC RESULTS =====")
        for pid in pmcids:
            print(f"🔸 https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pid}/")
    else:
        print("\n🔭 No PMC matches found.")


def summarize_result(result: Dict[str, Any]) -> Dict[str, Any]:
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


def save_results(results: List[Dict[str, Any]], filename: str, fmt: str = 'txt'):
    """Save results to file."""
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    if fmt == 'csv':
        import csv
        path = output_dir / f'{filename}.csv'
        keys = ['NCT', 'ClinicalTrials.gov Source', 'PubMed Count', 'PMC Count', 'PubMed IDs', 'PMC IDs']
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            for r in results:
                writer.writerow(summarize_result(r))
    elif fmt == 'json':
        path = output_dir / f'{filename}.json'
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    else:  # txt
        path = output_dir / f'{filename}.txt'
        with open(path, 'w', encoding='utf-8') as f:
            for r in results:
                f.write(json.dumps(r, indent=2, ensure_ascii=False))
                f.write('\n\n')

    print(f"💾 Results saved to {path}")