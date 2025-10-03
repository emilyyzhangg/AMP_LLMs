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

    # Loop until valid input for either PMID or NCT
    while True:
        pmid = input("Enter PubMed ID (PMID) to load study (or leave blank to skip): ").strip()
        nct_id = input("Enter Clinical Trial NCT number (or leave blank to skip): ").strip().upper()

        if not pmid and not nct_id:
            print("Both PMID and NCT number cannot be blank. Please enter at least one.")
            continue
        break

    # Fetch PubMed study if PMID provided
    if pmid:
        try:
            payload = fetch_pubmed_combined_payload(pmid)
            study_info = payload["data"]
            print(f"\n[PubMed Study Info]:\n{json.dumps(study_info, indent=2)}\n")
        except Exception as e:
            print(f"Error fetching PubMed study info: {e}")
            study_info = None
    else:
        study_info = None

    # Fetch DuckDuckGo search if NCT provided
    if nct_id:
        from data_fetchers import fetch_duckduckgo_nct_search  # assuming you added this
        ddg_payload = fetch_duckduckgo_nct_search(nct_id)
        if "error" in ddg_payload:
            print(f"Error fetching DuckDuckGo results: {ddg_payload['error']}")
            ddg_payload = None
        else:
            print(f"\n[DuckDuckGo Clinical Trial Search Results]:\n{json.dumps(ddg_payload['data'], indent=2)}\n")
    else:
        ddg_payload = None

    try:
        while True:
            prompt = input("Enter prompt (or 'exit' to quit): ").strip()
            if prompt.lower() == 'exit':
                break
            if not prompt:
                continue

            # Build final prompt text based on available data
            final_prompt = prompt

            # If prompt looks like a PMID
            if prompt.isdigit():
                try:
                    payload = fetch_pubmed_combined_payload(prompt)
                except Exception as e:
                    print(f"Error fetching study info: {e}")
                    continue
                study_info = payload["data"]
                print(f"\n[PubMed Study Info]:\n{json.dumps(study_info, indent=2)}\n")
                final_prompt = (
                    f"Summarize the following PubMed study JSON payload:\n\n{json.dumps(payload, indent=2)}"
                )

            # If prompt looks like NCT number
            elif prompt.upper().startswith("NCT") and prompt[3:].isdigit():
                nct_search = prompt.upper()
                print(f"\n[INFO] Searching DuckDuckGo for ClinicalTrial {nct_search}")
                from data_fetchers import fetch_duckduckgo_nct_search
                ddg_payload = fetch_duckduckgo_nct_search(nct_search)
                if "error" in ddg_payload:
                    print(f"Error in DuckDuckGo search: {ddg_payload['error']}")
                    continue
                print(f"\n[DuckDuckGo Search Results]:\n{json.dumps(ddg_payload['data'], indent=2)}\n")
                final_prompt = (
                    f"Summarize the following clinical trial search JSON payload for {nct_search}:\n\n{json.dumps(ddg_payload, indent=2)}"
                )

            # If prompt is 'web:' search
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

            # Otherwise freeform text prompt - final_prompt = prompt

            # Send prompt to Ollama (local or remote)
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
