# interactive.py

import json
from data.data_fetchers import fetch_clinical_trial_and_pubmed
from data.output_handler import save_results_to_excel, save_results_to_csv


def interactive_session():
    """Interactive CLI tool for fetching ClinicalTrials.gov and PubMed data."""
    print("🔬 ClinicalTrials.gov + PubMed Data Fetch Tool")
    print("----------------------------------------------------")

    nct_id = input("Enter NCT ID (e.g. NCT01234567): ").strip().upper()

    if not nct_id.startswith("NCT"):
        print("❌ Invalid NCT ID format.")
        return

    print(f"\n🔍 Fetching data for {nct_id}...\n")
    result = fetch_clinical_trial_and_pubmed(nct_id)

    if "error" in result:
        print(f"❌ Error fetching data: {result['error']}")
        return

    # Print summary
    sources = result.get("sources", {})
    pubmed_info = sources.get("pubmed", {})
    clinical_info = sources.get("clinical_trials", {})

    print("\n✅ Fetch complete!")
    print(f"  ClinicalTrials.gov source: {clinical_info.get('source')}")
    print(f"  PubMed source: {pubmed_info.get('source')}")
    print(f"  PubMed PMIDs found: {len(pubmed_info.get('pmids', []))}")
    print("----------------------------------------------------")

    # Ask for save format
    save_choice = input("Save results as (json/csv/xlsx/none)? ").strip().lower()

    if save_choice == "json":
        filename = f"{nct_id}_results.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"✅ Results saved to '{filename}'")

    elif save_choice == "csv":
        filename = f"{nct_id}_results.csv"
        save_results_to_csv(result, filename)
        print(f"✅ CSV saved to '{filename}'")

    elif save_choice == "xlsx":
        filename = f"{nct_id}_results.xlsx"
        save_results_to_excel(result, filename)
        print(f"✅ Excel file saved to '{filename}'")

    else:
        print("ℹ️ Results not saved.")


if __name__ == "__main__":
    interactive_session()
