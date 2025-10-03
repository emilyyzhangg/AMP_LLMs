# main.py
from data_fetchers import fetch_pubmed_combined_payload, fetch_duckduckgo_nct_search
from data_fetchers import fetch_clinical_trial_info
import json

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
            print("\nDuckDuckGo NCT search payload:")
            print(result)

        elif choice == "2":
            nct = input("Enter NCT number (e.g. NCT01234567): ").strip()
            result = fetch_clinical_trial_info(nct)
            print("\nClinicalTrials.gov NCT search result:")
            print(json.dumps(result, indent=2))  # Print full result, including pmid_message and full data


        elif choice == "3":
            pmid = input("Enter PubMed PMID: ").strip()
            try:
                result = fetch_pubmed_combined_payload(pmid)
                print("\nMerged PubMed study payload:")
                print(result)
            except Exception as e:
                print(f"Error fetching PubMed data: {e}")

        elif choice == "4" or choice.lower() == "exit":
            print("Exiting.")
            break

        else:
            print("Invalid choice, try again.")


if __name__ == "__main__":
    main()