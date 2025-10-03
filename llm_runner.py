# llm_runner.py
from interactive import interactive_session, fetch_pubmed_study
from llm_utils import check_ollama_installed, get_available_models, ensure_model_available, choose_model, run_ollama
from batch_runner import run_prompts_from_csv

def run_llm_prompt(ssh_client, model, prompt):
    """Send a single prompt to Ollama (remote or local)."""
    return run_ollama(ssh_client, model, prompt)

def summarize_study(ssh_client, model, study_info):
    """Generate a summary of the PubMed study using the LLM."""
    if not study_info or "error" in study_info:
        return "No study info available to summarize."
    
    authors = ", ".join(study_info.get("authors", []))
    prompt = (
        f"Summarize the following PubMed study:\n\n"
        f"PMID: {study_info.get('pmid', 'N/A')}\n"
        f"Title: {study_info.get('title', 'N/A')}\n"
        f"Authors: {authors}\n"
        f"Journal: {study_info.get('journal', 'N/A')}\n"
        f"Publication Date: {study_info.get('publication_date', 'N/A')}\n"
        f"Abstract: {study_info.get('abstract', 'N/A')}\n"
    )
    return run_ollama(ssh_client, model, prompt)

def run_llm_workflow(ssh_client):
    """
    Main workflow to interact with the LLM remotely via SSH using PubMed studies.
    """
    try:
        check_ollama_installed(ssh_client)
    except Exception as e:
        print(f"Error checking Ollama: {e}")
        return

    try:
        models = get_available_models(ssh_client)
    except Exception as e:
        print(f"Error retrieving models: {e}")
        models = []

    if not models:
        print("No available models found. Exiting.")
        return

    model = choose_model(models)
    if model is None:
        print("No model selected. Exiting.")
        return

    try:
        ensure_model_available(ssh_client, model)
    except Exception as e:
        print(f"Error ensuring model availability: {e}")
        return

    # Fetch study info before interactive loop
    study_info = None
    pmid = input("Enter PubMed ID to load study (or leave blank to skip): ").strip()
    if pmid:
        print(f"[INFO] Fetching PubMed study {pmid}...")
        study_info = fetch_pubmed_study(pmid)
        if "error" in study_info:
            print(f"Error fetching study info: {study_info['error']}")
            study_info = None
        else:
            print(study_info)

    print("\nLLM is ready to use. Type 'exit' anytime to quit.\n")

    while True:
        print("\nSelect input mode:")
        print("1. Interactive session")
        print("2. CSV file with prompts")
        print("3. Exit")
        mode = input("Enter choice (1, 2, or 3): ").strip()

        if mode == "3" or mode.lower() == "exit":
            print("Exiting workflow.")
            break
        elif mode == "1":
            try:
                interactive_session(ssh_client=ssh_client, model_name=model, study_info=study_info)
            except Exception as e:
                print(f"Error during interactive session: {e}")
        elif mode == "2":
            try:
                cont = run_prompts_from_csv(ssh_client, model)
                if cont is False:
                    print("Exiting workflow.")
                    break
            except Exception as e:
                print(f"Error running batch prompts: {e}")
        else:
            print("Invalid option. Please try again.")
