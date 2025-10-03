# interactive.py

import json
from output_handler import save_responses_to_excel
from data_fetchers import fetch_pubmed_combined_payload, search_web, create_payload
from llm_utils import query_ollama

# ------------------------------
# Interactive session
# ------------------------------
def interactive_session(ssh_client=None, model_name=None, study_info=None):
    print(f"\nStarting interactive LLM session (type 'exit' to quit)...\n")
    conversation = []

    try:
        while True:
            prompt = input("Enter prompt (PubMed ID, NCT ID, 'web:' for search, or text): ").strip()
            if prompt.lower() == 'exit':
                break
            if not prompt:
                continue

            final_prompt = prompt

            # If user enters a PubMed ID (digits only)
            if prompt.isdigit():
                try:
                    payload = fetch_pubmed_combined_payload(prompt)
                except Exception as e:
                    print(f"Error fetching study info: {e}")
                    continue

                study_info = payload["data"]  # For displaying
                print(f"\n[PubMed Study Info]:\n{json.dumps(study_info, indent=2)}\n")

                final_prompt = (
                    f"Summarize the following PubMed study JSON payload. "
                    f"Each field may come from a different source (API or scrape), as indicated:\n\n{json.dumps(payload, indent=2)}"
                )

            # If user enters an NCT ID
            elif prompt.upper().startswith("NCT") and prompt[3:].isdigit():
                nct_id = prompt.upper()
                print(f"\n[INFO] Searching web for ClinicalTrial {nct_id}")
                search_results = search_web(nct_id)
                if not search_results:
                    search_results = [{"title": "No recent results found.", "link": "", "snippet": ""}]

                payload = create_payload("clinical_trial_search", search_results)
                print(f"\n[Search Results]:\n{json.dumps(search_results, indent=2)}\n")

                final_prompt = (
                    f"Summarize the following clinical trial search JSON payload for {nct_id}:\n\n{json.dumps(payload, indent=2)}"
                )

            # If user wants web search
            elif prompt.lower().startswith("web:"):
                query = prompt[4:].strip()
                print(f"\n[INFO] Searching web for: {query}")
                search_results = search_web(query)
                if not search_results:
                    search_results = [{"title": "No recent results found.", "link": "", "snippet": ""}]

                payload = create_payload("web_search", search_results)
                final_prompt = (
                    f"You are a helpful assistant. A user asked: {query}\n\n"
                    f"Search results JSON payload:\n{json.dumps(payload, indent=2)}"
                )

            # Otherwise, freeform text prompt
            # `final_prompt` stays the same

            # Send to Ollama (local or via SSH)
            if ssh_client and model_name:
                from llm_utils import run_ollama as remote_ollama
                response = remote_ollama(ssh_client, model_name, final_prompt)
            else:
                response = query_ollama(model_name, final_prompt)

            print(f"\nResponse:\n{response}\n")
            conversation.append((prompt, response))

    except KeyboardInterrupt:
        print("\nSession interrupted by user.")
    finally:
        if conversation:
            save_format = None
            while save_format not in ('csv', 'xlsx', 'exit'):
                save_format = input("Save conversation as (csv/xlsx) or 'exit' to skip saving: ").strip().lower()

            if save_format == 'csv':
                path = input("Enter CSV file path: ").strip()
                save_responses_to_excel(conversation, path, csv_mode=True)
                print(f"Conversation saved to {path}")
            elif save_format == 'xlsx':
                path = input("Enter Excel file path: ").strip()
                save_responses_to_excel(conversation, path, csv_mode=False)
                print(f"Conversation saved to {path}")
            else:
                print("Conversation not saved.")
