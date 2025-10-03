# interactive.py
import json
from data_fetchers import (
    fetch_clinical_trial_data,
    fetch_pubmed_combined_payload,
    fetch_duckduckgo_nct_search,
)
from output_handler import save_responses_to_excel
from llm_utils import query_ollama


def pretty_print(data, label=None):
    if label:
        print(f"\n=== {label} ===")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def interactive_session(ssh_client=None, model_name=None, study_info=None):
    print(f"\n🌟 Starting interactive LLM session (type 'exit' or 'main menu' to quit)...\n")
    conversation = []

    while True:
        user_input = input("\nEnter PMID, NCT ID, 'search:<query>', or prompt: ").strip()

        if user_input.lower() in {"exit", "main menu"}:
            break
        elif not user_input:
            continue

        prompt = None
        source = "other"  # default source tag

        # Handle PubMed by PMID
        if user_input.isdigit():
            pmid = user_input
            try:
                study_info = fetch_pubmed_combined_payload(pmid)["data"]
                pretty_print(study_info, f"PubMed Data for PMID {pmid}")
                prompt = f"Summarize this PubMed study:\n\n{json.dumps(study_info, indent=2)}"
                source = "pubmed"
            except Exception as e:
                print(f"❌ Error fetching PubMed study: {e}")
                continue

        # Handle ClinicalTrials.gov by NCT ID
        elif user_input.upper().startswith("NCT"):
            nct_id = user_input.upper()
            try:
                trial_info = fetch_clinical_trial_info(nct_id)
                pretty_print(trial_info, f"ClinicalTrials.gov Info for {nct_id}")

                # Save clinical trial info with clinicaltrials_api source
                conversation.append({
                    "prompt": f"NCT ID: {nct_id}",
                    "response": json.dumps(trial_info, indent=2),
                    "source": "clinicaltrials_api"
                })

                # If related PubMed studies present, print and save each separately with pubmed_api source
                pubmed_studies = trial_info.get("pubmed_studies", [])
                if pubmed_studies:
                    for study in pubmed_studies:
                        pmid = study.get("pmid", "Unknown PMID")
                        pretty_print(study, f"PubMed Study for PMID {pmid}")

                        conversation.append({
                            "prompt": f"PubMed study for PMID {pmid} (related to {nct_id})",
                            "response": json.dumps(study, indent=2),
                            "source": "pubmed_api"
                        })

                # Compose prompt for LLM summarizing trial + related pubmed studies
                combined_data = {
                    "clinical_trial": trial_info,
                    "related_pubmed_studies": pubmed_studies
                }
                prompt = f"Summarize this clinical trial and its related PubMed studies:\n\n{json.dumps(combined_data, indent=2)}"
                source = "combined_prompt"  # or just 'clinicaltrials_api' if preferred

            except Exception as e:
                print(f"❌ Error fetching clinical trial: {e}")
                continue


        # DuckDuckGo search fallback
        elif user_input.lower().startswith("search:"):
            query = user_input.split("search:", 1)[1].strip()
            try:
                result = fetch_duckduckgo_nct_search(query)
                pretty_print(result["data"], f"DuckDuckGo Search Results for '{query}'")
                prompt = f"What do these results tell us about '{query}'?\n\n{json.dumps(result['data'], indent=2)}"
                source = "duckduckgo_search"
            except Exception as e:
                print(f"❌ Error fetching DuckDuckGo search results: {e}")
                continue

        # Raw prompt
        else:
            prompt = user_input
            source = "raw_prompt"

        # Query the LLM with local or remote Ollama
        if ssh_client and model_name:
            from llm_utils import run_ollama_remote
            response = run_ollama_remote(ssh_client, model_name, prompt)
        else:
            response = query_ollama(model_name, prompt)

        print("\n🧠 LLM Response:\n", response)

        # Append conversation entry as dict with tags
        conversation.append({
            "prompt": user_input,
            "response": response,
            "source": source
        })

    # Save conversation
    if conversation:
        choice = input("\nSave conversation as (csv/xlsx/none)? ").strip().lower()
        if choice in ("csv", "xlsx"):
            path = input("Enter filename to save (e.g. session.xlsx): ").strip()
            save_responses_to_excel(conversation, path, csv_mode=(choice == "csv"))
            print(f"✅ Saved to {path}")
        else:
            print("❌ Conversation not saved.")


if __name__ == "__main__":
    interactive_session()
