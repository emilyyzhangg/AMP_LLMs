import asyncio
from nct_core import NCTSearchEngine
from nct_models import SearchConfig

async def test_pmc_bioc():
    engine = NCTSearchEngine()
    await engine.initialize()
    
    nct_id = "NCT04043065"
    config = SearchConfig(use_extended_apis=False)
    
    # Run full search
    results = await engine.search(nct_id, config, None)
    
    # Print what we found
    print("\n" + "="*60)
    print("PUBMED RESULTS:")
    print("="*60)
    pubmed = results["sources"]["pubmed"]["data"]
    print(f"PMIDs: {pubmed.get('pmids', [])}")
    
    print("\n" + "="*60)
    print("PMC RESULTS:")
    print("="*60)
    pmc = results["sources"]["pmc"]["data"]
    print(f"PMCIDs: {pmc.get('pmcids', [])}")
    
    print("\n" + "="*60)
    print("PMC BioC RESULTS:")
    print("="*60)
    bioc = results["sources"]["pmc_bioc"]["data"]
    print(f"Total found: {bioc.get('total_found', 0)}")
    print(f"Total fetched: {bioc.get('total_fetched', 0)}")
    print(f"Errors: {len(bioc.get('errors', []))}")
    
    if bioc.get('errors'):
        print("\nErrors encountered:")
        for err in bioc['errors'][:5]:  # Show first 5 errors
            print(f"  - {err['identifier']}: {err['error']}")
    
    await engine.close()

if __name__ == "_main_":
    asyncio.run(test_pmc_bioc())