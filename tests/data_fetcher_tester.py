# main.py
import json
from data_fetchers import (
    fetch_pubmed_combined_payload,
    fetch_duckduckgo_nct_search,
    fetch_clinical_trial_info
)


def pretty_print(data, title=None):
    if title:
        print(f"\n{title}")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def main():
    while True:
        print("\nChoose fetch type:")
        print("1. DuckDuckGo NCT search")
        print("2. ClinicalTrials.gov NCT search")
        print("3. PubMed PMID fetch (API + Scrape merged)")
        print("4. Exit")
        choice = input("Enter choice (1, 2, 3, or 4): ").strip()

        if choice == "1":
            nct = input("Enter NCT number (e.g. NCT01234567): ").strip()
            result = fetch_duckduckgo_nct_search(nct)
            pretty_print(result, "DuckDuckGo NCT Search Result")

        elif choice == "2":
            nct = input("Enter NCT number (e.g. NCT01234567): ").strip()
            result = fetch_clinical_trial_info(nct)
            pretty_print(result, "ClinicalTrials.gov NCT Search Result")

            # Fetch PubMed data if PMIDs are available
            pmids = result.get("pmids", [])
            if pmids:
                fetch_pmids = input(f"\nFound PMIDs: {pmids}. Fetch related PubMed studies? (y/n): ").lower()
                if fetch_pmids == "y":
                    for pmid in pmids:
                        try:
                            pm_result = fetch_pubmed_combined_payload(pmid)
                            pretty_print(pm_result, f"PubMed Study for PMID {pmid}")
                        except Exception as e:
                            print(f"Error fetching PMID {pmid}: {e}")
            else:
                print("No PMIDs found in the clinical trial data.")

        elif choice == "3":
            pmid = input("Enter PubMed PMID (numeric only): ").strip()
            if not pmid.isdigit():
                print("Invalid PMID. It must be numeric.")
                continue
            try:
                result = fetch_pubmed_combined_payload(pmid)
                pretty_print(result, "Merged PubMed Study Payload")
            except Exception as e:
                print(f"Error fetching PubMed data: {e}")

        elif choice == "4" or choice.lower() == "exit":
            print("Exiting.")
            break

        else:
            print("Invalid choice, try again.")


if __name__ == "__main__":
    main()
