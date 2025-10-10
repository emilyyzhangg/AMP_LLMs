"""
Core fetching workflow - ClinicalTrials.gov + PubMed + PMC.

This replaces data/clinical_trials/fetchers/coordinator.py
Maintains backward compatibility with existing API.
"""
import asyncio
from typing import Dict, Any, List

from amp_llm.config import get_logger
from amp_llm.data.clinical_trials.fetchers import (
    fetch_clinical_trial_data,
    fetch_pubmed_by_pmid,
    search_pubmed_by_title_authors,
    search_pmc,
    fetch_pmc_esummary,
    convert_pmc_summary_to_metadata,
)

logger = get_logger(__name__)


async def fetch_clinical_trial_and_pubmed_pmc(nct_id: str) -> Dict[str, Any]:
    """
    Async wrapper that orchestrates fetching from core sources.
    
    Workflow:
    1. Fetch clinical trial data from ClinicalTrials.gov
    2. Extract references (title, authors) from trial data
    3. Search PubMed for each reference
    4. Fetch full PubMed metadata for each PMID
    5. Search PMC for each reference
    6. Fetch PMC metadata for each PMC ID
    
    Args:
        nct_id: NCT number (e.g., "NCT12345678")
        
    Returns:
        Combined result with data from all core sources:
        {
            "nct_id": "NCT...",
            "sources": {
                "clinical_trials": {
                    "source": "clinicaltrials_v2_detail",
                    "data": {...}
                },
                "pubmed": {
                    "pmids": ["123", "456"],
                    "studies": [{...}, {...}]
                },
                "pmc": {
                    "pmcids": ["789", "012"],
                    "summaries": [{...}, {...}]
                }
            }
        }
    """
    loop = asyncio.get_event_loop()
    
    # Step 1: Fetch clinical trial data
    logger.info(f"Fetching clinical trial data for {nct_id}")
    clin = await loop.run_in_executor(None, fetch_clinical_trial_data, nct_id)
    
    if "error" in clin:
        logger.error(f"Failed to fetch {nct_id}: {clin.get('error')}")
        return clin
    
    ctdata = clin.get("clinical_trial_data", {})
    protocol = ctdata.get("protocolSection", {}) if isinstance(ctdata, dict) else {}
    
    # Extract references from trial data
    refs = _extract_references(protocol)
    
    logger.info(f"Found {len(refs)} reference(s) for {nct_id}")
    
    # Initialize result containers
    pubmed = {"pmids": [], "studies": []}
    pmc = {"pmcids": [], "summaries": []}
    
    # Step 2-6: Search and fetch PubMed/PMC data for each reference
    for i, ref in enumerate(refs, 1):
        title = ref.get("title", "")
        authors = ref.get("authors", [])
        
        logger.debug(f"Processing reference {i}/{len(refs)}: {title[:50]}...")
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
            logger.info(f"Found PubMed article: PMID {pmid}")
        
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
                logger.info(f"Found PMC article: PMC{pid}")
    
    logger.info(
        f"Completed fetch for {nct_id}: "
        f"{len(pubmed['pmids'])} PubMed, {len(pmc['pmcids'])} PMC"
    )
    
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


def _extract_references(protocol: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract references from trial protocol section.
    
    Args:
        protocol: Trial protocolSection dictionary
        
    Returns:
        List of references with title and authors
    """
    # Try to get references from referencesModule
    refs = protocol.get("referencesModule", {}).get("referenceList", [])
    
    if not refs:
        # Fallback: use study title and investigators as reference
        ident = protocol.get("identificationModule", {})
        title = ident.get("officialTitle") or ident.get("briefTitle")
        
        contacts = protocol.get("contactsLocationsModule", {})
        officials = contacts.get("overallOfficials", [])
        authors = [o.get("name") for o in officials if "name" in o]
        
        if title:
            refs = [{"title": title, "authors": authors}]
    else:
        # Normalize reference format
        normalized_refs = []
        for ref in refs:
            title = ref.get("referenceTitle") or ref.get("title", "")
            authors = ref.get("authors", [])
            
            # Handle different author formats
            if isinstance(authors, str):
                # Split comma-separated author string
                authors = [a.strip() for a in authors.split(",") if a.strip()]
            
            if title:
                normalized_refs.append({
                    "title": title,
                    "authors": authors
                })
        
        refs = normalized_refs
    
    return refs


def print_study_summary(result: Dict[str, Any]) -> None:
    """
    Print formatted summary of fetched study.
    
    Args:
        result: Combined result from fetch_clinical_trial_and_pubmed_pmc
    """
    print("\n===== 📊 CLINICAL TRIAL SUMMARY =====")
    
    ct_data = result["sources"]["clinical_trials"]["data"]
    protocol = ct_data.get("protocolSection", {})
    ident = protocol.get("identificationModule", {})
    status_mod = protocol.get("statusModule", {})
    cond_mod = protocol.get("conditionsModule", {})
    
    # Basic info
    title = ident.get("officialTitle", ident.get("briefTitle", "Untitled"))
    status = status_mod.get("overallStatus", "Unknown")
    sponsor = ident.get("organization", {}).get("fullName", "Unknown")
    conditions = cond_mod.get("conditions", [])
    
    print(f"🧪 {title}")
    print(f"📅 Status: {status}")
    print(f"🏥 Sponsor: {sponsor}")
    print(f"🔬 Conditions: {', '.join(conditions) if conditions else 'Not specified'}")
    
    # PubMed results
    pubs = result["sources"]["pubmed"]["studies"]
    if pubs:
        print("\n===== 📚 PUBMED RESULTS =====")
        for p in pubs:
            pub_title = p.get('title', 'No title')
            pub_date = p.get('publication_date', 'Unknown')
            journal = p.get('journal', 'Unknown journal')
            pmid = p.get('pmid', 'Unknown')
            
            print(f"🔹 {pub_title} ({pub_date})")
            print(f"   {journal} — PMID: {pmid}")
    else:
        print("\n🔭 No PubMed matches found.")
    
    # PMC results
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
        Summary dictionary with key metrics
    """
    nct_id = result.get("nct_id", "Unknown")
    sources = result.get("sources", {})
    
    clin = sources.get("clinical_trials", {})
    pubmed = sources.get("pubmed", {})
    pmc = sources.get("pmc", {})
    
    pmids = pubmed.get("pmids", [])
    pmcids = pmc.get("pmcids", [])
    
    return {
        "NCT": nct_id,
        "ClinicalTrials.gov Source": clin.get("source", "Unknown"),
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
    import json
    from pathlib import Path
    
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
        
        logger.info(f"Saved {len(results)} results to CSV: {path}")
    
    elif fmt == 'json':
        path = output_dir / f'{filename}.json'
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved {len(results)} results to JSON: {path}")
    
    else:  # txt
        path = output_dir / f'{filename}.txt'
        
        with open(path, 'w', encoding='utf-8') as f:
            for r in results:
                f.write(json.dumps(r, indent=2, ensure_ascii=False))
                f.write('\n\n')
        
        logger.info(f"Saved {len(results)} results to TXT: {path}")
    
    print(f"💾 Results saved to {path}")