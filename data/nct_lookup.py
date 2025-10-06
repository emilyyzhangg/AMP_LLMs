import json
import os
from data.data_fetchers import (
    fetch_clinical_trial_data,
    fetch_pubmed_by_pmid,
    search_pubmed_by_title_authors,
    search_pmc,
    fetch_pmc_esummary,
    convert_pmc_summary_to_metadata,
    print_study_summary,
    summarize_result,
)

# ---------------------------------
# Save Results Function
# ---------------------------------
def save_results(results):
    """Prompt user to save results as TXT or CSV."""
    if not results:
        print("⚠️ No results to save.")
        return

    while True:
        choice = input("\n💾 Save results as [txt/csv]? (or 'cancel' to skip): ").strip().lower()
        if choice in ["txt", "csv"]:
            break
        elif choice == "cancel":
            print("❌ Save cancelled.")
            return
        else:
            print("Please choose 'txt', 'csv', or 'cancel'.")

    # Ask filename
    default_name = "nct_lookup_results"
    filename = input(f"Enter filename (default '{default_name}'): ").strip()
    if not filename:
        filename = default_name

    filepath = f"{filename}.{choice}"

    try:
        if choice == "txt":
            with open(filepath, "w", encoding="utf-8") as f:
                for res in results:
                    f.write(json.dumps(res, indent=2))
                    f.write("\n\n")
        elif choice == "csv":
            import csv
            import pandas as pd

            # Try to normalize data
            flat_results = [summarize_result(r) for r in results]
            df = pd.DataFrame(flat_results)
            df.to_csv(filepath, index=False)

        print(f"✅ Results saved to {filepath}")
    except Exception as e:
        print(f"❌ Failed to save results: {e}")


# ---------------------------------
# Main NCT Lookup Workflow
# ---------------------------------
def run_nct_lookup():
    """Interactive NCT lookup tool."""
    print("\n🔎 NCT Lookup Mode — enter one or more NCT IDs (comma-separated).")
    print("Type 'main menu' to return to the main menu.\n")

    all_results = []

    while True:
        user_input = input("Enter NCT ID(s): ").strip()
        if not user_input:
            continue
        if user_input.lower() == "main menu":
            print("↩️ Returning to Main Menu...")
            return

        nct_ids = [n.strip().upper() for n in user_input.split(",") if n.strip()]
        if not nct_ids:
            print("⚠️ No valid NCT IDs entered.")
            continue

        for nct_id in nct_ids:
            print(f"\n============================")
            print(f"🔬 Processing NCT ID: {nct_id}")
            print("============================")

            try:
                from data.data_fetchers import fetch_clinical_trial_and_pubmed_pmc
                result = fetch_clinical_trial_and_pubmed_pmc(nct_id)
                all_results.append(result)
                print_study_summary(result)
            except Exception as e:
                print(f"❌ Error processing {nct_id}: {e}")

        # Summary table
        print("\n===== ✅ SUMMARY =====")
        for res in all_results:
            summary = summarize_result(res)
            print(json.dumps(summary, indent=2))

        # Offer to save
        save_results(all_results)

        # Ask if user wants more lookups
        again = input("\nDo you want to lookup more NCT IDs? [y/n]: ").strip().lower()
        if again != "y":
            print("↩️ Returning to Main Menu...")
            return
