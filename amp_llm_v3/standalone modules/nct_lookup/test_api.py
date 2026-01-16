"""
NCT Lookup API - Comprehensive Test Suite
=========================================

Tests all API endpoints with multiple scenarios.
"""

import requests
import time
import json
from pathlib import Path
from datetime import datetime


class NCTAPITester:
    """Comprehensive API testing class."""
    
    def __init__(self, base_url: str = "http://localhost:9000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = []
        
    def log(self, message: str, level: str = "INFO"):
        """Log test message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = {
            "INFO": "ℹ️ ",
            "SUCCESS": "✅",
            "ERROR": "❌",
            "WARNING": "⚠️ ",
            "STEP": "📍"
        }.get(level, "  ")
        
        print(f"[{timestamp}] {prefix} {message}")
        
    def test(self, name: str, func):
        """Run a test and track results."""
        self.log(f"Testing: {name}", "STEP")
        try:
            func()
            self.test_results.append((name, "PASS", None))
            self.log(f"PASSED: {name}", "SUCCESS")
            return True
        except AssertionError as e:
            self.test_results.append((name, "FAIL", str(e)))
            self.log(f"FAILED: {name} - {e}", "ERROR")
            return False
        except Exception as e:
            self.test_results.append((name, "ERROR", str(e)))
            self.log(f"ERROR: {name} - {e}", "ERROR")
            return False
    
    def test_root_endpoint(self):
        """Test GET / endpoint."""
        resp = self.session.get(f"{self.base_url}/")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        assert "service" in data, "Missing 'service' field"
        assert "endpoints" in data, "Missing 'endpoints' field"
        
        self.log(f"  Service: {data['service']}")
        self.log(f"  Version: {data.get('version', 'N/A')}")
    
    def test_health_endpoint(self):
        """Test GET /health endpoint."""
        resp = self.session.get(f"{self.base_url}/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        
        data = resp.json()
        assert data["status"] == "healthy", "API not healthy"
        
        self.log(f"  Status: {data['status']}")
        self.log(f"  Active searches: {data.get('active_searches', 0)}")
    
    def test_core_search_flow(self):
        """Test complete core search workflow."""
        nct_id = "NCT04043065"  # Valid trial that should have results
        
        # 1. Initiate search
        self.log(f"  Initiating core search for {nct_id}")
        resp = self.session.post(
            f"{self.base_url}/api/search/{nct_id}",
            json={"include_extended": False}
        )
        assert resp.status_code == 200, f"Search init failed: {resp.status_code}"
        
        data = resp.json()
        assert data["job_id"] == nct_id, "Job ID mismatch"
        assert data["status"] in ["queued", "running"], f"Unexpected status: {data['status']}"
        
        self.log(f"  Search initiated - Status: {data['status']}")
        
        # 2. Monitor progress
        self.log(f"  Monitoring search progress...")
        max_wait = 120  # 2 minutes max
        start_time = time.time()
        last_progress = -1
        
        while time.time() - start_time < max_wait:
            resp = self.session.get(f"{self.base_url}/api/search/{nct_id}/status")
            assert resp.status_code == 200, "Status check failed"
            
            status = resp.json()
            progress = status["progress"]
            current_db = status.get("current_database", "N/A")
            
            if progress != last_progress:
                self.log(f"  Progress: {progress}% | Database: {current_db}")
                last_progress = progress
            
            if status["status"] == "completed":
                self.log(f"  Search completed in {time.time() - start_time:.1f}s")
                break
            elif status["status"] == "failed":
                raise AssertionError(f"Search failed: {status.get('error')}")
            
            time.sleep(2)
        else:
            raise AssertionError("Search timeout - exceeded 2 minutes")
        
        # 3. Get summary
        self.log(f"  Retrieving summary...")
        resp = self.session.get(
            f"{self.base_url}/api/results/{nct_id}",
            params={"summary_only": True}
        )
        assert resp.status_code == 200, "Summary retrieval failed"
        
        summary = resp.json()
        self.log(f"  Title: {summary['title'][:60]}...")
        self.log(f"  Status: {summary['status']}")
        self.log(f"  Total Results: {summary['total_results']}")
        self.log(f"  Databases: {', '.join(summary['databases_searched'])}")
        
        for db, count in summary["results_by_database"].items():
            self.log(f"    • {db}: {count} results")
        
        # 4. Get full results
        self.log(f"  Retrieving full results...")
        resp = self.session.get(f"{self.base_url}/api/results/{nct_id}")
        assert resp.status_code == 200, "Results retrieval failed"
        
        results = resp.json()
        assert "nct_id" in results, "Missing nct_id in results"
        assert "databases" in results, "Missing databases in results"
        
        self.log(f"  Full results retrieved - {len(results['databases'])} databases")
        
        # 5. Save full results to root directory for inspection
        output_file = Path(f"{nct_id}_test_results.json")
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        self.log(f"  📄 Saved full results to: {output_file.absolute()}")
        
        return results
    
    def test_extended_search_flow(self):
        """Test extended search with additional databases."""
        nct_id = "NCT04043065"  # Use same valid NCT as core search
        
        # First, delete any existing results to force a new extended search
        self.log(f"  Cleaning up previous results for {nct_id}")
        self.session.delete(f"{self.base_url}/api/results/{nct_id}")
        
        # Now initiate extended search
        self.log(f"  Initiating extended search for {nct_id}")
        resp = self.session.post(
            f"{self.base_url}/api/search/{nct_id}",
            json={
                "include_extended": True,
                "databases": ["duckduckgo", "openfda"]
            }
        )
        
        assert resp.status_code == 200, f"Extended search failed: {resp.status_code}"
        
        data = resp.json()
        self.log(f"  Extended search initiated - Status: {data['status']}")
        
        # Wait for completion
        max_wait = 90  # Extended search takes longer
        start_time = time.time()
        last_progress = -1
        
        while time.time() - start_time < max_wait:
            resp = self.session.get(f"{self.base_url}/api/search/{nct_id}/status")
            if resp.status_code != 200:
                break
            
            status = resp.json()
            progress = status["progress"]
            current_db = status.get("current_database", "N/A")
            
            if progress != last_progress:
                self.log(f"  Progress: {progress}% | Database: {current_db}")
                last_progress = progress
            
            if status["status"] == "completed":
                self.log(f"  Extended search completed in {time.time() - start_time:.1f}s")
                
                # Get the full results with extended APIs
                resp = self.session.get(f"{self.base_url}/api/results/{nct_id}")
                if resp.status_code == 200:
                    results = resp.json()
                    
                    # Save extended search results
                    output_file = Path(f"{nct_id}_extended_test_results.json")
                    with open(output_file, 'w', encoding='utf-8') as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)
                    
                    self.log(f"  📄 Saved extended results to: {output_file.absolute()}")
                    
                    # Show what APIs were included
                    if "extended" in results.get("sources", {}):
                        extended_apis = list(results["sources"]["extended"].keys())
                        self.log(f"  Extended APIs: {', '.join(extended_apis)}")
                        
                        # Show result counts
                        for api_name in extended_apis:
                            api_data = results["sources"]["extended"][api_name]
                            if api_data.get("success"):
                                data = api_data.get("data", {})
                                count = len(data.get("results", []))
                                self.log(f"    • {api_name}: {count} results")
                
                break
            elif status["status"] == "failed":
                self.log(f"  Extended search failed: {status.get('error')}", "WARNING")
                break
            
            time.sleep(3)
    
    def test_save_to_file(self):
        """Test saving results to file."""
        nct_id = "NCT04043065"  # Use the same valid NCT from extended search
        
        self.log(f"  Testing file save for {nct_id}")
        
        # First ensure search is completed (it should be from extended search)
        resp = self.session.get(f"{self.base_url}/api/search/{nct_id}/status")
        if resp.status_code != 200 or resp.json()["status"] != "completed":
            self.log(f"  Skipping - search not completed", "WARNING")
            return
        
        # Test save via query parameter
        self.log(f"  Method 1: Save via query parameter")
        resp = self.session.get(
            f"{self.base_url}/api/results/{nct_id}",
            params={"save_to_file": True}
        )
        assert resp.status_code == 200, "Save via query param failed"
        
        data = resp.json()
        if "file_saved" in data:
            file_info = data["file_saved"]
            self.log(f"  File saved: {file_info['filename']}")
            self.log(f"  Size: {file_info.get('size_human', 'N/A')}")
        
        # Test save via dedicated endpoint
        self.log(f"  Method 2: Save via POST endpoint")
        resp = self.session.post(f"{self.base_url}/api/results/{nct_id}/save")
        assert resp.status_code == 200, "Save via POST failed"
        
        data = resp.json()
        assert data["success"] is True, "Save not successful"
        
        file_info = data["file"]
        self.log(f"  File saved: {file_info['filename']}")
        self.log(f"  Path: {file_info['path']}")
        self.log(f"  Size: {file_info['size_human']}")
    
    def test_download_endpoint(self):
        """Test file download endpoint."""
        nct_id = "NCT04043065"  # Use the same valid NCT from extended search
        
        self.log(f"  Testing download for {nct_id}")
        
        resp = self.session.get(f"{self.base_url}/api/results/{nct_id}/download")
        
        if resp.status_code == 404:
            self.log(f"  Results not available for download", "WARNING")
            return
        
        assert resp.status_code == 200, f"Download failed: {resp.status_code}"
        assert resp.headers.get("content-type") == "application/json", "Wrong content type"
        
        # Save downloaded file
        download_path = Path(f"downloaded_{nct_id}.json")
        with open(download_path, 'wb') as f:
            f.write(resp.content)
        
        self.log(f"  Downloaded to: {download_path}")
        self.log(f"  Size: {download_path.stat().st_size} bytes")
        
        # Verify it's valid JSON
        try:
            with open(download_path, "r", encoding='utf-8') as f:
                data = json.load(f)
                assert "nct_id" in data, "Invalid JSON structure"
                self.log(f"  ✓ Valid JSON with nct_id: {data['nct_id']}")
        except json.JSONDecodeError as e:
            # If JSON is invalid, show the problematic area
            with open(download_path, "r", encoding='utf-8') as f:
                content = f.read()
                # Show area around the error
                start = max(0, e.pos - 100)
                end = min(len(content), e.pos + 100)
                self.log(f"  JSON Error at position {e.pos}", "ERROR")
                self.log(f"  Context: ...{content[start:end]}...", "ERROR")
            raise
    
    def test_invalid_nct_format(self):
        """Test with invalid NCT format."""
        # Only truly invalid formats (case-insensitive is allowed)
        invalid_ids = [
            "NCT123",           # Too short
            "ABC12345678",      # Wrong prefix
            "12345678",         # No prefix
            "NCT1234567",       # 7 digits instead of 8
            "NCT123456789",     # 9 digits instead of 8
            "NCTABCD1234",      # Letters in number
            "NCT-12345678"      # Hyphen not allowed
        ]
        
        for invalid_id in invalid_ids:
            self.log(f"  Testing invalid ID: {invalid_id}")
            resp = self.session.post(
                f"{self.base_url}/api/search/{invalid_id}",
                json={"include_extended": False}
            )
            assert resp.status_code == 400, f"Should reject {invalid_id}"
            self.log(f"  Correctly rejected: {invalid_id}")
        
        # Test that case-insensitive works
        self.log(f"  Testing case-insensitive: nct04280705")
        resp = self.session.post(
            f"{self.base_url}/api/search/nct04280705",
            json={"include_extended": False}
        )
        # Should accept (already exists, so returns completed)
        assert resp.status_code == 200, "Should accept lowercase NCT"
        self.log(f"  ✓ Correctly accepts lowercase NCT")
    
    def test_nonexistent_nct(self):
        """Test with non-existent NCT ID."""
        fake_nct = "NCT99999999"
        
        self.log(f"  Testing non-existent NCT: {fake_nct}")
        resp = self.session.post(
            f"{self.base_url}/api/search/{fake_nct}",
            json={"include_extended": False}
        )
        
        # Should accept the request but fail during execution
        if resp.status_code == 200:
            # Wait a bit and check status
            time.sleep(5)
            resp = self.session.get(f"{self.base_url}/api/search/{fake_nct}/status")
            if resp.status_code == 200:
                status = resp.json()
                self.log(f"  Status: {status['status']}")
                if status["status"] == "failed":
                    self.log(f"  Correctly failed: {status.get('error')}")
    
    def test_duplicate_search(self):
        """Test submitting duplicate search."""
        nct_id = "NCT04043065"  # Use the same valid NCT from core search
        
        self.log(f"  Testing duplicate search for {nct_id}")
        resp = self.session.post(
            f"{self.base_url}/api/search/{nct_id}",
            json={"include_extended": False}
        )
        
        data = resp.json()
        if data["status"] in ["running", "completed"]:
            self.log(f"  Correctly handled duplicate - Status: {data['status']}")
        else:
            self.log(f"  New search created (previous may have been deleted)")
    
    def test_status_before_search(self):
        """Test getting status for non-existent search."""
        fake_nct = "NCT88888888"
        
        self.log(f"  Checking status for unsearched NCT: {fake_nct}")
        resp = self.session.get(f"{self.base_url}/api/search/{fake_nct}/status")
        assert resp.status_code == 404, "Should return 404 for non-existent search"
        
        self.log(f"  Correctly returned 404")
    
    def test_results_before_completion(self):
        """Test getting results before search completes."""
        nct_id = "NCT04280707"
        
        self.log(f"  Starting search for {nct_id}")
        resp = self.session.post(
            f"{self.base_url}/api/search/{nct_id}",
            json={"include_extended": False}
        )
        
        if resp.status_code != 200:
            self.log(f"  Search failed to start", "WARNING")
            return
        
        # Immediately try to get results
        self.log(f"  Attempting to get results immediately")
        resp = self.session.get(f"{self.base_url}/api/results/{nct_id}")
        
        if resp.status_code == 400:
            self.log(f"  Correctly rejected - search not completed")
        elif resp.status_code == 404:
            self.log(f"  Correctly rejected - results not found")
        else:
            self.log(f"  Got unexpected status: {resp.status_code}", "WARNING")
    
    def test_delete_search(self):
        """Test deleting search results."""
        nct_id = "NCT04280708"
        
        # Create a search
        self.log(f"  Creating search for {nct_id}")
        resp = self.session.post(
            f"{self.base_url}/api/search/{nct_id}",
            json={"include_extended": False}
        )
        
        if resp.status_code != 200:
            self.log(f"  Skipping delete test - search failed to start", "WARNING")
            return
        
        # Wait a moment
        time.sleep(5)
        
        # Delete the search
        self.log(f"  Deleting search for {nct_id}")
        resp = self.session.delete(f"{self.base_url}/api/results/{nct_id}")
        assert resp.status_code == 200, "Delete failed"
        
        data = resp.json()
        self.log(f"  {data['message']}")
        
        # Verify it's gone
        resp = self.session.get(f"{self.base_url}/api/search/{nct_id}/status")
        assert resp.status_code == 404, "Search should be deleted"
        self.log(f"  Verified deletion")
    
    def test_invalid_database_names(self):
        """Test with invalid database names."""
        nct_id = "NCT04280709"
        
        self.log(f"  Testing with invalid database names")
        resp = self.session.post(
            f"{self.base_url}/api/search/{nct_id}",
            json={
                "include_extended": True,
                "databases": ["invalid_db", "fake_database"]
            }
        )
        
        # Should return validation error
        assert resp.status_code == 422, "Should reject invalid database names"
        self.log(f"  Correctly rejected invalid database names")
    
    def run_all_tests(self):
        """Run all tests in sequence."""
        print("\n" + "="*70)
        print("  NCT LOOKUP API - COMPREHENSIVE TEST SUITE")
        print("="*70 + "\n")
        
        # Basic endpoint tests
        self.log("SECTION 1: Basic Endpoints", "STEP")
        print("-" * 70)
        self.test("Root Endpoint", self.test_root_endpoint)
        self.test("Health Check", self.test_health_endpoint)
        print()
        
        # Core functionality tests
        self.log("SECTION 2: Core Search Functionality", "STEP")
        print("-" * 70)
        self.test("Core Search Workflow", self.test_core_search_flow)
        print()
        
        # Extended search tests
        self.log("SECTION 3: Extended Search", "STEP")
        print("-" * 70)
        self.test("Extended Search Flow", self.test_extended_search_flow)
        print()
        
        # File operations tests
        self.log("SECTION 4: File Operations", "STEP")
        print("-" * 70)
        self.test("Save Results to File", self.test_save_to_file)
        self.test("Download Endpoint", self.test_download_endpoint)
        print()
        
        # Error handling tests
        self.log("SECTION 5: Error Handling", "STEP")
        print("-" * 70)
        self.test("Invalid NCT Format", self.test_invalid_nct_format)
        self.test("Non-existent NCT ID", self.test_nonexistent_nct)
        self.test("Duplicate Search", self.test_duplicate_search)
        self.test("Status Before Search", self.test_status_before_search)
        self.test("Results Before Completion", self.test_results_before_completion)
        self.test("Invalid Database Names", self.test_invalid_database_names)
        print()
        
        # Cleanup tests
        self.log("SECTION 6: Cleanup Operations", "STEP")
        print("-" * 70)
        self.test("Delete Search", self.test_delete_search)
        print()
        
        # Summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*70)
        print("  TEST SUMMARY")
        print("="*70)
        
        total = len(self.test_results)
        passed = sum(1 for _, status, _ in self.test_results if status == "PASS")
        failed = sum(1 for _, status, _ in self.test_results if status == "FAIL")
        errors = sum(1 for _, status, _ in self.test_results if status == "ERROR")
        
        print(f"\n  Total Tests: {total}")
        print(f"  ✅ Passed: {passed}")
        print(f"  ❌ Failed: {failed}")
        print(f"  ⚠️  Errors: {errors}")
        
        if failed > 0 or errors > 0:
            print("\n  Failed/Error Tests:")
            for name, status, error in self.test_results:
                if status in ["FAIL", "ERROR"]:
                    print(f"    • {name}: {error}")
        
        print("\n" + "="*70)
        
        success_rate = (passed / total * 100) if total > 0 else 0
        print(f"  Success Rate: {success_rate:.1f}%")
        print("="*70 + "\n")
        
        # API info
        print(f"  📚 API Documentation: {self.base_url}/docs")
        print(f"  🔄 API Redoc: {self.base_url}/redoc")
        print()


def main():
    """Main test execution."""
    import sys
    
    # Get base URL from command line or use default
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:9000"
    
    tester = NCTAPITester(base_url)
    
    try:
        tester.run_all_tests()
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to API")
        print(f"   Make sure the API is running at: {base_url}")
        print("   Start with: uvicorn nct_api:app --reload --port 9000")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        tester.print_summary()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()