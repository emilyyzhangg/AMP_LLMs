import requests
import time
import json

def test_nct_api():
    """
    Quick test of NCT Lookup API.
    """
    
    API_BASE = "http://localhost:8000"
    NCT_ID = "NCT04280705"
    
    print("=== NCT Lookup API Test ===\n")
    
    # 1. Check API health
    print("1. Checking API health...")
    resp = requests.get(f"{API_BASE}/health")
    print(f"   Status: {resp.json()['status']}\n")
    
    # 2. Start core search
    print(f"2. Starting core search for {NCT_ID}...")
    resp = requests.post(
        f"{API_BASE}/api/search/{NCT_ID}",
        json={"include_extended": False}
    )
    
    if resp.status_code == 200:
        result = resp.json()
        print(f"   Job ID: {result['job_id']}")
        print(f"   Status: {result['status']}\n")
    else:
        print(f"   Error: {resp.status_code}\n")
        return
    
    # 3. Monitor progress
    print("3. Monitoring search progress...")
    while True:
        resp = requests.get(f"{API_BASE}/api/search/{NCT_ID}/status")
        status = resp.json()
        
        print(f"   Progress: {status['progress']}% - {status.get('current_database', 'N/A')}")
        
        if status['status'] == 'completed':
            print("   ✅ Search completed!\n")
            break
        elif status['status'] == 'failed':
            print(f"   ❌ Search failed: {status.get('error')}\n")
            return
        
        time.sleep(2)
    
    # 4. Get summary
    print("4. Retrieving summary...")
    resp = requests.get(
        f"{API_BASE}/api/results/{NCT_ID}",
        params={"summary_only": True}
    )
    
    if resp.status_code == 200:
        summary = resp.json()
        print(f"   Title: {summary['title']}")
        print(f"   Status: {summary['status']}")
        print(f"   Total Results: {summary['total_results']}")
        print(f"   Databases: {', '.join(summary['databases_searched'])}")
        print(f"\n   Results by Database:")
        for db, count in summary['results_by_database'].items():
            print(f"     • {db}: {count} results")
        print()
    else:
        print(f"   Error retrieving summary: {resp.status_code}\n")
        return
    
    # 5. Get full results
    print("5. Retrieving full results...")
    resp = requests.get(f"{API_BASE}/api/results/{NCT_ID}")
    
    if resp.status_code == 200:
        results = resp.json()
        
        # Save to file
        filename = f"{NCT_ID}_results.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"   ✅ Full results saved to: {filename}\n")
    else:
        print(f"   Error retrieving results: {resp.status_code}\n")
        return
    
    # 6. Test extended search (optional)
    print("6. Testing extended search (DuckDuckGo + OpenFDA)...")
    NCT_ID_2 = "NCT04280706"  # Different ID for second test
    
    resp = requests.post(
        f"{API_BASE}/api/search/{NCT_ID_2}",
        json={
            "include_extended": True,
            "databases": ["duckduckgo", "openfda"]
        }
    )
    
    if resp.status_code == 200:
        result = resp.json()
        print(f"   ✅ Extended search initiated for {NCT_ID_2}")
        print(f"   Status: {result['status']}\n")
    else:
        print(f"   ⚠️  Extended search failed (may need valid NCT ID)\n")
    
    print("=== Test Complete ===")
    print(f"\nAPI Documentation: {API_BASE}/docs")
    print(f"Results saved in: {filename}")


if __name__ == "__main__":
    try:
        test_nct_api()
    except requests.exceptions.ConnectionError:
        print("❌ Error: Cannot connect to API")
        print("   Make sure the API is running: uvicorn nct_api:app --reload")
    except Exception as e:
        print(f"❌ Error: {e}")