"""
Coordinator for fetching clinical trial data from all sources.
Orchestrates async execution and combines results from ClinicalTrials.gov, PubMed, and PMC.
"""
import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List

from .clinical_trials import fetch_clinical_trial_data
from .pubmed import fetch_pubmed_by_pmid, search_pubmed_by_title_authors
from .pmc import search_pmc, fetch_pmc_esummary, convert_pmc_summary_to_metadata


async def fetch_clinical_trial_and_pubmed_pmc(nct_id: str) -> Dict[str, Any]:
    """
    Async wrapper that orchestrates fetching from all sources.
    
    Workflow:
    1. Fetch clinical trial data from ClinicalTrials.gov
    2. Extract references (title, authors) from trial data
    3. Search PubMed for each reference
    4. Fetch full PubMed metadata for each PMID
    5. Search PMC for each reference
    6. Fetch PMC metadata for each PMC ID
    
    Args:
        nct_id: NCT number
        
    Returns:
        Combined result with data from all sources
    """
    loop = asyncio.get_event_loop()
    
    # Step 1: Fetch clinical trial data
    clin = await loop.run_in_executor(None, fetch_clinical_trial_data, nct_id)
    
    if "error" in clin:
        return clin
    
    ctdata = clin.get("clinical_trial_data", {})
    protocol = ctdata.get("protocolSection", {}) if isinstance(ctdata, dict) else {}
    
    # Extract references from trial data
    refs = protocol.get("referencesModule", {}).get("referenceList", [])
    
    if not refs:
        # Fallback: use study title and investigators as reference
        title = (protocol.get("identificationModule", {}).get("officialTitle") or
                 protocol.get("identificationModule", {}).get("briefTitle"))
        officials = protocol.get("contactsLocationsModule", {}).get("overallOfficials", [])
        authors = [o.get("name") for o in officials if "name" in o]
        if title:
            refs = [{"title": title, "authors": authors}]
    
    # Initialize result containers
    pubmed = {"pmids": [], "studies": []}
    pmc = {"pmcids": [], "summaries": []}
    
    # Step 2-4: Search and fetch PubMed data
    for ref in refs:
        title = ref.get("referenceTitle") or ref.get("title")
        authors = ref.get("authors", [])
        print(f"\n📖 Searching for related publications: '{title}'")
        
        # Search PubMed
        pmid = await loop.run_in_executor(
            None, search_pubmed_by_title_authors, title, authors
        )
        
        if pmid:
            pubmed["pmids"].append(pmid)
            pubmed_data = await loop.run_in_executor(
                None, fetch_pubmed_by_pmid, pmid
            )
            pubmed["studies"].append(pubmed_data)
        
        # Search PMC
        pmcids = await loop.run_in_executor(None, search_pmc, title)
        for pid in pmcids:
            if pid not in pmc["pmcids"]:
                pmc["pmcids"].append(pid)
                pmc_meta = await loop.run_in_executor(
                    None, fetch_pmc_esummary, pid
                )
                pmc["summaries"].append({
                    "pmcid": pid,
                    "metadata": convert_pmc_summary_to_metadata(pmc_meta)
                })
    
    # Return combined result
    return {
        "nct_id": nct_id,
        "sources": {
            "clinical_trials": {
                "source": clin.get("source"),
                "data": ctdata
            },
            "pubmed": pubmed,
            "pmc": pmc
        }
    }


def print_study_summary(result: Dict[str, Any]) -> None:
    """
    Print formatted summary of fetched study.
    
    Args:
        result: Combined result from fetch_clinical_trial_and_pubmed_pmc
    """
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
    """
    Return compact summary dict for CLI or JSON output.
    
    Args:
        result: Combined result from fetch_clinical_trial_and_pubmed_pmc
        
    Returns:
        Summary dictionary
    """
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


def save_results(results: List[Dict[str, Any]], filename: str, fmt: str = 'txt') -> None:
    """
    Save results to file.
    
    Args:
        results: List of combined results
        filename: Output filename (without extension)
        fmt: Format ('txt', 'csv', or 'json')
    """
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