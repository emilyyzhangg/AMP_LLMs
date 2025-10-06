import requests
import time
import xml.etree.ElementTree as ET
import json

# ========== ClinicalTrials.gov fetch ==========

def fetch_clinical_trial_data(nct_id):
    base = "https://clinicaltrials.gov/api/v2/studies/"
    url = f"{base}{nct_id}"
    try:
        print("🔍 Fetching ClinicalTrials.gov study data...")
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        print("✅ ClinicalTrials.gov: Study found.")
        return {
            "nct_id": nct_id,
            "clinical_trial_data": data,
            "source": "clinicaltrials_api"
        }
    except requests.exceptions.HTTPError as e:
        print(f"❌ ClinicalTrials.gov: HTTP error: {e}")
        return {"error": f"HTTP error: {e}", "source": "clinicaltrials_api"}
    except Exception as e:
        print(f"❌ ClinicalTrials.gov: Error: {e}")
        return {"error": str(e), "source": "clinicaltrials_api"}

# ========== PubMed utilities ==========

def fetch_pubmed_by_pmid(pmid):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pubmed", "id": pmid, "retmode": "xml"}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"❌ PubMed efetch error for PMID {pmid}: {e}")
        return {"error": str(e), "source": "pubmed_api", "pmid": pmid}

    root = ET.fromstring(resp.text)
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
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        time.sleep(0.34)
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
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        time.sleep(0.34)
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

# ========== PMC utilities ==========

def search_pmc(query, max_results=5):
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {"db": "pmc", "term": query, "retmode": "json", "retmax": max_results}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        time.sleep(0.34)
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
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        time.sleep(0.34)
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

# ========== Combined logic ==========

def fetch_pubmed_with_order(ref):
    """Return (pmid, method) if found, else (None, method_str)."""
    # Direct PMID
    if ref.get("pmid"):
        print(f"🔍 PubMed: direct PMID search: {ref['pmid']}")
        return ref["pmid"], "pmid_direct"
    # DOI → PMID
    if ref.get("doi"):
        pmid = convert_doi_to_pmid(ref["doi"])
        if pmid:
            return pmid, "doi_to_pmid"
    # PMCID → PMID
    if ref.get("pmcid"):
        pmid = convert_pmcid_to_pmid(ref["pmcid"])
        if pmid:
            return pmid, "pmcid_to_pmid"
    # Title + authors fallback
    title = ref.get("referenceTitle") or ref.get("title")
    authors = ref.get("authors")
    if title:
        print(f"🔍 PubMed: title/authors fallback: '{title}'")
        pmid = search_pubmed_by_title_authors(title, authors)
        if pmid:
            return pmid, "title_author"
    # If none found, but in your logic you want fallback always attempted, we already did
    return None, "no_match"

def fetch_pmc_with_order(ref):
    """Return (pmcid_list, method) if found, else ([], method_str)."""
    # Direct PMCID
    if ref.get("pmcid"):
        print(f"🔍 PMC: direct PMCID: {ref['pmcid']}")
        return [ref["pmcid"]], "pmcid_direct"
    # Title fallback
    title = ref.get("referenceTitle") or ref.get("title")
    authors = ref.get("authors")
    if title:
        print(f"🔍 PMC: title fallback: '{title}'")
        ids = search_pmc(title)
        if ids:
            return ids, "title_search"
        # Retry short title
        short = " ".join(title.split()[:5])
        print(f"\t🔄 PMC: retry short title: '{short}'")
        ids2 = search_pmc(short)
        if ids2:
            return ids2, "short_title_search"
    return [], "no_match"

def fetch_clinical_trial_and_pubmed_pmc(nct_id):
    clin = fetch_clinical_trial_data(nct_id)
    if "error" in clin:
        return clin

    ctdata = clin["clinical_trial_data"]
    protocol = ctdata.get("protocolSection", {})
    refs = protocol.get("referencesModule", {}).get("referenceList", [])

    if not refs:
        # fallback synthesize
        synthesized = {}
        title = (protocol.get("identificationModule", {}).get("officialTitle")
                 or protocol.get("identificationModule", {}).get("briefTitle"))
        officials = protocol.get("contactsLocationsModule", {}).get("overallOfficials", [])
        authors = [o.get("name") for o in officials if "name" in o]
        if title:
            synthesized["title"] = title
            synthesized["authors"] = authors
            refs = [synthesized]

    pubmed = {"pmids": [], "studies": [], "search_methods": []}
    pmc = {"pmcids": [], "summaries": [], "search_methods": []}

    # For each reference, run both PubMed and PMC searches
    for ref in refs:
        # PubMed
        pmid, method = fetch_pubmed_with_order(ref)
        pubmed["search_methods"].append(method)
        if pmid:
            if pmid not in pubmed["pmids"]:
                pubmed["pmids"].append(pmid)
                study = fetch_pubmed_by_pmid(pmid)
                pubmed["studies"].append(study)

        # PMC
        pmcids, pmc_method = fetch_pmc_with_order(ref)
        pmc["search_methods"].append(pmc_method)
        for pid in pmcids:
            if pid not in pmc["pmcids"]:
                pmc["pmcids"].append(pid)
                summary_json = fetch_pmc_esummary(pid)
                metadata = convert_pmc_summary_to_metadata(summary_json)
                pmc["summaries"].append({
                    "pmcid": pid,
                    "metadata": metadata
                })

    output = {
        "nct_id": nct_id,
        "sources": {
            "clinical_trials": {
                "source": clin["source"],
                "data": clin["clinical_trial_data"]
            },
            "pubmed": {
                "source": "pubmed_api",
                "pmids": pubmed["pmids"],
                "studies": pubmed["studies"],
                "search_methods": pubmed["search_methods"]
            },
            "pmc": {
                "source": "pmc",
                "pmcids": pmc["pmcids"],
                "summaries": pmc["summaries"],
                "search_methods": pmc["search_methods"]
            }
        }
    }

    return output

def save_json(data, fname):
    with open(fname, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n✅ Results saved to '{fname}'")

def main():
    print("🔬 ClinicalTrials.gov + PubMed + PMC (full, verbose) tool")
    nct_id = input("Enter NCT ID (e.g. NCT01234567): ").strip().upper()
    if not nct_id.startswith("NCT"):
        print("❌ Invalid NCT ID.")
        return

    print(f"\n🔍 Looking up data for {nct_id}...\n")
    result = fetch_clinical_trial_and_pubmed_pmc(nct_id)
    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return

    fname = f"{nct_id}_full_verbose.json"
    save_json(result, fname)

if __name__ == "__main__":
    main()
