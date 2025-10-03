# llm_runner.py
from interactive import interactive_session, fetch_pubmed_study
from llm_utils import (
    check_ollama_installed,
    get_available_models,
    ensure_model_available,
    choose_model,
    run_ollama,
)
from batch_runner import run_prompts_from_csv

def start_ollama_remote(ssh_client, model_name):
    """Starts Ollama remotely via SSH."""
    command = f"ollama run {model_name}"
    stdin, stdout, stderr = ssh_client.exec_command(command)
    output = stdout.read().decode()
    error = stderr.read().decode()
    if error:
        raise Exception(f"Error starting Ollama: {error.strip()}")
    print(f"Ollama started successfully:\n{output.strip()}")


def run_llm_prompt(ssh_client, model, prompt):
    """Send a single prompt to Ollama (remote or local)."""
    return run_ollama(ssh_client, model, prompt)


def summarize_study(ssh_client, model, study_info):
    """Generate a summary of the PubMed study using the LLM."""
    if not study_info or "error" in study_info:
        return "No study info available to summarize."

    authors = ", ".join(study_info.get("authors", []))
    prompt = (
        f"🧬 Summarize the following PubMed study: 🧬\n\n"
        f"PMID: {study_info.get('pmid', 'N/A')}\n"
        f"Title: {study_info.get('title', 'N/A')}\n"
        f"Authors: {authors}\n"
        f"Journal: {study_info.get('journal', 'N/A')}\n"
        f"Publication Date: {study_info.get('publication_date', 'N/A')}\n"
        f"Abstract: {study_info.get('abstract', 'N/A')}\n"
    )
    return run_ollama(ssh_client, model, prompt)


def run_pubmed_ollama_workflow(ssh_client):
    """
    Full LLM PubMed workflow: model selection, optional study loading, batch or interactive.
    Returns "main_menu" if user types "main menu" in interactive session.
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

    # Optional: Load PubMed study
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

    print("\nLLM is ready to use. Type 'exit' anytime to quit, or 'main menu' to return to the main menu.\n")

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
                result = interactive_session(ssh_client=ssh_client, model_name=model, study_info=study_info)
                if result == "main_menu":
                    print("Returning to main menu from interactive session.")
                    return "main_menu"
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


def run_llm_entrypoint(ssh_client):
    """
    Entry point with 2 options:
    1. Open a raw interactive SSH terminal session (no model or LLM)
    2. Run full Ollama PubMed workflow (model selection etc)

    At any point, typing "main menu" returns to this menu.
    """
    import sys
    import threading

    while True:
        print("\nChoose operation mode:")
        print("1. Interactive terminal session (raw SSH shell)")
        print("2. Ollama PubMed workflow")
        print("3. Exit")
        mode = input("Enter choice (1, 2, or 3): ").strip()

        if mode == "3" or mode.lower() == "exit":
            print("Exiting program.")
            break

        elif mode == "1":
            print("Opening interactive SSH terminal. Type 'main menu' to return to the main menu, 'exit' or Ctrl+D to quit.\n")

            channel = ssh_client.invoke_shell()

            def write_all(sock):
                try:
                    while True:
                        data = sock.recv(1024)
                        if not data:
                            break
                        sys.stdout.buffer.write(data)
                        sys.stdout.flush()
                except Exception:
                    pass

            writer = threading.Thread(target=write_all, args=(channel,))
            writer.daemon = True
            writer.start()

            try:
                while True:
                    line = sys.stdin.readline()
                    if not line:
                        # EOF (Ctrl+D)
                        break
                    stripped = line.strip().lower()
                    if stripped == "main menu":
                        print("\nReturning to main menu...\n")
                        break
                    if stripped == "exit":
                        print("Exiting interactive session.")
                        return  # Or break to exit full program if you want

                    channel.send(line.encode())
            except KeyboardInterrupt:
                print("\nSSH terminal session ended by user.")
            finally:
                channel.close()

        elif mode == "2":
            # Run PubMed workflow and return to main menu if user types "main menu"
            while True:
                try:
                    result = run_pubmed_ollama_workflow(ssh_client)
                    if result == "main_menu":
                        break  # Back to main menu
                except Exception as e:
                    print(f"Error in PubMed workflow: {e}")
                    break
                # After workflow ends, go back to main menu
                break

        else:
            print("Invalid choice. Please try again.")
