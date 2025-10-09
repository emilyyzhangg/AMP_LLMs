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
    """Fetch and parse as much metadata as possible from PubMed efetch."""
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


def fetch_pmc_efetch(pmcid):
    """
    Fetch full metadata from PMC using efetch (richer than esummary).
    Returns dict with title, journal, abstract, authors, doi, etc.
    """
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pmc", "id": pmcid, "retmode": "xml"}
    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception as e:
        print(f"❌ PMC efetch error for PMCID {pmcid}: {e}")
        return {"error": str(e), "source": "pmc_efetch", "pmcid": pmcid}

    article = root.find(".//article")
    if article is None:
        print(f"⚠️ PMC efetch: no article found for PMCID {pmcid}")
        return {"error": "No article found", "source": "pmc_efetch", "pmcid": pmcid}

    # --- Extract fields
    title = article.findtext(".//article-title", default="")
    abstract = " ".join([t.text or "" for t in article.findall(".//abstract//p")])
    journal = article.findtext(".//journal-title", default="")
    pub_date = article.findtext(".//pub-date/year", default="")
    authors = [
        " ".join(filter(None, [
            a.findtext("given-names"),
            a.findtext("surname")
        ])).strip()
        for a in article.findall(".//contrib[@contrib-type='author']")
    ]
    doi = article.findtext(".//article-id[@pub-id-type='doi']", default="")

    print(f"✅ PMC efetch: fetched full metadata for {pmcid}")
    return {
        "pmcid": pmcid,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "journal": journal,
        "publication_date": pub_date,
        "doi": doi,
        "url": f"https://www.ncbi.nlm.nih.gov/pmc/articles/PMC{pmcid}/",
        "source": "pmc_efetch"
    }

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
            meta = convert_pmc_summary_to_metadata(fetch_pmc_esummary(pid))
            pmc["summaries"].append({"pmcid": pid, "metadata": meta})

            # NEW: fetch full text if available
            fulltext = fetch_pmc_fulltext(pid)
            if "error" not in fulltext:
                pmc["summaries"][-1]["fulltext"] = fulltext

            if pid not in pmc["pmcids"]:
                pmc["pmcids"].append(pid)
                # Try full PMC efetch first, fallback to esummary if it fails
                pmc_meta = fetch_pmc_efetch(pid)
                if "error" in pmc_meta:
                    pmc_meta = convert_pmc_summary_to_metadata(fetch_pmc_esummary(pid))
                pmc["summaries"].append({"pmcid": pid, "metadata": pmc_meta})

    return {
        "nct_id": nct_id,
        "sources": {
            "clinical_trials": {"source": clin.get("source"), "data": ctdata},
            "pubmed": pubmed,
            "pmc": pmc
        }
    }

def fetch_pmc_fulltext(pmcid):
    """
    Fetch full-text article XML from PMC and extract sections, figures, references, and metadata.
    Returns a structured dict with parsed content.
    """
    pmcid_clean = str(pmcid).replace("PMC", "")
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {"db": "pmc", "id": pmcid_clean, "retmode": "xml"}

    try:
        resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except Exception as e:
        print(f"❌ PMC efetch error for {pmcid}: {e}")
        return {"error": str(e), "source": "pmc_efetch", "pmcid": pmcid}

    article = root.find(".//article")
    if article is None:
        print(f"⚠️ No full-text XML found for {pmcid}")
        return {"error": "No full-text XML", "pmcid": pmcid}

    # Metadata
    metadata = {
        "pmcid": f"PMC{pmcid_clean}",
        "title": article.findtext(".//article-title", default=""),
        "journal": article.findtext(".//journal-title", default=""),
        "pub_date": article.findtext(".//pub-date/year", default=""),
        "volume": article.findtext(".//volume", default=""),
        "issue": article.findtext(".//issue", default=""),
        "fpage": article.findtext(".//fpage", default=""),
        "lpage": article.findtext(".//lpage", default=""),
        "doi": article.findtext(".//article-id[@pub-id-type='doi']", default=None)
    }

    # Authors
    authors = []
    for a in article.findall(".//contrib[@contrib-type='author']"):
        name = " ".join(
            filter(None, [a.findtext(".//given-names"), a.findtext(".//surname")])
        )
        aff = [aff.text for aff in a.findall(".//aff") if aff.text]
        authors.append({"name": name, "affiliations": aff})
    metadata["authors"] = authors

    # Abstract
    abstract = "\n".join(
        [p.text or "" for p in article.findall(".//abstract//p") if p.text]
    )

    # Full text sections
    sections = []
    for sec in article.findall(".//body//sec"):
        sec_title = sec.findtext("title", default="(No title)")
        paras = [p.text or "" for p in sec.findall("p") if p.text]
        if paras:
            sections.append({"title": sec_title, "paragraphs": paras})

    # Figures & Tables (captions only)
    figures = []
    for fig in article.findall(".//fig"):
        caption = " ".join(
            [t.text or "" for t in fig.findall(".//caption//p") if t.text]
        )
        label = fig.findtext("label", default="")
        figures.append({"label": label, "caption": caption})

    tables = []
    for tbl in article.findall(".//table-wrap"):
        caption = " ".join(
            [t.text or "" for t in tbl.findall(".//caption//p") if t.text]
        )
        label = tbl.findtext("label", default="")
        tables.append({"label": label, "caption": caption})

    # References
    refs = []
    for ref in article.findall(".//ref"):
        title = ref.findtext(".//article-title", default="")
        year = ref.findtext(".//year", default="")
        source = ref.findtext(".//source", default="")
        doi = ref.findtext(".//pub-id[@pub-id-type='doi']", default="")
        authors = [
            " ".join(filter(None, [a.findtext('given-names'), a.findtext('surname')]))
            for a in ref.findall(".//name")
        ]
        refs.append({
            "title": title,
            "authors": authors,
            "year": year,
            "source": source,
            "doi": doi
        })

    print(f"✅ PMC: full-text content parsed for {pmcid}")

    return {
        "pmcid": f"PMC{pmcid_clean}",
        "metadata": metadata,
        "abstract": abstract,
        "sections": sections,
        "figures": figures,
        "tables": tables,
        "references": refs,
        "source": "pmc_fulltext"
    }

def merge_pubmed_pmc(pubmed_studies, pmc_summaries):
    merged = []
    for p in pubmed_studies:
        pmid = p.get("pmid")
        doi = p.get("doi")
        match = next(
            (pmc for pmc in pmc_summaries
             if str(pmid) == str(pmc.get("metadata", {}).get("pmid"))
             or doi and doi in str(pmc)),
            None
        )
        merged.append({"pubmed": p, "pmc": match})
    return merged

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