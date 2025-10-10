"""
Core fetching workflow - ClinicalTrials.gov + PubMed + PMC.

This replaces data/clinical_trials/fetchers/coordinator.py
Maintains backward compatibility with existing API.
"""



"""
Core fetching workflow - FULLY MIGRATED.
Uses api_clients only, no fetchers dependencies.
"""
import asyncio
from typing import Dict, Any, List
from amp_llm.config import get_logger
from amp_llm.data.api_clients.core.clinical_trials import ClinicalTrialsClient
from amp_llm.data.api_clients.core.pubmed import PubMedClient
from amp_llm.data.api_clients.core.pmc_basic import PMCBasicClient

logger = get_logger(__name__)


async def fetch_clinical_trial_and_pubmed_pmc(nct_id: str) -> Dict[str, Any]:
    """
    Orchestrate fetching from core sources.
    FULLY MIGRATED - no fetchers dependencies.
    
    Args:
        nct_id: NCT number
        
    Returns:
        Combined result from all core sources
    """
    async with ClinicalTrialsClient() as ct_client, \
               PubMedClient() as pubmed_client, \
               PMCBasicClient() as pmc_client:
        
        # Step 1: Fetch clinical trial
        logger.info(f"Fetching clinical trial data for {nct_id}")
        ct_result = await ct_client.fetch_by_id(nct_id)
        
        if "error" in ct_result:
            logger.error(f"Failed to fetch {nct_id}: {ct_result.get('error')}")
            return ct_result
        
        # Extract references
        ct_data = ct_result.get("clinical_trial_data", {})
        protocol = ct_data.get("protocolSection", {}) if isinstance(ct_data, dict) else {}
        refs = _extract_references(protocol)
        
        logger.info(f"Found {len(refs)} reference(s) for {nct_id}")
        
        # Initialize results
        pubmed_data = {"pmids": [], "studies": []}
        pmc_data = {"pmcids": [], "summaries": []}
        
        # Step 2: Process each reference
        for i, ref in enumerate(refs, 1):
            title = ref.get("title", "")
            authors = ref.get("authors", [])
            
            logger.debug(f"Processing reference {i}/{len(refs)}: {title[:50]}...")
            print(f"\n📖 Searching for: '{title}'")
            
            # Search PubMed
            pmid = await pubmed_client.search_by_title_authors(title, authors)
            if pmid:
                pubmed_data["pmids"].append(pmid)
                metadata = await pubmed_client.fetch_by_id(pmid)
                pubmed_data["studies"].append(metadata)
                logger.info(f"Found PubMed article: PMID {pmid}")
            
            # Search PMC
            pmcids = await pmc_client.search(title)
            for pmcid in pmcids:
                if pmcid not in pmc_data["pmcids"]:
                    pmc_data["pmcids"].append(pmcid)
                    metadata = await pmc_client.fetch_by_id(pmcid)
                    pmc_data["summaries"].append({
                        "pmcid": pmcid,
                        "metadata": metadata
                    })
                    logger.info(f"Found PMC article: PMC{pmcid}")
        
        logger.info(
            f"Completed {nct_id}: "
            f"{len(pubmed_data['pmids'])} PubMed, {len(pmc_data['pmcids'])} PMC"
        )
        
        # Return combined result
        return {
            "nct_id": nct_id,
            "sources": {
                "clinical_trials": {
                    "source": ct_result.get("source"),
                    "data": ct_data
                },
                "pubmed": pubmed_data,
                "pmc": pmc_data
            }
        }


def _extract_references(protocol: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract references from trial protocol."""
    refs = protocol.get("referencesModule", {}).get("referenceList", [])
    
    if not refs:
        # Fallback: use study title and investigators
        ident = protocol.get("identificationModule", {})
        title = ident.get("officialTitle") or ident.get("briefTitle")
        
        contacts = protocol.get("contactsLocationsModule", {})
        officials = contacts.get("overallOfficials", [])
        authors = [o.get("name") for o in officials if "name" in o]
        
        if title:
            refs = [{"title": title, "authors": authors}]
    else:
        # Normalize reference format
        normalized = []
        for ref in refs:
            title = ref.get("referenceTitle") or ref.get("title", "")
            authors = ref.get("authors", [])
            
            if isinstance(authors, str):
                authors = [a.strip() for a in authors.split(",") if a.strip()]
            
            if title:
                normalized.append({"title": title, "authors": authors})
        refs = normalized
    
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