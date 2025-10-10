"""
Index clinical trials into Meilisearch.
Supports batch processing of 1000s of NCT numbers.
"""
import asyncio
import aiohttp
from pathlib import Path
import json
from typing import List, Dict

MEILISEARCH_URL = "http://localhost:7700"  # Or your server
MEILISEARCH_KEY = "your_master_key"


async def create_index():
    """Create clinical trials index with optimal settings."""
    
    url = f"{MEILISEARCH_URL}/indexes"
    headers = {"Authorization": f"Bearer {MEILISEARCH_KEY}"}
    
    payload = {
        "uid": "clinical_trials",
        "primaryKey": "nct_id"
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            if resp.status in (200, 202):
                print("✅ Index created")
            elif resp.status == 409:
                print("ℹ️ Index already exists")
            else:
                print(f"❌ Error: {await resp.text()}")


async def configure_index():
    """Configure searchable attributes and filters."""
    
    url = f"{MEILISEARCH_URL}/indexes/clinical_trials/settings"
    headers = {"Authorization": f"Bearer {MEILISEARCH_KEY}"}
    
    settings = {
        "searchableAttributes": [
            "title",
            "brief_summary",
            "detailed_description",
            "conditions",
            "interventions",
            "sponsors",
            "nct_id"
        ],
        "filterableAttributes": [
            "status",
            "phase",
            "enrollment",
            "start_year",
            "conditions",
            "interventions",
            "is_peptide",
            "classification"
        ],
        "sortableAttributes": [
            "enrollment",
            "start_date"
        ],
        "rankingRules": [
            "words",
            "typo",
            "proximity",
            "attribute",
            "sort",
            "exactness"
        ]
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.patch(url, json=settings, headers=headers) as resp:
            if resp.status == 202:
                print("✅ Index configured")
            else:
                print(f"❌ Configuration error: {await resp.text()}")


async def index_trials_batch(trials: List[Dict], batch_size: int = 1000):
    """Index trials in batches."""
    
    url = f"{MEILISEARCH_URL}/indexes/clinical_trials/documents"
    headers = {"Authorization": f"Bearer {MEILISEARCH_KEY}"}
    
    total = len(trials)
    
    async with aiohttp.ClientSession() as session:
        for i in range(0, total, batch_size):
            batch = trials[i:i + batch_size]
            
            async with session.post(url, json=batch, headers=headers) as resp:
                if resp.status == 202:
                    print(f"✅ Indexed {i + len(batch)}/{total} trials")
                else:
                    print(f"❌ Batch error: {await resp.text()}")
            
            await asyncio.sleep(0.1)  # Rate limiting


async def load_and_index_from_directory(directory: Path):
    """Load all JSON files from directory and index."""
    
    print(f"📂 Loading trials from: {directory}")
    
    trials = []
    
    for json_file in directory.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Extract relevant fields for Meilisearch
                trial = extract_trial_data(data)
                if trial:
                    trials.append(trial)
        
        except Exception as e:
            print(f"⚠️ Error loading {json_file.name}: {e}")
    
    print(f"📊 Loaded {len(trials)} trials")
    
    if trials:
        await index_trials_batch(trials)
        print(f"✅ Indexed {len(trials)} trials into Meilisearch")


def extract_trial_data(raw_data: Dict) -> Dict:
    """Extract and flatten trial data for Meilisearch."""
    
    try:
        protocol = raw_data['sources']['clinical_trials']['data']['protocolSection']
        
        ident = protocol.get('identificationModule', {})
        status_mod = protocol.get('statusModule', {})
        desc = protocol.get('descriptionModule', {})
        cond_mod = protocol.get('conditionsModule', {})
        design = protocol.get('designModule', {})
        arms = protocol.get('armsInterventionsModule', {})
        sponsor = protocol.get('sponsorCollaboratorsModule', {})
        
        return {
            "nct_id": raw_data.get('nct_id'),
            "title": ident.get('officialTitle') or ident.get('briefTitle'),
            "brief_summary": desc.get('briefSummary', ''),
            "detailed_description": desc.get('detailedDescription', ''),
            "status": status_mod.get('overallStatus'),
            "phase": design.get('phases', []),
            "enrollment": design.get('enrollmentInfo', {}).get('count', 0),
            "start_date": status_mod.get('startDateStruct', {}).get('date'),
            "start_year": int(status_mod.get('startDateStruct', {}).get('date', '2000')[:4]),
            "conditions": cond_mod.get('conditions', []),
            "interventions": [i.get('name') for i in arms.get('interventions', [])],
            "sponsors": sponsor.get('leadSponsor', {}).get('name'),
            "is_peptide": 'peptide' in json.dumps(raw_data).lower(),
        }
    
    except Exception as e:
        print(f"⚠️ Extraction error: {e}")
        return None


async def main():
    """Main indexing workflow."""
    
    print("="*60)
    print("Meilisearch Clinical Trial Indexer")
    print("="*60)
    
    # Step 1: Create index
    await create_index()
    await asyncio.sleep(1)
    
    # Step 2: Configure
    await configure_index()
    await asyncio.sleep(1)
    
    # Step 3: Index trials
    ct_database = Path("ct_database")
    
    if not ct_database.exists():
        print(f"❌ Directory not found: {ct_database}")
        return
    
    await load_and_index_from_directory(ct_database)
    
    print("\n✅ Indexing complete!")
    print(f"   Access at: {MEILISEARCH_URL}")
    print(f"   Index: clinical_trials")


if __name__ == "__main__":
    asyncio.run(main())