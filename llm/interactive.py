# interactive.py

import json
from data.data_fetchers import (
    fetch_clinical_trial_data,
    fetch_clinical_trial_and_pubmed_pmc,
    fetch_pubmed_by_pmid,
)
from data.output_handler import save_responses_to_excel
from llm.llm_utils import run_ollama_local


def pretty_print(data, label=None):
    """Nicely format JSON output in console."""
    if label:
        print(f"\n=== {label} ===")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def interactive_session(ssh_client=None, model_name=None, study_info=None):
    """Interactive LLM + data fetch session for PubMed & ClinicalTrials.gov."""
    print(f"\n🌟 Starting interactive LLM session (type 'exit' or 'main menu' to quit)...\n")
    conversation = []

    while True:
        user_input = input("\nEnter PMID, NCT ID, or free-text prompt: ").strip()
        if user_input.lower() in {"exit", "main menu"}:
            break
        elif not user_input:
            continue

        prompt = None
        source = "other"

        # ---------- Case 1: Direct PubMed PMID ----------
        if user_input.isdigit():
            pmid = user_input
            print(f"\n🔍 Fetching PubMed study for PMID {pmid}...")
            try:
                study_info = fetch_pubmed_by_pmid(pmid)
                pretty_print(study_info, f"PubMed Data for PMID {pmid}")

                prompt = f"Summarize this PubMed study:\n\n{json.dumps(study_info, indent=2)}"
                source = "pubmed"

                conversation.append({
                    "prompt": f"PubMed study {pmid}",
                    "response": json.dumps(study_info, indent=2),
                    "source": "pubmed_api"
                })
            except Exception as e:
                print(f"❌ Error fetching PubMed study: {e}")
                continue

        # ---------- Case 2: ClinicalTrials.gov by NCT ID ----------
        elif user_input.upper().startswith("NCT"):
            nct_id = user_input.upper()
            print(f"\n🔍 Fetching full ClinicalTrials.gov + PubMed + PMC data for {nct_id}...\n")
            try:
                trial_info = fetch_clinical_trial_and_pubmed_pmc(nct_id)
                if "error" in trial_info:
                    print(f"❌ Error: {trial_info['error']}")
                    continue

                pretty_print(trial_info, f"Combined Data for {nct_id}")

                # Save the full structure to conversation
                conversation.append({
                    "prompt": f"NCT ID: {nct_id}",
                    "response": json.dumps(trial_info, indent=2),
                    "source": "clinicaltrials_api"
                })

                # Extract PubMed studies for readability
                pubmed_studies = (
                    trial_info.get("sources", {})
                    .get("pubmed", {})
                    .get("studies", [])
                )
                if pubmed_studies:
                    for study in pubmed_studies:
                        pmid = study.get("pmid", "Unknown PMID")
                        pretty_print(study, f"PubMed Study for PMID {pmid}")

                        conversation.append({
                            "prompt": f"PubMed study for PMID {pmid} (related to {nct_id})",
                            "response": json.dumps(study, indent=2),
                            "source": "pubmed_api"
                        })

                # Create an LLM summarization prompt
                combined_data = {
                    "nct_id": nct_id,
                    "clinical_trial": trial_info.get("sources", {}).get("clinical_trials", {}),
                    "pubmed": trial_info.get("sources", {}).get("pubmed", {}),
                    "pmc": trial_info.get("sources", {}).get("pmc", {}),
                }
                prompt = (
                    f"Summarize this clinical trial and its related PubMed/PMC studies:\n\n"
                    f"{json.dumps(combined_data, indent=2)}"
                )
                source = "combined_prompt"

            except Exception as e:
                print(f"❌ Error fetching data for {nct_id}: {e}")
                continue

        # ---------- Case 3: Raw prompt ----------
        else:
            prompt = user_input
            source = "raw_prompt"

        # ---------- LLM Query ----------
        if prompt:
            try:
                if ssh_client and model_name:
                    from llm.llm_utils import run_ollama_remote
                    response = run_ollama_remote(ssh_client, model_name, prompt)
                else:
                    response = run_ollama_local(model_name, prompt)

                print("\n🧠 LLM Response:\n", response)

                conversation.append({
                    "prompt": user_input,
                    "response": response,
                    "source": source
                })
            except Exception as e:
                print(f"❌ LLM error: {e}")

    # ---------- Save Session ----------
    if conversation:
        choice = input("\nSave conversation as (csv/xlsx/json/none)? ").strip().lower()
        if choice in ("csv", "xlsx"):
            path = input("Enter filename to save (e.g. session.xlsx): ").strip()
            save_responses_to_excel(conversation, path, csv_mode=(choice == "csv"))
            print(f"✅ Saved to {path}")
        elif choice == "json":
            path = input("Enter filename to save (e.g. session.json): ").strip()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(conversation, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved to {path}")
        else:
            print("❌ Conversation not saved.")

    print("\n👋 Exiting interactive session.\n")


if __name__ == "__main__":
    interactive_session()
