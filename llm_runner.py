from llm_utils import check_ollama_installed, get_available_models, ensure_model_available, choose_model
from interactive import interactive_session
from batch_runner import run_prompts_from_csv

def run_llm_workflow(ssh_client):
    """
    Main workflow to interact with the LLM remotely via SSH.

    Steps:
    - Check if Ollama CLI is installed on the remote host.
    - List available models and allow user to select one.
    - Ensure the selected model is available locally on the remote host.
    - Offer user to run an interactive session or batch prompts from CSV.
    """

    try:
        check_ollama_installed(ssh_client)
    except Exception as e:
        print(f"Error checking Ollama installation: {e}")
        return

    models = []
    try:
        models = get_available_models(ssh_client)
    except Exception as e:
        print(f"Error retrieving models: {e}")

    if not models:
        print("No available models found. Aborting.")
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

    print("\nLLM is ready to use. You can enter multiple prompts or CSV files.")
    print("Type 'exit' anytime to quit.\n")

    while True:
        print("\nSelect input mode:")
        print("1. Interactive session")
        print("2. CSV file with prompts")
        print("3. Exit")
        mode = input("Enter choice (1, 2, or 3): ").strip()

        if mode == "3" or mode.lower() == "exit":
            print("Exiting workflow.")
            break

        if mode == "1":
            try:
                interactive_session(ssh_client, model)
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
