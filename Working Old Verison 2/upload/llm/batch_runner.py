# batch_runner.py
import csv
from data.data_fetchers import create_payload
from llm_utils import run_ollama
import json

def run_prompts_from_csv(ssh_client, model):
    """
    Run batch prompts from a CSV file.
    CSV expected columns: 'type', 'input' 
    type: "pubmed_study", "clinical_trial", "web_search", or "text"
    input: depending on type, could be a PubMed ID, NCT ID, search query, or free text
    """

    csv_path = input("Enter path to CSV file with prompts: ").strip()
    try:
        with open(csv_path, newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            conversation = []
            for row in reader:
                prompt_type = row.get("type", "").strip()
                prompt_input = row.get("input", "").strip()

                if not prompt_type or not prompt_input:
                    print("Skipping row with missing 'type' or 'input'.")
                    continue

                # Create payload based on type
                if prompt_type == "pubmed_study":
                    # Expecting prompt_input is a PubMed ID
                    try:
                        from interactive import fetch_pubmed_study
                        study_info = fetch_pubmed_study(prompt_input)
                        if "error" in study_info:
                            print(f"Error fetching study {prompt_input}: {study_info['error']}")
                            response = f"Error fetching study {prompt_input}: {study_info['error']}"
                        else:
                            payload = create_payload(prompt_type, study_info)
                            prompt = f"🧬 Summarize the following PubMed study JSON payload: 🧬\n\n{payload}"
                            response = run_ollama(ssh_client, model, prompt)
                    except Exception as e:
                        response = f"Error processing PubMed study {prompt_input}: {e}"

                elif prompt_type == "clinical_trial":
                    # prompt_input expected as NCT ID or clinical trial identifier
                    # Use create_payload to wrap it as raw string
                    payload = create_payload(prompt_type, prompt_input)
                    prompt = f"Summarize the following clinical trial info:\n\n{payload}"
                    response = run_ollama(ssh_client, model, prompt)

                elif prompt_type == "web_search":
                    # prompt_input is a query string
                    payload = create_payload(prompt_type, prompt_input)
                    prompt = f"You are a helpful assistant. A user asked: {prompt_input}\n\nSearch results:\n{payload}"
                    response = run_ollama(ssh_client, model, prompt)

                elif prompt_type == "text":
                    # Freeform text prompt
                    payload = create_payload(prompt_type, prompt_input)
                    response = run_ollama(ssh_client, model, payload)

                else:
                    response = f"Unknown prompt type: {prompt_type}"

                print(f"\nPrompt type: {prompt_type}\nInput: {prompt_input}\nResponse:\n{response}\n")
                conversation.append((prompt_input, response))

            # Save conversation optionally
            if conversation:
                save_option = input("Save conversation to CSV? (y/n): ").strip().lower()
                if save_option == 'y':
                    save_path = input("Enter path for saving conversation CSV: ").strip()
                    with open(save_path, 'w', newline='', encoding='utf-8') as outcsv:
                        writer = csv.writer(outcsv)
                        writer.writerow(["Input", "Response"])
                        writer.writerows(conversation)
                    print(f"Conversation saved to {save_path}")

            return True

    except FileNotFoundError:
        print(f"File not found: {csv_path}")
        return False
    except Exception as e:
        print(f"Error processing CSV: {e}")
        return False
